"""A citizen report's lifecycle, escalation, retention and who sees what."""

from datetime import datetime, timedelta, timezone

import pytest

from app.services.auth import Principal, Role
from app.services.case_workflow import (
    CaseView,
    Reassignment,
    acknowledge,
    after_assignments_change,
    case_status,
    case_view,
    check_reassign,
    confirm_resolution,
    contact_purge_at,
    escalate,
    may_see_contact,
    resolve,
    shown_count,
)
from app.services.workflow import MissingInput, NotAllowed, WrongState

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
WORKS = Principal("u-w", "Works", "w@x.org", Role.DEPARTMENT, "dept-works")
POLICE = Principal("u-p", "Police", "p@x.org", Role.AGENCY, agency="agency-police")
WELFARE = Principal("u-s", "Welfare", "s@x.org", Role.DEPARTMENT, "dept-social-welfare")
FINANCE = Principal("u-f", "Finance", "f@x.org", Role.DEPARTMENT, "dept-finance")
MCE = Principal("u-m", "MCE", "m@x.org", Role.MCE)


def assignment(recipient: str, status: str = "assigned", active: bool = True) -> dict:
    return {"recipient": recipient, "status": status, "active": active}


def case(**fields) -> dict:
    return {"status": "assigned", "category": "civic_service", "recipients": ["dept-works"], **fields}


SAFETY = case(category="personal_safety", recipients=["agency-police", "dept-social-welfare"])


def test_a_recipient_acknowledges_then_resolves_with_a_note() -> None:
    started = acknowledge(WORKS, assignment("dept-works"), NOW)
    assert started["status"] == "in_progress"
    with pytest.raises(MissingInput):
        resolve(WORKS, assignment("dept-works", "in_progress"), "", NOW)
    done = resolve(WORKS, assignment("dept-works", "in_progress"), "Drain desilted.", NOW)
    assert done["status"] == "resolved" and done["resolutionNote"] == "Drain desilted."


def test_only_the_recipient_may_act_and_not_after_a_move() -> None:
    with pytest.raises(NotAllowed):
        acknowledge(FINANCE, assignment("dept-works"), NOW)
    with pytest.raises(NotAllowed):
        acknowledge(MCE, assignment("dept-works"), NOW)
    with pytest.raises(WrongState):
        acknowledge(WORKS, assignment("dept-works", active=False), NOW)


def test_a_two_recipient_case_is_resolved_only_when_both_are() -> None:
    both = [assignment("agency-police", "resolved"), assignment("dept-social-welfare", "assigned")]
    assert case_status(both) == "in_progress"
    both[1]["status"] = "resolved"
    assert after_assignments_change(SAFETY, both, NOW) == {"status": "resolved", "resolvedAt": NOW.isoformat()}
    moved_away = [assignment("dept-works", active=False), assignment("dept-finance")]
    assert case_status(moved_away) == "assigned"


def test_escalation_is_once_within_fourteen_days_with_a_reason() -> None:
    resolved = case(status="resolved", resolvedAt=(NOW - timedelta(days=13)).isoformat())
    assert escalate(resolved, "Still flooding.", NOW)["status"] == "escalated"
    with pytest.raises(MissingInput):
        escalate(resolved, "", NOW)
    with pytest.raises(WrongState):
        escalate(case(status="resolved", resolvedAt=(NOW - timedelta(days=15)).isoformat()), "Late", NOW)
    with pytest.raises(WrongState):
        escalate({**resolved, "escalatedAt": NOW.isoformat()}, "Again", NOW)
    with pytest.raises(WrongState):
        escalate(case(status="in_progress"), "Not done yet", NOW)


def test_the_mce_reassigns_with_a_reason_and_safety_cases_stay_with_safety_services() -> None:
    check_reassign(MCE, case(), Reassignment("dept-works", "dept-waste-management"), "Refuse, not drains.")
    with pytest.raises(MissingInput):
        check_reassign(MCE, case(), Reassignment("dept-works", "dept-waste-management"), "")
    with pytest.raises(NotAllowed):
        check_reassign(WORKS, case(), Reassignment("dept-works", "dept-finance"), "Mine?")
    with pytest.raises(WrongState):
        check_reassign(MCE, SAFETY, Reassignment("agency-police", "dept-works"), "Wrong")
    with pytest.raises(WrongState):
        check_reassign(MCE, case(status="resolved"), Reassignment("dept-works", "dept-finance"), "Late")


