"""Messages to the person who started a petition, at the moments its outcome changes.

Nothing when they withdraw it: they did that themselves. Signers are never messaged: WhatsApp can't reach someone
outside its 24-hour window without approved templates, and an SMS to every signer could cost hundreds of credits.
The petition's page carries everything.

The wording is neutral, as for report messages: what happened, the petition's number and link, no judgement, on
one SMS page.
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


# The short wording is for a site address longer than the deployed one, with which every full message fits a page.
MESSAGES: dict[Update, tuple[str, str]] = {
    Update.REFUSED: ("Nokware: the MCE refused your petition {number}. Reason: {reason}. Edit and send it back: {mine}",
                     "Nokware: the MCE refused your petition {number}: {reason}. See {mine}"),
    Update.PUBLISHED: ("Nokware: the MCE published your petition {number}. It is open for signatures for 90 days: {link}",
                       "Nokware: your petition {number} is published: {link}"),
    Update.AUTO_PUBLISHED: ("Nokware: your petition {number} was published automatically: the MCE didn't decide in 72 hours. "
                            "Open 90 days: {link}",
                            "Nokware: your petition {number} was published automatically after 72 hours: {link}"),
    Update.THRESHOLD_REACHED: ("Nokware: your petition {number} reached {threshold} signatures and went to the MCE, who has 30 "
                               "days to respond: {link}",
                               "Nokware: your petition {number} reached {threshold} signatures. The MCE has 30 days to respond: {link}"),
    Update.RESPONDED: ("Nokware: the MCE has responded to your petition {number}. Read the response: {link}",
                       "Nokware: the MCE responded to petition {number}: {link}"),
    Update.NO_RESPONSE: ("Nokware: no response from the MCE 30 days after your petition {number} reached its threshold. "
                         "Its page says so: {link}",
                         "Nokware: no response from the MCE 30 days after petition {number} reached its threshold: {link}"),
    Update.CLOSED: ("Nokware: your petition {number} closed after 90 days with {signatures} of {threshold} signatures: {link}",
                    "Nokware: petition {number} closed with {signatures} of {threshold} signatures: {link}"),
}
CHANNEL_NAMES = {NotificationChannel.SMS: "SMS", NotificationChannel.WHATSAPP: "WhatsApp message"}


def compose(update: Update, petition: dict[str, Any]) -> str:
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
    """Also returns why, for the trail."""
    if petition.get("creatorChannel") != NotificationChannel.WHATSAPP.value:
        return NotificationChannel.SMS, ""
    if get_settings().whatsapp_provider == "twilio" and not window_open(number):
        return NotificationChannel.SMS, " WhatsApp's 24-hour window had closed, so it went by SMS to the same number."
    return NotificationChannel.WHATSAPP, ""


def _deliver(channel: NotificationChannel, number: str, text: str) -> str:
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
    try:
        notify_creator(petition, update)
    except Exception:
        logger.exception("Updating the creator of petition %s failed", petition.get("code"))
