from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.sql_models import ChatHistory
from ..models.pydantic_models import ChatMessage, ChatResponse
from ..services.chat_service import process_chat
from ..utils.security import sanitize_input, limiter
from datetime import datetime

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
@limiter.limit("5/minute")
async def chat_endpoint(request: Request, msg: ChatMessage, db: Session = Depends(get_db)):
    # Note: Request object is needed for slowapi
    try:
        # Sanitize input
        user_message = sanitize_input(msg.message)
        
        # Save User Message
        user_msg = ChatHistory(
            user_id=1, 
            role="user", 
            content=user_message,
            timestamp=datetime.utcnow()
        )
        db.add(user_msg)
        db.commit()
        
        # Process Chat
        # We pass the original message object as process_chat expects it (or we can adapt process_chat)
        # Based on chat_service.py, process_chat takes (user_id, message_data, db)
        # message_data can be str or object. We pass the msg object.
        result = await process_chat(1, msg, db)
        
        return result

    except Exception as e:
        print(f"An error occurred: {e}")
        raise HTTPException(status_code=500, detail=str(e))
