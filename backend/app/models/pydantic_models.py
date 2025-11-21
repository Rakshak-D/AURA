from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None

class TaskUpdate(BaseModel):
    completed: bool

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed: bool

    class Config:
        from_attributes = True

class ChatMessage(BaseModel):
    message: str
    context: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    action_taken: Optional[str] = None # e.g., "created_task"

class Reminder(BaseModel):
    task_id: int
    time: datetime