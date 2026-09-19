"""Petitions on USSD and WhatsApp after the rework: checking one, and what a removed one may say.

Nobody approves a petition and a contributor can take one down, so a resident with only a keypad needs to be able
to ask what became of the number they signed — and a removed petition must answer from its removal record alone.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fakeredis
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app
from app.services import (
    channel_limits,
    channel_petitions,
    channel_sessions,
    petition_removals,
    petitions,
    phone_proof,
    redis_store,
    ussd,
    whatsapp,
    whatsapp_conversation,
    whatsapp_reply,
)
from app.services.phone_proof import Channel
from app.services.whatsapp_conversation import Inbound

NOW = datetime(2026, 9, 19, 11, 0, tzinfo=UTC)
PHONE = "+233241234567"
SITE = get_settings().public_site_url.rstrip("/")
BARE = SITE.split("://", 1)[-1]
TITLE = "[TEST] Desilt the Kaneshie drain"
OPEN = {"$id": "p1", "code": "482913", "title": TITLE, "status": "open", "threshold": 250, "signatureCount": 12,
        "publishedAt": "2026-09-14T09:00:00+00:00", "closesAt": "2026-12-13T09:00:00+00:00", "version": 1}
GONE = {"$id": "p2", "code": "771204", "title": "[TEST] Sack the man at the lorry park", "status": "removed",
        "publishedAt": "2026-09-10T09:00:00+00:00", "removalCount": 1}
REMOVAL = {"$id": "r1", "petitionId": "p2", "code": "771204", "ground": "personal_data", "duplicateOf": None,
           "previousRemovals": 0, "at": "2026-09-18T15:30:00+00:00"}


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> fakeredis.FakeRedis:
    fake = fakeredis.FakeRedis(decode_responses=True)
    for module in (redis_store, channel_limits, channel_sessions, phone_proof, whatsapp, whatsapp_conversation):
        monkeypatch.setattr(module, "get_redis", lambda: fake)
    return fake


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> dict[str, dict[str, Any]]:
    """One standing petition and one that was removed, with the removal record behind it."""
    removals: dict[str, dict[str, Any]] = {"p2": dict(REMOVAL)}
    by_code = {"482913": OPEN, "771204": GONE}

    def find(code: str) -> dict[str, Any]:
        if code not in by_code:
            raise petitions.PetitionNotFound(code)
        return dict(by_code[code])

    def public(code: str) -> dict[str, Any]:
        """No removed petition is found here, as in the service: its page is the tombstone."""
        found = find(code)
        if found["status"] == "removed":
            raise petitions.PetitionNotFound(code)
        return found

    monkeypatch.setattr(petitions, "find", find)
    monkeypatch.setattr(petitions, "public", public)
    monkeypatch.setattr(petition_removals, "latest_removal", lambda petition_id: removals.get(petition_id))
    return removals


def _dial(*presses: str, session_id: str = "s1") -> ussd.Reply:
    reply = ussd.respond(ussd.Dial(session_id, PHONE, "*928*1#", True), lambda *a: None)
    for press in presses:
        reply = ussd.respond(ussd.Dial(session_id, PHONE, press, False), lambda *a: None)
    return reply


@pytest.fixture
def chat(monkeypatch: pytest.MonkeyPatch, server: fakeredis.FakeRedis) -> list[str]:
    replies: list[str] = []
    monkeypatch.setattr(whatsapp_reply, "reply", lambda number, text: replies.append(text))
    return replies


def _say(text: str, sid: list[int] = [0]) -> None:  # noqa: B006
    sid[0] += 1
    whatsapp_conversation.handle(Inbound(PHONE, text, None, f"SM-petition-{sid[0]}"))


def test_the_menu_offers_checking_a_petition_and_still_fits_one_screen() -> None:
    assert ussd.MENU.splitlines()[-1] == "7 Check a petition"
    assert len(ussd.MENU) <= ussd.SCREEN_MAX
    assert len("Choose 1 to 7.\n" + ussd.MENU_ITEMS) <= ussd.SCREEN_MAX  # the correction shows every option too


def test_on_ussd_a_petition_says_its_stage_its_signatures_and_when_it_closes(store: dict[str, Any]) -> None:
    reply = _dial("7", "482 913")
    assert reply == ussd.Reply(
        "Petition 482 913: Open for signatures.\n12 of 250 signatures.\nCloses 13 Dec 2026.\n"
        f"{BARE}/petitions/482913", False)
    assert len(reply.message) <= ussd.SCREEN_MAX


def test_on_ussd_a_removed_petition_shows_the_tombstone_and_nothing_of_the_petition(store: dict[str, Any]) -> None:
    reply = _dial("7", "771204")
    assert reply == ussd.Reply(
        "Petition 771 204 was removed on 18 Sep 2026: Contains personal data.\n"
        f"Nothing of the petition is public.\n{BARE}/petitions/771204", False)
    assert len(reply.message) <= ussd.SCREEN_MAX
    assert GONE["title"] not in reply.message and "lorry" not in reply.message


def test_on_ussd_a_number_nobody_has_and_a_number_that_is_too_short_are_said_plainly(store: dict[str, Any]) -> None:
    assert _dial("7", "4829").message == ussd.SIX_DIGITS
    assert _dial("7", "111111").message == "No petition has the number 111111. Check it and dial again."


def test_on_whatsapp_petition_and_a_number_gets_the_same_standing_in_full(store: dict[str, Any], chat: list[str]) -> None:
    _say("petition 482913")
    assert chat[-1] == ("Petition 482 913: Open for signatures.\n12 of 250 signatures.\nCloses 13 December 2026.\n"
                        f"{SITE}/petitions/482913")
    _say("Petition: 771-204")
    assert chat[-1] == ("Petition 771 204 was removed on 18 September 2026: Contains personal data.\n"
                        f"Nothing of the petition is public.\n{SITE}/petitions/771204")
    assert "lorry" not in chat[-1]


def test_on_whatsapp_a_number_nobody_has_is_said_plainly(store: dict[str, Any], chat: list[str]) -> None:
    _say("petition 111111")
    assert chat[-1] == "No petition has the number 111111. Check it and send it again."


def test_the_petition_command_asks_for_the_word_so_it_never_swallows_a_phone_code() -> None:
    assert whatsapp_conversation.petition_asked("petition 482 913") == "482913"
    assert whatsapp_conversation.petition_asked("482913") is None
    assert phone_proof.typed_code("code 482913") == "482913"


def test_what_the_tombstone_holds_is_kept_in_full_where_there_is_room_and_the_address_never_gives_way(
        store: dict[str, dict[str, Any]]) -> None:
    store["p2"].update(duplicateOf="305118", previousRemovals=2)
    full = channel_petitions.standing_text(channel_petitions.standing("771204"), SITE)
    assert full.splitlines()[1:] == ["It duplicated petition 305 118.", "Nothing of the petition is public.",
                                     "It had been removed 2 times before.", f"{SITE}/petitions/771204"]
    screen = _dial("7", "771204").message
    assert "It duplicated petition 305 118." in screen  # the line that sends a reader somewhere is the one kept
    assert len(screen) <= ussd.SCREEN_MAX and screen.endswith(f"{BARE}/petitions/771204")
    assert "..." not in screen  # a line is dropped whole, never cut in half


def test_a_removed_petition_takes_no_signature_on_ussd(store: dict[str, Any]) -> None:
    assert _dial("6", "771204") == ussd.Reply("This petition was removed, so it takes no more signatures.", False)


def test_a_removed_petition_takes_no_signature_on_the_web(store: dict[str, Any]) -> None:
    # Issued against the real clock, not the fixture's: the route opens the proof at the time the test runs, so a
    # proof sealed at a fixed hour stops working once that hour is twelve hours past.
    proof = phone_proof.issue_proof(PHONE, Channel.USSD, datetime.now(UTC))
    response = TestClient(app).post("/api/petitions/771204/signatures", json={"show_name": False},
                                    headers={"X-Phone-Proof": proof})
    assert response.status_code == 409
    assert response.json()["detail"] == "This petition was removed, so it takes no more signatures."


def test_whatsapp_has_no_signing_path_so_it_has_no_signature_to_refuse() -> None:
    """WhatsApp reads a petition's standing and nothing else. A signature is refused where one can be given — the
    web and USSD — and this is what says WhatsApp is not a third such place."""
    modules = Path(whatsapp_conversation.__file__).parent.glob("whatsapp*.py")
    assert "petition_signatures" not in "\n".join(path.read_text() for path in modules)
    assert "sign" not in whatsapp_conversation.HELP.lower()
