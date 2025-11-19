from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db, Task
from services.schedule_service import add_task, generate_daily_schedule
from models.pydantic_models import TaskCreate, TaskResponse

router = APIRouter()

@router.post("/tasks", response_model=TaskResponse)
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    tid = add_task(1, task.dict())  # User 1
    return db.query(Task).get(tid)

@router.get("/schedule")
def get_schedule():
    return generate_daily_schedule(1)