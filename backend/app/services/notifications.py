"""Messages to citizens about their reports, by SMS and WhatsApp.

Three moments only (received, resolved, escalation received): anything more would feel like spam, and each message
costs money. Personal-safety messages say nothing but the reference, not even the word "report": a phone can be
shared. Every other message fits one GSM-7 SMS page (one credit), except an emergency's "received" message, whose
numbers to call are worth a second page.

The outbox row never holds the number; it is read from report_contacts at the moment of sending.

WhatsApp carries a free-form message only within 24 hours of the citizen's last message, and no templates are
approved yet. So an update outside that window goes by SMS to the same number when it is Ghanaian and gets no SMS
already: before sending if Redis shows the window closed, or afterwards when Twilio reports error 63016.
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
from app.contacts import EMERGENCY_TOPICS, short_line
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
from app.services.report_contacts import GHANA_CODE, contact_for, masked
from app.services.report_taxonomy import Category
from app.services.sms import SmsLimitReached, SmsNothingSent, SmsUnreachable, arkesel
from app.services.sms_bms import bms
from app.services.sms_text import bare_address, pages
from app.services.whatsapp import WhatsAppNothingSent, WhatsAppUnreachable, first_delivery, twilio, window_open
from app.teams import short_name

logger = logging.getLogger(__name__)

# Things that look alike in the outbox and are not: a message our own daily budget refused, where nothing at all
# left this process and sending it tomorrow is simply the message arriving late; a message our own side never
# attempted for some other reason; a message the provider never answered, which may have gone out and can never be
# settled by any delivery report; and a message the provider was asked for and refused with an answer. All end as
# `failed` — the outbox has no column for the difference and adding one would be a schema change — so the free-form
# `error` string carries it, under a prefix written here and read back by the readers below. A stale row the sweep
# gave up on is closed the same way: `failed` is the only status that means "settled, never retried", and the prefix
# says which kind of settled it is. REPAIRED is the one prefix that leaves the status alone: it is written onto a
# row whose message the sweep has now sent again, and it is what stops that row being sent a third time.
BUDGET_REFUSED = "our-daily-budget: "
NOTHING_SENT = "nothing-sent: "
UNREACHABLE = "provider-unreachable: "
STALE_QUEUED = "stale-queued: "
REPAIRED = "repaired: "

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
        """Returns the provider's message ID; raises on failure."""
        ...


@dataclass(frozen=True)
class Message:
    template: str
    body: str


def _who_options(case: dict[str, Any]) -> list[str]:
    names = [short_name(r) for r in case.get("recipients") or []]
    if len(names) <= 1:
        return [*names, "the office responsible"]
    others = len(names) - 1
    return [" and ".join(names), f"{names[0]} and {others} other office{'s' if others > 1 else ''}", f"{len(names)} offices"]


def _one_page(render: Callable[[str], str], case: dict[str, Any], pages_allowed: int = 1) -> str:
    bodies = [render(who) for who in _who_options(case)]
    return next((body for body in bodies if pages(body) <= pages_allowed), bodies[-1])


def _neutral(event: NotificationEvent, reference: str) -> Message:
    bodies = {
        NotificationEvent.SUBMITTED: f"Nokware: reference {reference} received.",
        NotificationEvent.RESOLVED: f"Nokware: reference {reference} has been updated.",
        NotificationEvent.ESCALATED: f"Nokware: reference {reference}: your request has been received.",
    }
    return Message(f"private_{event.value}", bodies[event])


