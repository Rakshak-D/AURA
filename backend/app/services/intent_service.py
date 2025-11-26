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
- intent: create_task, query_schedule, generate_routine, search, general_chat
- entities: title, time (YYYY-MM-DD HH:MM), duration (minutes), category (Personal, Work, College, Health)
- sentiment: positive, neutral, negative

Current Time: {current_time}

Example Input: "Schedule a gym session for 1 hour at 5pm"
Example Output: {{"intent": "create_task", "entities": {{"title": "Gym session", "time": "2025-11-23 17:00", "duration": 60, "category": "Health"}}, "sentiment": "neutral"}}
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