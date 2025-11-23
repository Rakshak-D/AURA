import re
import json
from datetime import datetime, timedelta
from typing import Dict, Optional
from ..models.llm_models import llm

def detect_intent(message: str) -> Dict:
    """
    Detect intent using LLM with fallback to Regex.
    Returns a dictionary with 'intent' and 'entities'.
    """
    # 1. Try LLM Detection
    try:
        prompt = f"""<|system|>
You are an intent classification engine. Analyze the user's message and extract the intent and entities.
Output ONLY valid JSON.

Intents:
- task_create: Create a new task or reminder (e.g., "Remind me to...", "Add task...", "Study Physics tomorrow")
- task_query: Ask about tasks/schedule (e.g., "What do I have today?", "Show my tasks")
- task_update: Complete or update a task (e.g., "Mark Physics as done")
- task_delete: Delete a task (e.g., "Remove the study task")
- day_summary: Ask for a summary (e.g., "Summarize my day")
- search: Search for something (e.g., "Search for notes on gravity")
- general_chat: Everything else (greetings, questions, etc.)

Entities to extract:
- title: Task title
- due_date: Date/time in "YYYY-MM-DD HH:MM" format (calculate relative dates like "tomorrow" based on current time: {datetime.now().strftime("%Y-%m-%d %H:%M")})
- priority: urgent, high, medium, low
- category: Personal, Work, College, Health

Example Input: "Remind me to submit assignment tomorrow at 5pm"
Example Output: {{"intent": "task_create", "entities": {{"title": "Submit assignment", "due_date": "2025-11-24 17:00", "priority": "medium"}}}}
<|end|>
<|user|>
{message}
<|end|>
<|assistant|>"""

        response = llm.generate(prompt, max_tokens=200)
        
        # Clean response to ensure JSON
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
            
        data = json.loads(response)
        return data
        
    except Exception as e:
        print(f"LLM Intent Detection Failed: {e}. Falling back to Regex.")
        return detect_intent_regex(message)

def detect_intent_regex(message: str) -> Dict:
    """Fallback Regex detection"""
    msg_lower = message.lower().strip()
    intent = 'general_chat'
    entities = {}
    
    if re.search(r'\b(create|add|make|new|remind)\b', msg_lower):
        intent = 'task_create'
    elif re.search(r'\b(show|list|what|schedule)\b', msg_lower) and ('task' in msg_lower or 'schedule' in msg_lower):
        intent = 'task_query'
    elif re.search(r'\b(complete|finish|mark|done)\b', msg_lower):
        intent = 'task_update'
    elif re.search(r'\b(delete|remove)\b', msg_lower):
        intent = 'task_delete'
    elif re.search(r'\b(summarize|summary)\b', msg_lower):
        intent = 'day_summary'
    elif 'search' in msg_lower:
        intent = 'search'
        
    if intent == 'task_create':
        entities = extract_task_info_regex(message)
        
    return {"intent": intent, "entities": entities}

def extract_task_info_regex(message: str) -> Dict:
    """Legacy regex extraction for fallback"""
    info = {
        'title': message,
        'priority': 'medium',
        'tags': [],
        'recurring': None
    }
    
    # Simple priority detection
    if 'urgent' in message.lower(): info['priority'] = 'urgent'
    
    # Simple title cleaning
    for word in ['create', 'add', 'task', 'remind me to']:
        info['title'] = re.sub(f'\\b{word}\\b', '', info['title'], flags=re.IGNORECASE)
    
    info['title'] = info['title'].strip().capitalize()
    return info

# Keep these for compatibility if imported elsewhere, but they are largely superseded
def extract_task_info(message: str) -> Dict:
    return extract_task_info_regex(message)

def extract_date_time(message: str) -> Optional[datetime]:
    # This is now handled by LLM, but kept for fallback
    return None