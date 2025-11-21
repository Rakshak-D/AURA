from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.pydantic_models import ChatMessage, ChatResponse
from ..services.chat_service import process_chat

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    return process_chat(1, msg.message, db)