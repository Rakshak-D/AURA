from sqlalchemy.orm import Session
from ..models.sql_models import ChatHistory, Task, User
from ..models.llm_models import llm
from .rag_service import query_rag
from .schedule_service import generate_daily_schedule, generate_routine
from .intent_service import detect_intent
from .personalization import update_user_name
from datetime import datetime, timedelta
import json
import re
import asyncio
import logging

logger = logging.getLogger(__name__)


def _get_user_temperature(db: Session, user_id: int) -> float:
    """
    Resolve the effective temperature for the current user from the DB,
    falling back to the global configuration default when not set.
    """
    from ..config import config

    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.settings:
            return getattr(config, "LLM_TEMPERATURE", 0.1)
        return float(user.settings.get("ai_temperature", getattr(config, "LLM_TEMPERATURE", 0.1)))
    except Exception as e:
        logger.error(f"Error resolving user temperature: {e}", exc_info=True)
        return getattr(config, "LLM_TEMPERATURE", 0.1)


def _get_user_name(db: Session, user_id: int) -> str:
    """
    Resolve the display name for the user from User.name / settings.
    """
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return "User"
        if user.name and user.name.strip():
            return user.name.strip()
        settings = user.settings or {}
        return settings.get("username") or "User"
    except Exception as e:
        logger.error(f"Error resolving user name: {e}", exc_info=True)
        return "User"


