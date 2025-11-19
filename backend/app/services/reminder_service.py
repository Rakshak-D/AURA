from apscheduler.schedulers.background import BackgroundScheduler
from database import get_db, Task
import smtplib  # Stub: Use local notify or print

scheduler = BackgroundScheduler()
scheduler.start()

def schedule_reminder(task_id: int, time: datetime):
    def send_reminder():
        db = next(get_db())
        task = db.query(Task).get(task_id)
        print(f"Reminder: {task.title} due now!")  # Replace with TTS or notify
    scheduler.add_job(send_reminder, 'date', run_date=time)

def check_adaptive(user_id: int):
    # If late, adjust next tasks
    db = next(get_db())
    tasks = db.query(Task).filter_by(user_id=user_id).all()
    now = datetime.now()
    late_tasks = [t for t in tasks if t.due_date < now and not t.completed]
    if late_tasks:
        for t in tasks:
            if t.due_date > now:
                t.due_date += timedelta(hours=1)  # Simple adjust
        db.commit()