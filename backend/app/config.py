from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Service settings have no defaults, so a missing variable raises at startup rather than silently defaulting."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    appwrite_endpoint: str
    appwrite_project_id: str
    appwrite_api_key: str

    postgres_url: str

    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_ledger_bucket: str
    minio_photos_bucket: str

    gemini_api_key: str

    cors_origins: str = ""  # comma-separated
    cors_origin_regex: str = r"^http://(localhost|127\.0\.0\.1)(:\d+)?$"

    # For a scheduler's X-Job-Token. Empty means only a signed-in MCE can run the jobs.
    job_token: str = ""

    # 0 turns the built-in runner off.
    deadline_job_interval_seconds: int = 120

    # "log" records each message without sending it.
    sms_provider: str = "log"
    whatsapp_provider: str = "log"
    # In sandbox mode Arkesel accepts each message without delivering it or spending credits.
    arkesel_api_key: str = ""
    arkesel_sender_id: str = ""
    arkesel_sandbox: bool = True
    sms_daily_limit: int = 50
    arkesel_webhook_secret: str = ""
    # BMS has no sandbox: every message is live and charged. The key travels in the request address, so it is
    # redacted from logs and never stored.
    bms_api_key: str = ""
    bms_sender_id: str = ""
    # BMS has no delivery webhook, so the API polls it. 0 turns it off.
    bms_delivery_poll_seconds: int = 120
    # Arkesel doesn't sign USSD callbacks yet, so this secret in the callback address is their only protection.
    # Empty: USSD is off.
    arkesel_ussd_token: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""  # e.g. whatsapp:+14155238886 (the sandbox)
    # Empty means no callbacks are asked for.
    public_api_url: str = ""
    # Empty: channels are off and the SMS count is kept in this process.
    redis_url: str = ""
    # Gemini's speech model is a preview, hence a setting. Each spoken reply is an extra WhatsApp message.
    gemini_tts_model: str = "gemini-3.1-flash-tts-preview"
    gemini_tts_voice: str = "Charon"
    voice_daily_limit: int = 20
    # Fresh parts of speech a day across everyone; cached repeats don't count.
    read_aloud_daily_limit: int = 300
    # Empty: USSD isn't offered for confirming a phone number.
    ussd_service_code: str = ""
    public_site_url: str = "http://localhost:3000"

    # Fixed on each petition when it opens, so changing these never moves a live goal.
    petition_threshold_area: int = 150
    petition_threshold_metro: int = 500
    # Only with an approved sender ID: messages from an unregistered one are held for review for about 15 minutes,
    # and a code that arrives 15 minutes late is worse than no SMS option at all. "Nokware" is approved on BMS; keep
    # this off on Arkesel until its sender ID is registered.
    sms_verification_codes: bool = False
    # A cap of its own, so codes never use up report notifications.
    sms_code_daily_limit: int = 30
    # Empty: derived from the Appwrite API key. Set it before launch, so that rotating that key doesn't reset who has
    # already signed.
    phone_key_secret: str = ""

    # 0 turns it off.
    contact_purge_interval_seconds: int = 3600

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_error_summary(exc: ValidationError) -> str:
    """Never print str(exc) for a settings error: pydantic includes the loaded input in it, which is the secrets."""
    problems = [
        f"{str(err['loc'][0]).upper()} ({err['msg'].lower()})"
        for err in exc.errors(include_url=False, include_input=False)
    ]
    return f"Cannot load settings from {ENV_FILE}: {', '.join(problems)}"
