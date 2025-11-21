from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.schedule_service import generate_daily_schedule, get_analytics

router = APIRouter()

@router.get("/schedule")
def get_schedule(db: Session = Depends(get_db)):
    try:
        return generate_daily_schedule(1, db)
    except Exception as e:
        return {"error": str(e)}

@router.get("/analytics")
def get_user_analytics(days: int = 30, db: Session = Depends(get_db)):
    try:
        return get_analytics(1, db, days)
    except Exception as e:
        return {"error": str(e)}
