from datetime import datetime, timezone

from app.services.reminder_schedule import due_daily_occurrences


def test_default_daily_occurrence_uses_asia_kolkata_and_exact_time():
    users = [{
        "_id": "user-a",
        "daily_reminders": [{
            "_id": "reminder-a",
            "medicine_name": "Synthetic medicine",
            "times": ["10:00", "14:00", "21:00"],
            "timezone": "Asia/Kolkata",
        }],
    }]

    due = due_daily_occurrences(users, datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc))

    assert len(due) == 1
    assert due[0]["delivery_key"] == "user-a:reminder-a:2026-10-17:10:00"
    assert due[0]["scheduled_at"] == datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc)


def test_custom_timezone_observes_daylight_saving_wall_clock():
    users = [{
        "_id": "user-b",
        "daily_reminders": [{
            "_id": "reminder-b", "times": ["10:00"], "timezone": "America/New_York"
        }],
    }]

    due = due_daily_occurrences(users, datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc))

    assert len(due) == 1
    assert due[0]["scheduled_at"] == datetime(2026, 3, 8, 14, 0, tzinfo=timezone.utc)


def test_disabled_and_stale_reminders_are_skipped_without_catchup_bursts():
    users = [{
        "_id": "user-c",
        "daily_reminders": [
            {"_id": "disabled", "times": ["10:00"], "timezone": "Asia/Kolkata", "is_active": False},
            {"_id": "stale", "times": ["10:00"], "timezone": "Asia/Kolkata", "is_active": True},
        ],
    }]

    due = due_daily_occurrences(users, datetime(2026, 10, 17, 4, 35, tzinfo=timezone.utc))

    assert due == []


def test_legacy_period_names_map_to_new_default_local_times():
    users = [{
        "_id": "user-d",
        "daily_reminders": [{"_id": "legacy", "timings": ["morning"], "timezone": "Asia/Kolkata"}],
    }]

    due = due_daily_occurrences(users, datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc))

    assert len(due) == 1
    assert due[0]["delivery_key"].endswith("2026-10-17:10:00")
