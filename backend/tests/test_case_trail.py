"""One trail, two sides: the note staff write at a stage, and the timeline the resident reads back."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import case_actions, case_notes, case_timeline, report_followups
from app.services.case_notes import NOTE_MAX, NoteRefused, clean_note
from app.services.case_workflow import Reassignment
from app.services.channel_status import status_text
from app.services.phrases import english
from app.services.ussd import SCREEN_MAX
from app.services.workflow import MissingInput
from tests.test_case_actions import MCE, POLICE, WELFARE, WORKS, Fake, fake  # noqa: F401  (the fixture)

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
SITE = "https://nokware.tstitagency.com"
STAFF = "Kofi Asare"  # the name on the audit trail entry; never on anything the resident reads


def entry(action: str, minutes: int, **fields: Any) -> dict[str, Any]:
    return {"action": action, "actorName": STAFF, "actorRole": "department", "note": None, "staffNote": None,
            "timestamp": (NOW + timedelta(minutes=minutes)).isoformat(), **fields}


CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "createdAt": NOW.isoformat(), "status": "in_progress",
         "category": "civic_service", "isSensitive": False, "topic": "drainage", "recipients": ["dept-urban-roads"],
         "wardLocation": "mudor", "subMetro": "ashiedu-keteke"}
TRAIL = [
    entry("submitted", 0, actorName="The citizen", actorRole="citizen"),
    entry("classified", 1, actorName="Nokware", actorRole="system", note="Classified as drainage."),
    entry("assigned", 2, actorName="Nokware", actorRole="system", note="Routed to Works Department.", toDept="dept-works"),
    entry("acknowledged", 30, note="Works Department started work.", staffNote="A crew comes on Monday."),
    entry("notified", 31, actorName="Nokware", actorRole="system", note="Work started SMS sent."),
    entry("reassigned", 90, actorName="MCE", actorRole="mce", note="Moved from Works Department to Urban Roads: the road, not the drain.",
          staffNote="The road, not the drain.", fromDept="dept-works", toDept="dept-urban-roads"),
]


def timeline(case: dict[str, Any], trail: list[dict[str, Any]], assignments: list[dict[str, Any]] | None = None,
             now: datetime = NOW + timedelta(days=1)) -> list[dict[str, Any]]:
    return case_timeline.for_resident(case, assignments or [], trail, now)


def test_the_timeline_is_the_whole_trail_oldest_first_and_names_no_one() -> None:
    steps = timeline(CIVIC, TRAIL)

    assert [step["action"] for step in steps] == ["filed", "routed", "started", "reassigned"]
    assert [step["at"] for step in steps] == sorted(step["at"] for step in steps)
    assert steps[1]["description"] == "Routed to Works Department."
    assert steps[3]["description"] == "Moved from Works Department to Urban Roads."
    assert steps[2]["note"] == "A crew comes on Monday." and steps[3]["note"] == "The road, not the drain."
    assert STAFF not in str(steps), "the audit trail keeps the name; nothing the resident reads carries it"
    assert "notified" not in str(steps), "messages Nokware sent are its own record-keeping, not the resident's trail"


def test_a_closed_case_ends_with_the_day_nothing_more_could_happen() -> None:
    resolved_at = NOW + timedelta(days=2)
    closed = {**CIVIC, "status": "resolved", "resolvedAt": resolved_at.isoformat()}
    trail = [*TRAIL, entry("resolved", 60 * 48, note="Resolved by Urban Roads. Re-laid.", staffNote="Re-laid.")]

    assert timeline(closed, trail)[-1]["action"] == "resolved"  # the 14 days to escalate are still open
    ended = timeline(closed, trail, now=resolved_at + timedelta(days=15))
    assert ended[-1] == {"action": "closed", "at": (resolved_at + timedelta(days=14)).isoformat(),
                         "description": "This report is closed.", "note": None}


SAFETY = {**CIVIC, "$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "isSensitive": True,
          "topic": "abuse", "recipients": ["agency-police", "dept-social-welfare"], "wardLocation": None,
          "photoIds": ["reports/c2/01.jpg"]}
SAFETY_TRAIL = [
    *TRAIL,
    entry("acknowledged", 40, note="Ghana Police Service started work.", staffNote="Statement taken at Kaneshie."),
    entry("reassigned", 95, note="Moved from Ghana Police Service to Social Welfare: a child is involved.",
          staffNote="A child is involved.", fromDept="agency-police", toDept="dept-social-welfare"),
]
LEAKS = ("Police", "Welfare", "Works", "Urban Roads", "abuse", "Abuse", "drainage", "Drainage", "Mudor",
         "Statement", "child", "reports/c2", "Kaneshie", STAFF)


@pytest.fixture
def safety_status(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    monkeypatch.setattr(report_followups.report_locations, "views", lambda case_id: [])
    started = {"caseId": "c2", "recipient": "agency-police", "active": True, "status": "in_progress",
               "acknowledgedAt": (NOW + timedelta(minutes=40)).isoformat()}
    return report_followups.public_status(SAFETY, [started], NOW + timedelta(days=1), SAFETY_TRAIL)


def test_a_safety_case_gives_up_no_department_note_category_or_photo_anywhere(safety_status: dict[str, Any]) -> None:
    """The three places anyone holding the reference can read it: the status response, the USSD screen, the chat."""
    replies = [str(safety_status), status_text(safety_status, SITE),
               status_text(safety_status, SITE, compact=True, limit=SCREEN_MAX)]

    for reply in replies:
        for leak in LEAKS:
            assert leak not in reply, reply
    assert [step["description"] for step in safety_status["timeline"]] == [
        english("case.safety.received"), english("case.safety.in_progress")]
    assert all(step["note"] is None for step in safety_status["timeline"])
    assert status_text(safety_status, SITE) == "Reference M3RD-8WQA: in progress."


def test_a_safety_case_that_is_over_says_only_that_it_is_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups.report_locations, "views", lambda case_id: [])
    resolved_at = NOW + timedelta(days=2)
    closed = {**SAFETY, "status": "resolved", "resolvedAt": resolved_at.isoformat()}

    steps = report_followups.public_status(closed, [], resolved_at + timedelta(days=15), SAFETY_TRAIL)["timeline"]

    assert [step["description"] for step in steps] == [english("case.safety.received"), english("case.safety.closed")]
    assert english("case.safety.closed") == "This case is closed."


def test_a_phone_screen_shows_the_latest_step_and_points_at_the_rest() -> None:
    status = report_followups.public_status(CIVIC, [], NOW + timedelta(days=1), TRAIL)
    screen = status_text(status, SITE, compact=True, limit=SCREEN_MAX)

    assert len(screen) <= SCREEN_MAX
    assert screen.endswith("Full history: nokware.tstitagency.com/report/status")  # no scheme: a screen is not tappable
    assert "The road, not the drain." in screen
    assert 'Latest - 13 Sep: Moved from Works Department to Urban Roads. "The road, not the drain."' in status_text(status, SITE)
    assert status_text(status, SITE).endswith(f"Full history: {SITE}/report/status")


def test_a_long_latest_step_gives_way_to_the_address_and_never_the_other_way_round() -> None:
    """A truncated link leaves a resident nowhere to go; a missing step leaves them the page that has it."""
    wordy = [*TRAIL, entry("resolved", 200, note="Resolved.", staffNote="The culvert " + "and the kerb " * 30)]
    status = report_followups.public_status({**CIVIC, "status": "resolved"}, [], NOW + timedelta(days=1), wordy)
    screen = status_text(status, SITE, compact=True, limit=SCREEN_MAX)

    assert len(screen) <= SCREEN_MAX and screen.endswith("Full history: nokware.tstitagency.com/report/status")
    assert screen.startswith("Report K7QM-4TXP")


def test_a_note_with_someones_details_in_it_is_refused_and_told_exactly_why() -> None:
    for written, why in (("Call the landlord on 024 123 4567.", "a phone number"),
                         ("Write to kofi@example.com about it.", "an email address"),
                         ("The owner is GHA-123456789-0.", "a Ghana Card number")):
        with pytest.raises(NoteRefused) as refused:
            clean_note(written, required=True, ask="Say what was done.")
        assert f"contains {why}" in str(refused.value) and refused.value.status_code == 422
    assert clean_note("Call the office on Monday.", required=True, ask="x") == "Call the office on Monday."


def test_a_note_past_the_cap_is_refused_and_one_at_the_cap_is_kept() -> None:
    assert NOTE_MAX == 500
    with pytest.raises(NoteRefused, match="500 characters; this one is 501"):
        clean_note("a" * 501, required=False)
    assert clean_note("a" * NOTE_MAX, required=False) == "a" * NOTE_MAX


def test_moving_and_resolving_need_a_reason_and_starting_and_reopening_do_not(fake: Fake) -> None:  # noqa: F811
    fake.add_case("c1", ["dept-works"])
    for empty in (None, "", "   "):
        with pytest.raises(MissingInput, match="what was done"):
            case_actions.resolve(WORKS, "c1", empty, NOW)
        with pytest.raises(MissingInput, match="a reason"):
            case_actions.reassign(MCE, "c1", Reassignment("dept-works", "dept-finance"), empty, NOW)

    assert case_actions.acknowledge(WORKS, "c1", None, NOW).case["status"] == "in_progress"
    fake.add_case("c2", ["dept-works"], status="escalated", escalatedAt=NOW.isoformat())
    assert case_actions.reopen(MCE, "c2", None, NOW).case["status"] == "assigned"
    fake.add_case("c3", ["dept-works"], status="escalated", escalatedAt=NOW.isoformat())
    assert case_actions.reopen(MCE, "c3", "Water still stands at the gate.", NOW).case["status"] == "assigned"
    assert fake.trail[-1].staff_note == "Water still stands at the gate."


def test_a_refused_note_changes_nothing_at_all(fake: Fake) -> None:  # noqa: F811
    fake.add_case("c1", ["dept-works"])
    with pytest.raises(NoteRefused):
        case_actions.resolve(WORKS, "c1", "Reach me on 0241234567.", NOW)

    assert fake.cases["c1"]["status"] == "assigned" and fake.trail == []
    assert fake.assignments_for("c1")[0]["status"] == "assigned"


def test_a_safety_note_is_kept_for_the_record_and_never_shown_back_to_the_resident(fake: Fake) -> None:  # noqa: F811
    fake.add_case("c2", ["agency-police", "dept-social-welfare"], category="personal_safety", isSensitive=True)
    case_actions.acknowledge(POLICE, "c2", "Statement taken at Kaneshie.", NOW)
    case_actions.resolve(WELFARE, "c2", "Family moved to a shelter.", NOW)

    assert [e.staff_note for e in fake.trail] == ["Statement taken at Kaneshie.", "Family moved to a shelter."]
    assert all("Kaneshie" not in (e.note or "") and "shelter" not in (e.note or "") for e in fake.trail)


def test_a_note_naming_a_private_person_is_refused_where_the_resident_will_read_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The status page is opened by whoever holds the reference, which on a shared phone is not always the resident."""
    monkeypatch.setattr(case_notes, "private_person", lambda text: "Auntie Esi")
    with pytest.raises(case_notes.NoteRefused, match="seems to name a private person"):
        case_notes.not_naming_anyone("Spoke to Auntie Esi next door.", read_by_the_resident=True)


def test_an_internal_note_on_a_safety_case_may_name_who_was_involved(monkeypatch: pytest.MonkeyPatch) -> None:
    """It is kept in the audit trail and shown to nobody outside the portal; naming who was there is the point."""
    monkeypatch.setattr(case_notes, "private_person", lambda text: "Auntie Esi")
    case_notes.not_naming_anyone("Auntie Esi confirmed the child is safe.", read_by_the_resident=False)


def test_a_naming_check_that_cannot_run_lets_the_note_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Advisory: a model that fails is no reason to stop a department recording what it did."""
    monkeypatch.setattr(case_notes, "private_person", lambda text: None)
    case_notes.not_naming_anyone("Cleared the drain at the market.", read_by_the_resident=True)
