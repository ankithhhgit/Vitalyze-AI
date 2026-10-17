import logging
from unittest.mock import Mock

import requests

from app.services import whatsapp_service
from app.tasks import reminder_tasks


def test_whatsapp_success_payload_and_logs_do_not_expose_sensitive_values(
    monkeypatch, caplog
):
    phone = "+19995550125"
    medicine = "Synthetic Medicine Name"
    response_body = {"messages": [{"id": "synthetic-provider-id"}]}
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = response_body
    response.text = str(response_body)
    post = Mock(return_value=response)
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    with caplog.at_level(logging.INFO):
        sent = whatsapp_service.send_template_message(
            phone, "synthetic-template", ["Synthetic User", medicine]
        )

    assert sent is True
    assert post.call_args.kwargs["json"]["to"] == phone
    assert post.call_args.kwargs["timeout"] == whatsapp_service.REQUEST_TIMEOUT_SECONDS
    assert "Authorization" in post.call_args.kwargs["headers"]
    assert "Synthetic User" not in caplog.text
    assert phone not in caplog.text
    assert medicine not in caplog.text
    assert "synthetic-provider-id" not in caplog.text
    assert "test-only-placeholder-token" not in caplog.text
    response.json.assert_not_called()


def test_whatsapp_failure_logs_exception_class_without_provider_details(
    monkeypatch, caplog
):
    phone = "+19995550126"
    medicine = "Synthetic Private Medicine"
    diagnostic = "synthetic-token-value https://provider.invalid private body"
    response = Mock()
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(diagnostic)
    response.text = diagnostic
    monkeypatch.setattr(whatsapp_service.requests, "post", Mock(return_value=response))

    with caplog.at_level(logging.ERROR):
        sent = whatsapp_service.send_template_message(
            phone, "synthetic-template", ["Synthetic User", medicine]
        )

    assert sent is False
    for sensitive_value in (phone, medicine, "Synthetic User", "synthetic-token-value", "provider.invalid", "private body"):
        assert sensitive_value not in caplog.text
    assert "HTTPError" in caplog.text


def test_daily_reminder_task_uses_correct_recipient_and_content_without_logging_pii(
    monkeypatch, caplog
):
    send = Mock(return_value=True)
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)

    with caplog.at_level(logging.INFO):
        result = reminder_tasks.send_daily_reminder_task.run(
            "Synthetic User", "+19995550127", "Synthetic Medicine"
        )

    send.assert_called_once_with(
        "+19995550127", "medication_reminder_v3", ["Synthetic User", "Synthetic Medicine"]
    )
    assert "Synthetic User" not in caplog.text
    assert "Synthetic Medicine" not in caplog.text
    assert "+19995550127" not in caplog.text
    assert result == "Daily reminder sent."


def test_refill_reminder_task_returns_generic_result(monkeypatch, caplog):
    monkeypatch.setattr(
        reminder_tasks.whatsapp_service,
        "send_template_message",
        Mock(return_value=False),
    )

    with caplog.at_level(logging.INFO):
        result = reminder_tasks.send_refill_reminder_task.run(
            "Synthetic User", "+19995550128", "Synthetic Medicine"
        )

    assert result == "Refill reminder failed."
    assert "Synthetic User" not in caplog.text
    assert "Synthetic Medicine" not in caplog.text
    assert "+19995550128" not in caplog.text
