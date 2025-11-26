from apscheduler.schedulers.background import BackgroundScheduler
from ..database import SessionLocal, Task
from datetime import datetime
import asyncio
# We need a way to send messages. Since scheduler runs in a thread, we need to be careful.
# Ideally, we'd use a queue or similar, but for now let's try to import the manager if possible, 
# or better: move manager to a separate file.
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
        tasks = db.query(Task).filter(
            Task.due_date <= now, 
            Task.completed == False
        ).all()
        
        for task in tasks:
            # This is a simple console log; in a real app, you'd check if you already notified
            print(f"🔔 OVERDUE: {task.title}")
    except Exception as e:
        print(f"Scheduler error: {e}")
    finally:
        db.close()

def start_scheduler():
    if not scheduler.running:
        # Add the polling job
        scheduler.add_job(check_reminders, 'interval', minutes=15)
        scheduler.start()
        print("--- Scheduler Started ---")