"""Petitions P3: the MCE's public response, the 30 days made visible, the creator's updates, and the figures."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routes import petition_presenters as present
from app.services import petition_clock, petition_figures, petition_responses, petition_updates, petitions
from app.services.auth import Principal, Role
from app.services.citizen_reports import NotificationChannel
from app.services.petition_rules import (
    InvalidPetition,
    PetitionAction,
    Response,
    WrongState,
    check_signable,
    days_late,
    response_fields,
    response_overdue,
)
from app.services.petition_updates import Update
from app.services.sms_text import is_gsm7, pages

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
MCE = Principal("u-m", "Hon. Test MCE", "m@x.org", Role.MCE)
TEXT = "The Works Department will desilt the Kaneshie market drain before 30 May, and publish the schedule on this page."
AWAITING = {"$id": "p1", "code": "534079", "title": "[TEST] Desilt the drain", "status": "awaiting_response", "threshold": 150,
            "signatureCount": 151, "thresholdReachedAt": (NOW - timedelta(days=10)).isoformat(),
            "responseDue": (NOW + timedelta(days=20)).isoformat(), "closesAt": (NOW + timedelta(days=60)).isoformat(),
            "publishedAt": (NOW - timedelta(days=20)).isoformat(), "creatorPhone": "+233241234567", "creatorChannel": "ussd"}


def test_a_response_is_one_of_three_with_a_statement_and_a_named_department_when_referred() -> None:
    fields = response_fields(AWAITING, Response("will_act", f"  {TEXT}  ", None, ("d1", "d1")), NOW)
    assert (fields["status"], fields["responseText"], fields["responseDocumentIds"]) == ("responded", TEXT, ["d1"])
    assert response_fields(AWAITING, Response("referred", TEXT, "dept-works", ()), NOW)["responseDepartment"] == "dept-works"
    for bad in (Response("maybe", TEXT, None, ()), Response("referred", TEXT, None, ()), Response("referred", TEXT, "agency-police", ()),
                Response("cannot_act", "No.", None, ()), Response("will_act", TEXT, None, ("a", "b", "c", "d"))):
        with pytest.raises(InvalidPetition):
            response_fields(AWAITING, bad, NOW)
    for status in ("open", "responded", "closed"):
        with pytest.raises(WrongState):
            response_fields({**AWAITING, "status": status}, Response("will_act", TEXT, None, ()), NOW)


def test_a_late_response_is_taken_and_says_how_late() -> None:
    due = NOW - timedelta(days=3, hours=2)
    late = {**AWAITING, "responseDue": due.isoformat(), "respondedAt": NOW.isoformat()}
    assert days_late(late) == 4 and days_late({**late, "respondedAt": due.isoformat()}) == 0
    assert response_fields({**AWAITING, "responseDue": due.isoformat()}, Response("cannot_act", TEXT, None, ()), NOW)["status"] == "responded"


def test_once_answered_it_takes_no_more_signatures() -> None:
    with pytest.raises(WrongState):
        check_signable({**AWAITING, "status": "responded"}, NOW)


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"petition": dict(AWAITING), "trail": [], "told": []}
    monkeypatch.setattr(petitions, "find", lambda code: dict(state["petition"]))
    monkeypatch.setattr(petitions, "check_documents", lambda ids: None)
    monkeypatch.setattr(petitions, "update_petition", lambda pid, changes: state.update(petition={**state["petition"], **changes}) or dict(state["petition"]))
    monkeypatch.setattr(petitions, "record_history", lambda p, action, actor, from_status, reason=None, note=None:
                        state["trail"].append((action, actor.role, actor.name, reason, note)))
    monkeypatch.setattr(petition_clock.petition_updates, "notify_quietly", lambda petition, update: state["told"].append(update))
    return state


def test_the_mces_response_is_published_and_the_trail_keeps_who_gave_it(stored: dict[str, Any]) -> None:
    updated = petition_responses.respond(MCE, "534079", Response("referred", TEXT, "dept-works", ()), NOW)
    assert updated["status"] == "responded" and updated["respondedByName"] == "Hon. Test MCE"
    assert stored["trail"] == [(PetitionAction.RESPONDED, "mce", "Hon. Test MCE", "referred", None)]
    shown = present.response(updated)
    assert shown is not None and shown.label == "Referred to a department" and shown.department == "Works Department"
    assert "Hon. Test MCE" not in shown.model_dump_json() and shown.days_late == 0


def test_thirty_days_without_a_response_is_recorded_once_and_the_creator_told(stored: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    stored["petition"]["responseDue"] = (NOW - timedelta(minutes=1)).isoformat()
    monkeypatch.setattr(petition_clock, "_due", lambda queries: [stored["petition"]] if "awaiting_response" in str(queries) else [])
    assert response_overdue(stored["petition"], NOW)
    assert petition_clock.run_clock(NOW)["unanswered"] == ["534079"]
    assert petition_clock.run_clock(NOW)["unanswered"] == []  # once
    assert stored["petition"]["noResponseAt"] == NOW.isoformat() and stored["told"] == [Update.NO_RESPONSE]
    assert stored["trail"][0][:2] == (PetitionAction.NO_RESPONSE, "system")


def _petition_for(update: Update) -> dict[str, Any]:
    return {**AWAITING, "refusalReason": "not_assembly" if update == Update.REFUSED else None}


def test_every_update_is_one_plain_sms_page_with_the_number_and_the_link(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = petition_updates.get_settings().model_copy(update={"public_site_url": "https://nokware.accra-metro.gov.gh"})
    monkeypatch.setattr(petition_updates, "get_settings", lambda: settings)
    for update in Update:
        text = petition_updates.compose(update, _petition_for(update))
        assert pages(text) == 1 and is_gsm7(text) and "534 079" in text, (update, text)
        assert ("petitions/mine" if update == Update.REFUSED else "petitions/534079") in text, (update, text)
        assert not any(word in text.lower() for word in ("ignored", "failed", "sorry", "unfortunately", "!")), text
    assert "Not the Assembly's responsibility" in petition_updates.compose(Update.REFUSED, _petition_for(Update.REFUSED))


def test_no_response_is_said_plainly_in_full_with_a_usual_site_address(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = petition_updates.get_settings().model_copy(update={"public_site_url": "https://nokware.org"})
    monkeypatch.setattr(petition_updates, "get_settings", lambda: settings)
    assert petition_updates.compose(Update.NO_RESPONSE, AWAITING) == (
        "Nokware: no response from the MCE 30 days after your petition 534 079 reached its threshold. "
        "Its page now says so: https://nokware.org/petitions/534079")


def test_an_update_goes_on_the_creators_own_channel_and_whatsapp_falls_back_to_sms(monkeypatch: pytest.MonkeyPatch) -> None:
    number = AWAITING["creatorPhone"]
    assert petition_updates.channel_for({"creatorChannel": "ussd"}, number) == (NotificationChannel.SMS, "")
    assert petition_updates.channel_for({"creatorChannel": "sms"}, number)[0] == NotificationChannel.SMS
    assert petition_updates.channel_for({"creatorChannel": "whatsapp"}, number)[0] == NotificationChannel.WHATSAPP  # WhatsApp on "log"
    settings = petition_updates.get_settings().model_copy(update={"whatsapp_provider": "twilio"})
    monkeypatch.setattr(petition_updates, "get_settings", lambda: settings)
    monkeypatch.setattr(petition_updates, "window_open", lambda n: False)
    channel, why = petition_updates.channel_for({"creatorChannel": "whatsapp"}, number)
    assert channel == NotificationChannel.SMS and "24-hour window had closed" in why
    monkeypatch.setattr(petition_updates, "window_open", lambda n: True)
    assert petition_updates.channel_for({"creatorChannel": "whatsapp"}, number)[0] == NotificationChannel.WHATSAPP


def test_an_update_leaves_a_private_line_in_the_trail_and_nothing_once_the_number_is_deleted(stored: dict[str, Any]) -> None:
    petition_updates.notify_creator(stored["petition"], Update.RESPONDED)
    note = stored["trail"][-1][4]
    assert stored["trail"][-1][0] == PetitionAction.CREATOR_NOTIFIED and "by SMS: recorded, not sent" in note and "241234567" not in note
    petition_updates.notify_creator({**stored["petition"], "creatorPhone": None}, Update.RESPONDED)
    assert len(stored["trail"]) == 1
    assert present.timeline([{"action": "creator_notified", "at": "t"}, {"action": "no_response", "at": "t2"}])[0].action == "no_response"


def test_the_figures_partition_every_petition_that_reached_its_threshold() -> None:
    start = NOW - timedelta(days=365)
    history = [{"action": a, "at": NOW.isoformat(), "reason": r} for a, r in
               (("submitted", None), ("submitted", None), ("published", None), ("auto_published", None), ("refused", "duplicate"))]
    history.append({"action": "submitted", "at": (start - timedelta(days=1)).isoformat(), "reason": None})  # before the period
    reached = [
        {**AWAITING, "status": "responded", "respondedAt": NOW.isoformat()},
        {**AWAITING, "status": "responded", "responseDue": (NOW - timedelta(days=2)).isoformat(), "respondedAt": NOW.isoformat()},
        {**AWAITING, "responseDue": (NOW - timedelta(days=1)).isoformat()},
        dict(AWAITING),
    ]
    figures = petition_figures.build(history, reached, start, NOW)
    assert (figures["sent"], figures["published_by_mce"], figures["published_automatically"], figures["refused"]) == (2, 1, 1, 1)
    assert (figures["answered_in_time"], figures["answered_late"], figures["unanswered"], figures["waiting"]) == (1, 1, 1, 1)
    assert figures["reached_threshold"] == 4 and next(r for r in figures["refusals"] if r["reason"] == "duplicate")["count"] == 1


def test_only_the_mce_can_respond() -> None:
    body = {"kind": "will_act", "text": TEXT}
    assert TestClient(app).post("/api/petitions/534079/response", json=body).status_code == 401
