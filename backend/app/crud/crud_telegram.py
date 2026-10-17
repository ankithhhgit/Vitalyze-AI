"""Persistence helpers for Telegram account linking.

Linking a Telegram chat to a Vitalyze account is a two-step, user-initiated
flow:

1. an authenticated user requests a short-lived, single-use code through the
   API (see ``app/api/v1/endpoints/reminders.py``);
2. the user sends that code to the bot (``/start <code>``), and the inbound
   Telegram webhook binds the chat id that Telegram reports.

The chat id is never accepted from the client, only from Telegram itself, and
the code is consumed atomically so it can be redeemed exactly once.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings

DEFAULT_LINK_CODE_TTL_SECONDS = 900
LINK_CODES_COLLECTION = "telegram_link_codes"


def generate_link_code() -> str:
    """Return a high-entropy, URL-safe, single-use linking code."""
    return secrets.token_urlsafe(24)


def _as_object_id(user_id) -> ObjectId:
    return user_id if isinstance(user_id, ObjectId) else ObjectId(str(user_id))


async def create_link_code(
    db: AsyncIOMotorDatabase,
    user_id,
    ttl_seconds: Optional[int] = None,
) -> dict:
    """Create a new linking code, revoking any earlier unused code for the user."""
    now = datetime.now(timezone.utc)
    ttl = ttl_seconds
    if ttl is None:
        ttl = getattr(
            settings, "TELEGRAM_LINK_CODE_TTL_SECONDS", DEFAULT_LINK_CODE_TTL_SECONDS
        )
    codes = db[LINK_CODES_COLLECTION]
    try:
        # Best-effort uniqueness guard; the atomic consume below is the real
        # single-use protection.
        await codes.create_index("code", unique=True)
    except Exception:  # pragma: no cover - index creation is optional
        pass
    await codes.update_many(
        {"user_id": str(user_id), "used_at": None, "revoked_at": None},
        {"$set": {"revoked_at": now}},
    )
    document = {
        "code": generate_link_code(),
        "user_id": str(user_id),
        "created_at": now,
        "expires_at": now + timedelta(seconds=ttl),
        "used_at": None,
        "revoked_at": None,
    }
    await codes.insert_one(document)
    return document


async def consume_link_code(
    db: AsyncIOMotorDatabase,
    code: str,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Atomically redeem an unused, unexpired code and return its document.

    Returns ``None`` when the code is unknown, already used, revoked, or
    expired. Concurrent redemptions of the same code can only succeed once.
    """
    now = now or datetime.now(timezone.utc)
    return await db[LINK_CODES_COLLECTION].find_one_and_update(
        {
            "code": code,
            "used_at": None,
            "revoked_at": None,
            "expires_at": {"$gt": now},
        },
        {"$set": {"used_at": now}},
    )


async def link_user_chat(
    db: AsyncIOMotorDatabase,
    user_id,
    chat_id: str,
    *,
    username: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Bind the verified Telegram chat id to the user's profile."""
    now = now or datetime.now(timezone.utc)
    update = {"telegram_chat_id": str(chat_id), "telegram_linked_at": now}
    if username:
        update["telegram_username"] = username
    result = await db["users"].update_one(
        {"_id": _as_object_id(user_id)}, {"$set": update}
    )
    return bool(getattr(result, "matched_count", 0))


async def unlink_user_chat(db: AsyncIOMotorDatabase, user_id) -> bool:
    """Remove any Telegram chat binding from the user's profile."""
    result = await db["users"].update_one(
        {"_id": _as_object_id(user_id)},
        {"$unset": {"telegram_chat_id": "", "telegram_linked_at": "", "telegram_username": ""}},
    )
    return bool(getattr(result, "matched_count", 0))
