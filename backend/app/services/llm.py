"""Gemini chat models: Ask (answering and query expansion) and the report classifier."""

import logging
from functools import lru_cache

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import get_settings

# google-genai logs an "automatic function calling" usage notice on every call;
# we use no function calling, so it is pure noise in server and script logs.
logging.getLogger("google_genai.models").setLevel(logging.ERROR)

# Must honour temperature: low temperature keeps answers grounded in the
# retrieved chunks, so fixed-sampling models (e.g. gemini-3.6-flash) are out.
CHAT_MODEL = "gemini-2.5-flash"


@lru_cache
def get_chat_model(temperature: float, thinking_budget: int | None = None) -> ChatGoogleGenerativeAI:
    """Cached per (temperature, thinking_budget). thinking_budget=0 disables thinking."""
    return ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        temperature=temperature,
        thinking_budget=thinking_budget,
        google_api_key=get_settings().gemini_api_key,
    )


# Filing a report waits on the classifier, so it gets a hard limit instead of
# the client's default of six retries; on failure the filing rules take over.
CLASSIFIER_TIMEOUT_SECONDS = 15
CLASSIFIER_RETRIES = 1


@lru_cache
def get_classifier_model() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        temperature=0.0,
        thinking_budget=0,
        timeout=CLASSIFIER_TIMEOUT_SECONDS,
        max_retries=CLASSIFIER_RETRIES,
        google_api_key=get_settings().gemini_api_key,
    )
