"""Shared Gemini Developer API (Google AI Studio) access.

The API key is read only from backend configuration (GEMINI_API_KEY). It is
never logged, never returned to clients, and never exposed through frontend
EXPO_PUBLIC_* variables.
"""

import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

# Free-tier, low-latency model recommended for new projects (2.5 models are
# limited to existing users). gemini-3.8-flash is also free-tier but is a
# reasoning model and too slow for the app's client timeout. Overridable via
# GEMINI_MODEL.
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class GeminiConfigurationError(RuntimeError):
    """The backend has no usable Gemini Developer API key configured."""


class GeminiProviderError(RuntimeError):
    """The Gemini request failed; intentionally carries no upstream details."""


@dataclass(frozen=True)
class GeminiResponse:
    """Minimal response surface shared by chat and report analysis."""

    text: str


def _configured_api_key() -> str:
    key = (settings.GEMINI_API_KEY or "").strip()
    if not key or key.lower().startswith("replace-with"):
        raise GeminiConfigurationError(
            "GEMINI_API_KEY is not configured on the backend."
        )
    return key


def configured_model() -> str:
    model = (settings.GEMINI_MODEL or "").strip()
    return model or DEFAULT_MODEL


def is_configured() -> bool:
    """True when a real (non-placeholder) Gemini API key is present."""
    try:
        _configured_api_key()
    except GeminiConfigurationError:
        return False
    return True


def get_client() -> genai.Client:
    """Build a Gemini Developer API client bound to the backend key."""
    return genai.Client(api_key=_configured_api_key())


def generate_text(prompt: str, *, json_mode: bool = False) -> str:
    """Generate a text completion, raising safe, typed errors on failure.

    Provider exception messages can embed request URLs or the API key, so they
    are logged by type name only and re-raised as GeminiProviderError.
    """
    try:
        client = get_client()
        config = (
            types.GenerateContentConfig(response_mime_type="application/json")
            if json_mode
            else None
        )
        response = client.models.generate_content(
            model=configured_model(),
            contents=prompt,
            config=config,
        )
    except GeminiConfigurationError:
        raise
    except Exception as exc:
        logger.error("Gemini request failed (%s).", type(exc).__name__)
        raise GeminiProviderError("Gemini request failed.") from None

    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise GeminiProviderError("Gemini returned an empty response.")
    return text


def generate_json(prompt: str) -> str:
    """Generate a completion constrained to JSON output."""
    return generate_text(prompt, json_mode=True)


class _TextModel:
    """Thin model handle exposing generate_content(prompt) -> .text.

    Keeps the chat endpoint's existing call shape (model.generate_content(...).text)
    while routing through the Gemini Developer API.
    """

    def generate_content(self, prompt: str) -> GeminiResponse:
        return GeminiResponse(text=generate_text(prompt))


def get_text_model() -> _TextModel:
    """Return a text model handle, validating configuration eagerly."""
    _configured_api_key()  # raises GeminiConfigurationError when absent
    return _TextModel()
