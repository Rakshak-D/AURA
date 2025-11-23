from sqlalchemy.orm import Session
from ..database import ChatHistory, Task, User
from ..models.llm_models import llm
from .rag_service import query_rag
from .schedule_service import generate_daily_schedule
from .intent_service import detect_intent
from datetime import datetime, timedelta
import json
import re

class ChatService:
    def __init__(self):
        self.intents = {
            'task_create': self.handle_task_create,
            'task_query': self.handle_task_query,
            'task_update': self.handle_task_update,
            'task_delete': self.handle_task_delete,
            'day_summary': self.handle_day_summary,
            'reminder': self.handle_reminder,
            'search': self.handle_search,
            'general_chat': self.handle_general_chat
        }
    
    def process_chat(self, user_id: int, message_data: any, db: Session):
        try:
            # Handle both string (legacy) and object input
            if isinstance(message_data, str):
                message = message_data
                context = {}
            else:
                message = message_data.message
                context = message_data.context or {}

            if not message or not message.strip():
                return {"response": "I'm listening. How can I help you today?", "action_taken": None}
            
            self.save_message(user_id, "user", message, db)
            
            # Detect Intent (Returns Dict)
            intent_result = detect_intent(message)
            intent = intent_result.get('intent', 'general_chat')
            
            # Pass context to handler if needed
            if intent == 'general_chat':
                result = self.handle_general_chat(user_id, message, db, context)
            else:
                handler = self.intents.get(intent, self.handle_general_chat)
                # Pass intent_result to handler to access entities
                result = handler(user_id, message, db, intent_result)
                
            self.save_message(user_id, "assistant", result['response'], db, intent=intent)
            result['suggestions'] = self.generate_suggestions(intent, db, user_id)
            
            return result
            
        except Exception as e:
            print(f"Chat processing error: {e}")
            return {
                "response": "I encountered an error. Please try again.",
                "action_taken": "error",
                "data": {"error": str(e)}
            }
    
    def handle_task_create(self, user_id: int, message: str, db: Session, intent_data: dict):
        try:
            entities = intent_data.get('entities', {})
            
            # Parse due date
            due_date = None
            if entities.get('time'):
                try:
                    due_date = datetime.fromisoformat(entities['time'])
                except:
                    pass
            
            new_task = Task(
                title=entities.get('title', message[:100]),
                description=message, # Use full message as description if needed
                due_date=due_date,
                priority=entities.get('priority', 'medium'),
                category=entities.get('category', 'Personal'),
                duration_minutes=int(entities.get('duration', 30)),
                tags='[]',
                user_id=user_id
            )
            
            db.add(new_task)
            db.commit()
            db.refresh(new_task)
            
            response = f"✅ Task created: '{new_task.title}'"
            if due_date:
                response += f" due {self.format_due_date(due_date)}"
            
            return {
                "response": response,
                "action_taken": "task_created",
                "data": {"task_id": new_task.id, "title": new_task.title}
            }
            
        except Exception as e:
            print(f"Task creation error: {e}")
            return {"response": f"I couldn't create the task. Error: {str(e)}", "action_taken": "error"}
    
    def handle_task_query(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            message_lower = message.lower()
            
            if any(word in message_lower for word in ['today', 'due today']):
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= datetime.now().replace(hour=0, minute=0, second=0),
                    Task.due_date < datetime.now().replace(hour=23, minute=59, second=59)
                ).all()
                response = f"You have {len(tasks)} tasks due today:"
            elif any(word in message_lower for word in ['tomorrow']):
                tomorrow = datetime.now() + timedelta(days=1)
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= tomorrow.replace(hour=0, minute=0, second=0),
                    Task.due_date < tomorrow.replace(hour=23, minute=59, second=59)
                ).all()
                response = f"You have {len(tasks)} tasks due tomorrow:"
            elif any(word in message_lower for word in ['week', 'this week']):
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= datetime.now(),
                    Task.due_date < datetime.now() + timedelta(days=7)
                ).all()
                response = f"You have {len(tasks)} tasks this week:"
            else:
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False
                ).order_by(Task.due_date.asc()).limit(10).all()
                response = f"You have {len(tasks)} pending tasks:"
            
            # Format for text response
            for task in tasks:
                response += f"\n• {task.title}"
                if task.due_date:
                    response += f" (due {self.format_due_date(task.due_date)})"
            
            # Format for frontend cards
            task_list = [{
                "id": t.id,
                "title": t.title,
                "completed": t.completed,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "priority": t.priority,
                "category": t.category
            } for t in tasks]
            
            # Return Widget
            return {
                "response": response,
                "action_taken": "task_query",
                "type": "widget",
                "widget_type": "task_list",
                "data": {
                    "title": response,
                    "tasks": task_list
                }
            }
            
        except Exception as e:
            print(f"Task query error: {e}")
            return {"response": "I couldn't retrieve your tasks.", "action_taken": "error"}
    
    def handle_task_update(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            message_lower = message.lower()
            
            if 'complete' in message_lower or 'done' in message_lower:
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False
                ).all()
                
                for task in tasks:
                    if task.title.lower() in message_lower:
                        task.completed = True
                        task.completed_at = datetime.now()
                        db.commit()
                        return {
                            "response": f"✅ Marked '{task.title}' as complete!",
                            "action_taken": "task_completed",
                            "data": {"task_id": task.id}
                        }
                
                return {"response": "I couldn't find that task. Can you be more specific?", "action_taken": None}
            
            return {"response": "I'm not sure how to update that task.", "action_taken": None}
            
        except Exception as e:
            print(f"Task update error: {e}")
            return {"response": "I couldn't update the task.", "action_taken": "error"}
    
    def handle_task_delete(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            tasks = db.query(Task).filter(Task.user_id == user_id).all()
            
            for task in tasks:
                if task.title.lower() in message.lower():
                    db.delete(task)
                    db.commit()
                    return {
                        "response": f"🗑️ Deleted task: '{task.title}'",
                        "action_taken": "task_deleted",
                        "data": {"task_id": task.id}
                    }
            
            return {"response": "I couldn't find that task to delete.", "action_taken": None}
            
        except Exception as e:
            print(f"Task delete error: {e}")
            return {"response": "I couldn't delete the task.", "action_taken": "error"}
    
    def handle_day_summary(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            schedule = generate_daily_schedule(user_id, db)
            
            today_start = datetime.now().replace(hour=0, minute=0, second=0)
            completed_today = db.query(Task).filter(
                Task.user_id == user_id,
                Task.completed == True,
                Task.completed_at >= today_start
            ).count()
            
            prompt = f"""Generate a friendly daily summary for the user:
            - Total tasks: {schedule['overview']['total']}
            - Completed: {schedule['overview']['completed']}
            - Pending: {schedule['overview']['pending']}
            - Completed today: {completed_today}
            
            Keep it encouraging and concise."""
            
            summary = llm.generate(prompt, max_tokens=200)
            
            return {
                "response": summary,
                "action_taken": "day_summary",
                "data": {
                    "overview": schedule['overview'],
                    "completed_today": completed_today
                }
            }
            
        except Exception as e:
            print(f"Day summary error: {e}")
            return {"response": "I couldn't generate your day summary.", "action_taken": "error"}
    
    def handle_reminder(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        return {"response": "Reminder feature coming soon!", "action_taken": "reminder"}
    
    def handle_search(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            search_term = message.lower().replace('search', '').replace('find', '').strip()
            
            tasks = db.query(Task).filter(
                Task.user_id == user_id,
                (Task.title.ilike(f'%{search_term}%') | Task.description.ilike(f'%{search_term}%'))
            ).all()
            
            if tasks:
                response = f"Found {len(tasks)} tasks matching '{search_term}':"
                for task in tasks[:5]:
                    response += f"\n• {task.title}"
            else:
                response = f"No tasks found matching '{search_term}'"
            
            return {
                "response": response,
                "action_taken": "search",
                "data": {"results_count": len(tasks)}
            }
            
        except Exception as e:
            print(f"Search error: {e}")
            return {"response": "I couldn't complete the search.", "action_taken": "error"}
    
    def get_user_context(self, user_id: int, db: Session) -> str:
        """Get user's tasks and routine for context"""
        try:
            now = datetime.now()
            today = now.date()
            
            # 1. Get Current Routine Status
            schedule = generate_daily_schedule(user_id, db) # Basic stats
            
            # We need the detailed timeline to find current activity
            from .schedule_service import generate_routine
            routine = generate_routine(user_id, db, now)
            timeline = routine.get('timeline', [])
            
            current_activity = "Free Time"
            next_activity = None
            
            for event in timeline:
                start = datetime.fromisoformat(event['start'])
                end = datetime.fromisoformat(event['end'])
                
                if start <= now <= end:
                    current_activity = f"{event['title']} ({event['type']})"
                elif start > now and not next_activity:
                    next_activity = f"{event['title']} at {start.strftime('%I:%M %p')}"
            
            # 2. Get Tasks
            today_tasks = db.query(Task).filter(
                Task.user_id == user_id,
                Task.completed == False,
                Task.due_date >= datetime.combine(today, datetime.min.time()),
                Task.due_date < datetime.combine(today + timedelta(days=1), datetime.min.time())
            ).limit(5).all()
            
            parts = []
            parts.append(f"Current Time: {now.strftime('%I:%M %p')}")
            parts.append(f"Current Activity: {current_activity}")
            if next_activity:
                parts.append(f"Next Up: {next_activity}")
                
            if today_tasks:
                tasks = ", ".join([t.title for t in today_tasks])
                parts.append(f"Tasks Due Today: {tasks}")
            
            return " | ".join(parts)
        except Exception as e:
            print(f"Context Error: {e}")
            return ""
    
    def handle_general_chat(self, user_id: int, message: str, db: Session, context: dict = None):
        try:
            # Get user context (tasks)
            task_context = self.get_user_context(user_id, db)
            user_name = context.get('user_name', 'User') if context else 'User'
            
            # Phi-3 prompt format
            prompt = f"<|system|>\nYou are AURA, a helpful AI assistant. You are talking to {user_name}. Be concise and direct.\n"
            if task_context:
                prompt += f"Task Context: {task_context}\n"
            prompt += "<|end|>\n"
            prompt += f"<|user|>\n{message}<|end|>\n<|assistant|>"
            
            response = llm.generate(prompt, max_tokens=500)
            
            return {
                "response": response,
                "action_taken": "general_chat",
                "data": {}
            }
            
        except Exception as e:
            print(f"General chat error: {e}")
            return {"response": "I'm having trouble thinking right now.", "action_taken": "error"}

    def save_message(self, user_id: int, role: str, content: str, db: Session, intent: str = None):
        try:
            history = ChatHistory(
                user_id=user_id,
                role=role,
                content=content,
                intent=intent,
                timestamp=datetime.utcnow()
            )
            db.add(history)
            db.commit()
        except Exception as e:
            print(f"Error saving message: {e}")

    def format_due_date(self, due_date: datetime) -> str:
        now = datetime.now()
        diff = due_date - now
        
        if diff.days == 0:
            return "today"
        elif diff.days == 1:
            return "tomorrow"
        elif diff.days < 7:
            return f"in {diff.days} days"
        else:
            return due_date.strftime("%B %d, %Y")
    
    def generate_suggestions(self, intent: str, db: Session, user_id: int):
        suggestions = {
            'task_create': [
                "Show my tasks for today",
                "What's due this week?",
                "Summarize my day"
            ],
            'task_query': [
                "Create a new task",
                "Mark task as complete",
                "Search my tasks"
            ],
            'day_summary': [
                "Show pending tasks",
                "Create a reminder",
                "What's next?"
            ]
        }
        
        return suggestions.get(intent, [
            "What can I help you with?",
            "Show my tasks",
            "Summarize my day"
        ])

chat_service = ChatService()

def process_chat(user_id: int, message: str, db: Session):
    return chat_service.process_chat(user_id, message, db)
