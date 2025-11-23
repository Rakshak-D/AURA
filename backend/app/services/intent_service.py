import json
from datetime import datetime
from typing import Dict
from ..models.llm_models import llm

def detect_intent(message: str) -> Dict:
    """
    Detect intent using LLM exclusively.
    Returns a dictionary with 'intent', 'entities', and 'sentiment'.
    """
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = f"""<|system|>
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

        response = llm.generate(prompt, max_tokens=200)
        
        # Clean response to ensure JSON
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
            
        data = json.loads(response)
        
        # Normalize keys
        if 'due_date' in data.get('entities', {}):
            data['entities']['time'] = data['entities']['due_date']
            
        return data
        
    except Exception as e:
        print(f"LLM Intent Detection Failed: {e}")
        # Minimal fallback to prevent crash
        return {
            "intent": "general_chat",
            "entities": {},
            "sentiment": "neutral"
        }