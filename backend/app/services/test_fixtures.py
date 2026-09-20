"""Test fixtures: filed, routed, worked and published like anything else, and shown to the public nowhere.

Descriptions and titles are rarely shown publicly, so the "[TEST]" prefix would be invisible there: a dashboard of
scripted reports would be presented as real, the same fabrication as a backdated history. Staff still see fixtures.
"""

TEST_PREFIX = "[TEST]"


def is_test(text: str | None) -> bool:
    return (text or "").lstrip().startswith(TEST_PREFIX)
