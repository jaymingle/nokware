"""Who represents an electoral area, found by any of its spellings."""

from fastapi.testclient import TestClient

from app.main import app
from app.wards import find_ward, sub_metro_of, sub_metros, wards

client = TestClient(app)


def test_areas_use_the_given_spellings_and_keep_the_earlier_ones_as_alternates() -> None:
    assert wards()["bubuashie"].name == "Bubiashie" and "Bubuashie" in wards()["bubuashie"].alternates
    for spelling in ("Bubiashie", "bubuashie", "Nmlitsa-Gonno", "nmlitsagonno", "Korle Wokon", "korle woko", "Kantsian"):
        assert find_ward(spelling) is not None, spelling
    assert find_ward("Madina") is None and find_ward("  ") is None


def test_the_sub_metros_and_their_areas_are_as_given() -> None:
    assert sub_metro_of("nmlitsagonno") == "ablekuma-south"  # the earlier report put it in Ashiedu Keteke
    assert sub_metro_of("awudome") == "okaikoi-south"
    assert len(wards()) == 20  # the given 19, plus Mukose from the earlier report
    chairs = {s.name: (s.chairperson, s.chairperson_area) for s in sub_metros().values()}
    assert chairs["Ashiedu Keteke"] == ("Hon. Peter Quaye", "Korle Woko")


def test_an_area_finds_its_sub_metro_chairperson_office_and_the_switchboard() -> None:
    body = client.get("/api/representatives", params={"area": "Bubuashie"}).json()
    assert body["matched"] == "bubuashie" and len(body["sub_metros"]) == 1
    sub_metro = body["sub_metros"][0]
    assert (sub_metro["name"], sub_metro["chairperson"], sub_metro["office"]) == ("Okaikoi South", "Hon. David Abalo", "Kaneshie")
    assert [a["name"] for a in sub_metro["electoral_areas"]] == ["Bubiashie"]
    assert body["switchboard"]["numbers"][0]["number"] == "0302 665 951"
    assert body["source"]["url"] == "https://ama.gov.gh/theassemblymembers.php"


def test_every_area_without_a_filter_and_a_clear_404_for_an_unknown_one() -> None:
    body = client.get("/api/representatives").json()
    assert sum(len(s["electoral_areas"]) for s in body["sub_metros"]) == 20 and body["matched"] is None
    missing = client.get("/api/representatives", params={"area": "Madina"})
    assert missing.status_code == 404 and "spelling" in missing.json()["detail"]
