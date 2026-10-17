import logging
from unittest.mock import Mock

import requests

from app.services import whatsapp_service
from app.tasks import reminder_tasks


def test_whatsapp_success_payload_and_logs_do_not_expose_sensitive_values(
    monkeypatch, caplog
):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "synthetic-template")
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
            phone, "synthetic-template", ["Synthetic User", medicine],
            user_opted_in=True, phone_verified=True,
        )

    assert sent == "synthetic-provider-id"
    assert post.call_args.kwargs["json"]["to"] == phone
    assert post.call_args.kwargs["timeout"] == whatsapp_service.REQUEST_TIMEOUT_SECONDS
    assert "Authorization" in post.call_args.kwargs["headers"]
    assert "Synthetic User" not in caplog.text
    assert phone not in caplog.text
    assert medicine not in caplog.text
    assert "synthetic-provider-id" not in caplog.text
    assert "test-only-placeholder-token" not in caplog.text


def test_whatsapp_failure_logs_exception_class_without_provider_details(
    monkeypatch, caplog
):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "synthetic-template")
    phone = "+19995550126"
    medicine = "Synthetic Private Medicine"
    diagnostic = "synthetic-token-value https://provider.invalid private body"
    response = Mock()
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(diagnostic)
    response.text = diagnostic
    monkeypatch.setattr(whatsapp_service.requests, "post", Mock(return_value=response))

    with caplog.at_level(logging.ERROR):
        sent = whatsapp_service.send_template_message(
            phone, "synthetic-template", ["Synthetic User", medicine],
            user_opted_in=True, phone_verified=True,
        )

    assert sent is None
    for sensitive_value in (phone, medicine, "Synthetic User", "synthetic-token-value", "provider.invalid", "private body"):
        assert sensitive_value not in caplog.text
    assert "HTTPError" in caplog.text


def test_missing_whatsapp_configuration_never_calls_provider(monkeypatch, caplog):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "false")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "")
    post = Mock()
    monkeypatch.setattr(whatsapp_service.requests, "post", post)
    with caplog.at_level(logging.INFO):
        result = whatsapp_service.send_template_message(
            "+19995550129", "synthetic-template", ["Synthetic User", "Synthetic Medicine"]
        )
    assert result is None
    post.assert_not_called()
    assert "no message was sent" in caplog.text


def test_whatsapp_requires_explicit_send_opt_in_even_with_configured_credentials(monkeypatch):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "false")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "synthetic-template")
    post = Mock()
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    assert not whatsapp_service.send_template_message(
        "+19995550131", "synthetic-template", ["Synthetic User", "Synthetic Medicine"]
    )
    post.assert_not_called()


def test_whatsapp_requires_template_consent_and_verified_phone(monkeypatch):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "approved-template")
    post = Mock()
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    assert not whatsapp_service.send_template_message(
        "+19995550132", "other-template", [], user_opted_in=True, phone_verified=True
    )
    assert not whatsapp_service.send_template_message(
        "+19995550132", "approved-template", [], user_opted_in=False, phone_verified=True
    )
    assert not whatsapp_service.send_template_message(
        "+19995550132", "approved-template", [], user_opted_in=True, phone_verified=False
    )
    post.assert_not_called()


def test_daily_reminder_task_uses_correct_recipient_and_content_without_logging_pii(
    monkeypatch, caplog
):
    send = Mock(return_value=True)
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _template: True)

    with caplog.at_level(logging.INFO):
        result = reminder_tasks.send_daily_reminder_task.run(
            "Synthetic User", "+19995550127", "Synthetic Medicine", True, True
        )

    send.assert_called_once_with(
        "+19995550127", "medication_reminder_v3", ["Synthetic User", "Synthetic Medicine"],
        user_opted_in=True, phone_verified=True,
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
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda _template: True)

    with caplog.at_level(logging.INFO):
        result = reminder_tasks.send_refill_reminder_task.run(
            "Synthetic User", "+19995550128", "Synthetic Medicine", True, True
        )

    assert result == "Refill reminder failed."
    assert "Synthetic User" not in caplog.text
    assert "Synthetic Medicine" not in caplog.text
    assert "+19995550128" not in caplog.text


