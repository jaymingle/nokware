"""Citizen phone numbers: normalised for sending, masked in logs."""

import pytest

from app.services.report_contacts import InvalidNumber, masked, normalise_phone, normalise_whatsapp


@pytest.mark.parametrize("typed", ["0241234567", "024 123 4567", "+233 24 123 4567", "233241234567", "(024) 123-4567"])
def test_ghanaian_mobiles_in_any_usual_form(typed: str) -> None:
    assert normalise_phone(typed) == "+233241234567"


@pytest.mark.parametrize("typed", ["0302123456", "12345", "+447700900123", "02412345678", "phone"])
def test_sms_needs_a_ghanaian_mobile(typed: str) -> None:
    with pytest.raises(InvalidNumber):
        normalise_phone(typed)


def test_whatsapp_also_takes_international_numbers_with_their_code() -> None:
    assert normalise_whatsapp("+44 7700 900123") == "+447700900123"
    assert normalise_whatsapp("0551234567") == "+233551234567"
    with pytest.raises(InvalidNumber):
        normalise_whatsapp("+12")


def test_logs_show_only_the_country_code_and_last_two_digits() -> None:
    assert masked("+233241234567") == "+233…67"
