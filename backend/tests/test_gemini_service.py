"""Focused tests for the shared Gemini Developer API service.

All provider calls are mocked: no real network traffic and no real patient
data ever reach Gemini. The API key is never asserted to equal a real value.
"""

import logging

import pytest

from app.services import gemini_service
from app.services.gemini_service import (
    GeminiConfigurationError,
    GeminiProviderError,
)


class FakeResponse:
    def __init__(self, text):
        self.text = text


class FakeModels:
    def __init__(self, text=None, error=None):
        self._text = text
        self._error = error
        self.calls = []

    def generate_content(self, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._error is not None:
            raise self._error
        return FakeResponse(self._text)


class FakeClient:
    def __init__(self, text=None, error=None):
        self.models = FakeModels(text=text, error=error)
        self.api_key = None


def test_missing_api_key_raises_configuration_error(monkeypatch):
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "")

    with pytest.raises(GeminiConfigurationError):
        gemini_service.get_text_model()


def test_placeholder_api_key_is_treated_as_unconfigured(monkeypatch):
    monkeypatch.setattr(
        gemini_service.settings, "GEMINI_API_KEY", "replace-with-a-real-key"
    )

    assert gemini_service.is_configured() is False
    with pytest.raises(GeminiConfigurationError):
        gemini_service.get_text_model()


def test_configured_api_key_is_recognised(monkeypatch):
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    assert gemini_service.is_configured() is True


def test_generate_text_returns_provider_text(monkeypatch):
    fake = FakeClient(text="Synthetic Gemini reply")
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    result = gemini_service.generate_text("synthetic prompt")

    assert result == "Synthetic Gemini reply"
    assert fake.models.calls[0]["contents"] == "synthetic prompt"
    assert fake.models.calls[0]["config"] is None


def test_generate_json_requests_json_mime_type(monkeypatch):
    fake = FakeClient(text='[{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}]')
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    result = gemini_service.generate_json("synthetic prompt")

    assert "Hemoglobin" in result
    config = fake.models.calls[0]["config"]
    assert config is not None
    assert config.response_mime_type == "application/json"


def test_provider_error_is_wrapped_and_does_not_leak(monkeypatch, caplog):
    fake = FakeClient(
        error=RuntimeError("https://generativelanguage.invalid?key=synthetic-secret")
    )
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(GeminiProviderError):
            gemini_service.generate_text("synthetic prompt")

    assert "synthetic-secret" not in caplog.text
    assert "generativelanguage.invalid" not in caplog.text


def test_empty_provider_response_is_a_provider_error(monkeypatch):
    fake = FakeClient(text="   ")
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    with pytest.raises(GeminiProviderError):
        gemini_service.generate_text("synthetic prompt")


def test_configured_model_defaults_and_override(monkeypatch):
    monkeypatch.setattr(gemini_service.settings, "GEMINI_MODEL", "")
    assert gemini_service.configured_model() == gemini_service.DEFAULT_MODEL

    monkeypatch.setattr(gemini_service.settings, "GEMINI_MODEL", "synthetic-model")
    assert gemini_service.configured_model() == "synthetic-model"


def test_api_key_is_never_logged(monkeypatch, caplog):
    secret = "synthetic-secret-key-value"
    fake = FakeClient(text="ok")
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", secret)

    with caplog.at_level(logging.DEBUG):
        gemini_service.generate_text("synthetic prompt")

    assert secret not in caplog.text
