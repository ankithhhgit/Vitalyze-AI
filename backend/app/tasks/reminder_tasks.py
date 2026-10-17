
import logging
import asyncio
import os
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from .celery_app import celery
from app.services import whatsapp_service, telegram_service
from app.services.reminder_schedule import due_daily_occurrences
from app.core.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Canonical approved template names. A name is only usable once the matching
# WHATSAPP_*_TEMPLATE_NAME setting is populated and Meta has approved it.
MEDICATION_TEMPLATE_NAME = "medication_reminder_v3"
REFILL_TEMPLATE_NAME = "refill_reminder_v1"


def _telegram_reminder_text(user_name: str, medicine_name: str) -> str:
    """Build the plain-text body for a reminder sent to a linked Telegram chat."""
    name = (user_name or "").strip()
    medicine = (medicine_name or "").strip() or "your medicine"
    greeting = f"Hi {name}, " if name else ""
    return f"{greeting}it's time to take your {medicine} (Vitalyze reminder)."


def _deliver_via_channel(channel: str, user: dict, reminder: dict) -> str | None:
    """Send one reminder through a single authorized channel.

    Returns the provider receipt when the provider accepted the message and
    ``None`` when nothing was sent. Authorization is re-checked here because
    consent or channel state may have changed since the record was queued.
    """
    if channel == "whatsapp":
        if not user.get("phone_verified", False) or not reminder.get("whatsapp_opt_in", False):
            return None
        return whatsapp_service.send_template_message(
            user["phone_number"],
            MEDICATION_TEMPLATE_NAME,
            [user.get("name", ""), reminder.get("medicine_name", "")],
            user_opted_in=True,
            phone_verified=True,
        )
    if channel == "telegram":
        chat_id = user.get("telegram_chat_id")
        if not chat_id or not reminder.get("telegram_opt_in", False):
            return None
        return telegram_service.send_message(
            chat_id,
            _telegram_reminder_text(user.get("name", ""), reminder.get("medicine_name", "")),
        )
    return None


@celery.task
def send_daily_reminder_task(
    user_name: str,
    phone_number: str,
    medicine_name: str,
    user_opted_in: bool = False,
    phone_verified: bool = False,
):
    """Celery task to send a daily medicine reminder via WhatsApp."""
    logger.info("Executing daily reminder task.")
    template_name = MEDICATION_TEMPLATE_NAME
    if not user_opted_in or not phone_verified or not whatsapp_service.is_configured(template_name):
        logger.info("Daily reminder is pending WhatsApp configuration; no message was sent.")
        return "Pending WhatsApp configuration; message not sent."

    template_params = [user_name, medicine_name]

    success = whatsapp_service.send_template_message(
        phone_number, template_name, template_params,
        user_opted_in=user_opted_in, phone_verified=phone_verified,
    )
    
    if success:
        return "Daily reminder sent."
    else:
        return "Daily reminder failed."
    


@celery.task
def send_refill_reminder_task(
    user_name: str,
    phone_number: str,
    medicine_name: str,
    user_opted_in: bool = False,
    phone_verified: bool = False,
):
    """Celery task to send a refill reminder via WhatsApp."""
    logger.info("Executing refill reminder task.")
    template_name = REFILL_TEMPLATE_NAME
    if not user_opted_in or not phone_verified or not whatsapp_service.is_configured(template_name):
        logger.info("Refill reminder is pending WhatsApp configuration; no message was sent.")
        return "Pending WhatsApp configuration; message not sent."

    template_params = [user_name, medicine_name]

    success = whatsapp_service.send_template_message(
        phone_number, template_name, template_params,
        user_opted_in=user_opted_in, phone_verified=phone_verified,
    )
    
    if success:
        return "Refill reminder sent."
    else:
        return "Refill reminder failed."


