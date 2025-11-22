import re
from datetime import datetime, timedelta
from typing import Dict, Optional

def detect_intent(message: str) -> str:
    """
    ULTRA-CONSERVATIVE intent detection.
    Only classify as task/reminder with EXPLICIT keywords to avoid false positives.
    DEFAULT: general_chat for anything questionable.
    """
    msg_lower = message.lower().strip()
    
    # EXPLICIT task creation - must have clear command words
    task_create_patterns = [
        r'\b(create|add|make|new)\s+(a\s+)?task\b',
        r'\btask:\s*',
        r'\bremind\s+me\s+to\b',
        r'\bset\s+(a\s+)?reminder\b',
    ]
    
    for pattern in task_create_patterns:
        if re.search(pattern, msg_lower):
            return 'task_create'
    
    # Task queries - must explicitly mention tasks
    task_query_patterns = [
        r'\b(show|list|display|get|what are)\s+(my\s+)?tasks?\b',
        r'\bmy\s+tasks?\b',
        r'\bwhat.s\s+(on\s+)?my\s+schedule\b',
    ]
    
    for pattern in task_query_patterns:
        if re.search(pattern, msg_lower):
            return 'task_query'
    
    # Task completion - explicit
    if re.search(r'\b(complete|finish|mark)\s+task\b', msg_lower):
        return 'task_update'
    
    # Task delete - explicit
    if re.search(r'\b(delete|remove)\s+task\b', msg_lower):
        return 'task_delete'
    
    # Summary - explicit
    if re.search(r'\b(summarize|summary\s+of)\s+(my\s+)?(day|week)\b', msg_lower):
        return 'day_summary'
    
    # Search - must say "search"
    if re.search(r'\bsearch\s+(for|in)\b', msg_lower):
        return 'search'
    
    # DEFAULT: General chat (most questions, explanations, etc.)
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
    elif any(word in message.lower() for word in ['low priority', 'low']):
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
    """Clean task title by removing command words"""
    command_words = ['create', 'add', 'schedule', 'remind me to', 'remind me', 'task']
    
    cleaned = message
    for word in command_words:
        cleaned = re.sub(f'\\b{word}\\b', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip().capitalize()

def extract_date_time(message: str) -> Optional[datetime]:
    """Extract date and time from message"""
    message_lower = message.lower()
    now = datetime.now()
    
    if 'today' in message_lower:
        return now.replace(hour=18, minute=0, second=0, microsecond=0)
    
    if 'tomorrow' in message_lower:
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    if 'next week' in message_lower:
        next_week = now + timedelta(days=7)
        return next_week.replace(hour=9, minute=0, second=0, microsecond=0)
    
    return None

def extract_time(message: str) -> Optional[tuple]:
    """Extract time from message"""
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
    
    return None