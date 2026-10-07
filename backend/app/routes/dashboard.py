from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..auth import get_current_user_id
from ..services.schedule_service import generate_daily_schedule, get_analytics

router = APIRouter()

@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    try:
        return generate_daily_schedule(current_user_id, db)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load schedule") from e

@router.get("/analytics")
def get_user_analytics(days: int = 30, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    try:
        return get_analytics(current_user_id, db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load analytics") from e
