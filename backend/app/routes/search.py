from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, Task, ChatHistory, Document, collection

router = APIRouter()

@router.get("/search")
def search_all(q: str, db: Session = Depends(get_db)):
    if not q:
        return {"tasks": [], "knowledge": []}
    
    query = q.lower()
    results = {"tasks": [], "knowledge": []}
    
    # 1. Search Tasks (SQL Fuzzy)
    tasks = db.query(Task).filter(
        Task.user_id == 1,
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
    if collection:
        try:
            vector_results = collection.query(
                query_texts=[q],
                n_results=5
            )
            
            if vector_results['documents']:
                for i, doc_text in enumerate(vector_results['documents'][0]):
                    meta = vector_results['metadatas'][0][i]
                    results["knowledge"].append({
                        "type": "document",
                        "title": meta.get('filename', 'Unknown Document'),
                        "snippet": (doc_text[:150] + "...") if doc_text else "",
                        "score": "High Relevance"
                    })
        except Exception as e:
            print(f"Vector search failed: {e}")
            
    # B. Chats (SQL Fallback/Supplement)
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == 1,
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
