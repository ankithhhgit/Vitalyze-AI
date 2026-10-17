from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from bson import ObjectId
import pytest

from app.api.v1.endpoints import auth, chat, maps, medicines, reminders, reports
from app.models.user import Token
from app.models.user import DailyReminder, RefillReminder
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
        "/api/v1/auth/me",
        "/api/v1/reminders",
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


def test_registration_response_does_not_expose_password_hash(client, monkeypatch, fake_user):
    monkeypatch.setattr(auth.crud_user, "get_user_by_phone_number", AsyncMock(return_value=None))
    monkeypatch.setattr(auth.crud_user, "create_user", AsyncMock(return_value=fake_user))

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Synthetic Test User",
            "phone_number": "+15555550123",
            "password": "synthetic-password",
            "age": 30,
            "gender": "other",
        },
    )

    assert response.status_code == 201
    assert not any("password" in key.lower() for key in response.json())


def test_current_user_profile_requires_authentication(client):
    assert client.get("/api/v1/auth/me").status_code == 401


def test_current_user_profile_excludes_password_fields(authenticated_client, fake_user):
    response = authenticated_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["phone_number"] == fake_user.phone_number
    assert not any("password" in key.lower() for key in response.json())


def test_registration_rejects_non_e164_phone_without_calling_database(client, monkeypatch):
    lookup = AsyncMock()
    monkeypatch.setattr(auth.crud_user, "get_user_by_phone_number", lookup)

    response = client.post(
        "/api/v1/auth/register",
        json={
            "name": "Synthetic Test User",
            "phone_number": "(555) 555-0123",
            "password": "synthetic-password",
        },
    )

    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    lookup.assert_not_awaited()


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


def test_local_extraction_status_points_to_owned_history_text(
    authenticated_client, fake_user, fake_db, monkeypatch
):
    report_id = ObjectId("65a000000000000000000010")
    fake_db.report_jobs.records["synthetic-report-task"] = {
        "_id": "synthetic-report-task",
        "user_id": str(fake_user.id),
    }
    fake_db.reports.documents = [report_document(str(fake_user.id), report_id=report_id)]
    task_result = {
        "status": "COMPLETED",
        "analysis_mode": "local_extraction_preview",
        "report_id": str(report_id),
        "simple_summary": "LOCAL EXTRACTION PREVIEW — AI interpretation is unavailable.",
    }
    monkeypatch.setattr(
        reports,
        "AsyncResult",
        Mock(return_value=SimpleNamespace(state="SUCCESS", result=task_result)),
    )

    status_response = authenticated_client.get("/api/v1/reports/status/synthetic-report-task")
    history_response = authenticated_client.get("/api/v1/reports/history")

    assert status_response.status_code == 200
    assert status_response.json()["result"]["analysis_mode"] == "local_extraction_preview"
    assert status_response.json()["result"]["report_id"] == str(report_id)
    assert history_response.status_code == 200
    saved_report = history_response.json()[0]
    assert (saved_report.get("id") or saved_report.get("_id")) == str(report_id)
    assert saved_report["raw_text"] == "Synthetic report text for automated tests."


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
        "error": "Report processing failed. The report was not saved.",
    }
    assert "synthetic database diagnostic" not in response.text