def test_unconfigured_reminder_task_stays_pending_without_calling_sender(monkeypatch):
    send = Mock()
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "is_configured", lambda *_args: False)
    monkeypatch.setattr(reminder_tasks.whatsapp_service, "send_template_message", send)
    result = reminder_tasks.send_daily_reminder_task.run(
        "Synthetic User", "+19995550130", "Synthetic Medicine"
    )
    assert result == "Pending WhatsApp configuration; message not sent."
    send.assert_not_called()


def _configure_valid_sender(monkeypatch, template_name):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MEDICATION_TEMPLATE_NAME", template_name)
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_REFILL_TEMPLATE_NAME", "")


def test_invalid_recipient_number_is_rejected_before_any_provider_call(monkeypatch, caplog):
    _configure_valid_sender(monkeypatch, "medication_reminder_v3")
    post = Mock()
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    with caplog.at_level(logging.WARNING):
        result = whatsapp_service.send_template_message(
            "555-0123", "medication_reminder_v3", ["Synthetic User"],
            user_opted_in=True, phone_verified=True,
        )

    assert result is None
    post.assert_not_called()
    assert "555-0123" not in caplog.text
    assert "E.164" in caplog.text


def test_transient_timeouts_are_retried_bounded_then_succeed(monkeypatch):
    _configure_valid_sender(monkeypatch, "medication_reminder_v3")
    monkeypatch.setattr(whatsapp_service, "RETRY_BACKOFF_SECONDS", 0.0)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"messages": [{"id": "synthetic-provider-id"}]}
    post = Mock(side_effect=[
        requests.exceptions.Timeout(),
        requests.exceptions.Timeout(),
        response,
    ])
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    result = whatsapp_service.send_template_message(
        "+19995550140", "medication_reminder_v3", ["Synthetic User"],
        user_opted_in=True, phone_verified=True,
    )

    assert result == "synthetic-provider-id"
    assert post.call_count == whatsapp_service.MAX_SEND_ATTEMPTS
    assert result is not None


def test_transient_failure_stops_after_bounded_attempts(monkeypatch):
    _configure_valid_sender(monkeypatch, "medication_reminder_v3")
    monkeypatch.setattr(whatsapp_service, "RETRY_BACKOFF_SECONDS", 0.0)
    post = Mock(side_effect=requests.exceptions.ConnectionError())
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    result = whatsapp_service.send_template_message(
        "+19995550141", "medication_reminder_v3", ["Synthetic User"],
        user_opted_in=True, phone_verified=True,
    )

    assert result is None
    assert post.call_count == whatsapp_service.MAX_SEND_ATTEMPTS


def test_permanent_provider_error_is_not_retried(monkeypatch):
    _configure_valid_sender(monkeypatch, "medication_reminder_v3")
    monkeypatch.setattr(whatsapp_service, "RETRY_BACKOFF_SECONDS", 0.0)
    response = Mock()
    response.raise_for_status.side_effect = requests.exceptions.HTTPError(
        response=Mock(status_code=400)
    )
    post = Mock(return_value=response)
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    result = whatsapp_service.send_template_message(
        "+19995550142", "medication_reminder_v3", ["Synthetic User"],
        user_opted_in=True, phone_verified=True,
    )

    assert result is None
    assert post.call_count == 1


def test_per_purpose_templates_are_each_approved_independently(monkeypatch):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MEDICATION_TEMPLATE_NAME", "medication_reminder_v3")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_REFILL_TEMPLATE_NAME", "refill_reminder_v1")

    assert whatsapp_service.is_configured("medication_reminder_v3") is True
    assert whatsapp_service.is_configured("refill_reminder_v1") is True
    assert whatsapp_service.is_configured("unapproved-template") is False


def test_unapproved_template_is_not_treated_as_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_SEND_ENABLED", "true")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_API_VERSION", "v20.0")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_ACCESS_TOKEN", "synthetic-test-token")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_PHONE_NUMBER_ID", "synthetic-test-phone-id")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_APPROVED_TEMPLATE_NAME", "")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_MEDICATION_TEMPLATE_NAME", "")
    monkeypatch.setattr(whatsapp_service.settings, "WHATSAPP_REFILL_TEMPLATE_NAME", "")
    post = Mock()
    monkeypatch.setattr(whatsapp_service.requests, "post", post)

    assert whatsapp_service.is_configured("medication_reminder_v3") is False
    assert whatsapp_service.send_template_message(
        "+19995550143", "medication_reminder_v3", ["Synthetic User"],
        user_opted_in=True, phone_verified=True,
    ) is None
    post.assert_not_called()
