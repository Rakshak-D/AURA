import json
from datetime import datetime
from typing import Dict
from ..models.llm_models import llm
import re

def extract_json_from_text(text: str) -> Dict:
    """Extract JSON object from text using regex"""
    try:
        # Find the first { and the last }
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str)
        return None
    except Exception:
        return None

def detect_intent(message: str) -> Dict:
    """
    Detect intent using LLM exclusively.
    Returns a dictionary with 'intent', 'entities', and 'sentiment'.
    """
    max_retries = 2
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    base_prompt = f"""<|system|>
You are an intent classification engine. Output ONLY valid JSON.
Extract:
- intent: One of: query_schedule, add_task, query_knowledge, general_chat, task_query, day_summary, search, change_name
- entities: title, time (YYYY-MM-DD HH:MM), duration (minutes), category (Personal, Work, College, Health)
- sentiment: positive, neutral, negative

Intent Classification Rules:
- query_schedule: Questions about schedule, calendar, availability (e.g., "What am I doing today?", "Do I have free time at 4?", "What's on my schedule?")
- add_task: Creating/adding tasks or reminders (e.g., "Remind me to call John at 5pm", "Add a task to buy groceries")
- query_knowledge: Questions about uploaded documents, knowledge base (e.g., "Summarize the PDF I uploaded", "What did the document say about X?")
- task_query: Asking about existing tasks (e.g., "What tasks do I have?", "Show my tasks")
- day_summary: Requesting daily summary or overview
- search: Searching for specific information
- general_chat: General conversation, greetings, jokes

Current Time: {current_time}

Example Input: "What am I doing today?"
Example Output: {{"intent": "query_schedule", "entities": {{}}, "sentiment": "neutral"}}

Example Input: "Remind me to call John at 5pm"
Example Output: {{"intent": "add_task", "entities": {{"title": "Call John", "time": "2025-11-23 17:00"}}, "sentiment": "neutral"}}

Example Input: "Summarize the PDF I uploaded"
Example Output: {{"intent": "query_knowledge", "entities": {{}}, "sentiment": "neutral"}}

Example Input: "Call me Rylix from now on"
Example Output: {{"intent": "change_name", "entities": {{"username": "Rylix"}}, "sentiment": "positive"}}
<|end|>
<|user|>
{message}
<|end|>
<|assistant|>"""

    for attempt in range(max_retries):
        try:
            response = llm.generate(base_prompt, max_tokens=200)
            
            # Try to extract and parse JSON
            data = extract_json_from_text(response)
            
            if data:
                # Normalize keys
                if 'due_date' in data.get('entities', {}):
                    data['entities']['time'] = data['entities']['due_date']
                return data
            
            print(f"Attempt {attempt + 1}: Invalid JSON from LLM. Retrying...")
            
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error - {e}")

    # Fallback if all retries fail
    print("All intent detection attempts failed. Defaulting to general_chat.")
    return {
        "intent": "general_chat",
        "entities": {},
        "sentiment": "neutral"
    }