def test_report_upload_persists_task_owner_before_returning_id(
    authenticated_client, fake_db, fake_user, monkeypatch, tmp_path
):
    class FakeWorkflow:
        def apply_async(self):
            return SimpleNamespace(id="synthetic-queued-task")

    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "chain", Mock(return_value=FakeWorkflow()))

    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"file": ("synthetic-report.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )

    assert response.status_code == 202
    assert response.json()["task_id"] == "synthetic-queued-task"
    assert fake_db.report_jobs.records["synthetic-queued-task"]["user_id"] == str(fake_user.id)


def test_report_upload_requires_the_backend_file_multipart_field(
    authenticated_client, monkeypatch, tmp_path
):
    queue = Mock()
    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "chain", queue)

    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"report": ("synthetic-report.pdf", b"%PDF-1.4 synthetic", "application/pdf")},
    )

    assert response.status_code == 422
    assert any(item["loc"][-1] == "file" for item in response.json()["detail"])
    queue.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_report_upload_rejects_invalid_pdf_before_queueing(
    authenticated_client, monkeypatch, tmp_path
):
    queue = Mock()
    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "chain", queue)
    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"file": ("synthetic-invalid.pdf", b"not a PDF", "application/pdf")},
    )
    assert response.status_code == 400
    queue.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_report_upload_rejects_oversized_pdf_before_queueing(
    authenticated_client, monkeypatch, tmp_path
):
    queue = Mock()
    monkeypatch.setattr(reports, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(reports, "MAX_REPORT_SIZE_BYTES", 8)
    monkeypatch.setattr(reports, "chain", queue)
    response = authenticated_client.post(
        "/api/v1/reports/upload",
        files={"file": ("synthetic-large.pdf", b"%PDF-1.4 larger than limit", "application/pdf")},
    )
    assert response.status_code == 413
    queue.assert_not_called()
    assert list(tmp_path.iterdir()) == []


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


def test_reminder_history_returns_only_authenticated_profile_records(authenticated_client, fake_user):
    fake_user.daily_reminders = []
    fake_user.refill_reminders = []
    response = authenticated_client.get("/api/v1/reminders")
    assert response.status_code == 200
    assert response.json() == {"daily_reminders": [], "refill_reminders": []}


@pytest.mark.parametrize("medicine_name", ["", "   ", "\t\n"])
def test_blank_medicine_name_is_rejected(authenticated_client, medicine_name, monkeypatch):
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


def test_daily_reminder_saves_times_and_timezone_for_token_user(
    authenticated_client, fake_user, monkeypatch
):
    saved = AsyncMock()
    monkeypatch.setattr(reminders.crud_reminder, "add_daily_reminder_to_user", saved)

    response = authenticated_client.post(
        "/api/v1/reminders/daily",
        json={"medicine_name": "Synthetic Medicine", "times": ["10:00", "21:00"]},
    )

    assert response.status_code == 201
    assert saved.await_args.kwargs["user_id"] == str(fake_user.id)
    reminder = saved.await_args.kwargs["reminder"]
    assert reminder.times == ["10:00", "21:00"]
    assert reminder.timezone == "Asia/Kolkata"
    assert response.json()["delivery_status"].startswith("saved;")


def test_daily_reminder_defaults_to_three_local_times(authenticated_client, monkeypatch):
    saved = AsyncMock()
    monkeypatch.setattr(reminders.crud_reminder, "add_daily_reminder_to_user", saved)
    response = authenticated_client.post(
        "/api/v1/reminders/daily", json={"medicine_name": "Synthetic Medicine"}
    )
    assert response.status_code == 201
    reminder = saved.await_args.kwargs["reminder"]
    assert reminder.times == ["10:00", "14:00", "21:00"]
    assert reminder.timezone == "Asia/Kolkata"


@pytest.mark.parametrize("payload", [
    {"times": ["24:00"]},
    {"times": ["10:00", "10:00"]},
    {"times": ["10:00"], "timezone": "not/a-zone"},
])
def test_daily_reminder_rejects_invalid_time_or_timezone(authenticated_client, payload):
    response = authenticated_client.post(
        "/api/v1/reminders/daily", json={"medicine_name": "Synthetic Medicine", **payload}
    )
    assert response.status_code == 422


def test_duplicate_daily_reminder_is_not_scheduled_again(
    authenticated_client, fake_user, monkeypatch
):
    fake_user.daily_reminders = [DailyReminder(medicine_name="Synthetic Medicine", timings=["morning"])]
    save = AsyncMock()
    monkeypatch.setattr(reminders.crud_reminder, "add_daily_reminder_to_user", save)
    response = authenticated_client.post(
        "/api/v1/reminders/daily",
        json={"medicine_name": " synthetic medicine ", "timings": ["morning"]},
    )
    assert response.status_code == 409
    save.assert_not_awaited()


def test_reminder_preferences_and_delete_are_scoped_to_owned_record(
    authenticated_client, fake_user, fake_db
):
    reminder = DailyReminder(medicine_name="Synthetic Medicine", times=["10:00", "14:00"])
    fake_user.daily_reminders = [reminder]
    reminder_id = str(reminder.id)

    updated = authenticated_client.patch(
        f"/api/v1/reminders/daily/{reminder_id}",
        json={
            "times": ["14:00", "21:00"],
            "timezone": "Asia/Kolkata",
            "local_notifications_enabled": False,
            "whatsapp_opt_in": True,
            "is_active": True,
        },
    )
    assert updated.status_code == 200
    assert fake_db.users.update_query["_id"] == fake_user.id
    assert fake_db.users.update_query["daily_reminders._id"] == ObjectId(reminder_id)
    assert fake_db.users.update_operation["$set"]["daily_reminders.$.whatsapp_opt_in"] is True

    unknown = authenticated_client.delete("/api/v1/reminders/daily/65a000000000000000000099")
    assert unknown.status_code == 404


def test_whatsapp_readiness_reports_disabled_delivery_without_secrets(authenticated_client, monkeypatch):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "false")
    monkeypatch.setattr(reminders.whatsapp_service, "is_configured", lambda _template: False)
    response = authenticated_client.get("/api/v1/reminders/status")
    assert response.status_code == 200
    assert response.json()["whatsapp_enabled"] is False
    assert response.json()["phone_verified"] is False
    assert response.json()["status"] == "not_configured"
    assert "token" not in response.text.lower()


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
        False,
        False,
    ]
    assert saved.await_args.kwargs["user_id"] == str(fake_user.id)


