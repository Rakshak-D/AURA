"""Shared deterministic fixtures for the AURA test suite."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from backend.app import database, main, runtime_diagnostics
from backend.app.auth import hash_password
from backend.app.config import config
from backend.app.models.llm_models import llm
from backend.app.models.sql_models import Base, User
from backend.app.services import rag_service, reminder_service
from backend.app.websocket_manager import manager


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Apply stable markers without requiring every legacy test to be edited."""
    marker_by_name = {
        "test_authentication.py": ("api", "security"),
        "test_web_security.py": ("api", "security", "websocket"),
        "test_reminder_reliability.py": ("integration", "websocket"),
        "test_ai_security.py": ("ai", "security"),
        "test_database_integrity.py": ("integration",),
        "test_frontend_contracts.py": ("unit", "security"),
        "test_provisioning.py": ("unit",),
        "test_foundation.py": ("unit",),
    }
    for item in items:
        for marker in marker_by_name.get(item.path.name, ()):
            item.add_marker(getattr(pytest.mark, marker))


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    """Install a fresh database and non-production runtime for every test."""
    runtime = tmp_path / "runtime"
    data_dir = runtime / "data"
    models_dir = runtime / "models"
    uploads_dir = data_dir / "uploads"
    logs_dir = data_dir / "logs"
    chroma_dir = data_dir / "chroma"
    for directory in (data_dir, models_dir, uploads_dir, logs_dir, chroma_dir):
        directory.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{(data_dir / 'test.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    # Patch every module-level database boundary, including imports that were
    # captured before this fixture ran. This is the important distinction from
    # only replacing database.SessionLocal.
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setattr(runtime_diagnostics, "SessionLocal", factory)
    monkeypatch.setattr(rag_service, "SessionLocal", factory)
    monkeypatch.setattr(
        reminder_service,
        "session_scope",
        lambda session_factory=None: database.session_scope(session_factory or factory),
    )
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr("backend.app.routes.reminders.schedule_reminder", lambda *args: None)
    monkeypatch.setattr(config, "environment", "test")
    monkeypatch.setattr(config, "data_dir", data_dir)
    monkeypatch.setattr(config, "models_dir", models_dir)
    monkeypatch.setattr(config, "db_path", data_dir / "test.db")
    monkeypatch.setattr(config, "chroma_path", chroma_dir)
    monkeypatch.setattr(config, "uploads_dir", uploads_dir)
    monkeypatch.setattr(config, "logs_dir", logs_dir)
    monkeypatch.setattr(config, "reminder_scheduler_enabled", False)
    monkeypatch.setattr(config, "auth_secret_key", "test-secret-key-with-at-least-32-bytes")
    database.reset_chroma_for_tests()
    llm.llm = None
    llm.embedding_model = None
    llm._llm_attempted = False
    llm._embedding_attempted = False
    from backend.app.utils.security import limiter

    if hasattr(limiter, "_storage"):
        limiter._storage.reset()

    yield factory
    # TestClient and explicit WebSocket fixtures normally perform orderly
    # shutdown. Clear residual bookkeeping as a final isolation guard so a
    # failed test cannot affect the next test's user/channel assertions.
    manager.active_connections.clear()
    manager.connection_users.clear()
    manager._states.clear()
    manager.loop = None
    database.reset_chroma_for_tests()
    llm.llm = None
    llm.embedding_model = None
    llm._llm_attempted = False
    llm._embedding_attempted = False
    if reminder_service.scheduler is not None:
        reminder_service.stop_scheduler()
    reminder_service.scheduler = None
    reminder_service.last_scheduler_tick = None
    engine.dispose()


@pytest.fixture
def api_client() -> Iterator[TestClient]:
    """A TestClient using the isolated runtime fixture above."""
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def auth_client(isolated_runtime) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """Backward-compatible authenticated client backed by the shared DB."""
    with TestClient(main.app) as client:
        yield client, isolated_runtime


@pytest.fixture
def user_factory() -> Callable[[Session, str], User]:
    """Create authenticated test users without sharing identities between tests."""

    def _create(db: Session, identifier: str = "user@example.com") -> User:
        user = User(
            username=identifier,
            email=identifier,
            password_hash=hash_password("test-password-123"),
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    return _create
