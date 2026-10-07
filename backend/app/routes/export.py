from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models.sql_models import ChatHistory, Document, Reminder, RoutineEvent, Task

router = APIRouter()

@router.get("/export")
def export_data(db: Session = Depends(get_db), user=Depends(get_current_user)):
    # Fetch all data
    tasks = db.query(Task).filter_by(user_id=user.id).all()
    chat_history = db.query(ChatHistory).filter_by(user_id=user.id).all()
    documents = db.query(Document).filter_by(user_id=user.id).all()
    reminders = db.query(Reminder).filter_by(user_id=user.id).all()
    routine_events = db.query(RoutineEvent).filter_by(user_id=user.id).all()
    
    data = {
        "user": {
            "name": user.name,
            "settings": user.settings,
            "created_at": user.created_at.isoformat()
        },
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": "completed" if t.completed else "pending",
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "created_at": t.created_at.isoformat()
            } for t in tasks
        ],
        "chat_history": [
            {
                "role": c.role,
                "content": c.content,
                "timestamp": c.timestamp.isoformat()
            } for c in chat_history
        ],
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "indexing_state": d.indexing_state,
                "uploaded_at": d.uploaded_at.isoformat()
            } for d in documents
        ],
        "reminders": [
            {
                "id": r.id,
                "task_id": r.task_id,
                "reminder_time": r.reminder_time.isoformat(),
                "timezone": r.timezone,
                "status": r.status,
            } for r in reminders
        ],
        "routine_events": [
            {
                "id": event.id,
                "title": event.title,
                "event_type": event.event_type,
                "start_time": event.start_time,
                "duration_minutes": event.duration_minutes,
                "days_of_week": event.days_of_week,
            } for event in routine_events
        ],
    }
    
    return data