def test_duplicate_refill_reminder_is_not_queued_again(
    authenticated_client, fake_user, monkeypatch
):
    fake_user.refill_reminders = [
        RefillReminder(
            medicine_name="Synthetic Medicine",
            initial_quantity=14,
            frequency_per_day=2,
            refill_date=datetime(2026, 2, 1),
            celery_task_id="synthetic-task",
        )
    ]
    queue = Mock()
    save = AsyncMock()
    monkeypatch.setattr(reminders.send_refill_reminder_task, "apply_async", queue)
    monkeypatch.setattr(reminders.crud_reminder, "add_refill_reminder_to_user", save)
    response = authenticated_client.post(
        "/api/v1/reminders/refill",
        json={"medicine_name": "synthetic medicine", "initial_quantity": 14, "frequency_per_day": 2},
    )
    assert response.status_code == 409
    queue.assert_not_called()
    save.assert_not_awaited()


@pytest.mark.parametrize("message", ["", "   ", "\t\n"])
def test_blank_chat_message_is_rejected_before_provider_call(authenticated_client, monkeypatch, message):
    get_model = Mock()
    monkeypatch.setattr(chat, "get_chat_model", get_model)

    response = authenticated_client.post("/api/v1/chat/", json={"message": message})

    assert response.status_code == 422
    get_model.assert_not_called()


def test_valid_chat_message_calls_provider(authenticated_client, monkeypatch):
    model = Mock(generate_content=Mock(return_value=SimpleNamespace(text="Synthetic response")))
    get_model = Mock(return_value=model)
    monkeypatch.setattr(chat, "get_chat_model", get_model)

    response = authenticated_client.post("/api/v1/chat/", json={"message": "  synthetic health question  "})

    assert response.status_code == 200
    assert response.json() == {"response": "Synthetic response"}
    get_model.assert_called_once_with()
    assert "synthetic health question" in model.generate_content.call_args.args[0]


