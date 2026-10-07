from datetime import datetime, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, field_validator


class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = 'medium'
    category: Optional[str] = 'Personal'
    duration_minutes: Optional[int] = 30
    tags: Optional[List[str]] = []
    recurring: Optional[str] = None
    recurring_end_date: Optional[datetime] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    completed: Optional[bool] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    duration_minutes: Optional[int] = None
    tags: Optional[List[str]] = None
    recurring: Optional[str] = None

class TaskResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    due_date: Optional[datetime]
    completed: bool
    priority: str
    category: Optional[str] = 'Personal'
    duration_minutes: Optional[int] = 30
    tags: List[str]
    recurring: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    warning: Optional[str] = None
    
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
    timezone: str = "UTC"

    @field_validator("reminder_time")
    @classmethod
    def require_aware_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reminder_time must include a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid timezone") from exc
        return value

class ReminderResponse(BaseModel):
    id: int
    task_id: int | None
    reminder_time: datetime
    status: str
    timezone: str
    
    class Config:
        from_attributes = True

class SearchQuery(BaseModel):
    query: str
    filters: Optional[dict] = {}

class DaySummaryRequest(BaseModel):
    date: Optional[datetime] = None

class SettingsUpdate(BaseModel):
    theme: Optional[str] = None
    notifications_enabled: Optional[bool] = None
    default_reminder_time: Optional[str] = None
    username: Optional[str] = None
    ai_temperature: Optional[float] = None
