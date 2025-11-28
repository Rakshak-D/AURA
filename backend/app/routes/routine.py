from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.sql_models import RoutineEvent
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class RoutineEventCreate(BaseModel):
    title: str
    start_time: str
    duration_minutes: int
    event_type: str = 'personal'
    days_of_week: str = '0,1,2,3,4,5,6'

class RoutineEventResponse(RoutineEventCreate):
    id: int
    user_id: int
    
    class Config:
        from_attributes = True

@router.get("/routine", response_model=List[RoutineEventResponse])
def get_routine(db: Session = Depends(get_db)):
    return db.query(RoutineEvent).filter_by(user_id=1).all()

@router.post("/routine", response_model=RoutineEventResponse)
def create_routine_event(event: RoutineEventCreate, db: Session = Depends(get_db)):
    new_event = RoutineEvent(
        user_id=1,
        title=event.title,
        start_time=event.start_time,
        duration_minutes=event.duration_minutes,
        event_type=event.event_type,
        days_of_week=event.days_of_week
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event

@router.delete("/routine/{event_id}")
def delete_routine_event(event_id: int, db: Session = Depends(get_db)):
    event = db.query(RoutineEvent).filter_by(id=event_id, user_id=1).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    db.delete(event)
    db.commit()
    return {"status": "deleted"}
