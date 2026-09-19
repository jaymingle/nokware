"""Filing a report end to end, with storage, photos and the model replaced by fakes."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import BackgroundTasks

from app.routes import reports
from app.services import report_intake
from app.services.citizen_reports import NotificationEvent
from app.services.notifications import compose, notify_quietly
from app.services.report_contacts import ContactChoice, InvalidNumber
from app.services.report_intake import ReportSubmission, submit
from app.services.report_rules import InvalidReport, ModelVerdict

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)


class Store:
    def __init__(self) -> None:
        self.cases: dict[str, dict[str, Any]] = {}
        self.assignments: list[dict[str, Any]] = []
        self.history: list[tuple[str, Any]] = []
        self.contacts: dict[str, dict[str, Any]] = {}
        self.model_calls: list[str] = []
        self.next_verdict: ModelVerdict | None = ModelVerdict("civic_service", "drainage", 3)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    s = Store()

    def create_report(case_id: str, data: dict[str, Any]) -> dict[str, Any]:
        s.cases[case_id] = {**data, "$id": case_id}
        return s.cases[case_id]

    def save_contact(case_id: str, choice: ContactChoice) -> None:
        s.contacts[case_id] = {"phone": choice.phone, "whatsapp": choice.whatsapp, "notify": choice.notify,
                               "callbackConsent": choice.callback_consent}

    def verdict(description: str) -> ModelVerdict | None:
        s.model_calls.append(description)
        return s.next_verdict

    monkeypatch.setattr(report_intake.report_store, "create_report", create_report)
    monkeypatch.setattr(report_intake.report_store, "create_assignment", s.assignments.append)
    monkeypatch.setattr(report_intake.case_history, "record", lambda case_id, entry: s.history.append((case_id, entry)))
    monkeypatch.setattr(report_intake, "save_contact", save_contact)
    monkeypatch.setattr(report_intake, "update_contact", lambda case_id, changes: s.contacts[case_id].update(changes))
    monkeypatch.setattr(report_intake, "store_photos", lambda case_id, photos: [f"p{i}" for i, _ in enumerate(photos)])
    monkeypatch.setattr(report_intake, "model_verdict", verdict)
    return s


def form(**fields: Any) -> ReportSubmission:
    base = dict(description="The drain on Mudor road is choked with plastic.", ward="mudor", sub_metro=None,
                safety_topic=None, phone=None, whatsapp=None, notify=False, callback_consent=False)
    return ReportSubmission(**{**base, **fields})


def test_a_civic_report_is_filed_routed_and_recorded(store: Store) -> None:
    receipt = submit(form(phone="024 123 4567"), [], NOW)
    case = receipt.case
    assert (case["category"], case["topic"], case["recipients"], case["status"]) == ("civic_service", "drainage", ["dept-works"], "assigned")
    assert case["wardLocation"] == "mudor" and case["subMetro"] == "ashiedu-keteke"
    assert len(case["reference"]) == 9 and len(case["$id"]) == 36
    assert [a["recipient"] for a in store.assignments] == ["dept-works"]
    assert [entry.action for _, entry in store.history] == ["submitted", "classified", "assigned"]
    assert receipt.messages_on and store.contacts[case["$id"]]["notify"] is True
    assert store.contacts[case["$id"]]["callbackConsent"] is False  # never from the normal form
    assert "phone" not in case and "+233241234567" not in str(case)  # the number lives apart


def test_a_declared_safety_report_never_reaches_the_model_and_keeps_no_ward(store: Store) -> None:
    receipt = submit(form(description="He hits my mother every night.", safety_topic="abuse", ward="kaneshie",
                          phone="0241234567", notify=False, callback_consent=True), [], NOW)
    case = receipt.case
    assert store.model_calls == []
    assert case["isSensitive"] and case["severity"] == 5 and case["wardLocation"] is None
    assert case["subMetro"] == "okaikoi-south" and len(store.assignments) == 2
    assert not receipt.messages_on and not receipt.held_for_consent
    assert store.contacts[case["$id"]]["callbackConsent"] is True
    assert all("hits" not in (entry.note or "") for _, entry in store.history)  # the trail never quotes it


def test_the_safety_opt_in_is_respected(store: Store) -> None:
    receipt = submit(form(description="My neighbour threatened to kill me.", safety_topic="threat_to_life",
                          phone="0241234567", notify=True), [], NOW)
    assert receipt.messages_on


def test_a_report_the_model_files_as_personal_safety_is_still_sent_the_neutral_message(
    store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    """The resident gave a number on the ordinary form, which promised messages, so the messages go: the neutral
    one, which names the reference and nothing else. Only the call waits for the answer they haven't given yet."""
    store.next_verdict = ModelVerdict("personal_safety", "child_at_risk", 2)
    with caplog.at_level(logging.INFO):
        receipt = submit(form(description="The children next door are beaten daily.", phone="0241234567"), [], NOW)
    contact = store.contacts[receipt.case["$id"]]

    assert receipt.case["isSensitive"] and receipt.case["wardLocation"] is None
    assert receipt.messages_on and contact["notify"] is True
    assert contact["callbackConsent"] is False and receipt.held_for_consent and receipt.preferences_token
    assert contact["preferencesTokenHash"] == report_intake.token_hash(receipt.preferences_token)
    decisions = [line for line in caplog.messages if "personal safety by the classifier" in line]
    assert len(decisions) == 1 and "neutral message" in decisions[0] and "0241234567" not in decisions[0]


