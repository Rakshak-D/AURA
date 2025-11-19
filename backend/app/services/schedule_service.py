from datetime import datetime, timedelta
from ..utils.parser import parse_timetable
from ..database import Task
from sqlalchemy.orm import Session

def generate_daily_schedule(user_id: int, db: Session, timetable_file: str = None):
    events = parse_timetable(timetable_file) if timetable_file else []
    tasks = db.query(Task).filter_by(user_id=user_id).all()
    now = datetime.now()
    
    today_tasks = [t for t in tasks if t.due_date and t.due_date.date() == now.date()]
    completed_today = len([t for t in today_tasks if t.completed])
    total_today = len(today_tasks)
    
    plan = {
        "today": [{"title": t.title, "completed": t.completed} for t in today_tasks] + events,
        "forecast_tomorrow": [{"title": t.title} for t in tasks if t.due_date and t.due_date.date() == now.date() + timedelta(days=1)],
        "insights": {
            "completion_rate": (completed_today / total_today) if total_today > 0 else 0
        }
    }
    return plan

def add_task(user_id: int, task_data: dict, db: Session):
    new_task = Task(**task_data, user_id=user_id)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task.id