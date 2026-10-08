from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..runtime_diagnostics import rag_status, readiness_status

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Lightweight liveness check; it does not load optional runtimes."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    """Core readiness plus non-loading optional capability diagnostics."""
    body = readiness_status()
    if body["status"] != "ready":
        return JSONResponse(status_code=503, content=body)
    return body


@router.get("/diagnostics/rag")
def rag_diagnostics() -> dict:
    """Report RAG capability without creating a Chroma store."""
    return rag_status()
