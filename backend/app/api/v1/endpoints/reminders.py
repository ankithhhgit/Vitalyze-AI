from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging
import os
import re
from bson import ObjectId

from app.db.mongodb import get_database
from app.crud import crud_reminder, crud_telegram  # we don't need crud_user anymore!
from app.models.user import DailyReminder, RefillReminder, UserInDB
from app.tasks.reminder_tasks import send_refill_reminder_task
from app.services import whatsapp_service, telegram_service

# --- NEW IMPORT: Get the user from the token ---
# (Make sure this path is correct for your project)
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def list_my_reminders(current_user: UserInDB = Depends(get_current_user)):
    """List reminder records attached to the authenticated user's own profile."""
    return {
        "daily_reminders": [item.model_dump(by_alias=True) for item in current_user.daily_reminders],
        "refill_reminders": [item.model_dump(by_alias=True) for item in current_user.refill_reminders],
    }

class DailyReminderCreate(BaseModel):
    medicine_name: str
    timings: List[Literal["morning", "afternoon", "evening"]] = Field(default_factory=list)
    times: Optional[List[str]] = None
    timezone: str = "Asia/Kolkata"
    local_notifications_enabled: bool = True
    whatsapp_opt_in: bool = False
    telegram_opt_in: bool = False

    @field_validator("medicine_name")
    @classmethod
    def medicine_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medicine_name must not be blank")
        return value.strip()

    @field_validator("times")
    @classmethod
    def validate_times(cls, value):
        if value is not None and (
            len(value) != len(set(value))
            or any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in value)
        ):
            raise ValueError("times must be unique 24-hour HH:MM values")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value


class DailyReminderUpdate(BaseModel):
    times: List[str]
    timezone: str = "Asia/Kolkata"
    local_notifications_enabled: bool = True
    whatsapp_opt_in: bool = False
    telegram_opt_in: bool = False
    is_active: bool = True

    @field_validator("times")
    @classmethod
    def validate_times(cls, value):
        if len(value) != len(set(value)) or any(
            not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in value
        ):
            raise ValueError("times must be unique 24-hour HH:MM values")
        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be a valid IANA timezone") from None
        return value

class RefillReminderCreate(BaseModel):
    medicine_name: str
    initial_quantity: int = Field(..., gt=0)
    frequency_per_day: int = Field(..., gt=0)
    whatsapp_opt_in: bool = False
    local_notifications_enabled: bool = True

    @field_validator("medicine_name")
    @classmethod
    def medicine_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medicine_name must not be blank")
        return value.strip()


class RefillReminderUpdate(BaseModel):
    local_notifications_enabled: bool = True
    whatsapp_opt_in: bool = False
    is_active: bool = True

TIMING_TO_TIME = {
    "morning": "10:00",
    "afternoon": "14:00",
    "evening": "21:00",
}

