from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db, Task, ChatHistory, Document

router = APIRouter()

@router.get("/search")
def search_all(q: str, db: Session = Depends(get_db)):
    if not q:
        return {"results": []}
    
    query = q.lower()
    results = {"tasks": [], "chats": [], "documents": []}
    
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
            "status": "Completed" if task.completed else "Pending"
        })
        
    # 2. Search Chat History (SQL Fuzzy)
    chats = db.query(ChatHistory).filter(
        ChatHistory.user_id == 1,
        ChatHistory.content.ilike(f'%{query}%')
    ).order_by(ChatHistory.timestamp.desc()).limit(10).all()
    
    for chat in chats:
        results["chats"].append({
            "id": chat.id,
            "title": f"Chat: {chat.role}",
            "snippet": (chat.content[:100] + "...") if len(chat.content) > 100 else chat.content,
            "date": chat.timestamp.strftime("%Y-%m-%d %H:%M")
        })

    # 3. Search Documents (Vector Search via ChromaDB)
    from ..database import collection, chroma_client
    
    if collection:
        try:
            # Vector Search
            vector_results = collection.query(
                query_texts=[q],
                n_results=5
            )
            
            if vector_results['documents']:
                for i, doc_text in enumerate(vector_results['documents'][0]):
                    meta = vector_results['metadatas'][0][i]
                    results["documents"].append({
                        "id": vector_results['ids'][0][i],
                        "title": meta.get('filename', 'Unknown Document'),
                        "snippet": (doc_text[:150] + "...") if doc_text else "",
                        "date": "Vector Match"
                    })
        except Exception as e:
            print(f"Vector search failed: {e}")
            # Fallback to SQL
            docs = db.query(Document).filter(
                Document.user_id == 1,
                Document.filename.ilike(f'%{query}%')
            ).all()
            for doc in docs:
                results["documents"].append({
                    "id": doc.id,
                    "title": doc.filename,
                    "snippet": "SQL Match",
                    "date": doc.uploaded_at.strftime("%Y-%m-%d")
                })
    else:
        # Fallback if Chroma is down
        docs = db.query(Document).filter(
            Document.user_id == 1,
            Document.filename.ilike(f'%{query}%')
        ).all()
        for doc in docs:
            results["documents"].append({
                "id": doc.id,
                "title": doc.filename,
                "snippet": "SQL Match",
                "date": doc.uploaded_at.strftime("%Y-%m-%d")
            })
    
    return results
