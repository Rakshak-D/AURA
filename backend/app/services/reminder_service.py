from apscheduler.schedulers.background import BackgroundScheduler
from ..database import get_db, Task  # FIXED: Relative import
from datetime import datetime, timedelta # FIXED: Added missing imports
import smtplib

# Local scheduler for reminders
scheduler = BackgroundScheduler()
scheduler.start()

def schedule_reminder(task_id: int, reminder_time: datetime):
    def send_reminder():
        # Create a new DB session for this background job
        db_gen = get_db()
        db = next(db_gen)
        try:
            task = db.query(Task).get(task_id)
            if task:
                print(f"Reminder: {task.title} due now!")
        except Exception as e:
            print(f"Error sending reminder: {e}")
        finally:
            db.close()
            
    scheduler.add_job(send_reminder, 'date', run_date=reminder_time)

def check_adaptive(user_id: int):
    # Create a new DB session
    db_gen = get_db()
    db = next(db_gen)
    try:
        tasks = db.query(Task).filter_by(user_id=user_id).all()
        now = datetime.now()
        
        # Find tasks that are overdue and not completed
        late_tasks = [t for t in tasks if t.due_date and t.due_date < now and not t.completed]
        
        if late_tasks:
            print(f"Found {len(late_tasks)} late tasks. Adjusting schedule...")
            for t in tasks:
                # Push future tasks back by 1 hour
                if t.due_date and t.due_date > now:
                    t.due_date += timedelta(hours=1)
            db.commit()
    except Exception as e:
        print(f"Error in adaptive check: {e}")
    finally:
        db.close()