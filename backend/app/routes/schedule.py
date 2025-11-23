from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.schedule_service import generate_routine, auto_schedule_tasks

router = APIRouter()

@router.get("/schedule/routine")
def get_routine(db: Session = Depends(get_db)):
    try:
        return generate_routine(1, db)
    except Exception as e:
        print(f"Error generating routine: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule/auto-assign")
def auto_assign_tasks(db: Session = Depends(get_db)):
    try:
        return auto_schedule_tasks(1, db)
    except Exception as e:
        print(f"Error auto-scheduling: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/schedule/conflicts")
def check_conflicts(start_time: str, end_time: str, db: Session = Depends(get_db)):
    """Check for conflicts in a specific time range"""
    # Implementation pending - for now return empty list
    return {"conflicts": []}