def compose(event: NotificationEvent, case: dict[str, Any]) -> Message:
    reference = case["reference"]
    if case.get("category") == Category.PERSONAL_SAFETY:
        return _neutral(event, reference)
    # Without "https://", so the office's full name fits one page beside the link. The reference stays out of the
    # address: the status page asks for it, so it never lands in browser history or server logs.
    site = bare_address(get_settings().public_site_url)
    status_page = f"{site}/report/status"
    if event == NotificationEvent.RESOLVED and case.get("escalatedAt"):  # after the one escalation: final
        return Message("resolved_after_escalation", f"Nokware: report {reference} was reviewed and resolved. Outcome: {status_page}")
    if event == NotificationEvent.ESCALATED:
        return Message(event.value, f"Nokware: we've received your escalation of report {reference}. The MCE's office will review it.")
    if event == NotificationEvent.SUBMITTED and case.get("topic") in EMERGENCY_TOPICS:  # worth a second page
        numbers = f"If anyone is in danger: {short_line(case['topic'], None)} More numbers: {site}/contacts/emergency"
        return Message("submitted_emergency", _one_page(lambda who: f"Nokware: report {reference} is with {who}. {numbers}", case, pages_allowed=2))
    renders: dict[NotificationEvent, Callable[[str], str]] = {
        NotificationEvent.SUBMITTED: lambda who: f"Nokware: report {reference} is with {who}. "
        f"We'll message you when it's resolved. Track it: {status_page}",
        NotificationEvent.RESOLVED: lambda who: f"Nokware: {who} marked report {reference} resolved. "
        f"Not fixed? Escalate within 14 days: {status_page}",
    }
    return Message(event.value, _one_page(renders[event], case))


def channels_for(contact: dict[str, Any] | None) -> list[tuple[NotificationChannel, str]]:
    if not contact or not contact.get("notify"):
        return []
    pairs = [(NotificationChannel.SMS, contact.get("phone")), (NotificationChannel.WHATSAPP, contact.get("whatsapp"))]
    return [(channel, number) for channel, number in pairs if number]


def provider_for(channel: NotificationChannel) -> Provider | None:
    settings = get_settings()
    configured = settings.sms_provider if channel == NotificationChannel.SMS else settings.whatsapp_provider
    if configured == "log":
        return None
    if channel == NotificationChannel.SMS and configured == "arkesel":
        return arkesel()
    if channel == NotificationChannel.SMS and configured == "bms":
        return bms()
    if channel == NotificationChannel.WHATSAPP and configured == "twilio":
        return twilio()
    raise NotImplementedError(f"{channel.value} provider {configured!r} is not wired in yet")


def check_providers() -> None:
    """A provider that is named but can't be built stops the API at startup, not the first message."""
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


NOTHING_LEFT_US = (SmsNothingSent, WhatsAppNothingSent)
NO_ANSWER = (SmsUnreachable, WhatsAppUnreachable)


def _why_failed(error: Exception) -> str:
    """Which kind of failure this was, as the prefix the sweep reads back. An unknown one carries none: it means the
    provider answered, so the message may have gone out, and only the three named kinds are ever sent again.

    Both channels are read the same way. A WhatsApp send that never reached Twilio is the same thing to a resident as
    an SMS that never reached Arkesel, and a Twilio timeout is the same thing as an Arkesel one.
    """
    if isinstance(error, SmsLimitReached):
        return BUDGET_REFUSED
    if isinstance(error, NOTHING_LEFT_US):
        return NOTHING_SENT
    return UNREACHABLE if isinstance(error, NO_ANSWER) else ""


def _deliver(provider: Provider | None, number: str, message: Message) -> dict[str, Any]:
    if provider is None:
        logger.info("Message not sent (no provider configured) to %s: %s", masked(number), message.body)
        return {"status": NotificationStatus.NOT_SENT.value, "provider": "log"}
    try:
        message_id = provider.send(number, message.body)
    except Exception as error:  # a provider failure must never break the case itself
        logger.exception("Message to %s failed", masked(number))
        return {"status": NotificationStatus.FAILED.value, "provider": provider.name, "error": f"{_why_failed(error)}{error}"[:500]}
    return {"status": NotificationStatus.SENT.value, "provider": provider.name, "providerMessageId": message_id, "sentAt": now_iso()}


def _failed_with(row: dict[str, Any], prefix: str) -> bool:
    return row.get("status") == NotificationStatus.FAILED and (row.get("error") or "").startswith(prefix)


