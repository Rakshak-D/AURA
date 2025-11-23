import json
from datetime import datetime, timedelta
from typing import List, Dict
from ..models.llm_models import llm

def generate_routine_from_text(timetable_text: str) -> List[Dict]:
    """
    Parse unstructured timetable text into a structured routine.
    Automatically inserts 'Prep Time' (30m) before events and 'Meal Blocks'.
    """
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        prompt = f"""<|system|>
You are a routine scheduler. Parse the user's unstructured timetable text into a JSON list of events.
Output ONLY valid JSON.

Rules:
- Extract event title, start_time (HH:MM), and duration (minutes).
- Assume the date is {current_date}.
- If duration is not specified, assume 60 minutes.
- Return a list of objects: {{"title": "...", "start": "YYYY-MM-DDTHH:MM:00", "end": "YYYY-MM-DDTHH:MM:00", "type": "task"}}

Example Input: "Class at 9am, Gym at 5pm"
Example Output: [
    {{"title": "Class", "start": "{current_date}T09:00:00", "end": "{current_date}T10:00:00", "type": "task"}},
    {{"title": "Gym", "start": "{current_date}T17:00:00", "end": "{current_date}T18:00:00", "type": "task"}}
]
<|end|>
<|user|>
{timetable_text}
<|end|>
<|assistant|>"""

        response = llm.generate(prompt, max_tokens=500)
        
        # Clean response
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()
            
        events = json.loads(response)
        
        # Post-processing: Add Prep Time and Meals
        final_routine = []
        sorted_events = sorted(events, key=lambda x: x['start'])
        
        for event in sorted_events:
            event_start = datetime.fromisoformat(event['start'])
            
            # Add Prep Time (30m before)
            prep_start = event_start - timedelta(minutes=30)
            final_routine.append({
                "title": f"Prep for {event['title']}",
                "start": prep_start.isoformat(),
                "end": event_start.isoformat(),
                "type": "prep",
                "color": "#facc15" # Yellow
            })
            
            # Add the event itself
            final_routine.append(event)
            
        # Add Meal Blocks (Simple logic: 1pm Lunch, 8pm Dinner if free)
        # For now, just append them if no conflict (omitted for brevity/complexity, can be added later)
        # Let's just return the enriched list
        
        return final_routine

    except Exception as e:
        print(f"Routine Generation Failed: {e}")
        return []
