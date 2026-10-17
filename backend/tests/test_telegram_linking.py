"""Tests for Telegram account linking: the API and the inbound webhook.

The chat id is only ever taken from an update Telegram itself delivered, and
only after a short-lived, single-use code issued to the authenticated owner is
redeemed. All provider calls are mocked so no message is ever sent.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from app.api.v1.endpoints import webhooks
from app.core.config import settings

SYNTHETIC_TOKEN = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"


@pytest.fixture(autouse=True)
def no_telegram_network(monkeypatch):
    """Guarantee no test can ever reach the Telegram API."""
    sender = Mock(return_value=None)
    monkeypatch.setattr(webhooks.telegram_service, "send_message", sender)
    return sender


def _update(chat_id, text, *, chat_type="private", username="synthetic_user"):
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id, "type": chat_type},
            "from": {"id": 1, "username": username},
            "text": text,
        },
    }


def _issue_code(client):
    response = client.post("/api/v1/reminders/telegram/link-code")
    assert response.status_code == 201
    return response.json()


def test_link_endpoints_require_authentication(client):
    assert client.post("/api/v1/reminders/telegram/link-code").status_code == 401
    assert client.get("/api/v1/reminders/telegram/status").status_code == 401
    assert client.delete("/api/v1/reminders/telegram/link").status_code == 401


def test_link_code_is_short_lived_and_leaks_no_secret_or_chat_id(
    authenticated_client, monkeypatch
):
    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "true")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", SYNTHETIC_TOKEN)
    monkeypatch.setattr(settings, "TELEGRAM_BOT_USERNAME", "VitalyzeBot")

    response = authenticated_client.post("/api/v1/reminders/telegram/link-code")

    assert response.status_code == 201
    payload = response.json()
    assert payload["code"]
    assert payload["expires_at"]
    assert 0 < payload["ttl_seconds"] <= 3600
    assert payload["deep_link"] == (
        f"https://t.me/VitalyzeBot?start={payload['code']}"
    )
    # The client is never asked for a chat id, and never receives one.
    assert "chat_id" not in payload
    # The bot token must never leave the backend.
    assert SYNTHETIC_TOKEN not in response.text
    assert "send_enabled" in payload


def test_valid_code_links_chat_from_the_owner_and_cannot_be_reused(
    authenticated_client, fake_db
):
    code = _issue_code(authenticated_client)["code"]

    first = authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(777000111, f"/start {code}")
    )
    assert first.status_code == 200
    assert fake_db.users.update_operation["$set"]["telegram_chat_id"] == "777000111"
    assert fake_db.users.update_operation["$set"]["telegram_username"] == "synthetic_user"

    # A second redemption must not bind another chat to the same account.
    fake_db.users.update_operation = None
    second = authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(999000222, f"/start {code}")
    )
    assert second.status_code == 200
    assert fake_db.users.update_operation is None


def test_confirmed_link_uses_only_the_verified_chat(
    authenticated_client, fake_db, no_telegram_network
):
    code = _issue_code(authenticated_client)["code"]

    authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(777000111, f"/start {code}")
    )

    assert no_telegram_network.call_count == 1
    # The chat id comes from the update Telegram delivered, passed through as
    # the integer it carries in JSON (send_message stringifies it for the API).
    assert no_telegram_network.call_args.args[0] == 777000111


def test_expired_code_is_not_redeemed(authenticated_client, fake_db, fake_user):
    now = datetime.now(timezone.utc)
    fake_db.telegram_link_codes.documents.append({
        "code": "Expired000001",
        "user_id": str(fake_user.id),
        "created_at": now - timedelta(minutes=30),
        "expires_at": now - timedelta(minutes=15),
        "used_at": None,
        "revoked_at": None,
    })

    response = authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(777000111, "/start Expired000001")
    )

    assert response.status_code == 200
    assert fake_db.users.update_operation is None


def test_issuing_a_new_code_revokes_the_previous_ones(authenticated_client, fake_db):
    first = _issue_code(authenticated_client)["code"]
    second = _issue_code(authenticated_client)["code"]

    codes = {document["code"]: document for document in fake_db.telegram_link_codes.documents}
    assert codes[first]["revoked_at"] is not None
    assert codes[second]["revoked_at"] is None

    # Only the newest code may be redeemed.
    authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(777000111, f"/start {second}")
    )
    fake_db.users.update_operation = None
    authenticated_client.post(
        "/api/v1/webhooks/telegram", json=_update(999000222, f"/start {first}")
    )
    assert fake_db.users.update_operation is None


def test_group_chat_is_never_linked(authenticated_client, fake_db):
    code = _issue_code(authenticated_client)["code"]

    response = authenticated_client.post(
        "/api/v1/webhooks/telegram",
        json=_update(777000111, f"/start {code}", chat_type="group"),
    )

    assert response.status_code == 200
    assert fake_db.users.update_operation is None


@pytest.mark.parametrize(
    "payload",
    [
        _update(777000111, "hello"),
        _update(777000111, "/help AbCdEf123456"),
        _update(777000111, "/start short"),
        _update("not-a-chat-id", "/start AbCdEf123456"),
        {"update_id": 1},
        {"update_id": 1, "message": "not-an-object"},
    ],
)
def test_unrecognised_updates_are_acknowledged_without_linking(
    authenticated_client, fake_db, payload
):
    response = authenticated_client.post("/api/v1/webhooks/telegram", json=payload)

    assert response.status_code == 200
    assert fake_db.users.update_operation is None


def test_malformed_body_is_accepted_without_error(authenticated_client, fake_db):
    response = authenticated_client.post(
        "/api/v1/webhooks/telegram",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert fake_db.users.update_operation is None


def test_webhook_secret_is_required_when_configured(authenticated_client, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_WEBHOOK_SECRET", "synthetic-webhook-secret")
    code = _issue_code(authenticated_client)["code"]
    body = _update(777000111, f"/start {code}")

    denied = authenticated_client.post("/api/v1/webhooks/telegram", json=body)
    assert denied.status_code == 403
    assert fake_db.users.update_operation is None

    wrong = authenticated_client.post(
        "/api/v1/webhooks/telegram",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
    )
    assert wrong.status_code == 403
    assert fake_db.users.update_operation is None

    accepted = authenticated_client.post(
        "/api/v1/webhooks/telegram",
        json=body,
        headers={"X-Telegram-Bot-Api-Secret-Token": "synthetic-webhook-secret"},
    )
    assert accepted.status_code == 200
    assert fake_db.users.update_operation["$set"]["telegram_chat_id"] == "777000111"


def test_link_status_reports_linked_chat_without_exposing_the_id(
    authenticated_client, fake_user, monkeypatch
):
    fake_user.telegram_chat_id = "777000111"
    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "true")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", SYNTHETIC_TOKEN)

    response = authenticated_client.get("/api/v1/reminders/telegram/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["telegram_linked"] is True
    assert payload["status"] == "ready"
    assert "777000111" not in response.text
    assert SYNTHETIC_TOKEN not in response.text


def test_link_status_is_not_ready_by_default(authenticated_client):
    payload = authenticated_client.get("/api/v1/reminders/telegram/status").json()

    assert payload["telegram_linked"] is False
    assert payload["status"] == "not_ready"
    assert "telegram_chat_id" not in payload


def test_unlink_clears_the_chat_binding(authenticated_client, fake_db):
    response = authenticated_client.delete("/api/v1/reminders/telegram/link")

    assert response.status_code == 200
    assert response.json() == {
        "telegram_linked": False,
        "message": "Telegram chat unlinked.",
    }
    assert fake_db.users.update_operation["$unset"]["telegram_chat_id"] == ""


def test_reminder_status_includes_telegram_readiness(authenticated_client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "true")
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", SYNTHETIC_TOKEN)

    payload = authenticated_client.get("/api/v1/reminders/status").json()

    assert payload["telegram_enabled"] is True
    assert payload["telegram_provider_ready"] is True
    assert payload["telegram_linked"] is False
    assert "telegram_message" in payload
    # WhatsApp fields that existing clients depend on stay present.
    assert "whatsapp_enabled" in payload
    assert "status" in payload
    assert SYNTHETIC_TOKEN not in str(payload)