class ChatService:
    def __init__(self):
        self.intents = {
            'query_schedule': self.handle_query_schedule,
            'add_task': self.handle_task_create,
            'query_knowledge': self.handle_query_knowledge,
            'task_create': self.handle_task_create,
            'task_query': self.handle_task_query,
            'task_update': self.handle_task_update,
            'task_delete': self.handle_task_delete,
            'day_summary': self.handle_day_summary,
            'reminder': self.handle_reminder,
            'search': self.handle_search,
            'change_name': self.handle_change_name,
            'general_chat': self.handle_general_chat
        }
    
    async def process_chat(self, user_id: int, message_data: any, db: Session):
        """
        Main chat processing with intelligent Tool Router.
        The bot now acts as an agent that can access schedule, create tasks, and query knowledge.
        """
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
            
            message_lower = message.lower()
            
            # ===== TOOL ROUTER: Intelligent Agent Logic =====
            
            # 1. Schedule/Calendar Query Detection
            schedule_keywords = ['schedule', 'calendar', 'what am i doing', 'what\'s on my schedule', 
                                'what do i have', 'am i free', 'free time', 'what am i scheduled',
                                'my day', 'appointments', 'meetings']
            if any(keyword in message_lower for keyword in schedule_keywords):
                logger.info(f"Detected schedule query: {message}")
                result = await self.handle_query_schedule(user_id, message, db, None)
                self.save_message(user_id, "assistant", result['response'], db, intent='query_schedule')
                result['suggestions'] = self.generate_suggestions('query_schedule', db, user_id)
                return result
            
            # 2. Task Creation Detection
            task_keywords = ['remind me', 'add task', 'create task', 'schedule a task', 
                           'add to my list', 'set a reminder', 'i need to', 'help me', 'remind',
                           'todo', 'to-do', 'buy', 'get', 'finish']
            if any(keyword in message_lower for keyword in task_keywords):
                logger.info(f"Detected task creation: {message}")
                # Use intent detection to extract task details
                intent_result = detect_intent(message)
                result = await self.handle_task_create(user_id, message, db, intent_result)
                self.save_message(user_id, "assistant", result['response'], db, intent='add_task')
                result['suggestions'] = self.generate_suggestions('add_task', db, user_id)
                return result
            
            # 3. Knowledge Base Query Detection (Question patterns)
            question_patterns = ['how', 'what is', 'what are', 'explain', 'tell me about', 
                               'summarize', 'what did', 'what does', 'describe', 'who', 'when', 
                               'where', 'why', 'can you', 'do you know']
            if any(message_lower.startswith(pattern) or f' {pattern} ' in message_lower 
                   for pattern in question_patterns):
                logger.info(f"Detected knowledge query: {message}")
                result = await self.handle_query_knowledge(user_id, message, db, None)
                self.save_message(user_id, "assistant", result['response'], db, intent='query_knowledge')
                result['suggestions'] = self.generate_suggestions('query_knowledge', db, user_id)
                return result
            
            # 4. Standard Intent Detection (fallback for other intents)
            intent_result = detect_intent(message)
            intent = intent_result.get('intent', 'general_chat')
            
            # Route to appropriate handler
            if intent == 'general_chat':
                result = await self.handle_general_chat(user_id, message, db, context)
            else:
                handler = self.intents.get(intent, self.handle_general_chat)
                # Pass intent_result to handler to access entities
                if asyncio.iscoroutinefunction(handler):
                    result = await handler(user_id, message, db, intent_result)
                else:
                    result = handler(user_id, message, db, intent_result)
                
            self.save_message(user_id, "assistant", result['response'], db, intent=intent)
            result['suggestions'] = self.generate_suggestions(intent, db, user_id)
            
            return result
            
        except Exception as e:
            logger.error(f"Chat processing error: {str(e)}", exc_info=True)
            return {
                "response": "I encountered an error. Please try again.",
                "action_taken": "error",
                "data": {"error": str(e)}
            }
    
    async def handle_task_create(self, user_id: int, message: str, db: Session, intent_data: dict):
        """Create task programmatically using TaskService"""
        try:
            entities = intent_data.get('entities', {})
            
            # Extract task details using LLM if not in entities
            if not entities.get('title'):
                # Use LLM to extract task details from natural language
                extract_prompt = f"""<|system|>
Extract task information from this message. Output JSON with: title, time (YYYY-MM-DD HH:MM format), duration (minutes), priority (low/medium/high/urgent).

Message: {message}
Current Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}
<|end|>
<|user|>
Extract task details.
<|end|>
<|assistant|>"""
                
                try:
                    temperature = _get_user_temperature(db, user_id)
                    extraction = await asyncio.to_thread(
                        llm.generate, extract_prompt, max_tokens=200, temperature=temperature
                    )
                    # Try to parse JSON from extraction
                    import json
                    extracted_data = json.loads(extraction.strip().replace('```json', '').replace('```', ''))
                    entities.update(extracted_data)
                except:
                    # Fallback: use message as title
                    entities['title'] = message[:100]
            
            # Parse due date
            due_date = None
            if entities.get('time'):
                try:
                    # Try ISO format first
                    due_date = datetime.fromisoformat(entities['time'].replace('Z', '+00:00'))
                except:
                    try:
                        # Try simple format YYYY-MM-DD HH:MM
                        due_date = datetime.strptime(entities['time'], "%Y-%m-%d %H:%M")
                    except:
                        pass
            
            # Safe integer casting with defaults
            duration_val = entities.get('duration')
            if duration_val is None:
                duration_minutes = 30
            else:
                try:
                    duration_minutes = int(duration_val)
                    if duration_minutes < 1:
                        duration_minutes = 30
                except (ValueError, TypeError):
                    duration_minutes = 30

            # Get title - use entities or fallback to message
            task_title = entities.get('title', message[:100].strip())
            if not task_title:
                task_title = "New Task"

            # Create task using TaskService (programmatic call)
            new_task = Task(
                title=task_title,
                description=message if len(message) > len(task_title) else None,
                due_date=due_date,
                priority=entities.get('priority', 'medium'),
                category=entities.get('category', 'Personal'),
                duration_minutes=duration_minutes,
                tags='[]',
                user_id=user_id
            )
            
            db.add(new_task)
            db.commit()
            db.refresh(new_task)
            
            response = f"I have added '{new_task.title}' to your list."
            if due_date:
                response += f" It's scheduled for {self.format_due_date(due_date)}."
            
            return {
                "response": response,
                "action_taken": "task_created",
                "data": {"task_id": new_task.id, "title": new_task.title}
            }
            
        except Exception as e:
            logger.error(f"Task creation error: {str(e)}", exc_info=True)
            return {"response": f"I couldn't create the task. Error: {str(e)}", "action_taken": "error"}
    
    async def handle_task_query(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        try:
            message_lower = message.lower()
            
            if any(word in message_lower for word in ['today', 'due today']):
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= datetime.now().replace(hour=0, minute=0, second=0),
                    Task.due_date < datetime.now().replace(hour=23, minute=59, second=59)
                ).all()
                header = "tasks due today"
            elif any(word in message_lower for word in ['tomorrow']):
                tomorrow = datetime.now() + timedelta(days=1)
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= tomorrow.replace(hour=0, minute=0, second=0),
                    Task.due_date < tomorrow.replace(hour=23, minute=59, second=59)
                ).all()
                header = "tasks due tomorrow"
            elif any(word in message_lower for word in ['week', 'this week']):
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False,
                    Task.due_date >= datetime.now(),
                    Task.due_date < datetime.now() + timedelta(days=7)
                ).all()
                header = "tasks this week"
            else:
                tasks = db.query(Task).filter(
                    Task.user_id == user_id,
                    Task.completed == False
                ).order_by(Task.due_date.asc()).limit(10).all()
                header = "pending tasks"
            
            if not tasks:
                return {
                    "response": "You don’t have any tasks that match that query right now.",
                    "action_taken": "task_query",
                    "data": {
                        "title": "No tasks found",
                        "tasks": []
                    }
                }

            response = f"You have {len(tasks)} {header}:"
            
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
            logger.error(f"Task query error: {str(e)}", exc_info=True)
            return {"response": "I couldn't retrieve your tasks.", "action_taken": "error"}
    
    async def handle_task_update(self, user_id: int, message: str, db: Session, intent_data: dict = None):
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
            logger.error(f"Task update error: {str(e)}", exc_info=True)
            return {"response": "I couldn't update the task.", "action_taken": "error"}
    
    async def handle_task_delete(self, user_id: int, message: str, db: Session, intent_data: dict = None):
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
            logger.error(f"Task delete error: {str(e)}", exc_info=True)
            return {"response": "I couldn't delete the task.", "action_taken": "error"}
    
    async def handle_query_schedule(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        """Handle schedule queries - fetch and format routine data using ScheduleService"""
        try:
            message_lower = message.lower()
            
            # Determine which date to query
            target_date = datetime.now()
            if 'tomorrow' in message_lower:
                target_date = datetime.now() + timedelta(days=1)
            elif 'yesterday' in message_lower:
                target_date = datetime.now() - timedelta(days=1)
            elif 'next week' in message_lower or 'week' in message_lower:
                # For week queries, we'll show today's schedule
                target_date = datetime.now()
            
            # Call ScheduleService to get today's routine
            routine = generate_routine(user_id, db, target_date)
            timeline = routine.get('timeline', [])
            
            # Filter out free blocks for summary
            events = [e for e in timeline if e.get('type') != 'free']
            
            if not events:
                response = f"You have no scheduled events for {target_date.strftime('%B %d, %Y')}."
                return {
                    "response": response,
                    "action_taken": "query_schedule",
                    "data": {"date": target_date.isoformat(), "events": []}
                }
            
            # Format response with markdown for better display
            date_str = target_date.strftime('%B %d, %Y')
            response = f"Here's your schedule for {date_str}:\n\n"
            
            for event in events:
                start_time = datetime.fromisoformat(event['start'])
                end_time = datetime.fromisoformat(event['end'])
                time_str = start_time.strftime('%I:%M %p')
                duration = (end_time - start_time).total_seconds() / 60
                
                event_type = event.get('type', 'event')
                title = event.get('title', 'Untitled')
                
                # Format based on event type
                if event_type == 'task':
                    priority = event.get('priority', 'medium')
                    response += f"• **{title}** ({time_str}, {int(duration)} min) - Priority: {priority}\n"
                elif event_type == 'routine' or event_type == 'class':
                    response += f"• **{title}** ({time_str}, {int(duration)} min) - Routine\n"
                else:
                    response += f"• **{title}** ({time_str}, {int(duration)} min)\n"
            
            # Format events for frontend
            formatted_events = [{
                "title": e.get('title', 'Untitled'),
                "start": e.get('start'),
                "end": e.get('end'),
                "type": e.get('type', 'event'),
                "priority": e.get('priority')
            } for e in events]
            
            return {
                "response": response,
                "action_taken": "query_schedule",
                "data": {
                    "date": target_date.isoformat(),
                    "events": formatted_events,
                    "count": len(events)
                }
            }
            
        except Exception as e:
            logger.error(f"Schedule query error: {str(e)}", exc_info=True)
            return {
                "response": "I couldn't retrieve your schedule. Please try again.",
                "action_taken": "error"
            }
    
    async def handle_query_knowledge(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        """Handle knowledge base queries using RAG Service"""
        try:
            # Extract the actual query (remove phrases like "summarize", "what did", etc.)
            query = message.lower()
            query = re.sub(r'(summarize|what did|what does|tell me about|explain|how)', '', query)
            query = query.strip()
            
            # Call RAG Service to query knowledge base
            rag_context = query_rag(query if query else message)
            
            if not rag_context or rag_context.strip() == "":
                # Fallback to general knowledge if no documents found
                rag_context = "No specific documents found in knowledge base."
                found_docs = False
            else:
                found_docs = True
            
            # Use LLM to generate a natural response based on RAG context
            prompt = f"""<|system|>
You are Aura, an advanced personal AI assistant. You are warm, clear, and practical.

You have access to the user's uploaded documents and prior messages.
If the user asks about something in their documents (Context provided below), use that information.
If the Context says "No specific documents found", or if the documents don't contain the answer, 
ANSWER FROM YOUR GENERAL KNOWLEDGE. Do not say "I couldn't find it in your documents" unless 
the user specifically asked "what does my document say about X".

When the user greets you (e.g. "hi", "hello"), respond naturally and conversationally.

Context from Knowledge Base:
{rag_context}
<|end|>
<|user|>
{message}
<|end|>
<|assistant|>"""
            
            temperature = _get_user_temperature(db, user_id)
            response = await asyncio.to_thread(
                llm.generate, prompt, max_tokens=500, temperature=temperature
            )
            response = response.replace("<|end|>", "").replace("<|user|>", "").replace("<|assistant|>", "").strip()
            
            return {
                "response": response,
                "action_taken": "query_knowledge",
                "data": {"found": found_docs, "context_length": len(rag_context)}
            }
            
        except Exception as e:
            logger.error(f"Knowledge query error: {str(e)}", exc_info=True)
            return {
                "response": "I encountered an error while searching your knowledge base. Please try again.",
                "action_taken": "error"
            }
    
    async def handle_day_summary(self, user_id: int, message: str, db: Session, intent_data: dict = None):
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
            
            # Run LLM in thread
            temperature = _get_user_temperature(db, user_id)
            summary = await asyncio.to_thread(
                llm.generate, prompt, max_tokens=200, temperature=temperature
            )
            
            return {
                "response": summary,
                "action_taken": "day_summary",
                "data": {
                    "overview": schedule['overview'],
                    "completed_today": completed_today
                }
            }
            
        except Exception as e:
            logger.error(f"Day summary error: {str(e)}", exc_info=True)
            return {"response": "I couldn't generate your day summary.", "action_taken": "error"}
    
    async def handle_reminder(self, user_id: int, message: str, db: Session, intent_data: dict):
        from .reminder_service import schedule_reminder
        entities = intent_data.get('entities', {})
        time_str = entities.get('time')
        title = entities.get('title', 'Untitled Reminder')
        
        if time_str:
            try:
                reminder_time = datetime.fromisoformat(time_str)
                # Create a dummy task for the reminder
                task = Task(
                    title=title, 
                    due_date=reminder_time, 
                    user_id=user_id, 
                    category="Reminder",
                    priority="high"
                )
                db.add(task)
                db.commit()
                db.refresh(task)
                
                schedule_reminder(task.id, reminder_time)
                return {"response": f"⏰ Reminder set for '{title}' at {reminder_time.strftime('%I:%M %p')}", "action_taken": "reminder_set"}
            except Exception as e:
                logger.error(f"Reminder error: {str(e)}", exc_info=True)
                return {"response": "I couldn't set that reminder. Please check the time format.", "action_taken": "error"}
        
        return {"response": "When should I remind you?", "action_taken": "ask_slot"}
    
    async def handle_search(self, user_id: int, message: str, db: Session, intent_data: dict = None):
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
            logger.error(f"Search error: {str(e)}", exc_info=True)
            return {"response": "I couldn't complete the search.", "action_taken": "error"}
    
    async def handle_change_name(self, user_id: int, message: str, db: Session, intent_data: dict = None):
        """
        Handle requests like 'Call me Rylix from now on'.
        """
        try:
            entities = intent_data.get("entities", {}) if intent_data else {}
            candidate = entities.get("username")

            if not candidate:
                # Simple regex fallback
                match = re.search(r"call me ([A-Za-z][A-Za-z0-9_\-\s']{0,40})", message, re.IGNORECASE)
                if match:
                    candidate = match.group(1).strip()

            if not candidate:
                return {
                    "response": "What should I call you?",
                    "action_taken": "ask_name"
                }

            new_name = update_user_name(user_id, candidate, db)
            return {
                "response": f"Got it, I’ll call you {new_name} from now on.",
                "action_taken": "name_updated",
                "data": {"username": new_name}
            }
        except Exception as e:
            logger.error(f"Change name error: {str(e)}", exc_info=True)
            return {
                "response": "I couldn't update your name right now.",
                "action_taken": "error"
            }
    
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
            logger.error(f"Context Error: {str(e)}", exc_info=True)
            return ""
    
    def get_recent_history(self, user_id: int, db: Session, limit: int = 10) -> str:
        """
        Return a short, linearized view of the most recent conversation turns.
        This helps the LLM stay grounded in the current thread without exceeding
        the context window.
        """
        try:
            history = (
                db.query(ChatHistory)
                .filter(ChatHistory.user_id == user_id)
                .order_by(ChatHistory.timestamp.desc())
                .limit(limit)
                .all()
            )
            if not history:
                return ""

            # Reverse to chronological order
            history = list(reversed(history))
            lines = []
            for h in history:
                role = "User" if h.role == "user" else "Aura"
                content = (h.content or "").strip()
                if not content:
                    continue
                lines.append(f"{role}: {content}")
            return "\n".join(lines)
        except Exception as e:
            logger.error(f"History context error: {str(e)}", exc_info=True)
            return ""
    
    async def handle_general_chat(self, user_id: int, message: str, db: Session, context: dict = None):
        try:
            # Get user context (tasks)
            task_context = self.get_user_context(user_id, db)
            user_name = context.get('user_name', 'User') if context else 'User'
            
            # Get RAG Context
            rag_context = query_rag(message)
            # Get recent conversation history
            conversation_history = self.get_recent_history(user_id, db, limit=10)
            
            # Phi-3 prompt format
            prompt = "<|system|>\n"
            prompt += (
                f"You are Aura, an advanced, context-aware AI assistant talking to {user_name}.\n"
                "Your personality: thoughtful, calm, and efficient. You explain things clearly without rambling,\n"
                "and you adapt your tone to be encouraging but not overly formal.\n\n"
                "HARD RULES:\n"
                "- Never mention your internal tools, retrieval system, model name, vector stores, or embeddings.\n"
                "- If you use information from the user's documents, refer to it naturally (e.g. "
                "\"from your notes\" or \"in what you shared\") without describing how you accessed it.\n"
                "- For simple greetings (\"hi\", \"hello\"), respond naturally and briefly.\n"
                "- Prefer concrete, helpful suggestions over vague advice.\n"
                "- Do NOT output internal tokens like BEGININPUT or ENDINPUT.\n\n"
            )

            if task_context:
                prompt += f"User schedule/tasks context: {task_context}\n"

            if conversation_history:
                prompt += "Recent conversation (most recent last):\n"
                prompt += conversation_history + "\n"

            if rag_context:
                prompt += (
                    "Additional context from the user's documents (use only if relevant):\n"
                    f"{rag_context}\n"
                )

            prompt += "<|end|>\n"
            prompt += f"<|user|>\n{message}<|end|>\n<|assistant|>"
            
            # Run LLM in thread
            temperature = _get_user_temperature(db, user_id)
            response = await asyncio.to_thread(
                llm.generate, prompt, max_tokens=500, temperature=temperature
            )
            
            # Post-processing: Strip tags
            response = response.replace("<|end|>", "").replace("<|user|>", "").replace("<|assistant|>", "").strip()
            
            return {
                "response": response,
                "action_taken": "general_chat",
                "data": {}
            }
            
        except Exception as e:
            logger.error(f"General chat error: {str(e)}", exc_info=True)
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
            logger.error(f"Error saving message: {str(e)}", exc_info=True)

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

async def process_chat(user_id: int, message: str, db: Session):
    return await chat_service.process_chat(user_id, message, db)
