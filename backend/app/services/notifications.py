"""Messages to citizens about their reports, by SMS and WhatsApp.

Three moments only: the report is received, it is resolved, an escalation is
received. Nothing in between: status changes would feel like spam and each
message costs money. A message goes to every channel the citizen gave (both if
both) and to none if they gave no number or didn't agree to messages.

Personal-safety messages say nothing but the reference: no category, no
service, not even the word "report". A phone can be shared.

Every message fits one SMS page in plain GSM-7 (a credit each): the office
names are short names, and when they still don't fit, a shorter way of saying
who replaces them.

Every message is written to the notifications outbox first (never with the
number, which is read from report_contacts at the moment of sending), then
handed to the channel's provider: Arkesel for SMS (SMS_PROVIDER=arkesel), or
"log", which records the message as not sent. Twilio (WhatsApp) comes later.
"""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from appwrite.id import ID
from appwrite.query import Query

from app.config import get_settings
from app.services import case_history
from app.services.appwrite_client import DATABASE_ID, get_databases
from app.services.case_history import SYSTEM, CaseEntry, CaseHistoryAction
from app.services.citizen_reports import (
    NOTIFICATIONS_COLLECTION,
    NotificationChannel,
    NotificationEvent,
    NotificationStatus,
)
from app.services.ledger_documents import now_iso
from app.services.report_contacts import contact_for, masked
from app.services.report_taxonomy import Category
from app.services.sms import arkesel
from app.services.sms_text import pages
from app.teams import short_name

logger = logging.getLogger(__name__)

CHANNEL_NAMES = {NotificationChannel.SMS: "SMS", NotificationChannel.WHATSAPP: "WhatsApp message"}
EVENT_NAMES = {
    NotificationEvent.SUBMITTED: "Submission",
    NotificationEvent.RESOLVED: "Resolution",
    NotificationEvent.ESCALATED: "Escalation",
}


class Provider(Protocol):
    name: str
    delivers: bool  # False for a sandbox: accepted, never delivered

    def send(self, to: str, body: str) -> str:
        """Send the message; return the provider's message ID. Raise on failure."""
        ...


@dataclass(frozen=True)
class Message:
    template: str
    body: str


def _who_options(case: dict[str, Any]) -> list[str]:
    """Ways to say who has the report, fullest first."""
    names = [short_name(r) for r in case.get("recipients") or []]
    if len(names) <= 1:
        return [*names, "the office responsible"]
    others = len(names) - 1
    return [" and ".join(names), f"{names[0]} and {others} other office{'s' if others > 1 else ''}", f"{len(names)} offices"]


def _one_page(render: Callable[[str], str], case: dict[str, Any]) -> str:
    """The fullest wording that fits one SMS page."""
    bodies = [render(who) for who in _who_options(case)]
    return next((body for body in bodies if pages(body) == 1), bodies[-1])


def _neutral(event: NotificationEvent, reference: str) -> Message:
    """Personal safety: the reference and nothing else. A phone can be shared."""
    bodies = {
        NotificationEvent.SUBMITTED: f"Nokware: reference {reference} received.",
        NotificationEvent.RESOLVED: f"Nokware: reference {reference} has been updated.",
        NotificationEvent.ESCALATED: f"Nokware: reference {reference}: your request has been received.",
    }
    return Message(f"private_{event.value}", bodies[event])


def compose(event: NotificationEvent, case: dict[str, Any]) -> Message:
    """The message for an event, on one SMS page: content-neutral for personal safety."""
    reference = case["reference"]
    if case.get("category") == Category.PERSONAL_SAFETY:
        return _neutral(event, reference)
    status_page = f"{get_settings().public_site_url.rstrip('/')}/report/status"
    if event == NotificationEvent.RESOLVED and case.get("escalatedAt"):  # after the one escalation: final
        return Message("resolved_after_escalation", f"Nokware: report {reference} was reviewed and resolved. Outcome: {status_page}")
    if event == NotificationEvent.ESCALATED:
        return Message(event.value, f"Nokware: we've received your escalation of report {reference}. The MCE's office will review it.")
    renders: dict[NotificationEvent, Callable[[str], str]] = {
        NotificationEvent.SUBMITTED: lambda who: f"Nokware: report {reference} is with {who}. "
        f"We'll message you when it's resolved. Track it: {status_page}",
        NotificationEvent.RESOLVED: lambda who: f"Nokware: {who} marked report {reference} resolved. "
        f"Not fixed? Escalate within 14 days: {status_page}",
    }
    return Message(event.value, _one_page(renders[event], case))


