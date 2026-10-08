import importlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from backend.app.config import PROJECT_DIR, Settings


def test_configuration_defaults_are_deterministic(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("AURA_ENVIRONMENT", raising=False)
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000
    assert settings.use_gpu is False
    assert settings.model_path == settings.models_dir / settings.model_filename
    assert settings.embedding_model_path == settings.models_dir / "embeddings" / "sentence-transformers--all-MiniLM-L6-v2"
    assert settings.resolved_database_url.startswith("sqlite:///")


def test_configuration_environment_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("USE_GPU", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MODEL_FILENAME", "test-model.gguf")

    settings = Settings(_env_file=None)

    assert settings.environment == "test"
    assert settings.port == 8123
    assert settings.use_gpu is True
    assert settings.data_dir == (tmp_path / "data").resolve()
    assert settings.model_path.name == "test-model.gguf"


def test_aura_environment_alias_is_supported(monkeypatch):
    monkeypatch.setenv("AURA_ENVIRONMENT", "test")
    assert Settings(_env_file=None).environment == "test"


@pytest.mark.parametrize("secret", [None, "short", "dev-only-change-me"])
def test_production_rejects_missing_or_insecure_auth_secret(monkeypatch, secret):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://aura.example.test")
    if secret is None:
        monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    else:
        monkeypatch.setenv("AUTH_SECRET_KEY", secret)
    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_production_rejects_reload(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://aura.example.test")
    monkeypatch.setenv("RELOAD", "true")
    with pytest.raises(ValueError, match="RELOAD"):
        Settings(_env_file=None)


def test_production_can_read_auth_secret_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / "auth-secret"
    secret_file.write_text("file-secret-" + "x" * 64, encoding="utf-8")
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("AUTH_SECRET_KEY", "")
    monkeypatch.setenv("AUTH_SECRET_KEY_FILE", str(secret_file))
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://aura.example.test")
    settings = Settings(_env_file=None)
    assert settings.auth_secret_key == secret_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ENVIRONMENT", "staging"),
        ("PORT", "0"),
        ("CONTEXT_WINDOW", "0"),
        ("LLM_TEMPERATURE", "3"),
        ("N_GPU_LAYERS", "-1"),
        ("LLM_MAX_TOKENS", "3000"),
        ("RAG_CHUNK_OVERLAP", "500"),
        ("REMINDER_DELIVERY_TIMEOUT_SECONDS", "0"),
        ("WEBSOCKET_MAX_MESSAGE_BYTES", "0"),
        ("WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS", "0"),
        ("WEBSOCKET_OUTBOUND_QUEUE_SIZE", "0"),
    ],
)
def test_invalid_configuration_is_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError):
        Settings(_env_file=None)


def test_app_import_does_not_load_optional_runtimes():
    module = importlib.import_module("backend.app.main")
    llm_module = importlib.import_module("backend.app.models.llm_models")
    database_module = importlib.import_module("backend.app.database")

    assert module.app.title == "AURA API"
    assert llm_module.llm.llm is None
    assert llm_module.llm.embedding_model is None
    assert database_module._collection is None


def test_startup_does_not_initialize_model_or_chroma():
    script = (
        "import asyncio\n"
        "from backend.app import main, database\n"
        "from backend.app.models.llm_models import llm\n"
        "asyncio.run(main.startup_event())\n"
        "assert llm.llm is None\n"
        "assert llm.embedding_model is None\n"
        "assert database._collection is None\n"
    )
    with tempfile.TemporaryDirectory() as data_dir:
        environment = os.environ.copy()
        environment.update({"ENVIRONMENT": "test", "DATA_DIR": data_dir, "LOGS_DIR": data_dir})
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_DIR,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr


def test_fastapi_application_is_constructed():
    from backend.app.main import app

    paths = set(app.openapi()["paths"])
    assert "/" in paths
    assert "/api/tasks" in paths
    assert "/api/chat" in paths


def test_environment_files_are_not_tracked():
    tracked = subprocess.check_output(
        ["git", "ls-files", "--", ".env", ".env.example"],
        cwd=PROJECT_DIR,
        text=True,
    ).splitlines()

    assert ".env" not in tracked
    assert ".env.example" in tracked or Path(PROJECT_DIR, ".env.example").exists()
