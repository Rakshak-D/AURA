from ..models.sql_models import User
from ..models.llm_models import llm
from sqlalchemy.orm import Session
import json

def update_preferences(user_id: int, feedback: str, db: Session):
    user = db.query(User).get(user_id)
    if not user: return
    prefs = json.loads(user.preferences or "{}")
    prefs["last_feedback"] = feedback
    user.preferences = json.dumps(prefs)
    db.commit()

def get_context(user_id: int, db: Session) -> str:
    user = db.query(User).get(user_id)
    if not user: return ""
    prefs = json.loads(user.preferences or "{}")
    return f"User prefs: {prefs.get('last_feedback', '')}"