import hashlib
import json
from pathlib import Path
from urllib.error import URLError

import pytest

from backend import download_models
from backend.app import runtime_diagnostics


class FakeResponse:
    status = 200

    def __init__(self, payload: bytes):
        self.payload = payload
        self.position = 0
        self.headers = {"Content-Length": str(len(payload))}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.payload[self.position : self.position + size]
        self.position += len(chunk)
        return chunk


def artifact_for(path: Path) -> dict:
    payload = path.read_bytes()
    return {
        "expected_size_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def test_valid_existing_model_is_verified(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"model")

    result = runtime_diagnostics.verify_artifact(path, artifact_for(path))

    assert result["valid"] is True
    assert result["integrity_state"] == "verified"
    assert result["checksum_verified"] is True


def test_missing_model_is_reported(tmp_path):
    result = runtime_diagnostics.verify_artifact(
        tmp_path / "missing.gguf",
        {"expected_size_bytes": 5, "sha256": "0" * 64},
    )

    assert result["valid"] is False
    assert result["integrity_state"] == "missing"


def test_invalid_checksum_is_reported(tmp_path):
    path = tmp_path / "model.gguf"
    path.write_bytes(b"model")

    result = runtime_diagnostics.verify_artifact(
        path,
        {"expected_size_bytes": 5, "sha256": "0" * 64},
    )

    assert result["valid"] is False
    assert result["integrity_state"] == "invalid"
    assert result["checksum_verified"] is False


def test_download_finalizes_atomically(tmp_path):
    destination = tmp_path / "model.gguf"
    payload = b"small model fixture"
    expected_sha = hashlib.sha256(payload).hexdigest()

    result = download_models.download_file(
        "https://example.invalid/model",
        destination,
        expected_size=len(payload),
        expected_sha256=expected_sha,
        opener=lambda *_args, **_kwargs: FakeResponse(payload),
    )

    assert destination.read_bytes() == payload
    assert not destination.with_name("model.gguf.part").exists()
    assert result["checksum_verified"] is True


def test_failed_download_removes_part_file(tmp_path):
    destination = tmp_path / "model.gguf"

    def fail(*_args, **_kwargs):
        raise URLError("offline")

    with pytest.raises(RuntimeError):
        download_models.download_file(
            "https://example.invalid/model",
            destination,
            opener=fail,
        )

    assert not destination.exists()
    assert not destination.with_name("model.gguf.part").exists()


def test_checksum_failure_removes_part_file(tmp_path):
    destination = tmp_path / "model.gguf"

    with pytest.raises(RuntimeError):
        download_models.download_file(
            "https://example.invalid/model",
            destination,
            expected_size=5,
            expected_sha256="0" * 64,
            opener=lambda *_args, **_kwargs: FakeResponse(b"model"),
        )

    assert not destination.exists()
    assert not destination.with_name("model.gguf.part").exists()


def test_existing_artifact_is_never_overwritten(tmp_path):
    destination = tmp_path / "model.gguf"
    destination.write_bytes(b"original")

    with pytest.raises(FileExistsError):
        download_models.download_file(
            "https://example.invalid/model",
            destination,
            opener=lambda *_args, **_kwargs: FakeResponse(b"replacement"),
        )

    assert destination.read_bytes() == b"original"


def test_gpu_requested_but_unavailable_is_reported(monkeypatch):
    settings = runtime_diagnostics.config.model_copy()
    object.__setattr__(settings, "use_gpu", True)
    object.__setattr__(settings, "n_gpu_layers", 4)
    monkeypatch.setattr(runtime_diagnostics, "config", settings)
    monkeypatch.setattr(runtime_diagnostics, "_dependency_installed", lambda name: False)

    result = runtime_diagnostics.gpu_status()

    assert result["requested"] is True
    assert result["available"] is False
    assert result["state"] == "optional_dependency_missing"


def test_health_is_lightweight_and_ready_keeps_optional_failures_nonfatal(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app.main import app

    monkeypatch.setattr(runtime_diagnostics, "database_status", lambda: {"state": "ready"})
    monkeypatch.setattr(runtime_diagnostics, "_dependency_installed", lambda _name: False)

    with TestClient(app) as client:
        health_response = client.get("/health")
        ready_response = client.get("/ready")

    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}
    assert ready_response.status_code == 200
    body = ready_response.json()
    assert body["status"] == "ready"
    assert body["optional"]["llm"]["state"] == "optional_dependency_missing"
    assert body["optional"]["rag"]["state"] == "optional_dependency_missing"


def test_rag_diagnostic_does_not_initialize_chroma(monkeypatch):
    monkeypatch.setattr(runtime_diagnostics, "_dependency_installed", lambda _name: False)
    monkeypatch.setattr(runtime_diagnostics.database, "_collection", None)

    result = runtime_diagnostics.rag_status()

    assert result["state"] == "optional_dependency_missing"
    assert result["collection_loaded"] is False


def test_verification_mode_returns_failure_for_missing_artifact(monkeypatch, capsys):
    monkeypatch.setattr(
        download_models,
        "_llm_artifact",
        lambda: {"logical_name": "fixture", "expected_size_bytes": 1, "sha256": "0" * 64},
    )

    assert download_models.main(["--verify"]) == 2
    assert json.loads(capsys.readouterr().out)["integrity_state"] == "missing"
