"""What a citizen sees and can do with a reference, and the deletion of numbers."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.services import report_followups
from app.services.report_followups import Preferences, public_status, set_preferences
from app.services.report_intake import PREFERENCES_WINDOW, token_hash
from app.services.workflow import NotAllowed

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
CIVIC = {
    "$id": "c1", "reference": "K7QM-4TXP", "createdAt": "2026-09-01T10:00:00+00:00", "status": "resolved",
    "resolvedAt": (NOW - timedelta(days=2)).isoformat(), "category": "civic_service", "isSensitive": False,
    "topic": "drainage", "recipients": ["dept-works"], "wardLocation": "mudor", "subMetro": "ashiedu-keteke",
    "description": "The drain is choked.",
}
SAFETY = {**CIVIC, "$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "isSensitive": True,
          "topic": "abuse", "recipients": ["agency-police", "dept-social-welfare"], "wardLocation": None,
          "status": "in_progress", "resolvedAt": None, "description": "He hits me."}
DONE = [{"recipient": "dept-works", "active": True, "resolutionNote": "Drain desilted on 11 September."}]


def test_an_everyday_case_shows_what_where_who_and_the_resolution() -> None:
    view = public_status(CIVIC, DONE, NOW)
    assert (view["topic"], view["ward"], view["recipients"]) == ("Drainage and flooding", "Mudor", ["Works Department"])
    assert view["resolution_notes"] == [{"recipient": "Works Department", "note": "Drain desilted on 11 September."}]
    assert view["escalate_until"] == (NOW - timedelta(days=2) + timedelta(days=14)).isoformat()


def test_a_personal_safety_case_shows_only_how_far_along_it_is(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report_followups.report_locations, "views", lambda case_id: [])
    view = public_status(SAFETY, [], NOW)
    assert view["private"] and view["stage"] == "in_progress"
    for hidden in ("topic", "recipients", "ward", "sub_metro", "resolution_notes", "status", "description"):
        assert hidden not in view
    assert "hits" not in str(view) and "Police" not in str(view)


@pytest.fixture
def contact(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    stored = {"notify": False, "callbackConsent": False, "preferencesTokenHash": token_hash("tok"),
              "preferencesExpiresAt": (NOW + timedelta(minutes=30)).isoformat()}
    monkeypatch.setattr(report_followups, "find", lambda reference: SAFETY)
    monkeypatch.setattr(report_followups, "contact_for", lambda case_id: stored)
    monkeypatch.setattr(report_followups, "update_contact", lambda case_id, changes: stored.update(changes))
    return stored


def test_the_messages_question_is_answered_once_with_the_receipt_token(contact: dict[str, Any]) -> None:
    _, on = set_preferences("M3RD-8WQA", "tok", Preferences(notify=True, callback_consent=True), NOW)
    assert on and contact["notify"] and contact["callbackConsent"] and contact["preferencesTokenHash"] is None
    with pytest.raises(NotAllowed):
        set_preferences("M3RD-8WQA", "tok", Preferences(notify=False, callback_consent=False), NOW)


def test_the_callback_question_can_still_be_answered_on_the_sixth_day(contact: dict[str, Any]) -> None:
    """The link lives a week, not an hour: a resident in danger weighs a phone call from the Police in their own
    time, and a link that expired while they thought about it asks them nothing."""
    contact["preferencesExpiresAt"] = (NOW + PREFERENCES_WINDOW).isoformat()
    _, receipt_owed = set_preferences(
        "M3RD-8WQA", "tok", Preferences(notify=True, callback_consent=True), NOW + timedelta(days=6)
    )
    assert contact["callbackConsent"] is True and receipt_owed  # their messages were off, so the receipt is owed


def test_a_resident_whose_messages_were_already_on_is_not_sent_the_receipt_a_second_time(contact: dict[str, Any]) -> None:
    """A case the classifier read as personal safety had its neutral receipt when it was filed. Answering the
    callback question is not a second filing, and a duplicate reference is a message they have to make sense of."""
    contact["notify"] = True
    _, receipt_owed = set_preferences("M3RD-8WQA", "tok", Preferences(notify=True, callback_consent=True), NOW)
    assert contact["callbackConsent"] is True and not receipt_owed


def test_a_wrong_or_late_token_changes_nothing(contact: dict[str, Any]) -> None:
    with pytest.raises(NotAllowed):
        set_preferences("M3RD-8WQA", "guess", Preferences(notify=True, callback_consent=True), NOW)
    with pytest.raises(NotAllowed):
        set_preferences("M3RD-8WQA", "tok", Preferences(notify=True, callback_consent=True), NOW + timedelta(hours=2))
    assert contact["notify"] is False


def test_expired_numbers_are_deleted_and_the_trail_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    deleted: list[str] = []
    trail: list[Any] = []
    monkeypatch.setattr(report_followups, "contacts_due_for_deletion", lambda now: [{"$id": "c1", "caseId": "c1"}])
    monkeypatch.setattr(report_followups, "delete_contact", deleted.append)
    monkeypatch.setattr(report_followups.case_history, "record", lambda case_id, entry: trail.append(entry))
    assert report_followups.purge_expired_contacts(NOW) == 1
    assert deleted == ["c1"] and trail[0].action == "contact_deleted"
