from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, User
from ..models.pydantic_models import SettingsUpdate
import json

router = APIRouter()

@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter_by(id=1).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Merge name into settings for frontend convenience
        settings = user.settings or {}
        settings['username'] = user.name
        
        return settings
    except Exception as e:
        print(f"Error fetching settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/settings")
def update_settings(settings_update: SettingsUpdate, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter_by(id=1).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_settings = user.settings or {}
        
        if settings_update.theme is not None:
            current_settings['theme'] = settings_update.theme
        if settings_update.notifications_enabled is not None:
            current_settings['notifications_enabled'] = settings_update.notifications_enabled
        if settings_update.default_reminder_time is not None:
            current_settings['default_reminder_time'] = settings_update.default_reminder_time
        
        # Handle username separately as it's a column
        if settings_update.username is not None:
            user.name = settings_update.username
            
        # Explicitly flag modified for JSON field if needed (SQLAlchemy usually handles this but good to be safe)
        user.settings = dict(current_settings)
        
        db.commit()
        db.refresh(user)
        
        response_settings = user.settings
        response_settings['username'] = user.name
        
        return response_settings
    except Exception as e:
        db.rollback()
        print(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))
