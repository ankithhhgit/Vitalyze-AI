from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bson import ObjectId
import pytest

from app.api.v1.endpoints import auth, chat, maps, reminders, reports
from app.models.user import Token
from conftest import report_document


def test_app_starts_and_declares_main_routes(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"] == "Welcome to the Vitalyze.ai API"

    openapi = client.get("/openapi.json").json()
    paths = openapi["paths"]
    expected = {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/reports/upload",
        "/api/v1/reports/status/{task_id}",
        "/api/v1/reports/history",
        "/api/v1/reminders/daily",
        "/api/v1/reminders/refill",
        "/api/v1/chat/",
        "/api/v1/maps/pharmacies",
    }
    assert expected.issubset(paths)


def test_login_issues_token_without_connecting_to_database(client, monkeypatch, fake_user):
    monkeypatch.setattr(auth.security, "authenticate_user", AsyncMock(return_value=fake_user))
    monkeypatch.setattr(auth.security, "create_access_token", Mock(return_value="synthetic-token"))

    response = client.post(
        "/api/v1/auth/login",
        data={"username": fake_user.phone_number, "password": "synthetic-password"},
    )

    assert response.status_code == 200
    assert Token(**response.json()).token_type == "bearer"
    assert response.json()["access_token"] == "synthetic-token"


def test_report_history_rejects_missing_and_invalid_tokens(client):
    assert client.get("/api/v1/reports/history").status_code == 401
    assert client.get(
        "/api/v1/reports/history", headers={"Authorization": "Bearer invalid-token"}
    ).status_code == 401


def test_report_status_requires_authentication(client, monkeypatch):
    monkeypatch.setattr(
        reports,
        "AsyncResult",
        Mock(return_value=SimpleNamespace(state="SUCCESS", result={"synthetic": True})),
    )

    response = client.get("/api/v1/reports/status/known-task-id")
    assert response.status_code == 401


def test_report_status_is_available_to_its_owner(authenticated_client, fake_db, monkeypatch):
    fake_db.report_jobs.records["synthetic-task-id"] = {
        "_id": "synthetic-task-id",
        "user_id": "65a000000000000000000001",
    }
    monkeypatch.setattr(
        reports,
        "AsyncResult",
        Mock(return_value=SimpleNamespace(state="PENDING", result=None)),
    )

    response = authenticated_client.get("/api/v1/reports/status/synthetic-task-id")

    assert response.status_code == 200
    assert response.json() == {"status": "PENDING"}


def test_report_status_denies_another_users_task(authenticated_client, fake_db, monkeypatch):
    fake_db.report_jobs.records["synthetic-task-id"] = {
        "_id": "synthetic-task-id",
        "user_id": "65a000000000000000000002",
    }
    async_result = Mock()
    monkeypatch.setattr(reports, "AsyncResult", async_result)

    response = authenticated_client.get("/api/v1/reports/status/synthetic-task-id")

    assert response.status_code == 404
    async_result.assert_not_called()


def test_report_status_fails_closed_when_ownership_lookup_fails(
    authenticated_client, fake_db, monkeypatch
):
    fake_db.report_jobs.find_one = AsyncMock(
        side_effect=RuntimeError("synthetic ownership store failure")
    )
    async_result = Mock()
    monkeypatch.setattr(reports, "AsyncResult", async_result)

    response = authenticated_client.get("/api/v1/reports/status/synthetic-task-id")

    assert response.status_code == 503
    assert "synthetic ownership store failure" not in response.text
    async_result.assert_not_called()


def test_report_status_hides_internal_failure_details(authenticated_client, fake_db, monkeypatch):
    fake_db.report_jobs.records["synthetic-task-id"] = {
        "_id": "synthetic-task-id",
        "user_id": "65a000000000000000000001",
    }
    monkeypatch.setattr(
        reports,
        "AsyncResult",
        Mock(
            return_value=SimpleNamespace(
                state="FAILURE", info=RuntimeError("synthetic database diagnostic")
            )
        ),
    )

    response = authenticated_client.get("/api/v1/reports/status/synthetic-task-id")

    assert response.status_code == 200
    assert response.json() == {
        "status": "FAILURE",
        "error": "Report processing failed.",
    }
    assert "synthetic database diagnostic" not in response.text


def test_report_upload_persists_task_owner_before_returning_id(
    authenticated_client, fake_db, fake_user, monkeypatch, tmp_path
):
    class FakeWorkflow:
        def apply_async(self):
            return SimpleNamespace(id="synthetic-queued-task")

    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "storage_service", None)
    monkeypatch.setattr(reports, "chain", Mock(return_value=FakeWorkflow()))

    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"file": ("synthetic-report.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "synthetic-queued-task"
    assert fake_db.report_jobs.records["synthetic-queued-task"]["user_id"] == str(fake_user.id)


def test_report_upload_fails_closed_if_task_ownership_cannot_be_saved(
    authenticated_client, fake_db, monkeypatch, tmp_path
):
    revoke = Mock()
    fake_db.report_jobs.insert_one = AsyncMock(
        side_effect=RuntimeError("synthetic ownership write failure")
    )

    class FakeWorkflow:
        def apply_async(self):
            return SimpleNamespace(id="synthetic-unowned-task", revoke=revoke)

    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "storage_service", None)
    monkeypatch.setattr(reports, "chain", Mock(return_value=FakeWorkflow()))

    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"file": ("synthetic-report.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )

    assert response.status_code == 503
    assert "task_id" not in response.json()
    revoke.assert_called_once_with(terminate=False)


def test_history_queries_only_the_authenticated_users_reports(
    authenticated_client, fake_db, fake_user
):
    fake_db.reports.documents = [
        report_document(str(fake_user.id)),
        report_document(
            "65a000000000000000000002",
            report_id=ObjectId("65a000000000000000000011"),
        ),
    ]

    response = authenticated_client.get("/api/v1/reports/history")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["structured_entities"][0]["Value"] == "12.5 g/dL"
    assert fake_db.reports.query == {"user_id": str(fake_user.id)}
    assert fake_db.reports.cursor.sort_spec == ("upload_date", -1)


def test_daily_reminder_rejects_unknown_timing(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/reminders/daily",
        json={"medicine_name": "Synthetic Medicine", "timings": ["midnight"]},
    )
    assert response.status_code == 422


def test_refill_reminder_rejects_nonpositive_supply(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/reminders/refill",
        json={
            "medicine_name": "Synthetic Medicine",
            "initial_quantity": 0,
            "frequency_per_day": 1,
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("medicine_name", ["", "   ", "\t\n"])
def test_blank_medicine_name_is_rejected(authenticated_client, medicine_name, monkeypatch):
    monkeypatch.setattr(reminders.celery, "add_periodic_task", Mock())
    monkeypatch.setattr(reminders.crud_reminder, "add_daily_reminder_to_user", AsyncMock())
    response = authenticated_client.post(
        "/api/v1/reminders/daily",
        json={"medicine_name": medicine_name, "timings": ["morning"]},
    )
    assert response.status_code == 422


def test_refill_rejects_whitespace_medicine_name(authenticated_client):
    response = authenticated_client.post(
        "/api/v1/reminders/refill",
        json={"medicine_name": " \t ", "initial_quantity": 14, "frequency_per_day": 2},
    )
    assert response.status_code == 422


def test_daily_reminder_schedules_each_selected_time_for_token_user(
    authenticated_client, fake_user, monkeypatch
):
    scheduled = []
    saved = AsyncMock()
    monkeypatch.setattr(reminders.celery, "add_periodic_task", Mock(side_effect=lambda *a, **k: scheduled.append((a, k))))
    monkeypatch.setattr(reminders.crud_reminder, "add_daily_reminder_to_user", saved)

    response = authenticated_client.post(
        "/api/v1/reminders/daily",
        json={"medicine_name": "Synthetic Medicine", "timings": ["morning", "evening"]},
    )

    assert response.status_code == 201
    assert len(scheduled) == 2
    assert saved.await_args.kwargs["user_id"] == str(fake_user.id)


def test_refill_reminder_queues_task_and_persists_for_token_user(
    authenticated_client, fake_user, monkeypatch
):
    queue_task = Mock(return_value=SimpleNamespace(id="synthetic-celery-task"))
    saved = AsyncMock()
    monkeypatch.setattr(reminders.send_refill_reminder_task, "apply_async", queue_task)
    monkeypatch.setattr(reminders.crud_reminder, "add_refill_reminder_to_user", saved)

    response = authenticated_client.post(
        "/api/v1/reminders/refill",
        json={
            "medicine_name": "Synthetic Medicine",
            "initial_quantity": 14,
            "frequency_per_day": 2,
        },
    )

    assert response.status_code == 201
    assert response.json()["celery_task_id"] == "synthetic-celery-task"
    assert queue_task.call_args.kwargs["args"] == [
        fake_user.name,
        fake_user.phone_number,
        "Synthetic Medicine",
    ]
    assert saved.await_args.kwargs["user_id"] == str(fake_user.id)


@pytest.mark.parametrize("message", ["", "   ", "\t\n"])
def test_blank_chat_message_is_rejected_before_provider_call(client, monkeypatch, message):
    get_model = Mock()
    monkeypatch.setattr(chat, "get_chat_model", get_model)

    response = client.post("/api/v1/chat/", json={"message": message})

    assert response.status_code == 422
    get_model.assert_not_called()


def test_valid_chat_message_calls_provider(client, monkeypatch):
    model = Mock(generate_content=Mock(return_value=SimpleNamespace(text="Synthetic response")))
    get_model = Mock(return_value=model)
    monkeypatch.setattr(chat, "get_chat_model", get_model)

    response = client.post("/api/v1/chat/", json={"message": "  synthetic health question  "})

    assert response.status_code == 200
    assert response.json() == {"response": "Synthetic response"}
    get_model.assert_called_once_with()
    assert "synthetic health question" in model.generate_content.call_args.args[0]


def test_chat_upstream_error_does_not_leak_provider_details(client, monkeypatch, caplog):
    class FailingModel:
        def generate_content(self, prompt):
            raise RuntimeError("https://provider.invalid credential=synthetic-secret")

    monkeypatch.setattr(chat, "get_chat_model", lambda: FailingModel())

    response = client.post("/api/v1/chat/", json={"message": "synthetic health question"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The healthcare assistant is temporarily unavailable."
    assert "provider.invalid" not in response.text
    assert "synthetic-secret" not in response.text
    assert "provider.invalid" not in caplog.text
    assert "synthetic-secret" not in caplog.text


def test_pharmacy_query_validates_required_coordinate_and_numeric_types(client):
    missing_latitude = client.get("/api/v1/maps/pharmacies", params={"lng": 10})
    invalid_latitude = client.get(
        "/api/v1/maps/pharmacies", params={"lat": "north", "lng": 10}
    )
    assert missing_latitude.status_code == 422
    assert invalid_latitude.status_code == 422


def test_pharmacy_external_failure_is_observed_without_external_call(client, monkeypatch):
    class FailingGoogleMaps:
        def places_nearby(self, **kwargs):
            raise RuntimeError("synthetic Maps upstream failure")

    monkeypatch.setattr(maps.maps_service, "gmaps", FailingGoogleMaps())

    response = client.get(
        "/api/v1/maps/pharmacies", params={"lat": 1, "lng": 2, "radius": 5000}
    )

    # Existing contract collapses a Maps failure into an empty successful result.
    assert response.status_code == 200
    assert response.json() == []


def test_chat_model_input_type_is_validated(client):
    response = client.post("/api/v1/chat/", json={"message": 42})
    assert response.status_code == 422


def test_user_record_endpoint_rejects_unauthenticated_access(client, fake_user):
    response = client.get(f"/api/v1/users/{fake_user.id}")

    assert response.status_code == 401


def test_user_profile_is_self_only_and_excludes_password_fields(
    authenticated_client, fake_user
):
    own_profile = authenticated_client.get(f"/api/v1/users/{fake_user.id}")
    other_profile = authenticated_client.get("/api/v1/users/65a000000000000000000002")

    assert own_profile.status_code == 200
    assert "hashed_password" not in own_profile.json()
    assert not any("password" in key.lower() for key in own_profile.json())
    assert other_profile.status_code == 404
