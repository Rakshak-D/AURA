from datetime import datetime, timedelta
import re
from typing import Dict, Optional, List

def detect_intent(message: str) -> str:
    """Detect the intent from user message"""
    message_lower = message.lower()
    
    # Task creation keywords
    task_create_keywords = ['create', 'add', 'schedule', 'remind me', 'todo', 'task', 'need to', 'have to', 'buy', 'call', 'email', 'meeting']
    if any(keyword in message_lower for keyword in task_create_keywords):
        return 'task_create'
    
    # Task query keywords
    task_query_keywords = ['show', 'list', 'what', 'tasks', 'todo', 'pending', 'upcoming', 'due', 'today', 'tomorrow', 'week']
    if any(keyword in message_lower for keyword in task_query_keywords) and 'create' not in message_lower:
        return 'task_query'
    
    # Task completion keywords
    task_complete_keywords = ['complete', 'done', 'finish', 'mark', 'check']
    if any(keyword in message_lower for keyword in task_complete_keywords):
        return 'task_update'
    
    # Delete keywords
    delete_keywords = ['delete', 'remove', 'cancel']
    if any(keyword in message_lower for keyword in delete_keywords):
        return 'task_delete'
    
    # Summary keywords
    summary_keywords = ['summary', 'summarize', 'overview', 'how am i doing', 'progress', 'today']
    if any(keyword in message_lower for keyword in summary_keywords) and any(w in message_lower for w in ['my', 'day', 'week']):
        return 'day_summary'
    
    # Search keywords
    search_keywords = ['search', 'find', 'look for']
    if any(keyword in message_lower for keyword in search_keywords):
        return 'search'
    
    return 'general_chat'

def extract_task_info(message: str) -> Dict:
    """Extract task information from message"""
    info = {
        'title': message,
        'description': None,
        'priority': 'medium',
        'tags': [],
        'recurring': None
    }
    
    # Detect priority
    if any(word in message.lower() for word in ['urgent', 'asap', 'important', 'critical']):
        info['priority'] = 'urgent'
    elif any(word in message.lower() for word in ['high priority', 'high']):
        info['priority'] = 'high'
    elif any(word in message.lower() for word in ['low priority', 'low', 'sometime']):
        info['priority'] = 'low'
    
    # Detect recurring
    if 'every day' in message.lower() or 'daily' in message.lower():
        info['recurring'] = 'daily'
    elif 'every week' in message.lower() or 'weekly' in message.lower():
        info['recurring'] = 'weekly'
    elif 'every month' in message.lower() or 'monthly' in message.lower():
        info['recurring'] = 'monthly'
    
    # Extract tags
    tags = re.findall(r'#(\w+)', message)
    if tags:
        info['tags'] = tags
    
    # Clean up title
    info['title'] = clean_task_title(message)
    
    return info

def clean_task_title(message: str) -> str:
    """Clean task title by removing command words and time expressions"""
    command_words = ['create', 'add', 'schedule', 'remind me to', 'remind me', 'i need to', 'i have to', 'todo', 'task']
    
    cleaned = message
    for word in command_words:
        cleaned = re.sub(f'\\b{word}\\b', '', cleaned, flags=re.IGNORECASE)
    
    # Remove time-related phrases
    time_patterns = [
        r'tomorrow', r'today', r'next week', r'next month',
        r'in \d+ (hour|hours|day|days|week|weeks)',
        r'at \d+:\d+ (am|pm|AM|PM)',
        r'on (monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
        r'(urgent|asap|high priority|low priority)',
        r'#\w+'
    ]
    
    for pattern in time_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip().capitalize()

def extract_date_time(message: str) -> Optional[datetime]:
    """Extract date and time from message"""
    message_lower = message.lower()
    now = datetime.now()
    
    # Today
    if 'today' in message_lower:
        time = extract_time(message)
        if time:
            return now.replace(hour=time[0], minute=time[1], second=0, microsecond=0)
        return now.replace(hour=18, minute=0, second=0, microsecond=0)
    
    # Tomorrow
    if 'tomorrow' in message_lower:
        tomorrow = now + timedelta(days=1)
        time = extract_time(message)
        if time:
            return tomorrow.replace(hour=time[0], minute=time[1], second=0, microsecond=0)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Next week
    if 'next week' in message_lower:
        next_week = now + timedelta(days=7)
        return next_week.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # In X days
    match = re.search(r'in (\d+) days?', message_lower)
    if match:
        days = int(match.group(1))
        future = now + timedelta(days=days)
        return future.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # In X hours
    match = re.search(r'in (\d+) hours?', message_lower)
    if match:
        hours = int(match.group(1))
        return now + timedelta(hours=hours)
    
    # Specific day of week
    days_of_week = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }
    
    for day_name, day_num in days_of_week.items():
        if day_name in message_lower:
            current_day = now.weekday()
            days_ahead = day_num - current_day
            if days_ahead <= 0:
                days_ahead += 7
            target_date = now + timedelta(days=days_ahead)
            time = extract_time(message)
            if time:
                return target_date.replace(hour=time[0], minute=time[1], second=0, microsecond=0)
            return target_date.replace(hour=9, minute=0, second=0, microsecond=0)
    
    # Date format MM/DD or MM/DD/YYYY
    match = re.search(r'(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?', message)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3)) if match.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            date = datetime(year, month, day)
            time = extract_time(message)
            if time:
                return date.replace(hour=time[0], minute=time[1])
            return date.replace(hour=9, minute=0)
        except ValueError:
            pass
    
    return None

def extract_time(message: str) -> Optional[tuple]:
    """Extract time from message"""
    # Format: "at 3:30 pm" or "at 3 pm"
    match = re.search(r'at (\d{1,2}):(\d{2})\s*(am|pm)', message.lower())
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        
        return (hour, minute)
    
    # Format: "at 3 pm"
    match = re.search(r'at (\d{1,2})\s*(am|pm)', message.lower())
    if match:
        hour = int(match.group(1))
        period = match.group(2)
        
        if period == 'pm' and hour != 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        
        return (hour, 0)
    
    return None