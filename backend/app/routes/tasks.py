from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db, Task
from ..models.pydantic_models import TaskCreate, TaskResponse, TaskUpdate
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

@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    try:
        new_task = Task(
            title=task.title,
            description=task.description,
            due_date=task.due_date,
            priority=task.priority or 'medium',
            tags=json.dumps(task.tags) if task.tags else '[]',
            recurring=task.recurring,
            recurring_end_date=task.recurring_end_date,
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
            tags=json.loads(new_task.tags) if new_task.tags else [],
            recurring=new_task.recurring,
            created_at=new_task.created_at,
            completed_at=new_task.completed_at
        )
    
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
            else:
                task.completed_at = None
        if update.priority is not None:
            task.priority = update.priority
        if update.tags is not None:
            task.tags = json.dumps(update.tags)
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
            tags=json.loads(task.tags) if task.tags else [],
            recurring=task.recurring,
            created_at=task.created_at,
            completed_at=task.completed_at
        )
    
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
