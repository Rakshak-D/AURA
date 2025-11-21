from sqlalchemy.orm import Session
from ..database import ChatHistory, Task
from ..models.llm_models import llm
from .rag_service import query_rag
from datetime import datetime, timedelta
import json
import re

def process_chat(user_id: int, message: str, db: Session):
    # 1. Input Validation
    if not message or not message.strip():
        return {"response": "Please say something!", "action_taken": None}

    # 2. Save User Message
    db.add(ChatHistory(user_id=user_id, role="user", content=message))
    db.commit()

    # 3. Intent Detection (Simple Rule-based + LLM Extraction for complex tasks)
    lower_msg = message.lower()
    if any(x in lower_msg for x in ["remind me", "schedule", "add task", "i have a test", "buy milk"]):
        # Attempt to extract task details using LLM
        try:
            extraction_prompt = (
                f"User input: '{message}'\n"
                f"Current Time: {datetime.now()}\n"
                "Extract task JSON: {title: str, due_date: YYYY-MM-DD HH:MM:SS (or null)}. "
                "Return ONLY JSON."
            )
            # This is a lightweight call - depending on model intelligence
            extraction = llm.generate(extraction_prompt, max_tokens=100)
            # Simple cleanup for JSON
            extraction = extraction.strip().replace("```json", "").replace("```", "")
            task_data = json.loads(extraction)
            
            new_task = Task(
                title=task_data.get("title", "Untitled Task"),
                user_id=user_id,
                due_date=datetime.strptime(task_data["due_date"], "%Y-%m-%d %H:%M:%S") if task_data.get("due_date") else None
            )
            db.add(new_task)
            db.commit()
            
            response_text = f"I've scheduled: {new_task.title}"
            if new_task.due_date:
                response_text += f" for {new_task.due_date}"
            
            # Save AI Response
            db.add(ChatHistory(user_id=user_id, role="assistant", content=response_text))
            db.commit()
            return {"response": response_text, "action_taken": "task_created"}
        except:
            # Fallback if extraction fails
            pass

    # 4. Retrieve Context (History + RAG)
    history = db.query(ChatHistory).filter_by(user_id=user_id).order_by(ChatHistory.timestamp.desc()).limit(5).all()
    history.reverse()
    
    history_text = ""
    for h in history:
        history_text += f"{'User' if h.role == 'user' else 'Aura'}: {h.content}\n"

    rag_context = query_rag(message)
    system_context = "You are Aura, a helpful, witty, and efficient AI assistant. Keep answers concise."
    
    prompt = f"{system_context}\n\nRelevant Info: {rag_context}\n\nChat History:\n{history_text}\nUser: {message}\nAura:"
    
    # 5. Generate Response
    response = llm.generate(prompt)
    
    # 6. Save AI Response
    db.add(ChatHistory(user_id=user_id, role="assistant", content=response))
    db.commit()

    return {"response": response, "action_taken": "chat"}