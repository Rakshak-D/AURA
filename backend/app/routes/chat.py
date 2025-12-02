from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime

from ..database import get_db
from ..models.sql_models import ChatHistory
from ..models.pydantic_models import ChatMessage, ChatResponse
from ..services.chat_service import process_chat
from ..utils.security import sanitize_input, limiter
from ..utils.responses import success_response

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
@limiter.limit("5/minute")
async def chat_endpoint(request: Request, msg: ChatMessage, db: Session = Depends(get_db)):
    """
    Primary chat endpoint. Persists the raw user message and then delegates
    to the ChatService, which handles tool routing and RAG.
    """
    # Note: Request object is needed for slowapi
    try:
        # Sanitize input
        user_message = sanitize_input(msg.message)

        # Save User Message
        user_msg = ChatHistory(
            user_id=1,
            role="user",
            content=user_message,
            timestamp=datetime.utcnow(),
        )
        db.add(user_msg)
        db.commit()

        # Process Chat
        # Based on chat_service.py, process_chat takes (user_id, message_data, db)
        result = await process_chat(1, msg, db)

        return result

    except HTTPException:
        # Let explicit HTTP errors bubble up
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Chat endpoint error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/chat/history")
async def clear_chat_history(db: Session = Depends(get_db)):
    """
    Clear all stored chat history for the default user.
    """
    try:
        deleted = db.query(ChatHistory).filter(ChatHistory.user_id == 1).delete()
        db.commit()
        return success_response(data={"deleted": deleted}, message="Chat history cleared.")
    except Exception as e:
        db.rollback()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error clearing chat history: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to clear chat history")
