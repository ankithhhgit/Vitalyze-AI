
import logging
from .celery_app import celery
from app.services import whatsapp_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@celery.task
def send_daily_reminder_task(user_name: str, phone_number: str, medicine_name: str):
    """Celery task to send a daily medicine reminder via WhatsApp."""
    logger.info("Executing daily reminder task.")
    
    template_name = "medication_reminder_v3"
    
    template_params = [user_name, medicine_name]
    
    success = whatsapp_service.send_template_message(phone_number, template_name, template_params)
    
    if success:
        return "Daily reminder sent."
    else:
        return "Daily reminder failed."
    


@celery.task
def send_refill_reminder_task(user_name: str, phone_number: str, medicine_name: str):
    """Celery task to send a refill reminder via WhatsApp."""
    logger.info("Executing refill reminder task.")
    
    template_name = "refill_reminder_v1"

    # Example Body: "Refill Reminder: Hello {{1}}, your supply of {{2}} is running low. Please remember to refill it soon."
    template_params = [user_name, medicine_name]
    
    success = whatsapp_service.send_template_message(phone_number, template_name, template_params)
    
    if success:
        return "Refill reminder sent."
    else:
        return "Refill reminder failed."
