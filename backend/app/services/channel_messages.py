"""An SMS to a citizen outside a case's outbox: an Ask answer, or a reference that couldn't wait on a USSD screen.

It goes through the same provider as notifications (SMS_PROVIDER, sandbox and
daily limit included). A failure is logged, never raised: the citizen's session
has already ended. The number is logged masked, the text not at all.
"""

import logging

from app.services.citizen_reports import NotificationChannel
from app.services.notifications import provider_for
from app.services.report_contacts import masked

logger = logging.getLogger(__name__)


def send_sms(to: str, text: str) -> bool:
    provider = provider_for(NotificationChannel.SMS)
    if provider is None:
        logger.info("SMS to %s not sent: no provider is configured", masked(to))
        return False
    try:
        provider.send(to, text)
    except Exception:
        logger.exception("SMS to %s failed", masked(to))
        return False
    return True
