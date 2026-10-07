from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
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
    result = db.execute(
        update(Reminder)
        .where(
            Reminder.id == reminder_id,
            Reminder.user_id == current_user_id,
            Reminder.status.in_(["pending", "failed"]),
        )
        .values(status="cancelled")
    )
    if result.rowcount == 1:
        db.commit()
        return {"status": "cancelled", "id": reminder_id}

    current = db.query(Reminder).filter(
        Reminder.id == reminder_id,
        Reminder.user_id == current_user_id,
    ).first()
    if current is None:
        db.rollback()
        raise HTTPException(status_code=404, detail="Reminder not found")
    if current.status == "cancelled":
        db.commit()
        return {"status": "cancelled", "id": reminder_id}
    db.rollback()
    raise HTTPException(status_code=409, detail="Reminder cannot be cancelled in its current state")
