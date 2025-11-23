from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db, Task, ChatHistory, User, Document
import json
from datetime import datetime

router = APIRouter()

@router.get("/export")
def export_data(db: Session = Depends(get_db)):
    # Helper to serialize datetime
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError ("Type not serializable")

    # Fetch all data
    user = db.query(User).filter_by(id=1).first()
    tasks = db.query(Task).filter_by(user_id=1).all()
    chat_history = db.query(ChatHistory).filter_by(user_id=1).all()
    documents = db.query(Document).filter_by(user_id=1).all()
    
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
                "filename": d.filename,
                "uploaded_at": d.uploaded_at.isoformat()
            } for d in documents
        ]
    }
    
    return data
