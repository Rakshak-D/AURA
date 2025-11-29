from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from ..models.sql_models import Task
from ..models.pydantic_models import TaskCreate, TaskResponse, TaskUpdate
from ..services.schedule_service import generate_routine
from datetime import datetime
import json

router = APIRouter()

@router.get("/tasks", response_model=List[TaskResponse])
def get_tasks(
    completed: Optional[bool] = None,
    priority: Optional[str] = None,
    tag: Optional[str] = None,
    db: Session = Depends(get_db)
):
    try:
        query = db.query(Task).filter_by(user_id=1)
        
        if completed is not None:
            query = query.filter(Task.completed == completed)
        
        if priority:
            query = query.filter(Task.priority == priority)
        
        if tag:
            query = query.filter(Task.tags.like(f'%"{tag}"%'))
        
        tasks = query.order_by(Task.completed.asc(), Task.due_date.asc()).all()
        
        result = []
        for task in tasks:
            task_dict = {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'due_date': task.due_date,
                'completed': task.completed,
                'priority': task.priority,
                'category': task.category,
                'duration_minutes': task.duration_minutes,
                'tags': json.loads(task.tags) if task.tags else [],
                'recurring': task.recurring,
                'created_at': task.created_at,
                'completed_at': task.completed_at
            }
            result.append(TaskResponse(**task_dict))
        
        return result
    
    except Exception as e:
        print(f"Error getting tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def check_conflict(db: Session, user_id: int, start_time: datetime, duration_minutes: int, exclude_task_id: int = None):
    from datetime import timedelta
    end_time = start_time + timedelta(minutes=duration_minutes)
    
    # Check for overlapping tasks using unified schedule
    routine = generate_routine(user_id, db, start_time)
    timeline = routine.get("timeline", [])
    
    conflicts = []
    for event in timeline:
        # Skip free blocks
        if event.get("type") == "free":
            continue
            
        # Skip the task itself if we are updating it
        if exclude_task_id and str(event.get("id")) == str(exclude_task_id) and event.get("type") == "task":
            continue
        
        event_start = datetime.fromisoformat(event["start"])
        event_end = datetime.fromisoformat(event["end"])
        
        # Overlap: StartA < EndB and EndA > StartB
        if event_start < end_time and event_end > start_time:
            conflicts.append(event)
            
    if conflicts:
        # Find next free slot
        last_conflict_end = datetime.fromisoformat(conflicts[-1]["end"])
        next_free_slot = last_conflict_end.strftime("%Y-%m-%d %H:%M")
        
        conflict_title = conflicts[0].get("title", "Unknown Event")
        
        raise HTTPException(
            status_code=409, 
            detail=f"Conflict detected with '{conflict_title}'. Suggested time: {next_free_slot}"
        )

@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    try:
        # Safely handle None values with defaults
        duration_minutes = int(task.duration_minutes) if task.duration_minutes is not None else 30
        priority = task.priority if task.priority else 'medium'
        category = task.category if task.category else 'Personal'
        
        # Ensure tags is a list and serialize to JSON
        tags_list = task.tags if isinstance(task.tags, list) else (task.tags if task.tags else [])
        tags_json = json.dumps(tags_list) if tags_list else '[]'
        
        # Conflict Detection
        if task.due_date:
            check_conflict(db, 1, task.due_date, duration_minutes)

        new_task = Task(
            title=task.title,
            description=task.description,
            due_date=task.due_date,
            priority=priority,
            category=category,
            duration_minutes=duration_minutes,
            tags=tags_json,
            recurring=task.recurring,
            recurring_end_date=task.recurring_end_date,
            is_flexible=task.is_flexible if hasattr(task, 'is_flexible') else False,
            conflict_flag=False,
            user_id=1
        )
        
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        
        return TaskResponse(
            id=new_task.id,
            title=new_task.title,
            description=new_task.description,
            due_date=new_task.due_date,
            completed=new_task.completed,
            priority=new_task.priority,
            category=new_task.category,
            duration_minutes=new_task.duration_minutes,
            tags=json.loads(new_task.tags) if new_task.tags else [],
            recurring=new_task.recurring,
            created_at=new_task.created_at,
            completed_at=new_task.completed_at,
            warning=None
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error creating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(Task).filter_by(id=task_id, user_id=1).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        due_date=task.due_date,
        completed=task.completed,
        priority=task.priority,
        category=task.category,
        duration_minutes=task.duration_minutes,
        tags=json.loads(task.tags) if task.tags else [],
        recurring=task.recurring,
        created_at=task.created_at,
        completed_at=task.completed_at
    )

@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    try:
        task = db.query(Task).filter_by(id=task_id, user_id=1).first()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Check for conflicts if time or duration changes
        new_due_date = update.due_date if update.due_date is not None else task.due_date
        new_duration = int(update.duration_minutes) if update.duration_minutes is not None else (task.duration_minutes if task.duration_minutes is not None else 30)
        
        # Only check if due_date is set (it might be None for backlog tasks)
        # And if either date or duration changed, OR if we are just verifying current state (optional, but good for UX)
        # Let's check if the new state would conflict
        if new_due_date and (update.due_date is not None or update.duration_minutes is not None):
             check_conflict(db, 1, new_due_date, new_duration, exclude_task_id=task_id)

        if update.title is not None:
            task.title = update.title
        if update.description is not None:
            task.description = update.description
        if update.due_date is not None:
            task.due_date = update.due_date
        if update.completed is not None:
            task.completed = update.completed
            if update.completed:
                task.completed_at = datetime.now()
                
                # Handle Recurrence
                if task.recurring:
                    from datetime import timedelta
                    next_due = None
                    if task.recurring == 'daily':
                        next_due = task.due_date + timedelta(days=1)
                    elif task.recurring == 'weekly':
                        next_due = task.due_date + timedelta(weeks=1)
                    elif task.recurring == 'monthly':
                        next_due = task.due_date + timedelta(days=30) # Simple approx
                        
                    if next_due:
                        new_task = Task(
                            title=task.title,
                            description=task.description,
                            due_date=next_due,
                            priority=task.priority,
                            category=task.category,
                            duration_minutes=task.duration_minutes,
                            tags=task.tags,
                            recurring=task.recurring,
                            user_id=task.user_id
                        )
                        db.add(new_task)
                        print(f"🔄 Created recurring task: {task.title} for {next_due}")
            else:
                task.completed_at = None
        if update.priority is not None:
            task.priority = update.priority
        if update.category is not None:
            task.category = update.category
        if update.duration_minutes is not None:
            task.duration_minutes = int(update.duration_minutes)
        if update.tags is not None:
            tags_list = update.tags if isinstance(update.tags, list) else []
            task.tags = json.dumps(tags_list) if tags_list else '[]'
        if update.recurring is not None:
            task.recurring = update.recurring
        
        task.updated_at = datetime.now()
        
        db.commit()
        db.refresh(task)
        
        return TaskResponse(
            id=task.id,
            title=task.title,
            description=task.description,
            due_date=task.due_date,
            completed=task.completed,
            priority=task.priority,
            category=task.category,
            duration_minutes=task.duration_minutes,
            tags=json.loads(task.tags) if task.tags else [],
            recurring=task.recurring,
            created_at=task.created_at,
            completed_at=task.completed_at
        )
    
    except HTTPException as he:
        raise he
    except Exception as e:
        db.rollback()
        print(f"Error updating task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    try:
        task = db.query(Task).filter_by(id=task_id, user_id=1).first()
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        db.delete(task)
        db.commit()
        
        return {"status": "deleted", "task_id": task_id}
    
    except Exception as e:
        db.rollback()
        print(f"Error deleting task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/search/{query}")
def search_tasks(query: str, db: Session = Depends(get_db)):
    try:
        tasks = db.query(Task).filter(
            Task.user_id == 1,
            (Task.title.ilike(f'%{query}%') | Task.description.ilike(f'%{query}%'))
        ).all()
        
        result = []
        for task in tasks:
            task_dict = {
                'id': task.id,
                'title': task.title,
                'description': task.description,
                'due_date': task.due_date,
                'completed': task.completed,
                'priority': task.priority,
                'category': task.category,
                'duration_minutes': task.duration_minutes,
                'tags': json.loads(task.tags) if task.tags else [],
                'recurring': task.recurring,
                'created_at': task.created_at,
                'completed_at': task.completed_at
            }
            result.append(task_dict)
        
        return {"results": result, "count": len(result)}
    
    except Exception as e:
        print(f"Error searching tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))
