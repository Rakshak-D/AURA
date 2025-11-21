from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List

class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = 'medium'
    tags: Optional[List[str]] = []
    recurring: Optional[str] = None
    recurring_end_date: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None
    priority: Optional[str] = None
    tags: Optional[List[str]] = None
    recurring: Optional[str] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed: bool
    priority: str
    tags: List[str]
    recurring: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ChatMessage(BaseModel):
    message: str
    context: Optional[dict] = {}

class ChatResponse(BaseModel):
    response: str
    action_taken: Optional[str] = None
    data: Optional[dict] = {}
    suggestions: Optional[List[str]] = []

class ReminderCreate(BaseModel):
    task_id: int
    reminder_time: datetime

class ReminderResponse(BaseModel):
    id: int
    task_id: int
    reminder_time: datetime
    sent: bool
    
    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    query: str
    filters: Optional[dict] = {}

class DaySummaryRequest(BaseModel):
    date: Optional[datetime] = None
