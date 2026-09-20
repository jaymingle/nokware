"""Settings a deploy can get wrong quietly: the site address residents are sent, and who may call the API."""

import logging

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.main import check_cors_is_meant_for_here

REQUIRED = {
    "appwrite_endpoint": "https://appwrite.example/v1",
    "appwrite_project_id": "nokware",
    "appwrite_api_key": "key",
    "postgres_url": "postgresql+psycopg://user:pw@localhost:5432/db",
    "minio_endpoint": "minio.example",
    "minio_access_key": "access",
    "minio_secret_key": "secret",
    "minio_ledger_bucket": "ledger",
    "minio_photos_bucket": "photos",
    "gemini_api_key": "key",
}


def test_the_api_refuses_to_start_without_the_address_it_puts_in_residents_messages() -> None:
    with pytest.raises(ValidationError) as raised:
        Settings(**REQUIRED, _env_file=None)  # type: ignore[arg-type]
    assert "public_site_url" in str(raised.value)


def test_the_address_given_is_the_one_used() -> None:
    settings = Settings(**REQUIRED, public_site_url="https://nokware.example", _env_file=None)  # type: ignore[arg-type]
    assert settings.public_site_url == "https://nokware.example"


def test_a_deployed_site_still_letting_localhost_in_is_called_out(caplog: pytest.LogCaptureFixture,
                                                                 monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main.settings, "public_site_url", "https://nokware.example")
    monkeypatch.setattr(main.settings, "cors_origin_regex", r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
    with caplog.at_level(logging.WARNING):
        check_cors_is_meant_for_here()
    assert "CORS_ORIGIN_REGEX" in caplog.text


def test_a_developer_on_localhost_is_not_nagged(caplog: pytest.LogCaptureFixture,
                                                monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main.settings, "public_site_url", "http://localhost:3000")
    monkeypatch.setattr(main.settings, "cors_origin_regex", r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
    with caplog.at_level(logging.WARNING):
        check_cors_is_meant_for_here()
    assert "CORS_ORIGIN_REGEX" not in caplog.text


def test_a_deploy_that_turned_localhost_off_is_not_nagged(caplog: pytest.LogCaptureFixture,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    from app import main

    monkeypatch.setattr(main.settings, "public_site_url", "https://nokware.example")
    monkeypatch.setattr(main.settings, "cors_origin_regex", "")
    with caplog.at_level(logging.WARNING):
        check_cors_is_meant_for_here()
    assert "CORS_ORIGIN_REGEX" not in caplog.text
