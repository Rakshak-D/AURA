from apscheduler.schedulers.background import BackgroundScheduler
from ..database import SessionLocal, Task
from datetime import datetime

scheduler = BackgroundScheduler()

def send_notification(task_id: int):
    """
    The actual function that triggers when the timer goes off.
    """
    db = SessionLocal()
    try:
        task = db.query(Task).get(task_id)
        if task:
            print(f"🔔 REMINDER: Time to do '{task.title}'!")
    except Exception as e:
        print(f"Notification Error: {e}")
    finally:
        db.close()

def schedule_reminder(task_id: int, reminder_time: datetime):
    """
    Adds a specific one-time job to the scheduler.
    """
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