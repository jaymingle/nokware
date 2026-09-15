"""What fonts leave in extracted PDF text, mended at ingestion: known letters restored, nothing guessed."""

from app.services import ingestion
from app.services.pdf_text import mend, needs_mending


def test_ligatures_become_their_letters_so_search_finds_the_word() -> None:
    assert mend("preventing \uf002ooding, signi\uf001cant, \ufb01re and \ufb03ce") == "preventing flooding, significant, fire and ffice"


def test_font_bullets_become_bullets() -> None:
    assert mend("\uf0b7 Name and proof\n\uf0a7 Address\n\uf0fc Done") == "• Name and proof\n• Address\n• Done"


def test_a_lost_character_becomes_a_space_never_a_guess() -> None:
    assert mend("Letter from the Mayor \ufffd\ufffd\ufffd\ufffd1") == "Letter from the Mayor  1"  # dot leaders
    assert mend("section 3\ufffd1") == "section 3 1"  # not "31", and not a guessed "3.1"
    assert mend("reacts to them\ufffd We will") == "reacts to them  We will"


def test_ingestion_mends_and_says_what_still_needs_it() -> None:
    assert ingestion.clean_text("\uf002ood\x00 risk\x07") == "flood risk "
    assert needs_mending("\uf002ood") and not needs_mending("flood • risk")
