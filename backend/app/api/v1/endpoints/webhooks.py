# backend/app/api/v1/endpoints/webhooks.py

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.crud import crud_telegram
from app.db.mongodb import get_database
from app.services import telegram_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Map provider delivery states to the statuses we persist. A message the
# provider accepted is "sent"; "delivered"/"read" are genuine delivery
# confirmations; anything else the provider reports as failed is terminal.
_PROVIDER_STATUS_MAP = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "delivered",
    "failed": "failed",
}


def _signature_is_valid(raw_body: bytes, signature_header: Optional[str]) -> bool:
    """Verify the Meta ``X-Hub-Signature-256`` header when a secret is set.

    When ``WHATSAPP_APP_SECRET`` is not configured, signature verification is
    skipped (documented prerequisite) rather than rejecting every callback.
    """
    secret = getattr(settings, "WHATSAPP_APP_SECRET", "") or ""
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


async def _apply_delivery_statuses(db: AsyncIOMotorDatabase, payload: dict) -> int:
    """Update delivery records from provider status callbacks; return updates."""
    updated = 0
    deliveries = db["reminder_deliveries"]
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            for status in value.get("statuses", []) or []:
                message_id = status.get("id")
                provider_status = str(status.get("status", "")).lower()
                mapped = _PROVIDER_STATUS_MAP.get(provider_status)
                if not message_id or not mapped:
                    continue
                result = await deliveries.update_one(
                    {"provider_message_id": message_id},
                    {
                        "$set": {
                            "status": mapped,
                            "provider_status": provider_status,
                            "delivery_updated_at": datetime.now(timezone.utc),
                        }
                    },
                )
                updated += result.modified_count
    return updated


@router.get("/whatsapp")
def verify_webhook(
    request: Request,
    mode: str = Query(..., alias="hub.mode"),
    challenge: int = Query(..., alias="hub.challenge"),
    token: str = Query(..., alias="hub.verify_token"),
):
    if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
        return challenge
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/whatsapp")
async def receive_webhook(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Record provider delivery-status callbacks for known message ids.

    The handler never logs recipients, message content, or credentials. Unknown
    message ids are ignored. A configured app secret enables signature checks.
    """
    raw_body = await request.body()
    if not _signature_is_valid(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except (ValueError, TypeError):
        return {"status": "ok"}

    if isinstance(payload, dict):
        updated = await _apply_delivery_statuses(db, payload)
        if updated:
            logger.info("WhatsApp webhook updated %s delivery record(s).", updated)
    logger.info("Received WhatsApp webhook notification.")
    return {"status": "ok"}


def _telegram_secret_is_valid(provided: Optional[str]) -> bool:
    """Verify Telegram's secret header when one is configured.

    When ``TELEGRAM_WEBHOOK_SECRET`` is blank, authentication is skipped
    (documented local-development prerequisite) rather than rejecting every
    update. A blank secret therefore also disables inbound linking.
    """
    expected = getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or ""
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(str(expected), str(provided))


@router.post("/telegram")
async def receive_telegram_update(
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Bind a Telegram chat after the account owner redeems a one-time code.

    The chat id is read from the update Telegram delivered, never from a
    client-supplied value, so possession of the code sent from that chat is
    what proves ownership. A code can be redeemed once and expires. Unknown or
    stale codes are acknowledged with 200 so Telegram does not retry. No chat
    id, code, or message text is ever logged.
    """
    if not _telegram_secret_is_valid(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    ):
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body) if raw_body else {}
    except (ValueError, TypeError):
        return {"status": "ok"}

    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return {"status": "ok"}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    # Only a private chat with the bot may be bound to an account; a group
    # chat could expose reminders to other members.
    if chat.get("type") != "private" or not telegram_service.is_valid_chat_id(chat_id):
        return {"status": "ok"}

    code = telegram_service.parse_link_command(message.get("text"))
    if not code:
        return {"status": "ok"}

    record = await crud_telegram.consume_link_code(db, code)
    if not record:
        logger.info("Telegram link rejected an expired, used, or unknown code.")
        return {"status": "ok"}

    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    username = str(sender.get("username") or "").lstrip("@")[:32] or None
    try:
        linked = await crud_telegram.link_user_chat(
            db, record["user_id"], chat_id, username=username
        )
    except Exception as exc:
        logger.error("Telegram link could not be persisted (%s).", type(exc).__name__)
        return {"status": "ok"}

    if linked:
        logger.info("Telegram chat linked for a Vitalyze account.")
        # Best-effort confirmation; sending stays disabled unless configured.
        telegram_service.send_message(
            chat_id,
            "Your Telegram chat is linked to Vitalyze. Reminders you enable "
            "for Telegram will be delivered to this chat.",
        )
    return {"status": "ok"}
