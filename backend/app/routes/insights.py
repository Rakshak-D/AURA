from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from ..database import get_db
from ..services.schedule_service import get_analytics
from ..models.sql_models import Task
from datetime import datetime, timedelta

router = APIRouter()

@router.get("/focus-score")
def get_focus_score(db: Session = Depends(get_db)):
    """
    Calculate productivity focus score.
    Focus Score = (Completed Tasks / Total Tasks) * 100 * (Consistency Factor)
    """
    try:
        analytics = get_analytics(1, db, days=7)
        
        completion_rate = analytics.get("completion_rate", 0)
        total_completed = analytics.get("total_completed", 0)
        total_created = analytics.get("total_created", 0)
        
        # Calculate productivity trend (compare with previous week)
        # Get analytics for previous 7 days (days 8-14)
        today = datetime.now()
        week_start = today - timedelta(days=7)
        week_end = today
        previous_week_start = today - timedelta(days=14)
        previous_week_end = today - timedelta(days=7)
        
        # Count completed tasks in current week
        current_week_completed = db.query(Task).filter(
            and_(
                Task.user_id == 1,
                Task.completed == True,
                Task.completed_at >= week_start,
                Task.completed_at < week_end
            )
        ).count()
        
        # Count completed tasks in previous week
        previous_week_completed = db.query(Task).filter(
            and_(
                Task.user_id == 1,
                Task.completed == True,
                Task.completed_at >= previous_week_start,
                Task.completed_at < previous_week_end
            )
        ).count()
        
        # Calculate trend percentage
        productivity_trend = None
        if previous_week_completed > 0:
            trend_percentage = ((current_week_completed - previous_week_completed) / previous_week_completed) * 100
            productivity_trend = round(trend_percentage, 1)
        elif current_week_completed > 0:
            productivity_trend = 100.0  # New activity (no previous data)
        
        # Simple Focus Score Algorithm
        # Base score is completion rate. Bonus for high volume.
        score = completion_rate
        if total_completed > 10:
            score += 10
        if score > 100:
            score = 100
        
        # Determine label and trend text
        if score > 80:
            label = "Excellent"
            trend_text = f"Top 10% of users" if productivity_trend and productivity_trend > 0 else "Keep it up!"
        elif score > 50:
            label = "Good"
            trend_text = f"+{productivity_trend}% from last week" if productivity_trend and productivity_trend > 0 else "On track"
        else:
            label = "Needs Improvement"
            trend_text = "Let's improve this week" if not productivity_trend or productivity_trend <= 0 else f"+{productivity_trend}% from last week"
            
        return {
            "score": round(score),
            "label": label,
            "trend": productivity_trend,
            "trend_text": trend_text,
            "details": {
                "completion_rate": completion_rate,
                "total_completed": total_completed,
                "total_created": total_created
            }
        }
    except Exception as e:
        print(f"Error calculating focus score: {e}")
        # Return safe defaults
        return {
            "score": 0,
            "label": "No Data",
            "trend": None,
            "trend_text": "Start completing tasks to see your score",
            "details": {
                "completion_rate": 0,
                "total_completed": 0,
                "total_created": 0
            }
        }

@router.get("/trends")
def get_trends(db: Session = Depends(get_db)):
    """
    Get data for line/pie charts.
    """
    try:
        analytics = get_analytics(1, db, days=7)
        
        # Prepare data for Chart.js
        tasks_by_day = analytics.get("tasks_by_day", {})
        dates = sorted(tasks_by_day.keys())
        values = [tasks_by_day[d] for d in dates]
        
        priority_breakdown = analytics.get("priority_breakdown", {})
        
        # Ensure we have data - provide defaults if empty
        if not dates:
            # Generate last 7 days with zero values
            today = datetime.now()
            dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(6, -1, -1)]
            values = [0] * 7
        
        return {
            "activity": {
                "labels": dates,
                "datasets": [{
                    "label": "Completed Tasks",
                    "data": values,
                    "borderColor": "#3B82F6",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "tension": 0.4,
                    "fill": True
                }]
            },
            "distribution": {
                "labels": list(priority_breakdown.keys()) if priority_breakdown else ["urgent", "high", "medium", "low"],
                "datasets": [{
                    "data": list(priority_breakdown.values()) if priority_breakdown else [0, 0, 0, 0],
                    "backgroundColor": ["#EF4444", "#F59E0B", "#3B82F6", "#6B7280"]
                }]
            }
        }
    except Exception as e:
        print(f"Error generating trends: {e}")
        # Return safe defaults
        return {
            "activity": {
                "labels": [],
                "datasets": [{
                    "label": "Completed Tasks",
                    "data": [],
                    "borderColor": "#3B82F6",
                    "backgroundColor": "rgba(59, 130, 246, 0.1)",
                    "tension": 0.4,
                    "fill": True
                }]
            },
            "distribution": {
                "labels": ["urgent", "high", "medium", "low"],
                "datasets": [{
                    "data": [0, 0, 0, 0],
                    "backgroundColor": ["#EF4444", "#F59E0B", "#3B82F6", "#6B7280"]
                }]
            }
        }
