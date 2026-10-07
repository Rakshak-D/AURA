from io import BytesIO
from pathlib import PurePath

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..auth import get_current_user_id
from ..config import config
from ..database import get_db
from ..models.sql_models import Document
from ..services.rag_service import delete_document_embeddings, index_document
from ..utils.parser import parse_document, sanitize_filename
from ..utils.responses import error_response, success_response

router = APIRouter()

_CONTENT_TYPES = {
    ".pdf": {"application/pdf"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/markdown", "text/plain", "application/octet-stream"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


def _validated_filename(raw_name: str | None) -> tuple[str, str]:
    if not raw_name or len(raw_name) > 255:
        raise HTTPException(status_code=400, detail="Invalid filename")
    normalized = raw_name.replace("\\", "/")
    if PurePath(normalized).name != normalized or normalized in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    filename = sanitize_filename(normalized, max_length=200)
    suffix = PurePath(filename).suffix.lower()
    if suffix not in _CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type")
    return filename, suffix


def _validate_content_type(suffix: str, content_type: str | None) -> str:
    value = (content_type or "application/octet-stream").split(";", 1)[0].lower()
    if value not in _CONTENT_TYPES[suffix]:
        raise HTTPException(status_code=415, detail="Unsupported content type")
    return value


@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id),
):
    """
    Upload a document, store it in SQL, and enqueue background RAG indexing.
    Uses a consistent response envelope for success/error.
    """
    try:
        user_id = current_user_id
        filename, suffix = _validated_filename(file.filename)
        content_type = _validate_content_type(suffix, file.content_type)
        raw_content = await file.read(config.max_upload_size + 1)
        if len(raw_content) > config.max_upload_size:
            raise HTTPException(status_code=413, detail="Uploaded file is too large")
        content = parse_document(BytesIO(raw_content), content_type)
        if len(content) > 5_000_000:
            raise HTTPException(status_code=413, detail="Extracted document is too large")

        # Check if file already exists to avoid duplicates (optional, but good practice)
        existing = db.query(Document).filter(
            Document.user_id == user_id, Document.filename == filename
        ).first()
        if existing:
            return error_response(
                message="File already exists",
                code="FILE_ALREADY_EXISTS",
                details={"filename": filename},
            )

        doc = Document(
            user_id=user_id,
            filename=filename,
            content=content,
            file_type=content_type,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Process RAG in background
        background_tasks.add_task(index_document, doc.id, user_id, filename, content)

        return success_response(
            data={
                "id": doc.id,
                "filename": doc.filename,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            },
            message="File uploaded. Processing for search in background.",
        )
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to upload file") from e


@router.get("/upload/files")
async def list_files(db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    """
    List all uploaded documents for the current user.
    """
    try:
        docs = db.query(Document).filter(Document.user_id == current_user_id).all()
        files = [
            {
                "id": doc.id,
                "filename": doc.filename,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            }
            for doc in docs
        ]
        return success_response(data={"files": files})
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"List files error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list files") from e


@router.delete("/upload/{doc_id}")
async def delete_file(doc_id: int, db: Session = Depends(get_db), current_user_id: int = Depends(get_current_user_id)):
    """
    Delete a document from SQL and remove its embeddings from ChromaDB.

    This performs a hard delete of the knowledge base entry for now.
    """
    try:
        doc = db.query(Document).filter(
            Document.id == doc_id, Document.user_id == current_user_id
        ).first()
        if not doc:
            return error_response(
                message="Document not found",
                code="DOCUMENT_NOT_FOUND",
                details={"doc_id": doc_id},
            )

        filename = doc.filename

        # Remove embeddings from ChromaDB
        deleted_count = delete_document_embeddings(current_user_id, filename)

        # Delete SQL record
        db.delete(doc)
        db.commit()

        return success_response(
            data={
                "doc_id": doc_id,
                "filename": filename,
                "deleted_embeddings": deleted_count,
            },
            message="Document deleted from knowledge base.",
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Delete file error: {str(e)}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete document") from e
