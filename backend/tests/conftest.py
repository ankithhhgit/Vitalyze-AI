"""Shared isolated fixtures for backend API and task tests."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

# Required settings use harmless, local-only values before importing the app.
_TEST_SETTINGS = {
    "MONGO_URI": "mongodb://127.0.0.1:27017",
    "MONGO_DB_NAME": "vitalyze_test_only",
    "REDIS_URL": "redis://127.0.0.1:6379/15",
    "SECRET_KEY": "test-only-placeholder-secret",
    "ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "5",
    "WHATSAPP_API_VERSION": "vXX.X",
    "WHATSAPP_ACCESS_TOKEN": "test-only-placeholder-token",
    "WHATSAPP_PHONE_NUMBER_ID": "test-only-placeholder-phone-id",
    "WHATSAPP_VERIFY_TOKEN": "test-only-placeholder-verify-token",
    "GEOAPIFY_API_KEY": "",
    "GCP_PROJECT_ID": "test-only-placeholder-project",
    "GCP_LOCATION": "us-central1",
    "GOOGLE_APPLICATION_CREDENTIALS": "./test-only-missing-service-account.json",
    "GEMINI_API_KEY": "",
    "GEMINI_MODEL": "gemini-3.5-flash-lite",
    "REPORT_ANALYSIS_MODE": "local",
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_BOT_USERNAME": "",
    "TELEGRAM_WEBHOOK_SECRET": "",
    "TELEGRAM_SEND_ENABLED": "false",
    "TELEGRAM_LINK_CODE_TTL_SECONDS": "900",
}
for _name, _value in _TEST_SETTINGS.items():
    os.environ[_name] = _value

import main  # noqa: E402
from app.api.v1.endpoints import auth  # noqa: E402
from app.db.mongodb import get_database  # noqa: E402
from app.models.user import UserInDB  # noqa: E402


class FakeCursor:
    def __init__(self, documents):
        self.documents = list(documents)
        self.sort_spec = None

    def sort(self, key, direction):
        self.sort_spec = (key, direction)
        return self

    def __aiter__(self):
        self._iterator = iter(self.documents)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration


class FakeReportsCollection:
    def __init__(self, documents=None):
        self.documents = documents or []
        self.query = None
        self.cursor = None

    def find(self, query):
        self.query = query
        self.cursor = FakeCursor(
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        )
        return self.cursor


class FakeReportJobsCollection:
    def __init__(self):
        self.records = {}

    async def find_one(self, query):
        document = self.records.get(query.get("_id"))
        if document and all(document.get(key) == value for key, value in query.items()):
            return document
        return None

    async def insert_one(self, document):
        self.records[document["_id"]] = dict(document)
        return SimpleNamespace(inserted_id=document["_id"])


class FakeUsersCollection:
    def __init__(self):
        self.update_query = None
        self.update_operation = None
        self.documents = []

    async def update_one(self, query, update):
        self.update_query = query
        self.update_operation = update
        modified = 0 if "$pull" in update else 1
        matches = [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        for document in matches:
            document.update(update.get("$set", {}))
            for key in update.get("$unset", {}):
                document.pop(key, None)
        if matches:
            modified = len(matches)
        return SimpleNamespace(matched_count=modified, modified_count=modified)


class FakeReminderDeliveriesCollection:
    def __init__(self, documents=None):
        self.documents = [dict(document) for document in (documents or [])]
        self.last_query = None
        self.last_update = None

    async def update_one(self, query, update):
        self.last_query = query
        self.last_update = update
        matches = [
            document
            for document in self.documents
            if all(document.get(key) == value for key, value in query.items())
        ]
        set_values = update.get("$set", {})
        for document in matches:
            document.update(set_values)
        return SimpleNamespace(matched_count=len(matches), modified_count=len(matches))


class FakeTelegramLinkCodesCollection:
    """In-memory stand-in for the one-time Telegram account-linking codes."""

    def __init__(self):
        self.documents = []
        self.indexes = []

    async def create_index(self, key, unique=False):
        self.indexes.append((key, unique))
        return key

    @staticmethod
    def _matches(document, query):
        for key, expected in query.items():
            actual = document.get(key)
            if isinstance(expected, dict) and "$gt" in expected:
                bound = expected["$gt"]
                if actual is None or not (actual > bound):
                    return False
            elif actual != expected:
                return False
        return True

    async def insert_one(self, document):
        self.documents.append(dict(document))
        return SimpleNamespace(inserted_id=document.get("_id"))

    async def update_many(self, query, update):
        matched = [doc for doc in self.documents if self._matches(doc, query)]
        for document in matched:
            document.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=len(matched), modified_count=len(matched))

    async def find_one_and_update(self, query, update):
        for document in self.documents:
            if self._matches(document, query):
                document.update(update.get("$set", {}))
                return dict(document)
        return None


class FakeDatabase:
    def __init__(self, reports=None):
        self.reports = FakeReportsCollection(reports)
        self.report_jobs = FakeReportJobsCollection()
        self.users = FakeUsersCollection()
        self.reminder_deliveries = FakeReminderDeliveriesCollection()
        self.telegram_link_codes = FakeTelegramLinkCodesCollection()

    def __getitem__(self, collection_name):
        if collection_name == "reports":
            return self.reports
        if collection_name == "report_jobs":
            return self.report_jobs
        if collection_name == "users":
            return self.users
        if collection_name == "reminder_deliveries":
            return self.reminder_deliveries
        if collection_name == "telegram_link_codes":
            return self.telegram_link_codes
        raise AssertionError(f"Unexpected test collection access: {collection_name}")


@pytest.fixture
def fake_user():
    return UserInDB(
        _id=ObjectId("65a000000000000000000001"),
        name="Synthetic Test User",
        phone_number="+15555550123",
        hashed_password="synthetic-test-hash",
    )


@pytest.fixture
def fake_db():
    return FakeDatabase()


@pytest.fixture
def client(monkeypatch, fake_db):
    async def no_database_connect():
        return None

    async def no_database_close():
        return None

    monkeypatch.setattr(main, "connect_to_mongo", no_database_connect)
    monkeypatch.setattr(main, "close_mongo_connection", no_database_close)
    main.app.dependency_overrides[get_database] = lambda: fake_db
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client, fake_user):
    async def test_current_user():
        return fake_user

    main.app.dependency_overrides[auth.get_current_user] = test_current_user
    main.app.dependency_overrides[auth.get_current_active_user] = test_current_user
    yield client
    main.app.dependency_overrides.clear()


def report_document(owner_id: str, *, report_id=None, upload_date=None):
    return {
        "_id": report_id or ObjectId("65a000000000000000000010"),
        "user_id": owner_id,
        "filename": "synthetic-report.pdf",
        "upload_date": upload_date or datetime(2026, 1, 2, tzinfo=timezone.utc),
        "raw_text": "Synthetic report text for automated tests.",
        "simple_summary": "Synthetic summary.",
        "structured_entities": [{"Indicator": "Hemoglobin", "Value": "12.5 g/dL"}],
        "file_storage_path": None,
    }
