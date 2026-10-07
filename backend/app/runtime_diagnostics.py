"""Safe, non-loading capability diagnostics for API health and provisioning."""

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from . import database
from .config import config
from .database import SessionLocal


def _dependency_installed(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def load_manifest() -> dict[str, Any]:
    with config.manifest_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def artifact_definition(logical_name: str) -> dict[str, Any] | None:
    manifest = load_manifest()
    return next(
        (item for item in manifest.get("artifacts", []) if item.get("logical_name") == logical_name),
        None,
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(
    path: Path, artifact: dict[str, Any], *, calculate_hash: bool = True
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "exists": path.is_file(),
        "file_size": path.stat().st_size if path.is_file() else None,
        "expected_size": artifact.get("expected_size_bytes"),
        "checksum_available": bool(artifact.get("sha256")),
        "checksum_verified": None,
        "actual_sha256": None,
        "valid": False,
        "integrity_state": "missing",
    }
    if not result["exists"]:
        return result

    if calculate_hash:
        result["actual_sha256"] = sha256_file(path)
    size_valid = (
        result["expected_size"] is None
        or result["file_size"] == result["expected_size"]
    )
    checksum = artifact.get("sha256")
    if checksum and result["actual_sha256"] is not None:
        result["checksum_verified"] = result["actual_sha256"].lower() == checksum.lower()
        result["valid"] = size_valid and result["checksum_verified"]
        result["integrity_state"] = "verified" if result["valid"] else "invalid"
    elif checksum:
        result["checksum_verified"] = "not_checked"
        result["valid"] = False
        result["integrity_state"] = "unverified" if size_valid else "invalid"
    else:
        result["valid"] = size_valid
        result["integrity_state"] = "unverified" if size_valid else "invalid"
    return result


def gpu_status() -> dict[str, Any]:
    if not config.use_gpu:
        return {
            "requested": False,
            "available": False,
            "state": "not_requested",
            "requested_layers": config.n_gpu_layers,
        }
    if not _dependency_installed("torch"):
        return {
            "requested": True,
            "available": False,
            "state": "optional_dependency_missing",
            "requested_layers": config.n_gpu_layers,
        }
    try:
        import torch

        available = bool(torch.cuda.is_available())
        return {
            "requested": True,
            "available": available,
            "state": "available" if available else "unavailable",
            "requested_layers": config.n_gpu_layers,
        }
    except Exception:  # noqa: BLE001 - diagnostics must never break readiness
        return {
            "requested": True,
            "available": False,
            "state": "runtime_failure",
            "requested_layers": config.n_gpu_layers,
        }


def llm_status() -> dict[str, Any]:
    artifact = artifact_definition("phi-3-mini-4k-instruct-q4") or {}
    file_status = verify_artifact(config.model_path, artifact, calculate_hash=False)
    dependency = _dependency_installed("llama_cpp")
    if not dependency:
        state = "optional_dependency_missing"
    elif not file_status["exists"]:
        state = "artifact_missing"
    elif file_status["integrity_state"] == "invalid":
        state = "artifact_invalid"
    elif file_status["integrity_state"] == "unverified":
        state = "artifact_unverified"
    else:
        state = "ready"
    return {
        "state": state,
        "configured": bool(config.model_filename),
        "file_exists": file_status["exists"],
        "file_size": file_status["file_size"],
        "expected_size": file_status["expected_size"],
        "checksum_available": file_status["checksum_available"],
        "checksum_verified": file_status["checksum_verified"],
        "runtime_dependency_installed": dependency,
        "model_available_locally": file_status["exists"],
        "loadable": "not_checked",
        "generation_functional": "not_checked",
        "gpu": gpu_status(),
    }


def embedding_status() -> dict[str, Any]:
    dependency = _dependency_installed("sentence_transformers")
    available = config.embedding_model_path.is_dir()
    if not dependency:
        state = "optional_dependency_missing"
    elif not available:
        state = "artifact_missing"
    else:
        state = "provisioned_not_loaded"
    return {
        "state": state,
        "configured": bool(config.embedding_model),
        "file_exists": available,
        "runtime_dependency_installed": dependency,
        "model_available_locally": available,
        "loadable": "not_checked",
        "generation_functional": "not_checked",
        "cache_configured": True,
    }


def database_status() -> dict[str, Any]:
    schema = database.schema_status()
    if not schema["ready"]:
        return {
            "state": "schema_incomplete",
            "schema_version": schema["version"],
            "missing": schema["missing"],
        }
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
        return {"state": "ready", "schema_version": schema["version"]}
    except Exception:  # noqa: BLE001 - diagnostics must never break readiness
        return {"state": "runtime_failure"}
    finally:
        session.close()


def rag_status() -> dict[str, Any]:
    dependency = _dependency_installed("chromadb")
    storage_available = config.chroma_path.exists()
    collection_loaded = database._collection is not None
    vector_count = None
    if collection_loaded:
        try:
            vector_count = database._collection.count()
        except Exception:  # noqa: BLE001 - Chroma is optional
            vector_count = None
    if not dependency:
        state = "optional_dependency_missing"
    elif not storage_available and not collection_loaded:
        state = "not_initialized"
    else:
        state = "ready" if collection_loaded else "available_not_initialized"
    return {
        "state": state,
        "runtime_dependency_installed": dependency,
        "storage_available": storage_available,
        "collection_loaded": collection_loaded,
        "vector_count": vector_count,
    }


def scheduler_status() -> dict[str, Any]:
    dependency = _dependency_installed("apscheduler")
    try:
        from .services.reminder_service import scheduler

        initialized = scheduler is not None
    except Exception:  # noqa: BLE001 - scheduler is optional
        initialized = False
    if not dependency:
        state = "optional_dependency_missing"
    elif initialized:
        state = "initialized"
    else:
        state = "not_initialized"
    return {
        "state": state,
        "runtime_dependency_installed": dependency,
        "initialized": initialized,
    }


def readiness_status() -> dict[str, Any]:
    database = database_status()
    return {
        "status": "ready" if database["state"] == "ready" else "unavailable",
        "core": {"state": "ready", "database": database},
        "optional": {
            "llm": llm_status(),
            "embeddings": embedding_status(),
            "rag": rag_status(),
            "scheduler": scheduler_status(),
        },
    }


def startup_summary() -> dict[str, str]:
    return {
        "database": database_status()["state"],
        "llm": llm_status()["state"],
        "embeddings": embedding_status()["state"],
        "rag": rag_status()["state"],
        "scheduler": scheduler_status()["state"],
    }
