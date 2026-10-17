from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from typing import Iterable


DEFAULT_DAILY_TIMES = ("10:00", "14:00", "21:00")
LEGACY_TIMES = {"morning": "10:00", "afternoon": "14:00", "evening": "21:00"}
DISPATCH_GRACE = timedelta(minutes=2)


def due_daily_occurrences(users: Iterable[dict], now: datetime) -> list[dict]:
    """Return only today's due occurrences inside the grace window; stale times are skipped."""
    now_utc = now.astimezone(timezone.utc) if now.tzinfo else now.replace(tzinfo=timezone.utc)
    occurrences = []
    for user in users:
        user_id = str(user.get("_id", ""))
        for reminder in user.get("daily_reminders", []):
            if not reminder.get("is_active", True):
                continue
            timezone_name = reminder.get("timezone") or "Asia/Kolkata"
            try:
                zone = ZoneInfo(timezone_name)
            except (ZoneInfoNotFoundError, ValueError):
                continue
            local_now = now_utc.astimezone(zone)
            times = reminder.get("times") or [
                LEGACY_TIMES[timing]
                for timing in reminder.get("timings", [])
                if timing in LEGACY_TIMES
            ]
            for clock_time in dict.fromkeys(times):
                try:
                    hour, minute = (int(part) for part in clock_time.split(":"))
                    target = datetime.combine(
                        local_now.date(), time(hour, minute), tzinfo=zone
                    )
                except (ValueError, TypeError):
                    continue
                target_utc = target.astimezone(timezone.utc)
                age = now_utc - target_utc
                if timedelta(0) <= age <= DISPATCH_GRACE:
                    reminder_id = str(reminder.get("_id", reminder.get("id", "")))
                    delivery_key = f"{user_id}:{reminder_id}:{local_now.date().isoformat()}:{hour:02d}:{minute:02d}"
                    occurrences.append({
                        "delivery_key": delivery_key,
                        "user_id": user_id,
                        "reminder_id": reminder_id,
                        "medicine_name": reminder.get("medicine_name", ""),
                        "timezone": timezone_name,
                        "scheduled_at": target_utc,
                        "whatsapp_opt_in": bool(reminder.get("whatsapp_opt_in", False)),
                        "phone_verified": bool(user.get("phone_verified", False)),
                        "telegram_opt_in": bool(reminder.get("telegram_opt_in", False)),
                        "telegram_linked": bool(user.get("telegram_chat_id")),
                    })
    return occurrences