# --- 1. REMOVED {user_id} FROM URL ---
@router.post("/daily", status_code=201)
async def schedule_daily_reminder(
    reminder_in: DailyReminderCreate,
    # --- 2. ADDED CURRENT_USER DEPENDENCY ---
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Sets up a recurring daily reminder for the logged-in user.
    """
    # We no longer need to look up the user manually. 
    # 'current_user' is already loaded from the token!

    # Get the ID from the logged-in user
    user_id = str(current_user.id)
    selected_times = reminder_in.times
    if selected_times is None:
        selected_times = (
            [TIMING_TO_TIME[timing] for timing in reminder_in.timings]
            if reminder_in.timings else ["10:00", "14:00", "21:00"]
        )
    if not selected_times:
        raise HTTPException(status_code=422, detail="Select at least one daily reminder time.")
    duplicate = any(
        item.is_active
        and item.medicine_name.casefold() == reminder_in.medicine_name.casefold()
        and set(item.times or [TIMING_TO_TIME[timing] for timing in item.timings]) == set(selected_times)
        and item.timezone == reminder_in.timezone
        for item in current_user.daily_reminders
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="This daily reminder is already saved.")

    reminder_db = DailyReminder(
        **reminder_in.model_dump(exclude={"times"}),
        times=selected_times,
        whatsapp_opt_in_at=datetime.now(timezone.utc) if reminder_in.whatsapp_opt_in else None,
        telegram_opt_in_at=datetime.now(timezone.utc) if reminder_in.telegram_opt_in else None,
    )
    
    # Save using the ID we got from the token
    await crud_reminder.add_daily_reminder_to_user(db, user_id=user_id, reminder=reminder_db)
    
    return {
        "message": "Daily reminder preferences saved.",
        "delivery_status": "saved; WhatsApp delivery has not been confirmed",
        "reminder": reminder_db.model_dump(by_alias=True),
    }


# --- 1. REMOVED {user_id} FROM URL ---
@router.post("/refill", status_code=201)
async def schedule_refill_reminder(
    reminder_in: RefillReminderCreate,
    # --- 2. ADDED CURRENT_USER DEPENDENCY ---
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Schedules a one-time refill reminder for the logged-in user.
    """
    # Get the ID from the logged-in user
    user_id = str(current_user.id)
    duplicate = any(
        item.is_active and item.medicine_name.casefold() == reminder_in.medicine_name.casefold()
        for item in current_user.refill_reminders
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="An active refill reminder already exists for this medicine.")

    days_of_supply = reminder_in.initial_quantity / reminder_in.frequency_per_day
    reminder_delay_days = max(0, days_of_supply - 3)
    refill_date = datetime.now(timezone.utc) + timedelta(days=reminder_delay_days)

    task = send_refill_reminder_task.apply_async(
        args=[
            current_user.name,
            current_user.phone_number,
            reminder_in.medicine_name,
            reminder_in.whatsapp_opt_in,
            bool(getattr(current_user, "phone_verified", False)),
        ],
        eta=refill_date
    )

    reminder_db = RefillReminder(
        **reminder_in.model_dump(),
        refill_date=refill_date,
        celery_task_id=task.id,
        whatsapp_opt_in_at=datetime.now(timezone.utc) if reminder_in.whatsapp_opt_in else None,
    )
    
    await crud_reminder.add_refill_reminder_to_user(db, user_id=user_id, reminder=reminder_db)

    return {
        "message": "Refill reminder scheduled successfully",
        "refill_date": refill_date.isoformat(),
        "celery_task_id": task.id
    }


@router.get("/status")
async def reminder_delivery_status(current_user: UserInDB = Depends(get_current_user)):
    """Report WhatsApp readiness without revealing secrets or implying delivery."""
    enabled = os.getenv("WHATSAPP_SEND_ENABLED", "false").strip().lower() == "true"
    medication_ready = whatsapp_service.is_configured("medication_reminder_v3")
    refill_ready = whatsapp_service.is_configured("refill_reminder_v1")
    provider_ready = medication_ready or refill_ready
    verified = bool(getattr(current_user, "phone_verified", False))
    telegram_ready = telegram_service.is_configured()
    telegram_linked = bool(getattr(current_user, "telegram_chat_id", None))
    return {
        "whatsapp_enabled": enabled,
        "provider_ready": provider_ready,
        "medication_template_configured": medication_ready,
        "refill_template_configured": refill_ready,
        "phone_verified": verified,
        "telegram_enabled": telegram_service.send_enabled(),
        "telegram_provider_ready": telegram_ready,
        "telegram_linked": telegram_linked,
        "status": "ready" if enabled and provider_ready and verified else "not_configured",
        "message": "WhatsApp delivery is disabled or missing verified configuration. Saved reminders are not sent.",
        "telegram_message": (
            "Telegram delivery is ready for this account."
            if telegram_ready and telegram_linked
            else "Telegram delivery is not configured or this account has no linked chat."
        ),
    }


@router.patch("/daily/{reminder_id}")
async def update_daily_reminder(
    reminder_id: str,
    update: DailyReminderUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not ObjectId.is_valid(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder = next((item for item in current_user.daily_reminders if str(item.id) == reminder_id), None)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    values = update.model_dump()
    values["whatsapp_opt_in_at"] = datetime.now(timezone.utc) if update.whatsapp_opt_in else None
    values["telegram_opt_in_at"] = datetime.now(timezone.utc) if update.telegram_opt_in else None
    values["updated_at"] = datetime.now(timezone.utc)
    result = await db["users"].update_one(
        {"_id": current_user.id, "daily_reminders._id": ObjectId(reminder_id)},
        {"$set": {f"daily_reminders.$.{key}": value for key, value in values.items()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"message": "Reminder preferences updated.", "delivery_status": "not sent"}


@router.delete("/daily/{reminder_id}", status_code=204)
async def delete_daily_reminder(
    reminder_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not ObjectId.is_valid(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    result = await db["users"].update_one(
        {"_id": current_user.id, "daily_reminders._id": ObjectId(reminder_id)},
        {"$pull": {"daily_reminders": {"_id": ObjectId(reminder_id)}}},
    )
    if not result.modified_count:
        raise HTTPException(status_code=404, detail="Reminder not found")


@router.patch("/refill/{reminder_id}")
async def update_refill_reminder(
    reminder_id: str,
    update: RefillReminderUpdate,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not ObjectId.is_valid(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder = next((item for item in current_user.refill_reminders if str(item.id) == reminder_id), None)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    values = update.model_dump()
    values["whatsapp_opt_in_at"] = datetime.now(timezone.utc) if update.whatsapp_opt_in else None
    result = await db["users"].update_one(
        {"_id": current_user.id, "refill_reminders._id": ObjectId(reminder_id)},
        {"$set": {f"refill_reminders.$.{key}": value for key, value in values.items()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if not update.is_active:
        send_refill_reminder_task.app.control.revoke(reminder.celery_task_id, terminate=False)
    return {"message": "Refill reminder preferences updated.", "delivery_status": "not sent"}


@router.delete("/refill/{reminder_id}", status_code=204)
async def delete_refill_reminder(
    reminder_id: str,
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    if not ObjectId.is_valid(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder = next((item for item in current_user.refill_reminders if str(item.id) == reminder_id), None)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    result = await db["users"].update_one(
        {"_id": current_user.id, "refill_reminders._id": ObjectId(reminder_id)},
        {"$pull": {"refill_reminders": {"_id": ObjectId(reminder_id)}}},
    )
    if not result.modified_count:
        raise HTTPException(status_code=404, detail="Reminder not found")
    send_refill_reminder_task.app.control.revoke(reminder.celery_task_id, terminate=False)


@router.post("/telegram/link-code", status_code=201)
async def create_telegram_link_code(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Issue a short-lived, single-use code that links a Telegram chat.

    The chat id is never accepted here. The user must send this code to the
    bot from their own Telegram chat; the id is taken only from the inbound
    webhook that carries the redeemed code, which proves ownership.
    """
    try:
        document = await crud_telegram.create_link_code(db, current_user.id)
    except Exception as exc:
        logger.error("Telegram link code creation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Linking is temporarily unavailable. Please try again.",
        )

    code = document["code"]
    return {
        "code": code,
        "expires_at": document["expires_at"].isoformat(),
        "ttl_seconds": int(
            (document["expires_at"] - document["created_at"]).total_seconds()
        ),
        "deep_link": telegram_service.bot_deep_link(code),
        "instructions": (
            "Open your chat with this Vitalyze bot and send /start "
            f"{code} before the code expires. Anyone else who sees the code "
            "could link their own chat to your account, so keep it private."
        ),
        "send_enabled": telegram_service.send_enabled(),
        "provider_ready": telegram_service.is_configured(),
    }


@router.get("/telegram/status")
async def telegram_link_status(current_user: UserInDB = Depends(get_current_user)):
    """Report whether this account has a linked Telegram chat. Never leaks the id."""
    linked_at = getattr(current_user, "telegram_linked_at", None)
    linked = bool(getattr(current_user, "telegram_chat_id", None))
    ready = linked and telegram_service.is_configured()
    return {
        "telegram_linked": linked,
        "telegram_linked_at": linked_at.isoformat() if linked_at else None,
        "send_enabled": telegram_service.send_enabled(),
        "provider_ready": telegram_service.is_configured(),
        "status": "ready" if ready else "not_ready",
        "message": (
            "Telegram reminders will be delivered to your linked chat."
            if ready
            else "Link a Telegram chat and configure the bot to enable Telegram delivery."
        ),
    }


@router.delete("/telegram/link")
async def unlink_telegram_chat(
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """Remove the Telegram chat binding from the authenticated user's account."""
    try:
        await crud_telegram.unlink_user_chat(db, current_user.id)
    except Exception as exc:
        logger.error("Telegram unlink failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="Could not update your Telegram link. Please try again.",
        )
    return {"telegram_linked": False, "message": "Telegram chat unlinked."}
