from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from ..services.rag_service import add_to_rag
from ..utils.parser import parse_document
from ..database import get_db, Document

router = APIRouter()

@router.post("/upload")
def upload(file: UploadFile = File(...), filename: str = Form(...), db: Session = Depends(get_db)):
    content = parse_document(file.file, file.content_type)
    add_to_rag(filename, content)
    doc = Document(filename=filename, content=content)
    db.add(doc)
    db.commit()
    return {"status": "uploaded", "content_len": len(content)}