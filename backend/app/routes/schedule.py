from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.schedule_service import generate_routine, auto_schedule_tasks
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

router = APIRouter()

class EventCreate(BaseModel):
    title: str
    start_time: str  # ISO format datetime
    end_time: str    # ISO format datetime
    event_type: str = "event"  # event, task, routine, meal, break
    description: Optional[str] = None
    color: Optional[str] = None

@router.get("/schedule/routine")
def get_routine(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    try:
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        return generate_routine(1, db, target_date)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error generating routine: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule/auto-assign")
def auto_assign_tasks(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    db: Session = Depends(get_db)
):
    try:
        target_date = None
        if date:
            try:
                target_date = datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        return auto_schedule_tasks(1, db, target_date)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error auto-scheduling: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule/events")
def create_event(event: EventCreate, db: Session = Depends(get_db)):
    """
    Create a fixed event (like classes or meetings) that is not a task.
    This creates a RoutineEvent for recurring events or a one-time event.
    """
    try:
        from ..models.sql_models import RoutineEvent
            
        start_dt = datetime.fromisoformat(event.start_time.replace('Z', '+00:00'))
        end_dt = datetime.fromisoformat(event.end_time.replace('Z', '+00:00'))
        
        # Calculate duration
        duration_minutes = int((end_dt - start_dt).total_seconds() / 60)
        
        # Extract day of week (0=Monday, 6=Sunday)
        day_of_week = str(start_dt.weekday())
        
        # Format time as HH:MM
        start_time_str = start_dt.strftime("%H:%M")
        
        new_event = RoutineEvent(
            user_id=1,
            title=event.title,
            start_time=start_time_str,
            duration_minutes=duration_minutes,
            event_type=event.event_type or "event",
            days_of_week=day_of_week
        )
        
        db.add(new_event)
        db.commit()
        db.refresh(new_event)
        
        return {
            "id": new_event.id,
            "title": new_event.title,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "event_type": new_event.event_type,
            "message": "Event created successfully"
        }
    except Exception as e:
        db.rollback()
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating event: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/schedule/conflicts")
def check_conflicts(start_time: str, end_time: str, db: Session = Depends(get_db)):
    """Check for conflicts in a specific time range"""
    try:
        start = datetime.fromisoformat(start_time)
        end = datetime.fromisoformat(end_time)
        
        # Get routine for the day
        routine = generate_routine(1, db, start)
        timeline = routine.get("timeline", [])
        
        conflicts = []
        for event in timeline:
            # Skip free blocks
            if event.get("type") == "free":
                continue
            
            event_start = datetime.fromisoformat(event["start"])
            event_end = datetime.fromisoformat(event["end"])
            
            # Overlap: StartA < EndB and EndA > StartB
            if event_start < end and event_end > start:
                conflicts.append(event)
                
        return {"conflicts": conflicts}
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error checking conflicts: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
