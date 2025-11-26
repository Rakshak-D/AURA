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

def generate_routine(user_id: int, db: Session, date: datetime = None) -> Dict:
    """
        start_time = base_date.replace(hour=start_h, minute=start_m)
        end_time = start_time + timedelta(minutes=duration)
        
        # Add Prep Time (30 mins before classes)
        if type_ == "class":
            prep_start = start_time - timedelta(minutes=30)
            timeline.append({
                "start": prep_start.isoformat(),
                "end": start_time.isoformat(),
                "title": f"Prep for {title}",
                "type": "prep",
                "fixed": True
            })
            
        timeline.append({
            "start": start_time.isoformat(),
            "end": end_time.isoformat(),
            "title": title,
            "type": type_,
            "fixed": True
        })
        
    # 3. Add Existing Scheduled Tasks
    scheduled_tasks = db.query(Task).filter(
        Task.user_id == user_id,
        Task.due_date >= base_date,
        Task.due_date < base_date + timedelta(days=1),
        Task.completed == False
    ).all()
    
    for task in scheduled_tasks:
        duration = task.duration_minutes or 30
        end_time = task.due_date + timedelta(minutes=duration)
        timeline.append({
            "start": task.due_date.isoformat(),
            "end": end_time.isoformat(),
            "title": task.title,
            "type": "task",
            "fixed": False,
            "id": task.id,
            "priority": task.priority
        })
        
    # 4. Sort Timeline
    timeline.sort(key=lambda x: x["start"])
    
    # 5. Identify Free Blocks
    # Start checking from 8 AM to 11 PM
    day_start = base_date.replace(hour=8, minute=0)
    day_end = base_date.replace(hour=23, minute=0)
    
    final_timeline = []
    current_time = day_start
    
    for event in timeline:
        event_start = datetime.fromisoformat(event["start"])
        event_end = datetime.fromisoformat(event["end"])
        
        # If there is a gap > 15 mins, mark as Free Block
        if event_start > current_time + timedelta(minutes=15):
            final_timeline.append({
                "start": current_time.isoformat(),
                "end": event_start.isoformat(),
                "title": "Free Block",
                "type": "free",
                "duration": (event_start - current_time).seconds // 60
            })
            
        final_timeline.append(event)
        if event_end > current_time:
            current_time = event_end
            
    # Check for final free block until day end
    if current_time < day_end:
        final_timeline.append({
            "start": current_time.isoformat(),
            "end": day_end.isoformat(),
            "title": "Free Block",
            "type": "free",
            "duration": (day_end - current_time).seconds // 60
        })
        
    return {"date": base_date.strftime("%Y-%m-%d"), "timeline": final_timeline}

def auto_schedule_tasks(user_id: int, db: Session) -> Dict:
    """
    Automatically assign unscheduled tasks to free blocks.
    """
    # 1. Get Unscheduled Tasks (High priority first)
    unscheduled = db.query(Task).filter(
        Task.user_id == user_id,
        Task.due_date == None,
        Task.completed == False
    ).order_by(
        # Custom sort: Urgent > High > Medium > Low
        Task.priority == 'urgent',
        Task.priority == 'high',
        Task.priority == 'medium',
        Task.priority == 'low'
    ).all()
    
    if not unscheduled:
        return {"status": "no_tasks", "message": "No unscheduled tasks found."}
    
    # 2. Get Today's Routine (to find free blocks)
    routine = generate_routine(user_id, db)
    free_blocks = [b for b in routine["timeline"] if b["type"] == "free"]
    
    scheduled_count = 0
    
    for task in unscheduled:
        task_duration = task.duration_minutes or 30
        
        # Find a suitable block
        for block in free_blocks:
            block_duration = block["duration"]
            
            if block_duration >= task_duration:
                # Assign Task
                start_time = datetime.fromisoformat(block["start"])
                task.due_date = start_time
                
                # Update Block (reduce duration)
                block["start"] = (start_time + timedelta(minutes=task_duration)).isoformat()
                block["duration"] -= task_duration
                
                scheduled_count += 1
                break
    
    db.commit()
    return {
        "status": "success", 
        "scheduled": scheduled_count, 
        "message": f"Successfully auto-scheduled {scheduled_count} tasks."
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