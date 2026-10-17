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
    "GOOGLE_MAPS_API_KEY": "",
    "GCP_PROJECT_ID": "test-only-placeholder-project",
    "GCP_LOCATION": "us-central1",
    "GOOGLE_APPLICATION_CREDENTIALS": "./test-only-missing-service-account.json",
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


class FakeDatabase:
    def __init__(self, reports=None):
        self.reports = FakeReportsCollection(reports)
        self.report_jobs = FakeReportJobsCollection()

    def __getitem__(self, collection_name):
        if collection_name == "reports":
            return self.reports
        if collection_name == "report_jobs":
            return self.report_jobs
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
