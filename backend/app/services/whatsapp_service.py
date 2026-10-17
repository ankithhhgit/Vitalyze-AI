
import requests
import logging
import re
import os
import time
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 10
# Bounded retry handling: transient network failures are retried a small,
# fixed number of times. Permanent provider responses are not retried.
MAX_SEND_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.5
# Placeholder values used by the example environment file and tests are never
# treated as real configuration.
_PLACEHOLDER_PREFIXES = ("replace-with-", "test-only-placeholder")
_E164_PATTERN = re.compile(r"^\+[1-9]\d{1,14}$")


def is_e164_phone_number(phone_number: Optional[str]) -> bool:
    """Return True only for a syntactically valid E.164 recipient number."""
    return bool(phone_number) and bool(_E164_PATTERN.fullmatch(phone_number.strip()))


def approved_template_names() -> set:
    """Return the set of template names Meta has approved for this deployment."""
    return {
        name.strip()
        for name in (
            settings.WHATSAPP_APPROVED_TEMPLATE_NAME,
            settings.WHATSAPP_MEDICATION_TEMPLATE_NAME,
            settings.WHATSAPP_REFILL_TEMPLATE_NAME,
        )
        if name and name.strip()
    }


def _has_credentials() -> bool:
    version = settings.WHATSAPP_API_VERSION or ""
    token = settings.WHATSAPP_ACCESS_TOKEN or ""
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID or ""
    return bool(
        re.fullmatch(r"v\d+\.\d+", version)
        and token
        and not token.startswith(_PLACEHOLDER_PREFIXES)
        and phone_number_id
        and not phone_number_id.startswith(_PLACEHOLDER_PREFIXES)
    )


def is_configured(template_name: str | None = None) -> bool:
    """Return True only when sending is enabled and the required config exists.

    When ``template_name`` is provided it must be one of the approved template
    names. When omitted, this only reports whether *any* template can be sent.
    """
    if os.getenv("WHATSAPP_SEND_ENABLED", "false").strip().lower() != "true":
        return False
    if not _has_credentials():
        return False
    approved = approved_template_names()
    if not approved:
        return False
    if template_name is None:
        return True
    return template_name in approved


def _extract_message_id(response) -> str:
    """Read the provider message id without ever logging the response body."""
    try:
        body = response.json()
    except (ValueError, TypeError):
        return ""
    if not isinstance(body, dict):
        return ""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return ""
    first = messages[0]
    if isinstance(first, dict) and isinstance(first.get("id"), str):
        return first["id"]
    return ""


def send_template_message(
    phone_number: str, 
    template_name: str, 
    template_params: list,
    *,
    user_opted_in: bool = False,
    phone_verified: bool = False,
) -> Optional[str]:
    """
    Sends a pre-approved template message using the WhatsApp Cloud API.

    Returns the provider message id on success (or an empty string when the
    provider accepted the message without returning an id), and ``None`` when
    nothing was sent. The caller must never treat ``None``/falsy as delivered.
    """
    # The recipient is always the authenticated user's own stored number. Reject
    # anything that is not a valid E.164 value before any configuration check.
    if not is_e164_phone_number(phone_number):
        logger.warning("WhatsApp reminder skipped: recipient is not a valid E.164 number.")
        return None

    if not user_opted_in or not phone_verified or not is_configured(template_name):
        logger.info("WhatsApp reminder is pending configuration; no message was sent.")
        return None

    api_url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # 1. Basic Payload (Always required)
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": settings.WHATSAPP_TEMPLATE_LANGUAGE},
        },
    }

    if template_params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": param} for param in template_params
                ],
            }
        ]

    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        try:
            response = requests.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            message_id = _extract_message_id(response)
            logger.info("WhatsApp template message accepted by provider.")
            return message_id
        except requests.exceptions.HTTPError as exc:
            # The provider answered. Permanent (4xx) errors and any other HTTP
            # error are treated as terminal to avoid endless retries.
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            logger.error(
                "WhatsApp template message rejected (%s, status=%s).",
                type(exc).__name__,
                status_code,
            )
            return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            logger.error(
                "WhatsApp template message failed (%s, attempt %s/%s).",
                type(exc).__name__,
                attempt,
                MAX_SEND_ATTEMPTS,
            )
            if attempt >= MAX_SEND_ATTEMPTS:
                return None
            time.sleep(RETRY_BACKOFF_SECONDS)
        except requests.exceptions.RequestException as exc:
            logger.error("WhatsApp template message failed (%s).", type(exc).__name__)
            return None
    return None
