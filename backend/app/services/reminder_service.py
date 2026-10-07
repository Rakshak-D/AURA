import json
import logging
from datetime import datetime

from ..database import SessionLocal
from ..models.sql_models import Task
from ..websocket_manager import manager

logger = logging.getLogger(__name__)
scheduler = None


def _get_scheduler():
    global scheduler
    if scheduler is not None:
        return scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise RuntimeError(
            "APScheduler is not installed. Install the scheduler dependency to use reminders."
        ) from exc
    scheduler = BackgroundScheduler()
    return scheduler

def send_notification(task_id: int):
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if task:
            message = json.dumps({
                "type": "reminder",
                "task": task.title,
                "task_id": task.id
            })
            logger.info("Reminder notification dispatched for task id=%s", task.id)
            manager.broadcast_sync(message)
    except Exception:
        logger.exception("Error sending reminder notification")
    finally:
        db.close()

def schedule_reminder(task_id: int, reminder_time: datetime):
    active_scheduler = _get_scheduler()
    if not active_scheduler.running:
        start_scheduler()
        
    active_scheduler.add_job(
        send_notification, 
        'date', 
        run_date=reminder_time, 
        args=[task_id]
    )
    print(f"🕒 Scheduled reminder for Task {task_id} at {reminder_time}")

def check_reminders():
    """
    Periodic check for tasks that are due (Backup polling).
    """
    db = SessionLocal()
    try:
        now = datetime.now()  # noqa: DTZ005 - temporal semantics are Phase 2 scope
        # Find tasks due within the last minute that haven't been completed
        # This is a bit simplistic, but serves as a backup
        _tasks = db.query(Task).filter(
            Task.due_date <= now, 
            Task.completed == False
        ).all()
        
        # Logic to avoid spamming would go here
    except Exception:
        logger.exception("Scheduler polling error")
    finally:
        db.close()

def start_scheduler():
    active_scheduler = _get_scheduler()
    if not active_scheduler.running:
        active_scheduler.add_job(check_reminders, 'interval', minutes=15)
        active_scheduler.start()
        logger.info("Reminder scheduler started")
