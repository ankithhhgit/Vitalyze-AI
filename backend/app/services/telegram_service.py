"""Telegram Bot API delivery for Vitalyze medicine reminders.

This mirrors the safety properties of :mod:`app.services.whatsapp_service`:

* the bot token is read only from backend configuration and is never exposed to
  the frontend or written to logs;
* sending is gated behind an explicit opt-in flag (``TELEGRAM_SEND_ENABLED``)
  so nothing is sent during development or tests by accident;
* transient network failures are retried a small, fixed number of times while
  provider-level rejections are terminal;
* no token, chat id, or message text is ever logged.
"""

import logging
import os
import re
import time
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10
# Bounded retry handling: only transient network failures are retried.
MAX_SEND_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5

# Placeholder values used by the example environment file and tests are never
# treated as real configuration.
_PLACEHOLDER_PREFIXES = ("replace-with-", "test-only-placeholder")
# Telegram chat ids are integers and may be negative for group chats.
_CHAT_ID_PATTERN = re.compile(r"^-?\d{1,20}$")
# Telegram /start payloads allow [A-Za-z0-9_-] and are limited to 64 chars.
_LINK_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
# Bot tokens look like "<numeric id>:<rest>"; validate the shape only.
_TOKEN_PATTERN = re.compile(r"^\d{6,}:[A-Za-z0-9_-]{20,}$")
# A private-chat command: "/start <code>", "/link <code>", optionally with an
# "@botusername" suffix that Telegram adds inside group chats.
_COMMAND_PATTERN = re.compile(
    r"^/(?:start|link)(?:@[A-Za-z0-9_]+)?(?:\s+(?P<code>[A-Za-z0-9_-]{6,64}))?\s*$"
)


def send_enabled() -> bool:
    """Return True only when Telegram sending has been explicitly enabled."""
    return os.getenv("TELEGRAM_SEND_ENABLED", "false").strip().lower() == "true"


def _has_credentials() -> bool:
    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    if not token or token.startswith(_PLACEHOLDER_PREFIXES):
        return False
    return bool(_TOKEN_PATTERN.fullmatch(token))


def is_configured() -> bool:
    """Return True only when sending is enabled and a usable token is present."""
    return send_enabled() and _has_credentials()


def is_valid_chat_id(chat_id: object) -> bool:
    """Return True for a syntactically valid Telegram chat id."""
    return bool(chat_id) and bool(_CHAT_ID_PATTERN.fullmatch(str(chat_id).strip()))


def parse_link_command(text: Optional[str]) -> Optional[str]:
    """Return the one-time code from ``/start <code>`` or ``/link <code>``.

    Returns ``None`` when the text is not a linking command or carries no code.
    """
    if not text or not isinstance(text, str):
        return None
    match = _COMMAND_PATTERN.match(text.strip())
    if not match:
        return None
    code = match.group("code")
    return code if code and _LINK_CODE_PATTERN.fullmatch(code) else None


def bot_deep_link(code: str) -> Optional[str]:
    """Return a t.me deep link that starts the bot with ``code``, if possible."""
    username = (settings.TELEGRAM_BOT_USERNAME or "").strip().lstrip("@")
    if not username or not _LINK_CODE_PATTERN.fullmatch(code or ""):
        return None
    return f"https://t.me/{username}?start={code}"


def _extract_message_id(response) -> Optional[str]:
    """Return the provider message id, "" when accepted without one, or None.

    ``None`` means the provider responded but did not accept the message, so
    the caller must not treat it as delivered.
    """
    try:
        body = response.json()
    except (ValueError, TypeError):
        return None
    if not isinstance(body, dict) or body.get("ok") is not True:
        return None
    result = body.get("result")
    if not isinstance(result, dict):
        return ""
    message_id = result.get("message_id")
    return str(message_id) if isinstance(message_id, int) else ""


def send_message(chat_id: object, text: str) -> Optional[str]:
    """Send a plain-text Telegram message.

    Returns the provider message id on success (or an empty string when the
    provider accepted the message without returning an id), and ``None`` when
    nothing was sent. Callers must never treat ``None``/falsy as delivered.
    """
    if not is_valid_chat_id(chat_id):
        logger.warning("Telegram message skipped: chat id is not valid.")
        return None
    if not text or not str(text).strip():
        return None
    if not is_configured():
        logger.info("Telegram message is pending configuration; no message was sent.")
        return None

    api_url = f"{TELEGRAM_API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": str(chat_id),
        "text": text,
        # Never preview links and never trust message text as markup.
        "disable_web_page_preview": True,
    }

    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        try:
            response = requests.post(
                api_url,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            message_id = _extract_message_id(response)
            if message_id is None:
                logger.error("Telegram sendMessage rejected by provider.")
                return None
            logger.info("Telegram message accepted by provider.")
            return message_id
        except requests.exceptions.HTTPError as exc:
            # The provider answered; treat any HTTP error as terminal.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.error(
                "Telegram sendMessage failed (%s, status=%s).",
                type(exc).__name__,
                status_code,
            )
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            logger.error(
                "Telegram sendMessage failed (%s, attempt %s/%s).",
                type(exc).__name__,
                attempt,
                MAX_SEND_ATTEMPTS,
            )
            if attempt >= MAX_SEND_ATTEMPTS:
                return None
            time.sleep(RETRY_BACKOFF_SECONDS)
        except requests.exceptions.RequestException as exc:
            logger.error("Telegram sendMessage failed (%s).", type(exc).__name__)
            return None
    return None
