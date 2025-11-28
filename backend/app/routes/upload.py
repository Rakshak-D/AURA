from fastapi import APIRouter, UploadFile, File, Form, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.sql_models import Document
from ..services.rag_service import add_to_rag
from ..utils.parser import parse_document

router = APIRouter()

@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
    try:
        content = parse_document(file.file, file.content_type)
        
        # Check if file already exists to avoid duplicates (optional, but good practice)
        existing = db.query(Document).filter(Document.filename == file.filename).first()
        if existing:
            return {"status": "error", "message": "File already exists"}

        doc = Document(filename=file.filename, content=content, file_type=file.content_type)
        db.add(doc)
        db.commit()
        
        # Process RAG in background
        background_tasks.add_task(add_to_rag, file.filename, content)
        
        return {"status": "success", "filename": file.filename, "message": "File uploaded. Processing for search in background."}
    except Exception as e:
        print(f"Upload error: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/upload/files")
async def list_files(db: Session = Depends(get_db)):
    try:
        docs = db.query(Document).all()
        return {
            "status": "success",
            "files": [
                {
                    "id": doc.id,
                    "filename": doc.filename,
                    "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None
                } for doc in docs
            ]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}