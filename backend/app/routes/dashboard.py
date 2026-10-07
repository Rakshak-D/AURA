from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, get_development_user_id
from ..services.schedule_service import generate_daily_schedule, get_analytics

router = APIRouter()

@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    try:
        return generate_daily_schedule(get_development_user_id(db), db)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load schedule") from e

@router.get("/analytics")
def get_user_analytics(days: int = 30, db: Session = Depends(get_db)):
    try:
        return get_analytics(get_development_user_id(db), db, days)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to load analytics") from e
