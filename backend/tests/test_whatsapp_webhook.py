"""Tests for the WhatsApp webhook verification and delivery-status handling."""

import hashlib
import hmac
import json

from bson import ObjectId

from app.core.config import settings


def test_webhook_verification_accepts_the_configured_token(client):
    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": 12345,
            "hub.verify_token": settings.WHATSAPP_VERIFY_TOKEN,
        },
    )
    assert response.status_code == 200
    assert response.json() == 12345


def test_webhook_verification_rejects_a_mismatched_token(client):
    response = client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": 12345,
            "hub.verify_token": "synthetic-wrong-token",
        },
    )
    assert response.status_code == 403


def _status_payload(message_id, status):
    return {
        "entry": [
            {"changes": [{"value": {"statuses": [{"id": message_id, "status": status}]}}]}
        ]
    }


def test_delivery_callback_updates_matching_delivery(client, fake_db):
    fake_db.reminder_deliveries.documents = [
        {"_id": ObjectId(), "delivery_key": "k", "provider_message_id": "wamid.1", "status": "sent"}
    ]

    response = client.post("/api/v1/webhooks/whatsapp", json=_status_payload("wamid.1", "delivered"))

    assert response.status_code == 200
    document = fake_db.reminder_deliveries.documents[0]
    assert document["status"] == "delivered"
    assert document["provider_status"] == "delivered"


def test_read_receipt_is_recorded_as_delivered(client, fake_db):
    fake_db.reminder_deliveries.documents = [
        {"_id": ObjectId(), "delivery_key": "k", "provider_message_id": "wamid.2", "status": "sent"}
    ]

    client.post("/api/v1/webhooks/whatsapp", json=_status_payload("wamid.2", "read"))

    assert fake_db.reminder_deliveries.documents[0]["status"] == "delivered"


def test_failed_status_is_recorded(client, fake_db):
    fake_db.reminder_deliveries.documents = [
        {"_id": ObjectId(), "delivery_key": "k", "provider_message_id": "wamid.3", "status": "sent"}
    ]

    client.post("/api/v1/webhooks/whatsapp", json=_status_payload("wamid.3", "failed"))

    assert fake_db.reminder_deliveries.documents[0]["status"] == "failed"


def test_unknown_message_id_is_ignored(client, fake_db):
    fake_db.reminder_deliveries.documents = [
        {"_id": ObjectId(), "delivery_key": "k", "provider_message_id": "wamid.known", "status": "sent"}
    ]

    response = client.post("/api/v1/webhooks/whatsapp", json=_status_payload("wamid.unknown", "delivered"))

    assert response.status_code == 200
    assert fake_db.reminder_deliveries.documents[0]["status"] == "sent"


def test_malformed_payload_is_accepted_without_error(client):
    response = client.post(
        "/api/v1/webhooks/whatsapp",
        content=b"not-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_configured_app_secret_requires_a_valid_signature(client, fake_db, monkeypatch):
    monkeypatch.setattr(settings, "WHATSAPP_APP_SECRET", "synthetic-app-secret")
    fake_db.reminder_deliveries.documents = [
        {"_id": ObjectId(), "delivery_key": "k", "provider_message_id": "wamid.4", "status": "sent"}
    ]
    body = json.dumps(_status_payload("wamid.4", "delivered")).encode("utf-8")

    unsigned = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={"Content-Type": "application/json"},
    )
    assert unsigned.status_code == 403
    assert fake_db.reminder_deliveries.documents[0]["status"] == "sent"

    signature = hmac.new(b"synthetic-app-secret", body, hashlib.sha256).hexdigest()
    signed = client.post(
        "/api/v1/webhooks/whatsapp",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    assert signed.status_code == 200
    assert fake_db.reminder_deliveries.documents[0]["status"] == "delivered"