@celery.task
def dispatch_due_daily_reminders():
    """Create one durable delivery record per due occurrence; skip stale occurrences."""
    async def dispatch():
        client = AsyncIOMotorClient(settings.MONGO_URI)
        try:
            db = client[settings.MONGO_DB_NAME]
            deliveries = db["reminder_deliveries"]
            await deliveries.create_index("delivery_key", unique=True)
            await deliveries.create_index("provider_message_id")
            users = []
            async for user in db["users"].find({"daily_reminders.0": {"$exists": True}}):
                users.append(user)
            now = datetime.now(timezone.utc)
            created = 0
            for occurrence in due_daily_occurrences(users, now):
                # Users who never consented on any channel have nothing to
                # deliver, so no delivery record is created for them.
                if not occurrence["whatsapp_opt_in"] and not occurrence.get("telegram_opt_in"):
                    continue
                channels, blocked_reasons = [], []
                if occurrence["whatsapp_opt_in"]:
                    if not occurrence["phone_verified"]:
                        blocked_reasons.append("phone_not_verified")
                    elif not whatsapp_service.is_configured(MEDICATION_TEMPLATE_NAME):
                        blocked_reasons.append("whatsapp_not_configured")
                    else:
                        channels.append("whatsapp")
                if occurrence.get("telegram_opt_in"):
                    if not occurrence.get("telegram_linked"):
                        blocked_reasons.append("telegram_not_linked")
                    elif not telegram_service.is_configured():
                        blocked_reasons.append("telegram_not_configured")
                    else:
                        channels.append("telegram")
                if channels:
                    status, blocked_reason, ready = "pending", None, True
                else:
                    # Keep a single reason so existing consumers see the same
                    # shape as before; join with a comma only when several
                    # channels are blocked at once.
                    status, blocked_reason, ready = (
                        "blocked",
                        ",".join(blocked_reasons) or "no_channel",
                        False,
                    )
                document = {
                    **occurrence,
                    "channels": channels,
                    "status": status,
                    "blocked_reason": blocked_reason,
                    "created_at": now,
                    "updated_at": now,
                }
                result = await deliveries.update_one(
                    {"delivery_key": occurrence["delivery_key"]},
                    {"$setOnInsert": document},
                    upsert=True,
                )
                if result.upserted_id is None:
                    continue
                created += 1
                if ready:
                    # Mark the record queued BEFORE handing it to the worker. A
                    # fast worker claims with an atomic queued->sending update,
                    # so queueing first guarantees it can never miss the record.
                    delivery_id = str(result.upserted_id)
                    try:
                        await deliveries.update_one(
                            {"_id": result.upserted_id, "status": "pending"},
                            {"$set": {"status": "queued", "updated_at": datetime.now(timezone.utc)}},
                        )
                        send_daily_reminder_delivery.delay(delivery_id)
                    except Exception as exc:
                        logger.error("Could not queue reminder delivery (%s).", type(exc).__name__)
                        await deliveries.update_one(
                            {"_id": result.upserted_id},
                            {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}},
                        )
            logger.info("Reminder dispatcher recorded %s due occurrences.", created)
            return created
        finally:
            client.close()

    try:
        return asyncio.run(dispatch())
    except Exception as exc:
        logger.error("Daily reminder dispatch failed (%s).", type(exc).__name__)
        return 0


@celery.task
def send_daily_reminder_delivery(delivery_id: str):
    """Send only an owned, opted-in, verified reminder after atomically claiming it."""
    async def deliver():
        client = AsyncIOMotorClient(settings.MONGO_URI)
        try:
            db = client[settings.MONGO_DB_NAME]
            deliveries = db["reminder_deliveries"]
            if not ObjectId.is_valid(delivery_id):
                return "Reminder delivery not found."
            delivery = await deliveries.find_one_and_update(
                {"_id": ObjectId(delivery_id), "status": "queued"},
                {"$set": {"status": "sending", "updated_at": datetime.now(timezone.utc)}},
                return_document=True,
            )
            if not delivery:
                return "Reminder delivery was already claimed or is unavailable."
            # Older records (and records with a single WhatsApp channel) have no
            # `channels` field; default them to WhatsApp for compatibility.
            channels = delivery.get("channels") or ["whatsapp"]
            user_id = ObjectId(delivery["user_id"])
            user = await db["users"].find_one({"_id": user_id})
            reminder_id = ObjectId(delivery["reminder_id"])
            reminder = None
            if user:
                reminder = next(
                    (item for item in user.get("daily_reminders", []) if item.get("_id") == reminder_id),
                    None,
                )
            if not user or not reminder or not reminder.get("is_active", True):
                await deliveries.update_one(
                    {"_id": delivery["_id"]},
                    {"$set": {"status": "failed", "updated_at": datetime.now(timezone.utc)}},
                )
                return "Reminder delivery is no longer enabled."

            receipts = {}
            for channel in channels:
                receipt = _deliver_via_channel(channel, user, reminder)
                if receipt:
                    receipts[channel] = receipt

            update = {"updated_at": datetime.now(timezone.utc)}
            if receipts:
                # "sent" means the provider accepted the message, not delivered.
                update["status"] = "sent"
                update["provider_message_ids"] = receipts
                # Keep the legacy field populated so the WhatsApp
                # delivery-status webhook can still match on it.
                update["provider_message_id"] = (
                    receipts.get("whatsapp") or next(iter(receipts.values()))
                )
            else:
                update["status"] = "failed"
            await deliveries.update_one({"_id": delivery["_id"]}, {"$set": update})
            return "Reminder accepted by provider." if receipts else "Reminder delivery failed."
        finally:
            client.close()

    try:
        return asyncio.run(deliver())
    except Exception as exc:
        logger.error("Reminder delivery failed (%s).", type(exc).__name__)
        return "Reminder delivery failed."
