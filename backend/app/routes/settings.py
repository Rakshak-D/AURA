from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.sql_models import User
from ..models.pydantic_models import SettingsUpdate

router = APIRouter()


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    """
    Fetch the current user's settings merged with safe defaults.
    """
    try:
        user = db.query(User).filter_by(id=1).first()

        # Return defaults if user doesn't exist or settings are empty
        if not user:
            return {
                "username": "User",
                "theme": "dark",
                "notifications_enabled": True,
                "default_reminder_time": "09:00",
                "ai_temperature": 0.7,
            }

        # Merge name into settings for frontend convenience
        settings = user.settings if user.settings else {}

        # Ensure all required fields have defaults
        default_settings = {
            "username": user.name if user.name else "User",
            "theme": settings.get("theme", "dark"),
            "notifications_enabled": settings.get("notifications_enabled", True),
            "default_reminder_time": settings.get("default_reminder_time", "09:00"),
            "ai_temperature": settings.get("ai_temperature", 0.7),
        }

        # Merge user settings with defaults
        default_settings.update(settings)
        default_settings["username"] = user.name if user.name else "User"

        return default_settings
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching settings: {str(e)}", exc_info=True)
        # Return safe defaults instead of crashing
        return {
            "username": "User",
            "theme": "dark",
            "notifications_enabled": True,
            "default_reminder_time": "09:00",
            "ai_temperature": 0.7,
        }


@router.put("/settings")
def update_settings(settings_update: SettingsUpdate, db: Session = Depends(get_db)):
    """
    Persist user settings including AI knobs such as temperature.
    """
    try:
        user = db.query(User).filter_by(id=1).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        current_settings = user.settings or {}

        if settings_update.theme is not None:
            current_settings["theme"] = settings_update.theme
        if settings_update.notifications_enabled is not None:
            current_settings["notifications_enabled"] = settings_update.notifications_enabled
        if settings_update.default_reminder_time is not None:
            current_settings["default_reminder_time"] = settings_update.default_reminder_time
        if settings_update.ai_temperature is not None:
            current_settings["ai_temperature"] = settings_update.ai_temperature

        # Handle username separately as it's a column
        if settings_update.username is not None:
            user.name = settings_update.username

        # Explicitly flag modified for JSON field if needed (SQLAlchemy usually handles this but good to be safe)
        user.settings = dict(current_settings)

        db.commit()
        db.refresh(user)

        response_settings = user.settings or {}
        response_settings["username"] = user.name

        return response_settings
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error updating settings: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update settings")
