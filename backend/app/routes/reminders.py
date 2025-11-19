from fastapi import APIRouter
from services.reminder_service import schedule_reminder
from models.pydantic_models import Reminder

router = APIRouter()

@router.post("/reminders")
def add_reminder(rem: Reminder):
    schedule_reminder(rem.task_id, rem.time)
    return {"status": "scheduled"}