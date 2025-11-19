from datetime import datetime, timedelta
from utils.parser import parse_timetable
from database import get_db, Task
import json

def generate_daily_schedule(user_id: int, timetable_file: str = None):
    db = next(get_db())
    events = parse_timetable(timetable_file) if timetable_file else []
    tasks = db.query(Task).filter_by(user_id=user_id).all()
    
    # Simple adaptive: Prioritize overdue
    overdue = [t for t in tasks if t.due_date < datetime.now() and not t.completed]
    today_tasks = [t for t in tasks if t.due_date.date() == datetime.now().date()]
    
    plan = {
        "today": today_tasks + events,
        "forecast_tomorrow": [t for t in tasks if t.due_date.date() == datetime.now().date() + timedelta(days=1)],
        "insights": {"completion_rate": len([t for t in today_tasks if t.completed]) / len(today_tasks) if today_tasks else 0}
    }
    return json.dumps(plan)

def add_task(user_id: int, task_data: dict):
    db = next(get_db())
    new_task = Task(**task_data, user_id=user_id)
    db.add(new_task)
    db.commit()
    return new_task.id