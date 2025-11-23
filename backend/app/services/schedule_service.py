from sqlalchemy.orm import Session
from ..database import Task
from datetime import datetime, timedelta
from typing import Dict
import json

def generate_daily_schedule(user_id: int, db: Session) -> Dict:
    """Generate a daily schedule summary for the user"""
    try:
        tasks = db.query(Task).filter_by(user_id=user_id).all()
        
        total = len(tasks)
        completed = len([t for t in tasks if t.completed])
        pending = total - completed
        
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        today_tasks = [t for t in tasks if t.due_date and today_start <= t.due_date <= today_end and not t.completed]
        overdue_tasks = [t for t in tasks if t.due_date and t.due_date < now and not t.completed]
        upcoming_tasks = [t for t in tasks if t.due_date and t.due_date > today_end and not t.completed]
        
        return {
            "overview": {
                "total": total,
                "completed": completed,
                "pending": pending,
                "completion_rate": round((completed / total * 100) if total > 0 else 0, 1)
            },
            "today": [
                {
                    "id": t.id,
                    "title": t.title,
                    "due": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "tags": json.loads(t.tags) if t.tags else []
                }
                for t in sorted(today_tasks, key=lambda x: x.due_date or datetime.max)
            ],
            "overdue": [
                {
                    "id": t.id,
                    "title": t.title,
                    "due": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority
                }
                for t in sorted(overdue_tasks, key=lambda x: x.due_date or datetime.max)
            ],
            "upcoming": [
                {
                    "id": t.id,
                    "title": t.title,
                    "due": t.due_date.isoformat() if t.due_date else None,
                    "priority": t.priority,
                    "tags": json.loads(t.tags) if t.tags else []
                }
                for t in sorted(upcoming_tasks, key=lambda x: x.due_date or datetime.max)[:10]
            ]
        }
    except Exception as e:
        print(f"Error generating schedule: {e}")
        return {
            "overview": {"total": 0, "completed": 0, "pending": 0, "completion_rate": 0},
            "today": [],
            "overdue": [],
            "upcoming": []
        }

def get_analytics(user_id: int, db: Session, days: int = 30) -> Dict:
    """Get user analytics for the specified number of days"""
    try:
        start_date = datetime.now() - timedelta(days=days)
        
        tasks = db.query(Task).filter(
            Task.user_id == user_id,
            Task.created_at >= start_date
        ).all()
        
        completed_tasks = [t for t in tasks if t.completed]
        
        total_created = len(tasks)
        total_completed = len(completed_tasks)
        completion_rate = (total_completed / total_created * 100) if total_created > 0 else 0
        
        priority_breakdown = {
            'urgent': len([t for t in tasks if t.priority == 'urgent']),
            'high': len([t for t in tasks if t.priority == 'high']),
            'medium': len([t for t in tasks if t.priority == 'medium']),
            'low': len([t for t in tasks if t.priority == 'low'])
        }
        
        tasks_by_day = {}
        for i in range(days):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            tasks_by_day[day] = len([t for t in completed_tasks if t.completed_at and t.completed_at.strftime('%Y-%m-%d') == day])
        
        return {
            "period_days": days,
            "total_created": total_created,
            "total_completed": total_completed,
            "completion_rate": round(completion_rate, 1),
            "average_per_day": round(total_completed / days, 1),
            "priority_breakdown": priority_breakdown,
            "tasks_by_day": tasks_by_day
        }
    except Exception as e:
        print(f"Error generating analytics: {e}")
        return {}