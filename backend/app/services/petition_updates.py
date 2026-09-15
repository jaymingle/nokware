"""Messages to the person who started a petition, at the moments its outcome changes.

Seven moments: the MCE refused it, published it, or let the 72 hours run out
so it published itself; it reached its threshold; the MCE responded; 30 days
passed after the threshold with no response (the moment the outcome becomes a
fact about the Assembly, not a pending matter); it closed after 90 days short
of its threshold. Nothing when they withdraw it: they did that themselves.

Only the creator is messaged. Signers are not: WhatsApp can't reach someone
outside its 24-hour window without approved templates, and an SMS to every
signer could cost hundreds of credits. The petition's page carries everything.

The wording is neutral, the same rule as report messages: what happened, the
petition's number and its link, no judgement. Each fits one SMS page in plain
GSM-7 (a credit each). It goes on the channel the creator confirmed their
number with: WhatsApp while its 24-hour window is open, otherwise SMS to the
same (Ghanaian) number; a number confirmed by USSD or SMS gets SMS. The number
is read from the petition (encrypted at rest) at the moment of sending and is
never logged whole. Each message leaves a line in the petition's trail, which
the public never sees. A failure is logged, never raised.
"""

import logging
from enum import StrEnum
from typing import Any

from app.config import get_settings
from app.services import petitions
from app.services.citizen_reports import NotificationChannel
from app.services.notifications import provider_for
from app.services.petition_rules import REFUSALS, PetitionAction
from app.services.report_contacts import masked
from app.services.sms_text import pages, plain
from app.services.whatsapp import window_open

logger = logging.getLogger(__name__)


class Update(StrEnum):
    REFUSED = "refused"
    PUBLISHED = "published"
    AUTO_PUBLISHED = "auto_published"
    THRESHOLD_REACHED = "threshold_reached"
    RESPONDED = "responded"
    NO_RESPONSE = "no_response"
    CLOSED = "closed"


# Each moment's message, and a shorter one for when a long site address would take it past one SMS page.
MESSAGES: dict[Update, tuple[str, str]] = {
    Update.REFUSED: ("Nokware: the MCE refused your petition {number}. Reason: {reason}. You can edit it and send it back: {mine}",
                     "Nokware: the MCE refused your petition {number}: {reason}. See {mine}"),
    Update.PUBLISHED: ("Nokware: the MCE published your petition {number}. It is open for signatures for 90 days: {link}",
                       "Nokware: your petition {number} is published: {link}"),
    Update.AUTO_PUBLISHED: ("Nokware: your petition {number} was published automatically: the MCE didn't decide within 72 "
                            "hours. Open for 90 days: {link}",
                            "Nokware: your petition {number} was published automatically after 72 hours: {link}"),
    Update.THRESHOLD_REACHED: ("Nokware: your petition {number} reached {threshold} signatures and has gone to the MCE, who has "
                               "30 days to respond publicly: {link}",
                               "Nokware: your petition {number} reached {threshold} signatures. The MCE has 30 days to respond: {link}"),
    Update.RESPONDED: ("Nokware: the MCE has responded to your petition {number}. Read the response: {link}",
                       "Nokware: the MCE responded to petition {number}: {link}"),
    Update.NO_RESPONSE: ("Nokware: no response from the MCE 30 days after your petition {number} reached its threshold. "
                         "Its page now says so: {link}",
                         "Nokware: no response from the MCE 30 days after petition {number} reached its threshold: {link}"),
    Update.CLOSED: ("Nokware: your petition {number} closed after 90 days with {signatures} of {threshold} signatures: {link}",
                    "Nokware: petition {number} closed with {signatures} of {threshold} signatures: {link}"),
}
CHANNEL_NAMES = {NotificationChannel.SMS: "SMS", NotificationChannel.WHATSAPP: "WhatsApp message"}


def compose(update: Update, petition: dict[str, Any]) -> str:
    """The message, in one plain SMS page: the full wording if it fits, else the short one."""
    site = get_settings().public_site_url.rstrip("/")
    code = petition["code"]
    values = {
        "number": f"{code[:3]} {code[3:]}", "link": f"{site}/petitions/{code}", "mine": f"{site}/petitions/mine",
        "reason": REFUSALS[petition["refusalReason"]].label if petition.get("refusalReason") in REFUSALS else "",
        "threshold": f"{petition.get('threshold') or 0:,}", "signatures": f"{petition.get('signatureCount') or 0:,}",
    }
    full, short = (plain(template.format(**values)) for template in MESSAGES[update])
    return full if pages(full) == 1 else short


def channel_for(petition: dict[str, Any], number: str) -> tuple[NotificationChannel, str]:
    """WhatsApp for a number confirmed on WhatsApp while its window is open; SMS otherwise. With why, for the trail."""
    if petition.get("creatorChannel") != NotificationChannel.WHATSAPP.value:
        return NotificationChannel.SMS, ""
    if get_settings().whatsapp_provider == "twilio" and not window_open(number):
        return NotificationChannel.SMS, " WhatsApp's 24-hour window had closed, so it went by SMS to the same number."
    return NotificationChannel.WHATSAPP, ""


def _deliver(channel: NotificationChannel, number: str, text: str) -> str:
    """Hand it to the channel's provider; what happened, in words for the trail."""
    provider = provider_for(channel)
    if provider is None:
        logger.info("Petition update to %s not sent (no provider is configured): %s", masked(number), text)
        return "recorded, not sent: no provider is configured"
    try:
        provider.send(number, text)
    except Exception:  # a messaging failure never undoes the petition's change
        logger.exception("Petition update to %s failed", masked(number))
        return "failed to send"
    return "sent" if provider.delivers else "accepted by the provider's sandbox, not delivered"


def notify_creator(petition: dict[str, Any], update: Update) -> None:
    number = petition.get("creatorPhone")
    if not number:  # deleted with the rest of the creator's details, 30 days after the petition ended
        return
    channel, why = channel_for(petition, number)
    outcome = _deliver(channel, number, compose(update, petition))
    note = f"Update to the creator ({update.value}) by {CHANNEL_NAMES[channel]}: {outcome}.{why}"
    petitions.record_history(petition, PetitionAction.CREATOR_NOTIFIED, petitions.SYSTEM, petition.get("status"), note=note)


def notify_quietly(petition: dict[str, Any], update: Update) -> None:
    """For background tasks and the clock: logged, never raised."""
    try:
        notify_creator(petition, update)
    except Exception:
        logger.exception("Updating the creator of petition %s failed", petition.get("code"))
