"""A reply in a WhatsApp chat, split to WhatsApp's 1,600 characters; logged instead while WhatsApp is on "log"."""

import logging

from app.services.citizen_reports import NotificationChannel
from app.services.notifications import provider_for
from app.services.report_contacts import masked
from app.services.whatsapp import WhatsAppError, split

logger = logging.getLogger(__name__)


def reply(number: str, text: str) -> None:
    """Send a reply in the chat (the citizen just wrote, so the 24-hour window is open)."""
    provider = provider_for(NotificationChannel.WHATSAPP)
    if provider is None:
        logger.info("WhatsApp reply to %s not sent (no provider is configured): %s", masked(number), text)
        return
    try:
        for piece in split(text):
            provider.send(number, piece)
    except WhatsAppError:
        logger.exception("WhatsApp reply to %s failed", masked(number))
