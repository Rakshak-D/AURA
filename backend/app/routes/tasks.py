from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, Task
from ..services.schedule_service import add_task, generate_daily_schedule
from ..models.pydantic_models import TaskCreate, TaskResponse
from typing import List

router = APIRouter()

@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    # Pass the DB session to the service
    tid = add_task(1, task.dict(), db)  # Hardcoded User 1
    created_task = db.query(Task).get(tid)
    return created_task

@router.get("/tasks", response_model=List[TaskResponse])
def get_tasks(db: Session = Depends(get_db)):
    # Endpoint required by frontend/js/main.js
    tasks = db.query(Task).filter_by(user_id=1).all()
    return tasks

@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    return generate_daily_schedule(1, db)