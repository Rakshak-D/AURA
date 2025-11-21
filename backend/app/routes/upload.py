from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from ..database import get_db, Document
from ..services.rag_service import add_to_rag
from ..utils.parser import parse_document

router = APIRouter()

@router.post("/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = parse_document(file.file, file.content_type)
    
    doc = Document(filename=file.filename, content=content)
    db.add(doc)
    db.commit()
    
    add_to_rag(file.filename, content)
    
    return {"status": "success", "filename": file.filename}