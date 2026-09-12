from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file.

    Field names are snake_case; pydantic-settings maps them to the uppercase
    environment variables case-insensitively (e.g. ``appwrite_endpoint`` reads
    ``APPWRITE_ENDPOINT``). All fields are required — a missing variable raises
    at startup rather than silently defaulting.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Appwrite
    appwrite_endpoint: str
    appwrite_project_id: str
    appwrite_api_key: str

    # Postgres (pgvector)
    postgres_url: str

    # MinIO
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_ledger_bucket: str
    minio_photos_bucket: str

    # Google Gemini
    gemini_api_key: str


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_error_summary(exc: ValidationError) -> str:
    """Name the missing/invalid variables without echoing any values.

    Never print str(exc) for a settings error: pydantic includes the loaded
    input in it, which is the secrets.
    """
    problems = [
        f"{str(err['loc'][0]).upper()} ({err['msg'].lower()})"
        for err in exc.errors(include_url=False, include_input=False)
    ]
    return f"Cannot load settings from {ENV_FILE}: {', '.join(problems)}"