def test_chat_upstream_error_does_not_leak_provider_details(authenticated_client, monkeypatch, caplog):
    class FailingModel:
        def generate_content(self, prompt):
            raise RuntimeError("https://provider.invalid credential=synthetic-secret")

    monkeypatch.setattr(chat, "get_chat_model", lambda: FailingModel())

    response = authenticated_client.post("/api/v1/chat/", json={"message": "synthetic health question"})

    assert response.status_code == 502
    assert response.json()["detail"] == "The healthcare assistant is temporarily unavailable."
    assert "provider.invalid" not in response.text
    assert "synthetic-secret" not in response.text
    assert "provider.invalid" not in caplog.text
    assert "synthetic-secret" not in caplog.text


def test_chat_missing_configuration_is_distinct_from_provider_failure(authenticated_client, monkeypatch, caplog):
    def missing_credentials():
        raise FileNotFoundError("/private/path/credential.json")

    monkeypatch.setattr(chat, "get_chat_model", missing_credentials)

    response = authenticated_client.post("/api/v1/chat/", json={"message": "synthetic health question"})

    assert response.status_code == 503
    assert response.json()["detail"] == "The healthcare assistant is not configured on the backend."
    assert "/private/path" not in response.text + caplog.text


def test_pharmacy_query_validates_required_coordinate_and_numeric_types(authenticated_client):
    missing_latitude = authenticated_client.get("/api/v1/maps/pharmacies", params={"lng": 10})
    invalid_latitude = authenticated_client.get(
        "/api/v1/maps/pharmacies", params={"lat": "north", "lng": 10}
    )
    assert missing_latitude.status_code == 422
    assert invalid_latitude.status_code == 422


def test_pharmacy_search_returns_geoapify_results(authenticated_client, monkeypatch):
    monkeypatch.setattr(maps.maps_service, "api_key", "synthetic-key")
    monkeypatch.setattr(
        maps.maps_service,
        "get_nearby_pharmacies",
        lambda lat, lng, radius: [
            {
                "name": "Synthetic Pharmacy",
                "vicinity": "1 Synthetic Street",
                "rating": None,
                "user_ratings_total": None,
                "geometry": {"lat": lat, "lng": lng},
                "place_id": "geoapify-place-1",
            }
        ],
    )

    response = authenticated_client.get(
        "/api/v1/maps/pharmacies", params={"lat": 1.5, "lng": 2.5, "radius": 3000}
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "name": "Synthetic Pharmacy",
            "vicinity": "1 Synthetic Street",
            "rating": None,
            "user_ratings_total": None,
            "geometry": {"lat": 1.5, "lng": 2.5},
            "place_id": "geoapify-place-1",
        }
    ]


def test_pharmacy_search_empty_results_returns_empty_list(authenticated_client, monkeypatch):
    monkeypatch.setattr(maps.maps_service, "api_key", "synthetic-key")
    monkeypatch.setattr(maps.maps_service, "get_nearby_pharmacies", lambda *args, **kwargs: [])

    response = authenticated_client.get("/api/v1/maps/pharmacies", params={"lat": 1, "lng": 2})

    assert response.status_code == 200
    assert response.json() == []


def test_pharmacy_external_failure_is_generic_and_not_reported_as_empty_success(
    authenticated_client, monkeypatch, caplog
):
    import requests

    from app.services import maps_service as maps_service_module

    monkeypatch.setattr(maps.maps_service, "api_key", "synthetic-key")

    def boom(*args, **kwargs):
        raise requests.ConnectionError("https://maps.invalid?key=synthetic-secret")

    monkeypatch.setattr(maps_service_module.requests, "get", boom)

    with caplog.at_level("ERROR"):
        response = authenticated_client.get(
            "/api/v1/maps/pharmacies", params={"lat": 1, "lng": 2, "radius": 5000}
        )

    assert response.status_code == 502
    assert response.json()["detail"] == "The pharmacy provider is temporarily unavailable."
    assert "maps.invalid" not in response.text + caplog.text
    assert "synthetic-secret" not in response.text + caplog.text