def budget_refused(row: dict[str, Any]) -> bool:
    """True when our own daily budget refused this message: nothing reached anyone, so sending it again is safe."""
    return _failed_with(row, BUDGET_REFUSED)


def nothing_was_sent(row: dict[str, Any]) -> bool:
    """True when our own side stopped before the provider was asked: the budget, or the counter it needs. Nothing
    reached anyone, so a later send is this message arriving late, not a second one."""
    return budget_refused(row) or _failed_with(row, NOTHING_SENT)


def provider_unreachable(row: dict[str, Any]) -> bool:
    """True when the provider never answered: no message ID, so no delivery report and no poll can ever say whether
    the resident got it. The sweep sends it again once — a duplicate reference is smaller than a silence."""
    return _failed_with(row, UNREACHABLE)


def repaired(row: dict[str, Any]) -> bool:
    """True when the sweep has already sent this row's message again. It is never sent a third time."""
    return (row.get("error") or "").startswith(REPAIRED)


def _mark(outbox_id: str, changes: dict[str, Any]) -> None:
    get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, outbox_id, changes)


def mark_stale_queued(outbox_id: str, note: str) -> None:
    """Closes a row left `queued` by a process that died mid-send. We can never learn whether that message went, so
    the row is settled rather than left open, and the prefix keeps it from being retried a second time."""
    _mark(outbox_id, {"status": NotificationStatus.FAILED.value, "error": f"{STALE_QUEUED}{note}"[:500]})


def mark_repaired(outbox_id: str, note: str, was: str = "") -> None:
    """Records that the sweep has sent this row's message again. The status is left as it was — `not_sent` really is
    what happened to this row, and `failed` really was — and the prefix alone settles it."""
    _mark(outbox_id, {"error": f"{REPAIRED}{note}{f' (was: {was})' if was else ''}"[:500]})


def _history_note(event: NotificationEvent, channel: NotificationChannel, outcome: dict[str, Any], provider: Provider | None) -> str:
    what = f"{EVENT_NAMES[event]} {CHANNEL_NAMES[channel]}"
    if outcome["status"] == NotificationStatus.SENT:
        return f"{what} sent." if provider is None or provider.delivers else f"{what} accepted by the provider's sandbox, not delivered."
    if outcome["status"] == NotificationStatus.NOT_SENT:
        return f"{what} recorded, not sent: no provider is configured yet. It will be sent once one is."
    if budget_refused(outcome):  # nothing left this process, and a later sweep sends it: don't call that a failure
        return f"{what} not sent: today's message limit was reached. It will be sent again."
    if nothing_was_sent(outcome):  # likewise: our own side stopped short of the provider
        return f"{what} not sent: it never reached the provider. It will be sent again."
    if provider_unreachable(outcome):  # nobody can ever learn whether it went, so it is sent again
        return f"{what} may not have gone out: the provider didn't answer. It will be sent again."
    return f"{what} failed to send."


WINDOW_CLOSED = "WhatsApp's 24-hour window had closed, so it went by SMS to the same number."
OUTSIDE_WINDOW_ERROR = "63016"  # Twilio: a free-form WhatsApp message outside the 24-hour window


def _send(case_id: str, event: NotificationEvent, channel: NotificationChannel, number: str, message: Message, why: str = "") -> None:
    outbox_id = _outbox(case_id, event, channel, message)
    provider = provider_for(channel)
    outcome = _deliver(provider, number, message)
    get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, outbox_id, outcome)
    note = _history_note(event, channel, outcome, provider) + (f" {why}" if why else "")
    case_history.record(case_id, CaseEntry(CaseHistoryAction.NOTIFIED, SYSTEM, note=note, channel=channel.value))


def _sms_can_stand_in(number: str, contact: dict[str, Any]) -> bool:
    return get_settings().whatsapp_provider == "twilio" and number.startswith(f"+{GHANA_CODE}") and not contact.get("phone")


