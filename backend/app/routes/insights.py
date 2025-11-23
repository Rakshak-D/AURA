from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..services.schedule_service import get_analytics
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/focus-score")
def get_focus_score(db: Session = Depends(get_db)):
    """
    Calculate productivity focus score.
    Focus Score = (Completed Tasks / Total Tasks) * 100 * (Consistency Factor)
    """
    analytics = get_analytics(1, db, days=7)
    
    completion_rate = analytics.get("completion_rate", 0)
    total_completed = analytics.get("total_completed", 0)
    
    # Simple Focus Score Algorithm
    # Base score is completion rate. Bonus for high volume.
    score = completion_rate
    if total_completed > 10:
        score += 10
    if score > 100:
        score = 100
        
    return {
        "score": round(score),
        "label": "Excellent" if score > 80 else "Good" if score > 50 else "Needs Improvement",
        "details": {
            "completion_rate": completion_rate,
            "total_completed": total_completed
        }
    }

@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    """
    Get data for line/pie charts.
    """
    analytics = get_analytics(1, db, days=7)
    
    # Prepare data for Chart.js
    tasks_by_day = analytics.get("tasks_by_day", {})
    dates = sorted(tasks_by_day.keys())
    values = [tasks_by_day[d] for d in dates]
    
    priority_breakdown = analytics.get("priority_breakdown", {})
    
    return {
        "activity": {
            "labels": dates,
            "datasets": [{
                "label": "Completed Tasks",
                "data": values,
                "borderColor": "#00f2fe",
                "tension": 0.4
            }]
        },
        "distribution": {
            "labels": list(priority_breakdown.keys()),
            "datasets": [{
                "data": list(priority_breakdown.values()),
                "backgroundColor": ["#ff4b4b", "#ff9f43", "#feca57", "#48dbfb"]
            }]
        }
    }
