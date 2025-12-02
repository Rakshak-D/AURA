from fastapi import APIRouter, UploadFile, File, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.sql_models import Document
from ..services.rag_service import add_to_rag, delete_document_embeddings
from ..utils.parser import parse_document
from ..utils.responses import success_response, error_response

router = APIRouter()


@router.post("/upload")
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Upload a document, store it in SQL, and enqueue background RAG indexing.
    Uses a consistent response envelope for success/error.
    """
    try:
        content = parse_document(file.file, file.content_type)

        # Check if file already exists to avoid duplicates (optional, but good practice)
        existing = db.query(Document).filter(Document.filename == file.filename).first()
        if existing:
            return error_response(
                message="File already exists",
                code="FILE_ALREADY_EXISTS",
                details={"filename": file.filename},
            )

        doc = Document(filename=file.filename, content=content, file_type=file.content_type)
        db.add(doc)
        db.commit()
        db.refresh(doc)

        # Process RAG in background
        background_tasks.add_task(add_to_rag, file.filename, content)

        return success_response(
            data={
                "id": doc.id,
                "filename": doc.filename,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            },
            message="File uploaded. Processing for search in background.",
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Upload error: {str(e)}", exc_info=True)
        return error_response(message="Failed to upload file", code="UPLOAD_ERROR", details={"error": str(e)})


@router.get("/upload/files")
async def list_files(db: Session = Depends(get_db)):
    """
    List all uploaded documents for the current user.
    """
    try:
        docs = db.query(Document).all()
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
        return error_response(message="Failed to list files", code="LIST_FILES_ERROR", details={"error": str(e)})


@router.delete("/upload/{doc_id}")
async def delete_file(doc_id: int, db: Session = Depends(get_db)):
    """
    Delete a document from SQL and remove its embeddings from ChromaDB.

    This performs a hard delete of the knowledge base entry for now.
    """
    try:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        if not doc:
            return error_response(
                message="Document not found",
                code="DOCUMENT_NOT_FOUND",
                details={"doc_id": doc_id},
            )

        filename = doc.filename

        # Remove embeddings from ChromaDB
        deleted_count = delete_document_embeddings(filename)

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
        return error_response(message="Failed to delete document", code="DELETE_DOCUMENT_ERROR", details={"error": str(e)})