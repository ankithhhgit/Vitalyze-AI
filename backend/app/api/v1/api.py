from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth, 
    users, 
    reports, 
    reminders, 
    maps, 
    chat,       
    medicines,
    webhooks
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(reminders.router, prefix="/reminders", tags=["reminders"])
api_router.include_router(maps.router, prefix="/maps", tags=["maps"])
api_router.include_router(chat.router, prefix="/chat", tags=["chat"])
api_router.include_router(medicines.router, prefix="/medicines", tags=["medicines"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])