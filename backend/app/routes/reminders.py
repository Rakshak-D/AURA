from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..database import get_db
from ..models.pydantic_models import ReminderCreate
from ..models.sql_models import Reminder, Task
from ..services.reminder_service import schedule_reminder

router = APIRouter()

@router.post("/reminders")
def add_reminder(rem: ReminderCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    user_id = current_user_id
    task = db.query(Task).filter(Task.id == rem.task_id, Task.user_id == user_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    reminder = Reminder(
        user_id=user_id,
        task_id=task.id,
        reminder_time=rem.reminder_time,
        timezone=rem.timezone,
    )
    db.add(reminder)
    try:
        db.commit()
        db.refresh(reminder)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to persist reminder")
    try:
        schedule_reminder(task.id, user_id, rem.reminder_time)
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Reminder persisted but scheduler registration was unavailable id=%s",
            reminder.id,
        )
    return {"status": "persisted", "id": reminder.id}


@router.delete("/reminders/{reminder_id}")
def cancel_reminder(
    reminder_id: int,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    reminder = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user_id,
    ).first()
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    if reminder.status == "sent":
        raise HTTPException(status_code=409, detail="Sent reminders cannot be cancelled")
    reminder.status = "cancelled"
    db.commit()
    return {"status": "cancelled", "id": reminder.id}
