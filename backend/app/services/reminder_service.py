from apscheduler.schedulers.background import BackgroundScheduler
from ..database import SessionLocal
from ..models.sql_models import Task
from ..websocket_manager import manager
from datetime import datetime
import json

scheduler = BackgroundScheduler()

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
            print(f"🔔 REMINDER SENT: {task.title}")
            manager.broadcast_sync(message)
    except Exception as e:
        print(f"Error sending notification: {e}")
    finally:
        db.close()

def schedule_reminder(task_id: int, reminder_time: datetime):
    if not scheduler.running:
        start_scheduler()
        
    scheduler.add_job(
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
        now = datetime.now()
        # Find tasks due within the last minute that haven't been completed
        # This is a bit simplistic, but serves as a backup
        tasks = db.query(Task).filter(
            Task.due_date <= now, 
            Task.completed == False
        ).all()
        
        # Logic to avoid spamming would go here
    except Exception as e:
        print(f"Scheduler error: {e}")
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(check_reminders, 'interval', minutes=15)
        scheduler.start()
        print("--- Scheduler Started ---")