def test_the_mce_can_confirm_an_escalated_resolution_which_closes_the_case() -> None:
    escalated = case(status="escalated", escalatedAt=NOW.isoformat(), resolvedAt=(NOW - timedelta(days=3)).isoformat())
    changes = confirm_resolution(MCE, escalated, "The drain was cleared on 4 September.", NOW)
    closed = {**escalated, **changes}
    assert contact_purge_at(closed) == NOW + timedelta(days=30)
    with pytest.raises(WrongState):
        confirm_resolution(MCE, case(), "n", NOW)


def test_numbers_are_kept_thirty_days_after_the_escalation_window_ends() -> None:
    resolved = case(status="resolved", resolvedAt=NOW.isoformat())
    assert contact_purge_at(resolved) == NOW + timedelta(days=14 + 30)
    assert contact_purge_at(case()) is None  # open cases keep the numbers for the resolution message


def test_recipients_see_everything_and_the_mce_sees_safety_cases_only_in_outline() -> None:
    assert case_view(WORKS, case()) == CaseView.FULL
    assert case_view(MCE, case()) == CaseView.FULL
    assert case_view(POLICE, SAFETY) == CaseView.FULL and case_view(WELFARE, SAFETY) == CaseView.FULL
    assert case_view(MCE, SAFETY) == CaseView.OVERSIGHT
    assert case_view(FINANCE, SAFETY) == CaseView.NONE and case_view(FINANCE, case()) == CaseView.NONE


def test_a_number_is_shown_only_to_a_recipient_and_only_with_callback_consent() -> None:
    assert may_see_contact(POLICE, SAFETY, {"callbackConsent": True})
    assert not may_see_contact(POLICE, SAFETY, {"callbackConsent": False})
    assert not may_see_contact(MCE, SAFETY, {"callbackConsent": True})
    assert not may_see_contact(FINANCE, SAFETY, {"callbackConsent": True})


def test_small_personal_safety_counts_are_never_shown_as_numbers() -> None:
    assert shown_count(4) is None and shown_count(0) is None and shown_count(5) == 5


def test_each_person_is_offered_only_what_they_may_do() -> None:
    from app.services.case_workflow import allowed_case_actions

    works = [assignment("dept-works")]
    assert allowed_case_actions(WORKS, case(), works) == ["acknowledge", "resolve"]
    assert allowed_case_actions(WORKS, case(), [assignment("dept-works", "in_progress")]) == ["resolve"]
    assert allowed_case_actions(FINANCE, case(), works) == []
    assert allowed_case_actions(MCE, case(), works) == ["reassign"]
    escalated = case(status="escalated")
    assert allowed_case_actions(MCE, escalated, works) == ["reassign", "reopen", "confirm-resolution"]
    assert allowed_case_actions(WORKS, escalated, [assignment("dept-works", "resolved")]) == []
    assert allowed_case_actions(MCE, case(status="resolved"), works) == []


def test_the_mce_reopens_an_escalated_case_with_a_note_for_the_recipients() -> None:
    from app.services.case_workflow import reopen

    reopen(MCE, case(status="escalated"), "The water still stands at the gate.")
    with pytest.raises(MissingInput):
        reopen(MCE, case(status="escalated"), "")
    with pytest.raises(WrongState):
        reopen(MCE, case(status="in_progress"), "Why?")
    with pytest.raises(NotAllowed):
        reopen(WORKS, case(status="escalated"), "Me")


def test_reassign_is_offered_only_when_there_is_somewhere_to_move_the_case() -> None:
    from app.services.case_workflow import allowed_case_actions, reassign_targets

    assert reassign_targets(SAFETY) == []  # already with both Police and Social Welfare
    assert allowed_case_actions(MCE, SAFETY, []) == []
    police_only = {**SAFETY, "recipients": ["agency-police"]}
    assert reassign_targets(police_only) == ["dept-social-welfare"]
