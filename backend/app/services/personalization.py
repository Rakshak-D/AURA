from database import get_db
from models.llm_models import llm
import json

def update_preferences(user_id: int, feedback: str):
    # Simple: Embed feedback, store as avg context
    db = next(get_db())
    user = db.query(User).get(user_id)
    prefs = json.loads(user.preferences or "{}")
    prefs["last_feedback"] = feedback
    user.preferences = json.dumps(prefs)
    db.commit()

def get_context(user_id: int) -> str:
    db = next(get_db())
    user = db.query(User).get(user_id)
    prefs = json.loads(user.preferences or "{}")
    return f"User prefs: {prefs.get('last_feedback', '')}"