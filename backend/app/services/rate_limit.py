"""A small in-memory rate limit for the public report routes.

Filing a report costs a model call and up to 10 photos, and a status lookup by
reference must not become a way to guess references. Counts are per client
address and per route, kept in this process (the API runs as a single worker).
Behind a reverse proxy, the proxy must pass the real client address.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimit:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def retry_after(self, key: str, now: float | None = None) -> float | None:
        """Record a hit for key. None if it is allowed; otherwise the seconds until it would be."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= moment - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - moment
            hits.append(moment)
            return None


SUBMISSIONS = RateLimit(limit=5, window_seconds=600)
LOOKUPS = RateLimit(limit=30, window_seconds=60)
ESCALATIONS = RateLimit(limit=5, window_seconds=3600)
VOICES = RateLimit(limit=20, window_seconds=3600)
SPOKEN_QUESTIONS = RateLimit(limit=20, window_seconds=3600)  # each is heard by Gemini
EXPORTS = RateLimit(limit=30, window_seconds=3600)  # each renders a PDF, a Word file or a CSV
PETITION_CHECKS = RateLimit(limit=30, window_seconds=3600)  # each reads the draft with Gemini or searches the Ledger
PETITION_CHANGES = RateLimit(limit=20, window_seconds=3600)
PETITION_REPORTS = RateLimit(limit=10, window_seconds=3600)  # reports one device can send about any petitions
PETITION_REPORTS_ABOUT_ONE = RateLimit(limit=30, window_seconds=3600)  # and how many one petition takes in an hour
PETITION_COMMENTS = RateLimit(limit=10, window_seconds=3600)  # comments one confirmed number can leave anywhere
PETITION_COMMENTS_ON_ONE = RateLimit(limit=60, window_seconds=3600)  # and how many one petition takes in an hour
PHONE_CHALLENGES = RateLimit(limit=20, window_seconds=3600)
PHONE_POLLS = RateLimit(limit=400, window_seconds=900)  # the page asks every few seconds while it waits
SIGNING = RateLimit(limit=120, window_seconds=3600)  # generous: many phones share one address on a mobile network
SPEECH = RateLimit(limit=120, window_seconds=3600)  # one request per part: a long answer is up to seven
MCP = RateLimit(limit=120, window_seconds=600)  # every MCP message is a request; a count reads a cached list, so this only stops floods