def channels_for(contact: dict[str, Any] | None) -> list[tuple[NotificationChannel, str]]:
    """Each channel to use, with its number: none unless the citizen agreed to messages."""
    if not contact or not contact.get("notify"):
        return []
    pairs = [(NotificationChannel.SMS, contact.get("phone")), (NotificationChannel.WHATSAPP, contact.get("whatsapp"))]
    return [(channel, number) for channel, number in pairs if number]


def provider_for(channel: NotificationChannel) -> Provider | None:
    """The configured provider, or None while the channel is on "log"."""
    settings = get_settings()
    configured = settings.sms_provider if channel == NotificationChannel.SMS else settings.whatsapp_provider
    if configured == "log":
        return None
    if channel == NotificationChannel.SMS and configured == "arkesel":
        return arkesel()
    raise NotImplementedError(f"{channel.value} provider {configured!r} is not wired in yet")


def check_providers() -> None:
    """At startup: a provider that is named but can't be built stops the API, not the first message."""
    for channel in NotificationChannel:
        provider_for(channel)


def _outbox(case_id: str, event: NotificationEvent, channel: NotificationChannel, message: Message) -> str:
    document = get_databases().create_document(
        DATABASE_ID,
        NOTIFICATIONS_COLLECTION,
        ID.unique(),
        {
            "caseId": case_id,
            "event": event.value,
            "channel": channel.value,
            "template": message.template,
            "body": message.body,
            "status": NotificationStatus.QUEUED.value,
            "createdAt": now_iso(),
        },
    )
    return document.id


def _deliver(provider: Provider | None, number: str, message: Message) -> dict[str, Any]:
    """Hand one message to its provider; the outbox fields that record what happened."""
    if provider is None:
        logger.info("Message not sent (no provider configured) to %s: %s", masked(number), message.body)
        return {"status": NotificationStatus.NOT_SENT.value, "provider": "log"}
    try:
        message_id = provider.send(number, message.body)
    except Exception as error:  # a provider failure must never break the case itself
        logger.exception("Message to %s failed", masked(number))
        return {"status": NotificationStatus.FAILED.value, "provider": provider.name, "error": str(error)[:500]}
    return {"status": NotificationStatus.SENT.value, "provider": provider.name, "providerMessageId": message_id, "sentAt": now_iso()}


def _history_note(event: NotificationEvent, channel: NotificationChannel, outcome: dict[str, Any], provider: Provider | None) -> str:
    what = f"{EVENT_NAMES[event]} {CHANNEL_NAMES[channel]}"
    if outcome["status"] == NotificationStatus.SENT:
        return f"{what} sent." if provider is None or provider.delivers else f"{what} accepted by the provider's sandbox, not delivered."
    if outcome["status"] == NotificationStatus.NOT_SENT:
        return f"{what} recorded, not sent: no provider is configured yet."
    return f"{what} failed to send."


def notify(case: dict[str, Any], event: NotificationEvent) -> None:
    """Message the citizen about one of the three events, on every channel they agreed to."""
    for channel, number in channels_for(contact_for(case["$id"])):
        message = compose(event, case)
        outbox_id = _outbox(case["$id"], event, channel, message)
        provider = provider_for(channel)
        outcome = _deliver(provider, number, message)
        get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, outbox_id, outcome)
        note = _history_note(event, channel, outcome, provider)
        entry = CaseEntry(CaseHistoryAction.NOTIFIED, SYSTEM, note=note, channel=channel.value)
        case_history.record(case["$id"], entry)


def record_delivery(provider_message_id: str, status: str, now: datetime) -> bool:
    """A provider's delivery report, on the outbox row it is about. False if no message has that ID."""
    rows = get_databases().list_documents(
        DATABASE_ID, NOTIFICATIONS_COLLECTION, queries=[Query.equal("providerMessageId", provider_message_id), Query.limit(1)]
    ).documents
    if not rows:
        return False
    delivery = re.sub(r"[^A-Za-z_ -]", "", status).upper()[:32]
    changes = {"deliveryStatus": delivery, **({"deliveredAt": now.isoformat()} if delivery == "DELIVERED" else {})}
    get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, rows[0].id, changes)
    return True


def notify_quietly(case: dict[str, Any], event: NotificationEvent) -> None:
    """For background tasks: a messaging failure is logged, never raised."""
    try:
        notify(case, event)
    except Exception:
        logger.exception("Notifying the citizen about case %s failed", case.get("$id"))
