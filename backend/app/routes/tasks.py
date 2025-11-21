from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from ..database import get_db, Task
from ..services.schedule_service import add_task, generate_daily_schedule
from ..models.pydantic_models import TaskCreate, TaskResponse, TaskUpdate

router = APIRouter()

@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    tid = add_task(1, task.dict(), db)
    return db.query(Task).get(tid)

@router.get("/tasks", response_model=List[TaskResponse])
def get_tasks(db: Session = Depends(get_db)):
    return db.query(Task).filter_by(user_id=1).order_by(Task.due_date.asc()).all()

@router.put("/tasks/{task_id}", response_model=TaskResponse)
def update_task(task_id: int, update: TaskUpdate, db: Session = Depends(get_db)):
    task = db.query(Task).filter_by(id=task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.completed = update.completed
    db.commit()
    db.refresh(task)
    return task

@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    return generate_daily_schedule(1, db)