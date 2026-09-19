"""Per-number limits for the messaging channels, counted in Redis.

A channel message arrives from the provider's servers, so the count is per citizen number, not per client address.

A limit marked `charged` guards SMS credits rather than the citizen's own conduct: it is counted only when an SMS
really is handed to a provider that delivers and bills for it. It is still counted before the work it guards is
done, never after the message goes out — a resident must be refused on the screen they are standing at, not after
waiting for an answer, and counting afterwards would let a burst of dials all pass the check and all be sent.
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.config import get_settings
from app.services.notifications import sms_is_charged
from app.services.redis_store import get_redis, key, subject_key


@dataclass(frozen=True)
class NumberLimit:
    name: str
    limit: int | Callable[[], int]
    window_seconds: int
    charged: bool = False

    @property
    def allowed(self) -> int:
        """Read at each check, not when the limit was built: a setting raised for a test pass takes effect on the
        next dial, and the number that refuses somebody is the one the process is actually using."""
        return self.limit() if callable(self.limit) else self.limit

    def allow(self, number: str, now: float) -> bool:
        if self.charged and not sms_is_charged():
            return True
        window = int(now // self.window_seconds)
        counter = key("limit", self.name, subject_key(number), str(window))
        pipe = get_redis().pipeline()
        pipe.incr(counter)
        pipe.expire(counter, self.window_seconds)
        used, _ = pipe.execute()
        return int(used) <= self.allowed


MESSAGES = NumberLimit("messages", limit=60, window_seconds=3600)  # every WhatsApp reply costs money
QUESTIONS = NumberLimit("questions", limit=20, window_seconds=3600)
# Each costs up to 2 credits. Raise SMS_ANSWER_DAILY_LIMIT for a test pass: the count is keyed by the day alone, so
# a higher limit lets the same number ask again at once, with nothing to clear out first.
SMS_ANSWERS = NumberLimit("sms-answers", lambda: get_settings().sms_answer_daily_limit, 86400, charged=True)
REPORTS = NumberLimit("reports", limit=5, window_seconds=3600)
LOOKUPS = NumberLimit("lookups", limit=30, window_seconds=3600)  # status by reference: no guessing
VOICE_NOTES = NumberLimit("voice-notes", limit=10, window_seconds=3600)  # each is transcribed by Gemini
SIGNATURES = NumberLimit("signatures", limit=30, window_seconds=86400)  # petitions one number signs in a day
PETITIONS = NumberLimit("petitions", limit=3, window_seconds=86400)  # started by one verified number
NUMBERS_SMS = NumberLimit("numbers-sms", limit=3, window_seconds=86400)  # emergency numbers by SMS: 2 credits each
SMS_CODES = NumberLimit("sms-codes", limit=3, window_seconds=3600)  # each verification code is an SMS credit
CODE_CLAIMS = NumberLimit("code-claims", limit=10, window_seconds=3600)  # each WhatsApp claim is answered
SPOKEN_REPLIES = NumberLimit("spoken-replies", limit=10, window_seconds=86400)  # each is an extra WhatsApp message
