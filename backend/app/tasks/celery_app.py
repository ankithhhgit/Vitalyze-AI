import ssl
import asyncio
import logging
from urllib.parse import urlsplit
from celery import Celery
from celery.schedules import crontab
from motor.motor_asyncio import AsyncIOMotorClient

from app.core.config import settings

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force SSL settings for Upstash/Redis
ssl_options = {
    # Require a trusted server certificate for managed Redis TLS connections.
    'ssl_cert_reqs': ssl.CERT_REQUIRED
}


def redis_ssl_settings(redis_url: str) -> dict:
    """Return Celery TLS options only for TLS-enabled Redis URLs."""
    if urlsplit(redis_url).scheme == "rediss":
        return {
            "broker_use_ssl": ssl_options,
            "redis_backend_use_ssl": ssl_options,
        }
    return {}

celery = Celery(
    "app.tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.reminder_tasks", "app.tasks.report_processing"]
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
)

# Celery rejects explicit SSL options with a plain redis:// URL. Keep TLS
# verification behavior for managed rediss:// brokers while allowing local
# loopback Redis used for development and tests.
celery.conf.update(**redis_ssl_settings(settings.REDIS_URL))


TIMING_TO_CRONTAB = {
    "morning": crontab(hour=8, minute=0),
    "afternoon": crontab(hour=13, minute=0),
    "evening": crontab(hour=20, minute=0),
}

async def restore_reminders_from_db():
    """
    Async function to fetch all users and re-schedule their active daily reminders.
    """
    logger.info("♻️  Attempting to restore reminders from MongoDB...")
    
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]
    
    cursor = db["users"].find({"daily_reminders": {"$exists": True, "$not": {"$size": 0}}})
    
    count = 0
    async for user in cursor:
        user_id = str(user["_id"])
        user_name = user.get("name", "User")
        phone_number = user.get("phone_number")
        
        for reminder in user.get("daily_reminders", []):
            if reminder.get("is_active", True):
                medicine_name = reminder["medicine_name"]
                timings = reminder["timings"] # List like ["morning", "evening"]
                
                from app.tasks.reminder_tasks import send_daily_reminder_task
                
                for timing in timings:
                    if timing in TIMING_TO_CRONTAB:
                        task_name = f"daily-reminder-{user_id}-{medicine_name}-{timing}"
                        
                        celery.add_periodic_task(
                            TIMING_TO_CRONTAB[timing],
                            send_daily_reminder_task.s(user_name, phone_number, medicine_name),
                            name=task_name
                        )
                        count += 1
                        
    logger.info(f"✅ Successfully restored {count} daily reminder tasks from Database.")
    client.close()

@celery.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    This signal runs when the Celery worker (or beat) starts up.
    It triggers the async restoration logic.
    """
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(restore_reminders_from_db())
        loop.close()
    except Exception as e:
        logger.error(f"❌ Failed to restore reminders on startup: {e}")
