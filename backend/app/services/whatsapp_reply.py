"""A reply in a WhatsApp chat, split to WhatsApp's 1,600 characters; logged instead while WhatsApp is on "log"."""

import logging

from app.services.citizen_reports import NotificationChannel
from app.services.notifications import provider_for
from app.services.report_contacts import masked
from app.services.whatsapp import WhatsAppError, split

logger = logging.getLogger(__name__)


def reply(number: str, text: str) -> str | None:
    """The citizen just wrote, so the 24-hour window is open. Returns the last message's id where one was sent, so
    a caller whose reply IS the confirmation of something can record it as sent."""
    provider = provider_for(NotificationChannel.WHATSAPP)
    if provider is None:
        logger.info("WhatsApp reply to %s not sent (no provider is configured): %s", masked(number), text)
        return None
    try:
        return [provider.send(number, piece) for piece in split(text)][-1]
    except WhatsAppError:
        logger.exception("WhatsApp reply to %s failed", masked(number))
        return None


def reply_audio(number: str, media_url: str, about: str) -> str | None:
    """The message SID, or None if it wasn't sent."""
    provider = provider_for(NotificationChannel.WHATSAPP)
    if provider is None:
        logger.info("WhatsApp voice note to %s not sent (no provider is configured): %s, at %s", masked(number), about, media_url)
        return None
    try:
        return provider.send(number, "", media_url=media_url)
    except WhatsAppError:
        logger.exception("WhatsApp voice note to %s failed", masked(number))
        return None