def test_the_neutral_message_that_reaches_such_a_resident_says_nothing_about_their_report(store: Store) -> None:
    """The reason the message can be sent at all: whoever is holding that phone learns nothing from it."""
    store.next_verdict = ModelVerdict("personal_safety", "child_at_risk", 2)
    receipt = submit(form(description="The children next door are beaten daily.", phone="0241234567"), [], NOW)
    body = compose(NotificationEvent.SUBMITTED, receipt.case).body

    assert body == f"Nokware: reference {receipt.case['reference']} received."
    for giveaway in ("child", "safety", "police", "welfare", "report", "http"):
        assert giveaway not in body.lower()


def test_the_web_form_hands_that_message_to_the_ordinary_path_rather_than_filing_in_silence(store: Store) -> None:
    """The route is what sends the receipt, so the wiring is the whole of it: while the form held the consent back,
    no task was queued, no outbox row was ever written, and the resident heard nothing from anyone, ever."""
    store.next_verdict = ModelVerdict("personal_safety", "child_at_risk", 2)
    tasks = BackgroundTasks()

    receipt = reports.file_report(tasks, form(description="The children next door are beaten daily.", phone="0241234567"))

    assert receipt.private and receipt.messages_on and receipt.held_for_consent
    assert [(task.func, task.args[1]) for task in tasks.tasks] == [(notify_quietly, NotificationEvent.SUBMITTED)]


def test_the_link_that_asks_about_a_call_lasts_a_week_and_still_answers_on_the_sixth_day(store: Store) -> None:
    """An hour was gone before a resident in danger had a quiet moment to weigh a phone call from the Police."""
    store.next_verdict = ModelVerdict("personal_safety", "child_at_risk", 2)
    receipt = submit(form(description="The children next door are beaten daily.", phone="0241234567"), [], NOW)
    contact = store.contacts[receipt.case["$id"]]
    expires = datetime.fromisoformat(contact["preferencesExpiresAt"])

    assert timedelta(days=7) <= report_intake.PREFERENCES_WINDOW and NOW + timedelta(days=7) <= expires
    assert NOW + timedelta(days=6) < expires  # the day the resident comes back to it


def test_without_a_number_there_is_nothing_to_store_or_send(store: Store) -> None:
    receipt = submit(form(), [], NOW)
    assert store.contacts == {} and not receipt.messages_on


def test_nothing_is_stored_when_any_part_is_invalid(store: Store) -> None:
    with pytest.raises(InvalidNumber):
        submit(form(phone="0302123456"), [], NOW)
    with pytest.raises(InvalidReport):
        submit(form(description="drain"), [], NOW)
    with pytest.raises(InvalidReport):
        submit(form(ward=None), [], NOW)
    assert store.cases == {} and store.contacts == {}
