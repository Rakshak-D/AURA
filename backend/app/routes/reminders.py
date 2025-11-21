from fastapi import APIRouter
from ..services.reminder_service import schedule_reminder
from ..models.pydantic_models import ReminderCreate

router = APIRouter()

@router.post("/reminders")
def add_reminder(rem: ReminderCreate):
    schedule_reminder(rem.task_id, rem.reminder_time)
    return {"status": "scheduled"}
