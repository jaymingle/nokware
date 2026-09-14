"""Gemini: chat models for Ask (answering, query expansion, planning its live figures) and the report classifier,
and the plain client for voice notes."""

import logging
from functools import lru_cache

from google import genai
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import get_settings

# google-genai logs an "automatic function calling" usage notice on every call;
# Ask's planner binds its own tools and runs them itself, so the notice is noise.
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


# Quick decisions a person waits on (filing a report, planning Ask's figures) get
# a hard limit instead of the client's default of six retries; on failure the
# caller carries on without the model's view.
CLASSIFIER_TIMEOUT_SECONDS = 15
CLASSIFIER_RETRIES = 1


@lru_cache
def get_quick_model() -> ChatGoogleGenerativeAI:
    """No thinking, temperature 0, a short timeout and one retry: the report classifier and Ask's planner."""
    return ChatGoogleGenerativeAI(
        model=CHAT_MODEL,
        temperature=0.0,
        thinking_budget=0,
        timeout=CLASSIFIER_TIMEOUT_SECONDS,
        max_retries=CLASSIFIER_RETRIES,
        google_api_key=get_settings().gemini_api_key,
    )


def get_classifier_model() -> ChatGoogleGenerativeAI:
    return get_quick_model()


@lru_cache
def get_genai_client() -> genai.Client:
    """Gemini's own client, for what LangChain doesn't wrap simply: voice notes in, speech out."""
    return genai.Client(api_key=get_settings().gemini_api_key)
