"""The portal's document rules: roles, ownership, states, clocks and changes."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services.auth import Principal, Role
from app.services.document_history import HistoryAction
from app.services.ledger_documents import LedgerStatus
from app.services.workflow import (
    MCE_WINDOW,
    REVIEW_WINDOW,
    Action,
    MissingInput,
    NotAllowed,
    Submission,
    WrongState,
    allowed_actions,
    can_view,
    expiry,
    new_document,
    transition,
)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
FINANCE = Principal("u-fin", "Finance", "f@x.org", Role.DEPARTMENT, "dept-finance")
WORKS = Principal("u-works", "Works", "w@x.org", Role.DEPARTMENT, "dept-works")
CONTRIBUTOR = Principal("u-con", "Contributor", "c@x.org", Role.CONTRIBUTOR)
OTHER_CONTRIBUTOR = Principal("u-con2", "Someone", "s@x.org", Role.CONTRIBUTOR)
MCE = Principal("u-mce", "MCE", "m@x.org", Role.MCE)


def doc(status: LedgerStatus, **fields: Any) -> dict[str, Any]:
    base = {
        "$id": "d1",
        "status": status.value,
        "department": "dept-finance",
        "uploadedBy": "u-con",
        "escalatedToMce": False,
        "resubmissionCount": 0,
        "heldUntil": (NOW + timedelta(hours=10)).isoformat() if status == LedgerStatus.HELD else None,
    }
    return {**base, **fields}


def escalated(**fields: Any) -> dict[str, Any]:
    return doc(
        LedgerStatus.DISPUTED, **{"escalatedToMce": True, "heldUntil": (NOW + timedelta(hours=5)).isoformat(), **fields}
    )


# Department review of held documents


def test_department_accepts_its_held_document() -> None:
    t = transition(Action.ACCEPT, doc(LedgerStatus.HELD), FINANCE, NOW)
    assert t.changes == {"status": "published", "publishedAt": NOW.isoformat(), "heldUntil": None}
    assert t.publishes and t.history == HistoryAction.ACCEPTED and t.from_status == LedgerStatus.HELD


def test_dispute_records_who_when_why_and_stops_the_clock() -> None:
    t = transition(Action.DISPUTE, doc(LedgerStatus.HELD), FINANCE, NOW, note="Figures are wrong")
    assert t.changes == {
        "status": "disputed",
        "disputeReason": "Figures are wrong",
        "disputedBy": "u-fin",
        "disputedAt": NOW.isoformat(),
        "heldUntil": None,
    }
    assert not t.publishes


def test_dispute_needs_a_reason() -> None:
    with pytest.raises(MissingInput):
        transition(Action.DISPUTE, doc(LedgerStatus.HELD), FINANCE, NOW, note=None)


def test_another_department_cannot_act() -> None:
    with pytest.raises(NotAllowed):
        transition(Action.ACCEPT, doc(LedgerStatus.HELD), WORKS, NOW)


@pytest.mark.parametrize("who", [CONTRIBUTOR, MCE])
def test_only_departments_review_held_documents(who: Principal) -> None:
    with pytest.raises(NotAllowed):
        transition(Action.ACCEPT, doc(LedgerStatus.HELD), who, NOW)


def test_accepting_an_already_published_document_is_a_conflict() -> None:
    with pytest.raises(WrongState):
        transition(Action.ACCEPT, doc(LedgerStatus.PUBLISHED), FINANCE, NOW)


def test_no_review_once_the_clock_has_run_out() -> None:
    expired = doc(LedgerStatus.HELD, heldUntil=(NOW - timedelta(minutes=1)).isoformat())
    with pytest.raises(WrongState, match="published automatically"):
        transition(Action.DISPUTE, expired, FINANCE, NOW, note="too late")


# Contributor responses to a dispute


def test_contributor_accepts_the_dispute() -> None:
    t = transition(Action.ACCEPT_DISPUTE, doc(LedgerStatus.DISPUTED), CONTRIBUTOR, NOW)
    assert t.changes == {"status": "withdrawn", "heldUntil": None}


def test_only_the_submitting_contributor_can_respond() -> None:
    with pytest.raises(NotAllowed):
        transition(Action.ACCEPT_DISPUTE, doc(LedgerStatus.DISPUTED), OTHER_CONTRIBUTOR, NOW)


def test_resubmit_sends_a_new_file_back_on_a_fresh_clock_keeping_the_dispute() -> None:
    disputed = doc(LedgerStatus.DISPUTED, disputeReason="Wrong year", resubmissionCount=0)
    t = transition(Action.RESUBMIT, disputed, CONTRIBUTOR, NOW, note="Corrected", file_id="portal/d1/new.pdf")
    assert t.changes == {
        "status": "held",
        "fileId": "portal/d1/new.pdf",
        "contributorResponse": "Corrected",
        "resubmissionCount": 1,
        "heldUntil": (NOW + REVIEW_WINDOW).isoformat(),
    }
    assert "disputeReason" not in t.changes  # the department still sees the earlier dispute


def test_resubmit_needs_a_file() -> None:
    with pytest.raises(MissingInput):
        transition(Action.RESUBMIT, doc(LedgerStatus.DISPUTED), CONTRIBUTOR, NOW)


def test_resubmit_only_once() -> None:
    with pytest.raises(WrongState, match="only once"):
        transition(Action.RESUBMIT, doc(LedgerStatus.DISPUTED, resubmissionCount=1), CONTRIBUTOR, NOW, file_id="f")


def test_escalate_starts_the_mce_clock_and_stays_disputed() -> None:
    t = transition(Action.ESCALATE, doc(LedgerStatus.DISPUTED), CONTRIBUTOR, NOW, note="The data is from the AMA site")
    assert t.changes == {
        "escalatedToMce": True,
        "contributorResponse": "The data is from the AMA site",
        "heldUntil": (NOW + MCE_WINDOW).isoformat(),
    }
    assert "status" not in t.changes


def test_escalate_needs_a_response() -> None:
    with pytest.raises(MissingInput):
        transition(Action.ESCALATE, doc(LedgerStatus.DISPUTED), CONTRIBUTOR, NOW)


def test_contributor_cannot_act_once_escalated() -> None:
    for action in (Action.ACCEPT_DISPUTE, Action.RESUBMIT, Action.ESCALATE):
        with pytest.raises(WrongState):
            transition(action, escalated(), CONTRIBUTOR, NOW, note="n", file_id="f")


# MCE rulings


def test_mce_upholds_or_overrules_escalated_disputes() -> None:
    assert transition(Action.UPHOLD, escalated(), MCE, NOW).changes["status"] == "withdrawn"
    assert transition(Action.OVERRULE, escalated(), MCE, NOW).publishes


def test_mce_cannot_rule_on_a_dispute_that_was_not_escalated() -> None:
    with pytest.raises(WrongState):
        transition(Action.OVERRULE, doc(LedgerStatus.DISPUTED), MCE, NOW)


def test_departments_cannot_rule_on_escalations() -> None:
    with pytest.raises(NotAllowed):
        transition(Action.OVERRULE, escalated(), FINANCE, NOW)


# The clock


def test_expired_held_and_escalated_documents_publish() -> None:
    past = (NOW - timedelta(seconds=1)).isoformat()
    for document in (doc(LedgerStatus.HELD, heldUntil=past), escalated(heldUntil=past)):
        t = expiry(document, NOW)
        assert t is not None and t.publishes and t.history == HistoryAction.AUTO_PUBLISHED


def test_nothing_expires_early_or_while_waiting_on_the_contributor() -> None:
    assert expiry(doc(LedgerStatus.HELD), NOW) is None
    assert expiry(doc(LedgerStatus.DISPUTED), NOW) is None  # no clock
    assert expiry(doc(LedgerStatus.WITHDRAWN, heldUntil=(NOW - timedelta(days=1)).isoformat()), NOW) is None


# What each role sees and may do


def test_allowed_actions_match_the_rules() -> None:
    assert allowed_actions(doc(LedgerStatus.HELD), FINANCE, NOW) == [Action.ACCEPT, Action.DISPUTE]
    assert allowed_actions(doc(LedgerStatus.HELD), WORKS, NOW) == []
    assert allowed_actions(doc(LedgerStatus.DISPUTED), CONTRIBUTOR, NOW) == [
        Action.ACCEPT_DISPUTE,
        Action.RESUBMIT,
        Action.ESCALATE,
    ]
    assert allowed_actions(escalated(), MCE, NOW) == [Action.UPHOLD, Action.OVERRULE]


def test_visibility() -> None:
    held = doc(LedgerStatus.HELD)
    assert can_view(FINANCE, held) and can_view(CONTRIBUTOR, held) and can_view(MCE, held)
    assert not can_view(WORKS, held) and not can_view(OTHER_CONTRIBUTOR, held)
    assert can_view(OTHER_CONTRIBUTOR, doc(LedgerStatus.PUBLISHED))


# Uploads

SUBMISSION = Submission(title="Budget", category="Annual Reports", document_year=2025, department=None, source_url=None)


def test_department_upload_publishes_under_its_own_name() -> None:
    fields = new_document(FINANCE, SUBMISSION, "portal/d1/a.pdf", NOW)
    assert fields["department"] == "dept-finance" and fields["sourceType"] == "agency"
    assert fields["status"] == "published" and fields["publishedAt"] == NOW.isoformat()
    assert fields["origin"] == "portal"  # Ask says "Submitted by Finance", not "Published … on ama.gov.gh"


def test_department_cannot_upload_for_another_department() -> None:
    with pytest.raises(NotAllowed):
        new_document(FINANCE, Submission(**{**SUBMISSION.__dict__, "department": "dept-works"}), "f", NOW)


def test_contributor_upload_is_held_for_the_chosen_department() -> None:
    submission = Submission(**{**SUBMISSION.__dict__, "department": "dept-press", "source_url": "https://ama.gov.gh/x"})
    fields = new_document(CONTRIBUTOR, submission, "f", NOW)
    assert fields["status"] == "held" and fields["department"] == "dept-press"
    assert fields["heldUntil"] == (NOW + REVIEW_WINDOW).isoformat() and fields["sourceType"] == "contributor"
    assert fields["origin"] == "portal"


@pytest.mark.parametrize(
    "department, source_url", [(None, "https://ama.gov.gh/x"), ("dept-nowhere", "https://x"), ("dept-press", None)]
)
def test_contributor_upload_needs_a_department_and_a_source(department: str | None, source_url: str | None) -> None:
    with pytest.raises(MissingInput):
        new_document(
            CONTRIBUTOR,
            Submission(**{**SUBMISSION.__dict__, "department": department, "source_url": source_url}),
            "f",
            NOW,
        )


def test_mce_does_not_upload() -> None:
    with pytest.raises(NotAllowed):
        new_document(MCE, SUBMISSION, "f", NOW)


POLICE = Principal("u-pol", "Police liaison", "p@x.org", Role.AGENCY, agency="agency-police")


def test_agencies_have_no_part_in_the_ledger() -> None:
    with pytest.raises(NotAllowed):
        new_document(POLICE, SUBMISSION, "f", NOW)
    held = doc(LedgerStatus.HELD, heldUntil=(NOW + REVIEW_WINDOW).isoformat())
    assert allowed_actions(held, POLICE, NOW) == []
    assert can_view(POLICE, doc(LedgerStatus.PUBLISHED)) and not can_view(POLICE, held)
