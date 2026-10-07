from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user_id
from ..models.sql_models import Reminder, Task
from ..services.reminder_service import schedule_reminder
from ..models.pydantic_models import ReminderCreate

router = APIRouter()

@router.post("/reminders")
def add_reminder(rem: ReminderCreate, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    user_id = current_user_id
    task = db.query(Task).filter(Task.id == rem.task_id, Task.user_id == user_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    reminder = Reminder(user_id=user_id, task_id=task.id, reminder_time=rem.reminder_time)
    db.add(reminder)
    try:
        db.commit()
        db.refresh(reminder)
        schedule_reminder(task.id, user_id, rem.reminder_time)
    except Exception:
        db.rollback()
        if reminder.id is not None:
            persisted = db.query(Reminder).filter(Reminder.id == reminder.id).first()
            if persisted is not None:
                persisted.status = "failed"
                db.commit()
        raise HTTPException(status_code=500, detail="Failed to persist reminder")
    return {"status": "scheduled", "id": reminder.id}
