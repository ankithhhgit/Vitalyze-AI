
import requests
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)
REQUEST_TIMEOUT_SECONDS = 10

def send_template_message(
    phone_number: str, 
    template_name: str, 
    template_params: list
):
    """
    Sends a pre-approved template message using the WhatsApp Cloud API.
    """
    api_url = (
        f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
        f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    )
    
    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    
    # 1. Basic Payload (Always required)
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "en_US"},
        },
    }

    if template_params:
        payload["template"]["components"] = [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": param} for param in template_params
                ],
            }
        ]

    try:
        response = requests.post(
            api_url,
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        logger.info("WhatsApp template message sent successfully.")
        return True
    except requests.exceptions.RequestException as exc:
        # Provider errors may echo recipient data, message content, or credentials.
        logger.error("WhatsApp template message failed (%s).", type(exc).__name__)
        return False
