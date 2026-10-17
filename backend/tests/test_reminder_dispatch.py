"""Tests for the shared daily-reminder dispatcher and delivery task.

The dispatcher's time calculation is covered by ``test_reminder_schedule.py``.
These tests focus on persistence, idempotency, worker overlap, and the
blocked/consent/configuration states, using an in-memory fake Mongo client so
no real broker, database, or provider is contacted.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bson import ObjectId

from app.tasks import reminder_tasks


class FakeResult:
    def __init__(self, *, upserted_id=None, matched=0, modified=0):
        self.upserted_id = upserted_id
        self.matched_count = matched
        self.modified_count = modified


class FakeAsyncCursor:
    def __init__(self, documents):
        self._documents = list(documents)

    def __aiter__(self):
        self._iterator = iter(self._documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []

    def _matches(self, query):
        for document in self.documents:
            if all(document.get(key) == value for key, value in query.items()):
                yield document

    async def create_index(self, key, unique=False):
        self.indexes.append((key, unique))
        return key

    def find(self, query):
        return FakeAsyncCursor(list(self._matches(query)))

    async def find_one(self, query):
        for document in self._matches(query):
            return document
        return None

    async def update_one(self, query, update, upsert=False):
        for document in self._matches(query):
            document.update(update.get("$set", {}))
            return FakeResult(matched=1, modified=1)
        if upsert:
            new_document = dict(update.get("$setOnInsert", {}))
            new_document.update(update.get("$set", {}))
            new_document.setdefault("_id", ObjectId())
            self.documents.append(new_document)
            return FakeResult(upserted_id=new_document["_id"])
        return FakeResult()

    async def find_one_and_update(self, query, update, return_document=False):
        for document in self._matches(query):
            document.update(update.get("$set", {}))
            return dict(document)
        return None


class FakeDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeMongoClient:
    def __init__(self, *args, **kwargs):
        self.databases = {}

    def __getitem__(self, name):
        return self.databases.setdefault(name, FakeDatabase())

    def collection(self, name):
        return self[reminder_tasks.settings.MONGO_DB_NAME][name]

    def close(self):
        return None


@pytest.fixture
def fake_mongo(monkeypatch):
    client = FakeMongoClient()
    monkeypatch.setattr(reminder_tasks, "AsyncIOMotorClient", lambda *a, **k: client)
    return client


def _occurrence(*, user_id, reminder_id, opted_in=True, verified=True):
    return {
        "delivery_key": f"{user_id}:{reminder_id}:2026-10-17:10:00",
        "user_id": str(user_id),
        "reminder_id": str(reminder_id),
        "medicine_name": "Synthetic Medicine",
        "timezone": "Asia/Kolkata",
        "scheduled_at": datetime(2026, 10, 17, 4, 30, tzinfo=timezone.utc),
        "whatsapp_opt_in": opted_in,
        "phone_verified": verified,
    }


def _monkeypatch_occurrences(monkeypatch, occurrences):
    monkeypatch.setattr(
        reminder_tasks, "due_daily_occurrences", lambda users, now: list(occurrences)
    )


def test_due_occurrence_is_recorded_and_queued_once(monkeypatch, fake_mongo):
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id)])
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: True)
    queue = Mock()
    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=queue)
    )

    first = reminder_tasks.dispatch_due_daily_reminders.run()
    second = reminder_tasks.dispatch_due_daily_reminders.run()

    assert first == 1
    # A repeated dispatch must not create or re-queue the same occurrence.
    assert second == 0
    queue.assert_called_once()
    deliveries = fake_mongo.collection("reminder_deliveries").documents
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "queued"
    assert deliveries[0]["delivery_key"] == f"{user_id}:{reminder_id}:2026-10-17:10:00"


def test_dispatcher_marks_queued_before_handing_to_worker(monkeypatch, fake_mongo):
    """The record must be claimable (queued) before the worker id is published.

    A fast worker claims with an atomic queued->sending update, so if the
    dispatcher queued the task before flipping the status the worker could miss
    the record and silently drop the reminder.
    """
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id)])
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: True)

    observed = []

    def observe(delivery_id):
        documents = fake_mongo.collection("reminder_deliveries").documents
        observed.append(next(d for d in documents if str(d["_id"]) == delivery_id)["status"])

    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=observe)
    )

    assert reminder_tasks.dispatch_due_daily_reminders.run() == 1
    assert observed == ["queued"]


def test_dispatcher_marks_failed_when_queueing_raises(monkeypatch, fake_mongo):
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id)])
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: True)

    def boom(_delivery_id):
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=boom)
    )

    assert reminder_tasks.dispatch_due_daily_reminders.run() == 1
    assert fake_mongo.collection("reminder_deliveries").documents[0]["status"] == "failed"


def test_dispatcher_skips_occurrence_without_consent(monkeypatch, fake_mongo):
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(
        monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id, opted_in=False)]
    )
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: True)
    queue = Mock()
    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=queue)
    )

    assert reminder_tasks.dispatch_due_daily_reminders.run() == 0
    queue.assert_not_called()
    assert fake_mongo.collection("reminder_deliveries").documents == []


def test_dispatcher_blocks_unverified_phone_without_sending(monkeypatch, fake_mongo):
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(
        monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id, verified=False)]
    )
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: True)
    queue = Mock()
    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=queue)
    )

    assert reminder_tasks.dispatch_due_daily_reminders.run() == 1
    queue.assert_not_called()
    delivery = fake_mongo.collection("reminder_deliveries").documents[0]
    assert delivery["status"] == "blocked"
    assert delivery["blocked_reason"] == "phone_not_verified"


def test_dispatcher_blocks_when_whatsapp_is_not_configured(monkeypatch, fake_mongo):
    user_id, reminder_id = ObjectId(), ObjectId()
    _monkeypatch_occurrences(monkeypatch, [_occurrence(user_id=user_id, reminder_id=reminder_id)])
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _t: False)
    queue = Mock()
    monkeypatch.setattr(
        reminder_tasks, "send_daily_reminder_delivery", SimpleNamespace(delay=queue)
    )

    assert reminder_tasks.dispatch_due_daily_reminders.run() == 1
    queue.assert_not_called()
    delivery = fake_mongo.collection("reminder_deliveries").documents[0]
    assert delivery["status"] == "blocked"
    assert delivery["blocked_reason"] == "whatsapp_not_configured"


def _seed_delivery(fake_mongo, *, verified=True, active=True, opted_in=True):
    user_id, reminder_id = ObjectId(), ObjectId()
    fake_mongo.collection("users").documents.append({
        "_id": user_id,
        "name": "Synthetic User",
        "phone_number": "+19995550155",
        "phone_verified": verified,
        "daily_reminders": [{
            "_id": reminder_id,
            "medicine_name": "Synthetic Medicine",
            "times": ["10:00"],
            "timezone": "Asia/Kolkata",
            "is_active": active,
            "whatsapp_opt_in": opted_in,
        }],
    })
    delivery_id = ObjectId()
    fake_mongo.collection("reminder_deliveries").documents.append({
        "_id": delivery_id,
        "delivery_key": "synthetic-key",
        "user_id": str(user_id),
        "reminder_id": str(reminder_id),
        "medicine_name": "Synthetic Medicine",
        "status": "queued",
    })
    return delivery_id


def test_delivery_task_claims_and_records_provider_receipt(monkeypatch, fake_mongo):
    delivery_id = _seed_delivery(fake_mongo)
    send = Mock(return_value="wamid.synthetic-provider-id")
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)

    first = reminder_tasks.send_daily_reminder_delivery.run(str(delivery_id))
    second = reminder_tasks.send_daily_reminder_delivery.run(str(delivery_id))

    assert send.call_count == 1
    assert "accepted" in first.lower()
    assert "already claimed" in second.lower()
    delivery = fake_mongo.collection("reminder_deliveries").documents[0]
    assert delivery["status"] == "sent"
    assert delivery["provider_message_id"] == "wamid.synthetic-provider-id"


def test_delivery_task_marks_failure_when_provider_declines(monkeypatch, fake_mongo):
    delivery_id = _seed_delivery(fake_mongo)
    send = Mock(return_value=None)
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)

    result = reminder_tasks.send_daily_reminder_delivery.run(str(delivery_id))

    assert "failed" in result.lower()
    assert fake_mongo.collection("reminder_deliveries").documents[0]["status"] == "failed"


def test_delivery_task_refuses_unverified_or_disabled_reminders(monkeypatch, fake_mongo):
    delivery_id = _seed_delivery(fake_mongo, verified=False)
    send = Mock(return_value="wamid.synthetic")
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)

    reminder_tasks.send_daily_reminder_delivery.run(str(delivery_id))

    send.assert_not_called()
    assert fake_mongo.collection("reminder_deliveries").documents[0]["status"] == "failed"
