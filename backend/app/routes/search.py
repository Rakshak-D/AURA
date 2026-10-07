from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_chroma_collection, get_db
from ..auth import get_current_user_id
from ..models.sql_models import ChatHistory, Task

router = APIRouter()

@router.get("/search")
def search_all(q: str, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):  # noqa: B008 - FastAPI dependency injection
    if not q:
        return {"tasks": [], "knowledge": []}
    
    query = q.lower()
    user_id = current_user_id
    results = {"tasks": [], "knowledge": []}
    
    # 1. Search Tasks (SQL Fuzzy)
    tasks = db.query(Task).filter(
        Task.user_id == user_id,
        (Task.title.ilike(f'%{query}%') | Task.description.ilike(f'%{query}%'))
    ).all()
    
    for task in tasks:
        results["tasks"].append({
            "id": task.id,
            "title": task.title,
            "snippet": (task.description[:100] + "...") if task.description else "No description",
            "date": task.created_at.strftime("%Y-%m-%d"),
            "status": "Completed" if task.completed else "Pending",
            "priority": task.priority
        })
        
    # 2. Search Knowledge (Documents via ChromaDB + Chats via SQL)
    
    # A. Documents (Vector Search)
    try:
        collection = get_chroma_collection()
        vector_results = collection.query(query_texts=[q], n_results=5, where={"user_id": user_id})
        if vector_results["documents"]:
            for i, doc_text in enumerate(vector_results["documents"][0]):
                meta = vector_results["metadatas"][0][i]
                results["knowledge"].append({
                    "type": "document",
                    "title": meta.get("filename", "Unknown Document"),
                    "snippet": (doc_text[:150] + "...") if doc_text else "",
                    "score": "High Relevance",
                })
    except RuntimeError:
        pass
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Vector search failed")
            
    # B. Chats (SQL Fallback/Supplement)
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == user_id,
        ChatHistory.content.ilike(f'%{query}%')
    ).order_by(ChatHistory.timestamp.desc()).limit(5).all()
    
    for chat in chats:
        results["knowledge"].append({
            "type": "chat",
            "title": f"Chat History ({chat.role})",
            "snippet": (chat.content[:100] + "...") if len(chat.content) > 100 else chat.content,
            "date": chat.timestamp.strftime("%Y-%m-%d %H:%M")
        })

    return results
