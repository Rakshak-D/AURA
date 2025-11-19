from fastapi import APIRouter
from services.schedule_service import generate_daily_schedule

router = APIRouter()

@router.get("/stats")
def get_stats():
    return generate_daily_schedule(1)  # Includes insights