from ..models.sql_models import User
from sqlalchemy.orm import Session
import json


def update_preferences(user_id: int, feedback: str, db: Session):
    user = db.query(User).get(user_id)
    if not user:
        return
    prefs = json.loads(user.preferences or "{}")
    prefs["last_feedback"] = feedback
    user.preferences = json.dumps(prefs)
    db.commit()


def get_context(user_id: int, db: Session) -> str:
    user = db.query(User).get(user_id)
    if not user:
        return ""
    prefs = json.loads(user.preferences or "{}")
    return f"User prefs: {prefs.get('last_feedback', '')}"


def update_user_name(user_id: int, new_name: str, db: Session) -> str:
    """
    Update the user's display name in both the User column and settings JSON.
    """
    user = db.query(User).get(user_id)
    if not user:
        return new_name

    cleaned = (new_name or "").strip()
    if not cleaned:
        return user.name or "User"

    user.name = cleaned

    settings = user.settings or {}
    settings["username"] = cleaned
    user.settings = dict(settings)

    db.commit()
    db.refresh(user)
    return cleaned