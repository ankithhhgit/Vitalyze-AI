from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from typing import List, Literal
from motor.motor_asyncio import AsyncIOMotorDatabase
from celery.schedules import crontab
from datetime import datetime, timedelta

from app.db.mongodb import get_database
from app.crud import crud_reminder  # we don't need crud_user anymore!
from app.models.user import DailyReminder, RefillReminder, UserInDB
from app.tasks.reminder_tasks import send_daily_reminder_task, send_refill_reminder_task
from app.tasks.celery_app import celery

# --- NEW IMPORT: Get the user from the token ---
# (Make sure this path is correct for your project)
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()

class DailyReminderCreate(BaseModel):
    medicine_name: str
    timings: List[Literal["morning", "afternoon", "evening"]]

    @field_validator("medicine_name")
    @classmethod
    def medicine_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medicine_name must not be blank")
        return value

class RefillReminderCreate(BaseModel):
    medicine_name: str
    initial_quantity: int = Field(..., gt=0)
    frequency_per_day: int = Field(..., gt=0)

    @field_validator("medicine_name")
    @classmethod
    def medicine_name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("medicine_name must not be blank")
        return value

TIMING_TO_CRONTAB = {
    "morning": crontab(hour=8, minute=0),
    "afternoon": crontab(hour=13, minute=0),
    "evening": crontab(hour=20, minute=0),
}

# --- 1. REMOVED {user_id} FROM URL ---
@router.post("/daily", status_code=201)
async def schedule_daily_reminder(
    reminder_in: DailyReminderCreate,
    # --- 2. ADDED CURRENT_USER DEPENDENCY ---
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Sets up a recurring daily reminder for the logged-in user.
    """
    # We no longer need to look up the user manually. 
    # 'current_user' is already loaded from the token!

    # Get the ID from the logged-in user
    user_id = str(current_user.id)

    for timing in reminder_in.timings:
        task_name = f"daily-reminder-{user_id}-{reminder_in.medicine_name}-{timing}"
        
        # We use current_user.name and current_user.phone_number directly
        celery.add_periodic_task(
            TIMING_TO_CRONTAB[timing],
            send_daily_reminder_task.s(current_user.name, current_user.phone_number, reminder_in.medicine_name),
            name=task_name
        )
    
    reminder_db = DailyReminder(**reminder_in.model_dump())
    
    # Save using the ID we got from the token
    await crud_reminder.add_daily_reminder_to_user(db, user_id=user_id, reminder=reminder_db)
    
    return {"message": "Daily reminders scheduled successfully."}


# --- 1. REMOVED {user_id} FROM URL ---
@router.post("/refill", status_code=201)
async def schedule_refill_reminder(
    reminder_in: RefillReminderCreate,
    # --- 2. ADDED CURRENT_USER DEPENDENCY ---
    current_user: UserInDB = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Schedules a one-time refill reminder for the logged-in user.
    """
    # Get the ID from the logged-in user
    user_id = str(current_user.id)

    days_of_supply = reminder_in.initial_quantity / reminder_in.frequency_per_day
    reminder_delay_days = max(0, days_of_supply - 3)
    refill_date = datetime.utcnow() + timedelta(days=reminder_delay_days)

    task = send_refill_reminder_task.apply_async(
        args=[current_user.name, current_user.phone_number, reminder_in.medicine_name],
        eta=refill_date
    )

    reminder_db = RefillReminder(
        **reminder_in.model_dump(),
        refill_date=refill_date,
        celery_task_id=task.id
    )
    
    await crud_reminder.add_refill_reminder_to_user(db, user_id=user_id, reminder=reminder_db)

    return {
        "message": "Refill reminder scheduled successfully",
        "refill_date": refill_date.isoformat(),
        "celery_task_id": task.id
    }
