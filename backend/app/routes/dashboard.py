from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.schedule_service import generate_daily_schedule

router = APIRouter()

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    return generate_daily_schedule(1, db)