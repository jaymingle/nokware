from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file.

    Field names are snake_case; pydantic-settings maps them to the uppercase
    environment variables case-insensitively (e.g. ``appwrite_endpoint`` reads
    ``APPWRITE_ENDPOINT``). Service settings are required — a missing variable
    raises at startup rather than silently defaulting. Only settings whose
    defaults suit local development (CORS, the job intervals, the notification
    providers and the public site URL) and the optional JOB_TOKEN have defaults.
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

    # Browser origins allowed to call the API: exact origins (comma-separated)
    # plus a pattern. The default pattern admits localhost on any port.
    cors_origins: str = ""
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

    # Lets a scheduler call POST /api/jobs/publish-expired with an X-Job-Token
    # header. Empty means only a signed-in MCE can run the job.
    job_token: str = ""

    # How often the API publishes documents whose 72-hour clock has run out
    # (and retries stalled ingestion). 0 turns the built-in runner off.
    deadline_job_interval_seconds: int = 120

    # Citizen notifications. "log" records each message without sending it.
    # SMS_PROVIDER=arkesel sends SMS through Arkesel; the Twilio (WhatsApp)
    # provider is wired in later.
    sms_provider: str = "log"
    whatsapp_provider: str = "log"
    # Arkesel SMS. In sandbox mode (the default) Arkesel accepts each message
    # without delivering it or spending credits.
    arkesel_api_key: str = ""
    arkesel_sender_id: str = ""
    arkesel_sandbox: bool = True
    # The most SMS pages (credits) sent in a day outside the sandbox.
    sms_daily_limit: int = 50
    # Arkesel's webhook secret: verifies the signed delivery reports it sends.
    arkesel_webhook_secret: str = ""
    # The secret in Arkesel's USSD callback address. Arkesel doesn't sign USSD
    # callbacks yet, so this is their only protection. Empty: USSD is off.
    arkesel_ussd_token: str = ""
    # Twilio WhatsApp, needed when WHATSAPP_PROVIDER=twilio. The sender is the
    # WhatsApp address messages come from, e.g. whatsapp:+14155238886 (the sandbox).
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    # The API's public HTTPS address, which Arkesel and Twilio call back.
    # Empty means no callbacks are asked for.
    public_api_url: str = ""
    # Redis, for short-lived channel state (USSD menus, WhatsApp drafts),
    # per-number limits and the SMS page count. Empty: channels are off and the
    # SMS count is kept in this process.
    redis_url: str = ""
    # Spoken replies to WhatsApp voice questions: Gemini's speech model (a
    # preview, hence a setting) and its voice, and the most spoken replies sent
    # in a day across everyone (each is an extra WhatsApp message).
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_tts_voice: str = "Charon"
    voice_daily_limit: int = 20
    # Where citizens follow their reports; used in the links messages carry.
    public_site_url: str = "http://localhost:3000"

    # How often the API deletes citizens' numbers whose retention has ended.
    # 0 turns it off.
    contact_purge_interval_seconds: int = 3600

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


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
