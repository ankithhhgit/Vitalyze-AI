"""Tests for the Telegram Bot API sender.

Every network call is mocked: no Telegram request is ever made from tests.
"""

import logging
from unittest.mock import Mock

import pytest
import requests

from app.services import telegram_service

# A syntactically valid synthetic token, never a real credential.
SYNTHETIC_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


def _configure(monkeypatch, token=SYNTHETIC_TOKEN):
    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "true")
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", token)


def _ok_response(message_id=42):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True, "result": {"message_id": message_id}}
    return response


def test_is_configured_requires_explicit_enable_and_usable_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_SEND_ENABLED", raising=False)
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", SYNTHETIC_TOKEN)
    # Even with a token, sending stays off until explicitly enabled.
    assert telegram_service.is_configured() is False

    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "true")
    assert telegram_service.is_configured() is True

    for unusable in ("", "replace-with-telegram-bot-token", "test-only-placeholder-token", "not-a-token"):
        monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_TOKEN", unusable)
        assert telegram_service.is_configured() is False


def test_send_message_skips_provider_when_not_configured(monkeypatch, caplog):
    monkeypatch.delenv("TELEGRAM_SEND_ENABLED", raising=False)
    post = Mock()
    monkeypatch.setattr(telegram_service.requests, "post", post)

    with caplog.at_level(logging.INFO):
        assert telegram_service.send_message("777000111", "Synthetic reminder") is None

    post.assert_not_called()
    assert "no message was sent" in caplog.text


@pytest.mark.parametrize(
    "chat_id",
    [None, "", "abc", "+15551234567", "12.5", "123456789012345678901", ["1"]],
)
def test_invalid_chat_id_is_rejected_before_any_network_call(monkeypatch, chat_id):
    _configure(monkeypatch)
    post = Mock()
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message(chat_id, "Synthetic reminder") is None
    post.assert_not_called()


@pytest.mark.parametrize("text", [None, "", "   ", "\n"])
def test_blank_message_text_is_skipped_without_network(monkeypatch, text):
    _configure(monkeypatch)
    post = Mock()
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", text) is None
    post.assert_not_called()


def test_send_message_payload_and_logs_exclude_secrets(monkeypatch, caplog):
    _configure(monkeypatch)
    monkeypatch.setattr(telegram_service, "RETRY_BACKOFF_SECONDS", 0.0)
    post = Mock(return_value=_ok_response(4242))
    monkeypatch.setattr(telegram_service.requests, "post", post)

    with caplog.at_level(logging.INFO):
        result = telegram_service.send_message(
            "777000111", "Synthetic medicine reminder"
        )

    assert result == "4242"
    kwargs = post.call_args.kwargs
    assert kwargs["json"]["chat_id"] == "777000111"
    assert kwargs["json"]["text"] == "Synthetic medicine reminder"
    assert kwargs["json"]["disable_web_page_preview"] is True
    assert kwargs["timeout"] == telegram_service.REQUEST_TIMEOUT_SECONDS
    assert post.call_args.args[0].endswith("/sendMessage")
    # The token is used to build the URL but must never reach the logs.
    assert SYNTHETIC_TOKEN not in caplog.text
    assert "777000111" not in caplog.text
    assert "Synthetic medicine reminder" not in caplog.text


def test_transient_timeouts_are_retried_bounded_then_succeed(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(telegram_service, "RETRY_BACKOFF_SECONDS", 0.0)
    post = Mock(
        side_effect=[
            requests.exceptions.Timeout(),
            requests.exceptions.Timeout(),
            _ok_response(7),
        ]
    )
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", "Synthetic reminder") == "7"
    assert post.call_count == telegram_service.MAX_SEND_ATTEMPTS


def test_transient_failure_stops_after_bounded_attempts(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(telegram_service, "RETRY_BACKOFF_SECONDS", 0.0)
    post = Mock(side_effect=requests.exceptions.ConnectionError())
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", "Synthetic reminder") is None
    assert post.call_count == telegram_service.MAX_SEND_ATTEMPTS


def test_permanent_http_error_is_not_retried(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(telegram_service, "RETRY_BACKOFF_SECONDS", 0.0)
    response = Mock()
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=Mock(status_code=400)
    )
    post = Mock(return_value=response)
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", "Synthetic reminder") is None
    assert post.call_count == 1


def test_api_level_error_is_never_treated_as_delivered(monkeypatch):
    """Telegram can report failure inside a 200 body; that is still a failure."""
    _configure(monkeypatch)
    monkeypatch.setattr(telegram_service, "RETRY_BACKOFF_SECONDS", 0.0)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": False, "error_code": 400, "description": "synthetic"}
    post = Mock(return_value=response)
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", "Synthetic reminder") is None
    assert post.call_count == 1


def test_accepted_without_message_id_returns_empty_receipt(monkeypatch):
    _configure(monkeypatch)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"ok": True, "result": True}
    post = Mock(return_value=response)
    monkeypatch.setattr(telegram_service.requests, "post", post)

    assert telegram_service.send_message("777000111", "Synthetic reminder") == ""


@pytest.mark.parametrize(
    ("chat_id", "valid"),
    [
        ("777000111", True),
        (777000111, True),
        (0, False),
        ("-1001234567", True),
        (None, False),
        ("", False),
        ("abc", False),
        ("+15551234567", False),
        ("12.5", False),
        ("123456789012345678901", False),
    ],
)
def test_is_valid_chat_id(chat_id, valid):
    assert telegram_service.is_valid_chat_id(chat_id) is valid


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/start AbCdEf123456", "AbCdEf123456"),
        ("/link AbCdEf123456", "AbCdEf123456"),
        ("/start@VitalyzeBot AbCdEf123456", "AbCdEf123456"),
        ("  /start AbCdEf123456\n", "AbCdEf123456"),
        ("/start", None),
        ("/start@VitalyzeBot", None),
        ("/help AbCdEf123456", None),
        ("/start short", None),
        ("/start badcode!", None),
        ("/start two words", None),
        ("/start " + "A" * 65, None),
        ("", None),
        (None, None),
        ("just some text", None),
    ],
)
def test_parse_link_command(text, expected):
    assert telegram_service.parse_link_command(text) == expected


def test_bot_deep_link_requires_username_and_valid_code(monkeypatch):
    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_USERNAME", "@VitalyzeBot")
    assert (
        telegram_service.bot_deep_link("AbCdEf123456")
        == "https://t.me/VitalyzeBot?start=AbCdEf123456"
    )
    assert telegram_service.bot_deep_link("bad code") is None

    monkeypatch.setattr(telegram_service.settings, "TELEGRAM_BOT_USERNAME", "")
    assert telegram_service.bot_deep_link("AbCdEf123456") is None
