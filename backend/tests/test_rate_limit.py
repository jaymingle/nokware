"""The public routes' rate limit."""

from app.services.rate_limit import RateLimit


def test_hits_beyond_the_limit_wait_until_the_oldest_leaves_the_window() -> None:
    limit = RateLimit(limit=2, window_seconds=60)
    assert limit.retry_after("a", now=0) is None
    assert limit.retry_after("a", now=10) is None
    assert limit.retry_after("a", now=20) == 40
    assert limit.retry_after("b", now=20) is None  # counted per client
    assert limit.retry_after("a", now=61) is None  # the first hit has left the window
