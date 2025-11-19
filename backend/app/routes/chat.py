from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import get_db
from services.rag_service import rag_qa
from services.personalization import get_context
from models.pydantic_models import ChatMessage
from models.llm_models import llm

router = APIRouter()

@router.post("/chat")
def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    context = get_context(1) + "\n" + rag_qa(msg.message)  # User ID=1 stub
    prompt = f"{context}\nUser: {msg.message}\nAura:"
    response = llm.generate(prompt)
    return {"response": response}