"""Messages to citizens about their reports, by SMS and WhatsApp.

Three moments only: the report is received, it is resolved, an escalation is
received. Nothing in between: status changes would feel like spam and each
message costs money. A message goes to every channel the citizen gave (both if
both) and to none if they gave no number or didn't agree to messages.

Personal-safety messages say nothing but the reference: no category, no
service, not even the word "report". A phone can be shared.

Every message is written to the notifications outbox first (never with the
number, which is read from report_contacts at the moment of sending), then
handed to the channel's provider. Until Arkesel (SMS) and Twilio (WhatsApp)
are wired in, the provider is "log": the message is recorded as not sent.
"""

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from appwrite.id import ID

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
from app.teams import RECIPIENT_NAMES

logger = logging.getLogger(__name__)

CHANNEL_NAMES = {NotificationChannel.SMS: "SMS", NotificationChannel.WHATSAPP: "WhatsApp message"}
EVENT_NAMES = {
    NotificationEvent.SUBMITTED: "Submission",
    NotificationEvent.RESOLVED: "Resolution",
    NotificationEvent.ESCALATED: "Escalation",
}


class Provider(Protocol):
    name: str

    def send(self, to: str, body: str) -> str:
        """Send the message; return the provider's message ID. Raise on failure."""
        ...


@dataclass(frozen=True)
class Message:
    template: str
    body: str


def recipients_named(case: dict[str, Any]) -> str:
    names = [RECIPIENT_NAMES.get(r, r) for r in case.get("recipients") or []]
    return " and ".join(names) or "the Assembly"


def compose(event: NotificationEvent, case: dict[str, Any]) -> Message:
    """The message for an event: content-neutral for personal safety."""
    reference = case["reference"]
    if case.get("category") == Category.PERSONAL_SAFETY:
        neutral = {
            NotificationEvent.SUBMITTED: f"Nokware: reference {reference} received.",
            NotificationEvent.RESOLVED: f"Nokware: reference {reference} has been updated.",
            NotificationEvent.ESCALATED: f"Nokware: reference {reference}: your request has been received.",
        }
        return Message(f"private_{event.value}", neutral[event])
    site = get_settings().public_site_url.rstrip("/")
    who = recipients_named(case)
    bodies = {
        NotificationEvent.SUBMITTED: f"Nokware: your report {reference} was received and sent to {who}. "
        f"We'll message you when it's resolved. Track it at {site}/report/status",
        NotificationEvent.RESOLVED: f"Nokware: {who} marked report {reference} resolved. "
        f"Not fixed? You can escalate it within 14 days at {site}/report/status",
        NotificationEvent.ESCALATED: f"Nokware: we've received your escalation of report {reference}. "
        "The MCE's office will review it.",
    }
    return Message(event.value, bodies[event])


def channels_for(contact: dict[str, Any] | None) -> list[tuple[NotificationChannel, str]]:
    """Each channel to use, with its number: none unless the citizen agreed to messages."""
    if not contact or not contact.get("notify"):
        return []
    pairs = [(NotificationChannel.SMS, contact.get("phone")), (NotificationChannel.WHATSAPP, contact.get("whatsapp"))]
    return [(channel, number) for channel, number in pairs if number]


def provider_for(channel: NotificationChannel) -> Provider | None:
    """The configured provider, or None while the channel is on "log" (not wired yet)."""
    settings = get_settings()
    configured = settings.sms_provider if channel == NotificationChannel.SMS else settings.whatsapp_provider
    if configured == "log":
        return None
    raise NotImplementedError(f"{channel.value} provider {configured!r} is not wired in yet")


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


def _history_note(event: NotificationEvent, channel: NotificationChannel, outcome: dict[str, Any]) -> str:
    what = f"{EVENT_NAMES[event]} {CHANNEL_NAMES[channel]}"
    if outcome["status"] == NotificationStatus.SENT:
        return f"{what} sent."
    if outcome["status"] == NotificationStatus.NOT_SENT:
        return f"{what} recorded, not sent: no provider is configured yet."
    return f"{what} failed to send."


def notify(case: dict[str, Any], event: NotificationEvent) -> None:
    """Message the citizen about one of the three events, on every channel they agreed to."""
    for channel, number in channels_for(contact_for(case["$id"])):
        message = compose(event, case)
        outbox_id = _outbox(case["$id"], event, channel, message)
        outcome = _deliver(provider_for(channel), number, message)
        get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, outbox_id, outcome)
        entry = CaseEntry(CaseHistoryAction.NOTIFIED, SYSTEM, note=_history_note(event, channel, outcome), channel=channel.value)
        case_history.record(case["$id"], entry)


def notify_quietly(case: dict[str, Any], event: NotificationEvent) -> None:
    """For background tasks: a messaging failure is logged, never raised."""
    try:
        notify(case, event)
    except Exception:
        logger.exception("Notifying the citizen about case %s failed", case.get("$id"))