def test_pharmacy_provider_timeout_returns_504(authenticated_client, monkeypatch):
    import requests

    from app.services import maps_service as maps_service_module

    monkeypatch.setattr(maps.maps_service, "api_key", "synthetic-key")

    def boom(*args, **kwargs):
        raise requests.Timeout("synthetic timeout")

    monkeypatch.setattr(maps_service_module.requests, "get", boom)

    response = authenticated_client.get(
        "/api/v1/maps/pharmacies", params={"lat": 1, "lng": 2, "radius": 5000}
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "The pharmacy provider timed out. Please try again."


def test_pharmacy_missing_key_returns_clear_configuration_state(authenticated_client, monkeypatch):
    monkeypatch.setattr(maps.maps_service, "api_key", "")

    response = authenticated_client.get(
        "/api/v1/maps/pharmacies", params={"lat": 1, "lng": 2, "radius": 5000}
    )

    assert response.status_code == 503
    assert "GEOAPIFY_API_KEY" in response.json()["detail"]


def test_chat_model_input_type_is_validated(authenticated_client):
    response = authenticated_client.post("/api/v1/chat/", json={"message": 42})
    assert response.status_code == 422


def test_chat_uses_gemini_service_not_vertex(authenticated_client, monkeypatch):
    from app.services import gemini_service

    captured = {}

    def fake_generate_content(model, contents, config=None):
        captured["prompt"] = contents
        return SimpleNamespace(text="Synthetic Gemini answer")

    class FakeModels:
        generate_content = staticmethod(fake_generate_content)

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(gemini_service, "get_client", lambda: fake_client)
    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "synthetic-key")

    response = authenticated_client.post(
        "/api/v1/chat/", json={"message": "synthetic health question"}
    )

    assert response.status_code == 200
    assert response.json() == {"response": "Synthetic Gemini answer"}
    assert "synthetic health question" in captured["prompt"]


def test_chat_missing_gemini_key_returns_503(authenticated_client, monkeypatch):
    from app.services import gemini_service

    monkeypatch.setattr(gemini_service.settings, "GEMINI_API_KEY", "")

    response = authenticated_client.post(
        "/api/v1/chat/", json={"message": "synthetic health question"}
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "The healthcare assistant is not configured on the backend."


def test_user_record_endpoint_rejects_unauthenticated_access(client, fake_user):
    response = client.get(f"/api/v1/users/{fake_user.id}")

    assert response.status_code == 401


def test_chat_and_locator_require_authentication(client):
    assert client.post("/api/v1/chat/", json={"message": "synthetic"}).status_code == 401
    assert client.get("/api/v1/maps/pharmacies", params={"lat": 0, "lng": 0}).status_code == 401


def test_medicine_route_reports_missing_vertex_credentials(client):
    response = client.get("/api/v1/medicines/Synthetic%20Medicine")
    assert response.status_code == 503
    assert "backend AI provider configuration" in response.json()["detail"]


def test_locator_rejects_out_of_range_coordinates_and_radius(authenticated_client):
    response = authenticated_client.get(
        "/api/v1/maps/pharmacies", params={"lat": 91, "lng": 181, "radius": 100000}
    )
    assert response.status_code == 422


def test_user_profile_is_self_only_and_excludes_password_fields(
    authenticated_client, fake_user
):
    own_profile = authenticated_client.get(f"/api/v1/users/{fake_user.id}")
    other_profile = authenticated_client.get("/api/v1/users/65a000000000000000000002")

    assert own_profile.status_code == 200
    assert "hashed_password" not in own_profile.json()
    assert not any("password" in key.lower() for key in own_profile.json())
    assert other_profile.status_code == 404
