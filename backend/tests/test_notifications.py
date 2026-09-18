"""Messages to citizens: when, to which channels, and what they say."""

import logging
from typing import Any

import pytest

from app.services import notifications
from app.services.citizen_reports import NotificationChannel, NotificationEvent, NotificationStatus
from app.services.notifications import channels_for, compose
from app.services.sms import SmsError, SmsLimitReached, SmsNothingSent, SmsUnreachable

CIVIC = {"$id": "c1", "reference": "K7QM-4TXP", "category": "civic_service", "recipients": ["dept-works"]}
SAFETY = {"$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "recipients": ["agency-police", "dept-social-welfare"]}


def test_everyday_messages_name_the_department_and_how_to_follow_up() -> None:
    body = compose(NotificationEvent.SUBMITTED, CIVIC).body
    assert "K7QM-4TXP" in body and "Works" in body and "/report/status" in body
    assert "Escalate within 14 days" in compose(NotificationEvent.RESOLVED, CIVIC).body


@pytest.mark.parametrize("event", list(NotificationEvent))
def test_personal_safety_messages_say_nothing_but_the_reference(event: NotificationEvent) -> None:
    message = compose(event, SAFETY)
    lowered = message.body.lower()
    assert "M3RD-8WQA" in message.body and message.template.startswith("private_")
    for giveaway in ("police", "social welfare", "report", "safety", "abuse", "http"):
        assert giveaway not in lowered


def test_every_channel_given_is_used_and_none_without_agreement() -> None:
    both = {"notify": True, "phone": "+233241234567", "whatsapp": "+447700900123"}
    assert [c for c, _ in channels_for(both)] == [NotificationChannel.SMS, NotificationChannel.WHATSAPP]
    assert channels_for({**both, "whatsapp": None}) == [(NotificationChannel.SMS, "+233241234567")]
    assert channels_for({**both, "notify": False}) == []
    assert channels_for(None) == []


def test_until_a_provider_is_wired_in_messages_are_recorded_as_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[dict[str, Any]] = []
    history: list[Any] = []
    monkeypatch.setattr(notifications, "contact_for", lambda case_id: {"notify": True, "phone": "+233241234567"})
    monkeypatch.setattr(notifications, "_outbox", lambda *args: "n1")
    monkeypatch.setattr(notifications.get_databases(), "update_document", lambda *args: written.append(args[3]))
    monkeypatch.setattr(notifications.case_history, "record", lambda case_id, entry: history.append(entry))

    notifications.notify(CIVIC, NotificationEvent.SUBMITTED)

    assert written == [{"status": NotificationStatus.NOT_SENT.value, "provider": "log"}]
    assert history[0].note == "Submission SMS recorded, not sent: no provider is configured yet. It will be sent once one is."
    assert "+233" not in history[0].note


class Broken:
    """A provider that refuses whatever it is handed."""

    name = "arkesel"

    def __init__(self, error: Exception) -> None:
        self.error = error

    def send(self, to: str, body: str) -> str:
        raise self.error


def test_a_provider_failure_is_recorded_and_never_raised() -> None:
    outcome = notifications._deliver(Broken(RuntimeError("gateway down")), "+233241234567", compose(NotificationEvent.SUBMITTED, CIVIC))
    assert outcome["status"] == NotificationStatus.FAILED.value and outcome["provider"] == "arkesel"
    assert not notifications.budget_refused(outcome)  # the provider was asked and may have delivered: never retried


def test_our_own_budget_refusing_a_message_is_told_apart_from_the_provider_refusing_it() -> None:
    """Both end as `failed`; only one means nothing reached anyone, and only that one may be sent again."""
    refusal = SmsLimitReached("Today's limit of 200 SMS pages is reached.")
    outcome = notifications._deliver(Broken(refusal), "+233241234567", compose(NotificationEvent.SUBMITTED, CIVIC))

    assert outcome["status"] == NotificationStatus.FAILED.value and notifications.budget_refused(outcome)
    assert str(refusal) in outcome["error"] and "+233" not in outcome["error"]


def test_a_budget_refusal_is_not_written_into_the_case_history_as_a_failure() -> None:
    refused = {"status": NotificationStatus.FAILED.value, "error": f"{notifications.BUDGET_REFUSED}spent"}
    note = notifications._history_note(NotificationEvent.SUBMITTED, NotificationChannel.SMS, refused, None)
    assert note == "Submission SMS not sent: today's message limit was reached. It will be sent again."

    failed = {"status": NotificationStatus.FAILED.value, "error": "Arkesel refused the request (400)"}
    assert notifications._history_note(NotificationEvent.SUBMITTED, NotificationChannel.SMS, failed, None) == "Submission SMS failed to send."


def test_a_row_left_queued_mid_send_is_closed_so_it_is_never_retried_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[Any] = []
    monkeypatch.setattr(notifications.get_databases(), "update_document", lambda *args: written.append(args[3]))

    notifications.mark_stale_queued("n1", "the send never finished")

    assert written[0]["status"] == NotificationStatus.FAILED.value  # `failed` is the one status the sweep never retries
    assert written[0]["error"].startswith(notifications.STALE_QUEUED) and not notifications.budget_refused(written[0])


def test_a_resolution_after_the_escalation_is_final_and_offers_no_second_escalation() -> None:
    message = compose(NotificationEvent.RESOLVED, {**CIVIC, "escalatedAt": "2026-09-13T10:00:00+00:00"})
    assert message.template == "resolved_after_escalation" and "escalate" not in message.body


def test_a_report_with_no_agreed_channel_says_so_in_the_log(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A safety reclassification holds consent: nothing is sent and nothing fails, so the quiet has to be findable."""
    monkeypatch.setattr(notifications, "contact_for", lambda case_id: {"phone": "", "whatsapp": "", "notify": False})
    with caplog.at_level(logging.INFO):
        notifications.notify({"$id": "case-1"}, NotificationEvent.SUBMITTED)
    assert "No message about case case-1" in caplog.text


def test_a_send_our_own_side_never_attempted_is_told_apart_from_one_the_provider_refused() -> None:
    """The counter the daily budget needs couldn't be reached: nothing was handed to the provider, so it goes again."""
    stopped = SmsNothingSent("The SMS limit can't be checked (RedisUnavailable), so nothing was sent.")
    outcome = notifications._deliver(Broken(stopped), "+233241234567", compose(NotificationEvent.SUBMITTED, CIVIC))

    assert notifications.nothing_was_sent(outcome) and not notifications.budget_refused(outcome)
    assert not notifications.provider_unreachable(outcome) and "+233" not in outcome["error"]
    note = notifications._history_note(NotificationEvent.SUBMITTED, NotificationChannel.SMS, outcome, None)
    assert note == "Submission SMS not sent: it never reached the provider. It will be sent again."


def test_a_send_the_provider_never_answered_is_told_apart_so_it_can_be_sent_again() -> None:
    """No message ID came back, so no delivery report and no poll can ever say whether the resident got it."""
    unanswered = SmsUnreachable("Arkesel couldn't be reached (ReadTimeout).")
    outcome = notifications._deliver(Broken(unanswered), "+233241234567", compose(NotificationEvent.SUBMITTED, CIVIC))

    assert notifications.provider_unreachable(outcome) and not notifications.nothing_was_sent(outcome)
    assert "ReadTimeout" in outcome["error"] and "+233" not in outcome["error"]
    note = notifications._history_note(NotificationEvent.SUBMITTED, NotificationChannel.SMS, outcome, None)
    assert note == "Submission SMS may not have gone out: the provider didn't answer. It will be sent again."


def test_a_provider_that_refused_with_an_answer_is_none_of_the_three_and_is_never_sent_again() -> None:
    outcome = notifications._deliver(Broken(SmsError("Arkesel refused the request (400): invalid")), "+233", compose(NotificationEvent.SUBMITTED, CIVIC))
    assert not notifications.nothing_was_sent(outcome) and not notifications.provider_unreachable(outcome)
    assert not notifications.repaired(outcome)


def test_a_repaired_row_keeps_its_own_status_and_says_what_it_was(monkeypatch: pytest.MonkeyPatch) -> None:
    """`not_sent` is what really happened to that row; the prefix alone is what stops a second send."""
    written: list[Any] = []
    monkeypatch.setattr(notifications.get_databases(), "update_document", lambda *args: written.append(args[3]))

    notifications.mark_repaired("n1", "the sweep sent this message again", was="provider-unreachable: ReadTimeout")

    assert "status" not in written[0] and notifications.repaired(written[0]) and "ReadTimeout" in written[0]["error"]
