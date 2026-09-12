from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file.

    Field names are snake_case; pydantic-settings maps them to the uppercase
    environment variables case-insensitively (e.g. ``appwrite_endpoint`` reads
    ``APPWRITE_ENDPOINT``). All fields are required — a missing variable raises
    at startup rather than silently defaulting.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