def notify_channel(case: dict[str, Any], event: NotificationEvent, channel: NotificationChannel) -> None:
    """One message, on one channel the resident agreed to. Every send goes through here, whether it is the ordinary
    one (notify, below, calls this once per agreed channel) or the sweep repairing the one channel still owed.

    The WhatsApp-window rule lives here rather than in notify, so a repair obeys it exactly as a first send does: the
    window is read at the moment of sending, so repairing the WhatsApp channel hours later may go out by SMS to the
    same number even though the first attempt went (or tried to go) by WhatsApp, and the other way round. The row it
    writes then names the SMS channel, which is why the sweep reads a stand-in row as settling the WhatsApp channel.
    """
    contact = contact_for(case["$id"]) or {}
    number = dict(channels_for(contact)).get(channel)
    if number is None:
        # The contact changed between a caller reading it and this send. Nothing is sent and nothing fails, so say so.
        logger.info("No %s about case %s: the citizen hasn't agreed to it (%s)", channel.value, case["$id"], EVENT_NAMES[event])
        return
    message = compose(event, case)
    if channel == NotificationChannel.WHATSAPP and _sms_can_stand_in(number, contact) and not window_open(number):
        _send(case["$id"], event, NotificationChannel.SMS, number, message, WINDOW_CLOSED)
    else:
        _send(case["$id"], event, channel, number, message)


def notify(case: dict[str, Any], event: NotificationEvent) -> None:
    channels = channels_for(contact_for(case["$id"]) or {})
    if not channels:
        # Nothing is sent and nothing fails: without this line the quiet is indistinguishable from a lost message.
        logger.info("No message about case %s: the citizen agreed to none (%s)", case["$id"], EVENT_NAMES[event])
    for channel, _ in channels:
        notify_channel(case, event, channel)


def _outbox_row(provider_message_id: str) -> dict[str, Any] | None:
    if not provider_message_id:
        # A provider that answers without an ID leaves a row with an empty one, so an empty ID here would match some
        # other resident's message — and a delivery report about nothing would be written onto it, or the SMS
        # stand-in sent to whoever it belongs to.
        logger.warning("A delivery report arrived with no message ID, so no outbox row can answer for it")
        return None
    rows = get_databases().list_documents(
        DATABASE_ID, NOTIFICATIONS_COLLECTION, queries=[Query.equal("providerMessageId", provider_message_id), Query.limit(1)]
    ).documents
    return {"$id": rows[0].id, **rows[0].data} if rows else None


def record_delivery(provider_message_id: str, status: str, now: datetime) -> bool:
    row = _outbox_row(provider_message_id)
    if row is None:
        return False
    delivery = re.sub(r"[^A-Za-z_ -]", "", status).upper()[:32]
    changes = {"deliveryStatus": delivery, **({"deliveredAt": now.isoformat()} if delivery == "DELIVERED" else {})}
    get_databases().update_document(DATABASE_ID, NOTIFICATIONS_COLLECTION, row["$id"], changes)
    return True


def whatsapp_undelivered(provider_message_id: str, error_code: str) -> bool:
    row = _outbox_row(provider_message_id) if error_code == OUTSIDE_WINDOW_ERROR else None
    if row is None or row["channel"] != NotificationChannel.WHATSAPP.value:
        return False
    contact = contact_for(row["caseId"]) or {}
    number = contact.get("whatsapp")
    if not number or not contact.get("notify") or not _sms_can_stand_in(number, contact):
        return False
    if not first_delivery(f"sms-instead:{provider_message_id}"):
        return False
    message = Message(row["template"], row["body"])
    _send(row["caseId"], NotificationEvent(row["event"]), NotificationChannel.SMS, number, message, WINDOW_CLOSED)
    return True


def notify_quietly(case: dict[str, Any], event: NotificationEvent) -> None:
    try:
        notify(case, event)
    except Exception:
        logger.exception("Notifying the citizen about case %s failed", case.get("$id"))
