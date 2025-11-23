from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, Task, ChatHistory, Document

router = APIRouter()

@router.get("/search")
def search_all(q: str, db: Session = Depends(get_db)):
    if not q:
        return {"results": []}
    
    query = q.lower()
    results = []
    
    # Search Tasks
    tasks = db.query(Task).filter(
        Task.user_id == 1,
        (Task.title.ilike(f'%{query}%') | Task.description.ilike(f'%{query}%'))
    ).all()
    
    for task in tasks:
        results.append({
            "type": "task",
            "id": task.id,
            "title": task.title,
            "snippet": (task.description[:100] + "...") if task.description else "No description",
            "date": task.created_at.strftime("%Y-%m-%d")
        })
        
    # Search Chat History
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == 1,
        ChatHistory.content.ilike(f'%{query}%')
    ).order_by(ChatHistory.timestamp.desc()).limit(10).all()
    
    for chat in chats:
        results.append({
            "type": "chat",
            "id": chat.id,
            "title": f"Chat: {chat.role}",
            "snippet": (chat.content[:100] + "...") if len(chat.content) > 100 else chat.content,
            "date": chat.timestamp.strftime("%Y-%m-%d %H:%M")
        })

    # Search Documents
    docs = db.query(Document).filter(
        Document.user_id == 1,
        Document.filename.ilike(f'%{query}%')
    ).all()
    
    for doc in docs:
        results.append({
            "type": "document",
            "id": doc.id,
            "title": doc.filename,
            "snippet": f"Document uploaded on {doc.uploaded_at.strftime('%Y-%m-%d')}",
            "date": doc.uploaded_at.strftime("%Y-%m-%d")
        })
    
    return {"results": results}
