import ssl

from app.tasks import celery_app
from app.tasks.celery_app import redis_ssl_settings, ssl_options


def test_plain_redis_url_does_not_receive_tls_options():
    assert redis_ssl_settings("redis://127.0.0.1:6379/0") == {}


def test_tls_redis_url_preserves_existing_tls_options():
    assert ssl_options["ssl_cert_reqs"] == ssl.CERT_REQUIRED
    assert redis_ssl_settings("rediss://redis.example.invalid:6379/0") == {
        "broker_use_ssl": ssl_options,
        "redis_backend_use_ssl": ssl_options,
    }


def test_daily_reminders_use_one_shared_beat_dispatcher():
    schedule = celery_app.celery.conf.beat_schedule
    assert schedule["dispatch-due-daily-reminders-every-minute"] == {
        "task": "app.tasks.reminder_tasks.dispatch_due_daily_reminders",
        "schedule": 60.0,
    }
    assert len(schedule) == 1
