"""Test fixtures: filed, routed, worked and published like anything else, and shown to the public nowhere.

A report whose description starts "[TEST]", or a document whose title does, is a
fixture made by a test script or a tester. It goes through the real pipeline so
the pipeline is tested for real, but no public figure counts it and no public
answer cites it. Descriptions and titles are rarely shown publicly, so the prefix
would be invisible there: a dashboard of scripted reports, or an answer citing a
test document as the Assembly's, would be presented as real — the same fabrication
as a backdated history.

Staff still see fixtures in their own queues and library, where testing happens.
"""

TEST_PREFIX = "[TEST]"


def is_test(text: str | None) -> bool:
    return (text or "").lstrip().startswith(TEST_PREFIX)
