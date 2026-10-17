import ssl
import logging
from urllib.parse import urlsplit
from celery import Celery

from app.core.config import settings

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
    beat_schedule={
        "dispatch-due-daily-reminders-every-minute": {
            "task": "app.tasks.reminder_tasks.dispatch_due_daily_reminders",
            "schedule": 60.0,
        },
    },
)

# Celery rejects explicit SSL options with a plain redis:// URL. Keep TLS
# verification behavior for managed rediss:// brokers while allowing local
# loopback Redis used for development and tests.
celery.conf.update(**redis_ssl_settings(settings.REDIS_URL))
