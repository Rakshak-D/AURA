from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed: bool

class ChatMessage(BaseModel):
    message: str
    context: Optional[str] = None  # RAG context

class UploadFile(BaseModel):
    filename: str
    content: str  # Extracted text

class Reminder(BaseModel):
    task_id: int
    time: datetime