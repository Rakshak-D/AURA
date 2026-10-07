from fastapi import APIRouter

from ..runtime_diagnostics import rag_status, readiness_status

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Lightweight liveness check; it does not load optional runtimes."""
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict:
    """Core readiness plus non-loading optional capability diagnostics."""
    return readiness_status()


@router.get("/diagnostics/rag")
def rag_diagnostics() -> dict:
    """Report RAG capability without creating a Chroma store."""
    return rag_status()
