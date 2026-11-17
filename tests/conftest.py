"""Shared deterministic fixtures for the AURA test suite."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
import asyncio
import json
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


class SyntheticProviderTransport:
    """Provider transport boundary with controlled local responses and no sockets."""

    def __init__(self) -> None:
        from types import SimpleNamespace

        self.requests: list[dict[str, object]] = []
        self.streams_opened = 0
        self.streams_closed = 0
        self.slow_stream_started = False
        self.limits = SimpleNamespace(
            max_response_bytes=1_048_576,
            max_streamed_response_bytes=4_194_304,
        )

    @staticmethod
    def _message(body: bytes | str | None) -> tuple[str, str]:
        payload = json.loads(body or b"{}")
        messages = payload.get("messages", [])
        user_message = next(
            (item.get("content", "") for item in reversed(messages) if item.get("role") == "user"),
            "",
        )
        return str(payload.get("model", "")), str(user_message)

    @staticmethod
    def _status(message: str) -> int:
        if "SYNTHETIC_AUTH_FAILURE" in message:
            return 401
        if "SYNTHETIC_MODEL_MISSING" in message:
            return 404
        if "SYNTHETIC_UNAVAILABLE" in message:
            return 503
        return 200

    @staticmethod
    def _response(status_code: int, value: object):
        from types import SimpleNamespace

        return SimpleNamespace(
            status_code=status_code,
            headers=(("content-type", "application/json"),),
            body=json.dumps(value).encode("utf-8"),
        )

    def _record(self, method, url, context, headers, body) -> tuple[str, str]:
        from backend.app.providers.endpoint_policy import EndpointPolicy

        EndpointPolicy().preflight_local_only(context)
        self.requests.append(
            {"method": method, "url": url, "context": context, "headers": dict(headers or {}), "body": body}
        )
        return self._message(body)

    async def request(self, method, url, *, context, headers=None, body=None):
        model_id, message = self._record(method, url, context, headers, body)
        status = self._status(message)
        path = url.split("?", 1)[0]
        if path.endswith("/api/tags"):
            value = {"models": [{"name": "qwen2.5:latest", "model": "qwen2.5:latest"}]}
        elif path.endswith("/api/show"):
            value = {"capabilities": ["tools", "embedding"], "model_info": {"x.context_length": 8192}}
        elif path.endswith("/v1/models"):
            value = {"data": [{"id": "gpt-test"}, {"id": "gpt-test-2"}]}
        elif path.endswith("/api/chat"):
            value = {
                "model": model_id,
                "done": True,
                "done_reason": "stop",
                "message": {"role": "assistant", "content": "Synthetic provider response."},
            }
        elif path.endswith("/v1/chat/completions"):
            value = {
                "model": model_id,
                "choices": [{
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Synthetic provider response."},
                }],
            }
        else:
            value = {"error": {"message": "synthetic upstream failure"}}
        return self._response(status, value)

    def stream(self, method, url, *, context, headers=None, body=None):
        return SyntheticProviderStream(self, method, url, context, headers, body)


class SyntheticProviderStream:
    def __init__(self, transport, method, url, context, headers, body) -> None:
        self.transport = transport
        self.method = method
        self.url = url
        self.context = context
        self.headers_in = headers
        self.body = body
        self.status_code = 200
        self.headers = (("content-type", "application/x-ndjson"),)
        self.frames: list[bytes] = []

    async def __aenter__(self):
        from backend.app.providers.endpoint_policy import EndpointPolicy

        EndpointPolicy().preflight_local_only(self.context)
        model_id, message = self.transport._message(self.body)
        self.transport.requests.append({
            "method": self.method,
            "url": self.url,
            "context": self.context,
            "headers": dict(self.headers_in or {}),
            "body": self.body,
        })
        self.status_code = self.transport._status(message)
        self.transport.streams_opened += 1
        if self.url.split("?", 1)[0].endswith("/api/chat"):
            if "SYNTHETIC_STREAM_INTERRUPTED" in message:
                self.frames = [json.dumps({"model": model_id, "message": {"role": "assistant", "content": "partial"}, "done": False}).encode() + b"\n"]
            elif "SYNTHETIC_SLOW_STREAM" in message:
                self.frames = [json.dumps({"model": model_id, "message": {"role": "assistant", "content": "Synthetic partial"}, "done": False}).encode() + b"\n"]
            else:
                self.frames = [
                    json.dumps({"model": model_id, "message": {"role": "assistant", "content": "Synthetic "}, "done": False}).encode() + b"\n",
                    json.dumps({"model": model_id, "message": {"role": "assistant", "content": "stream response."}, "done": False}).encode() + b"\n",
                    json.dumps({"model": model_id, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}).encode() + b"\n",
                ]
        elif "SYNTHETIC_SLOW_STREAM" in message:
            self.headers = (("content-type", "text/event-stream"),)
            self.frames = [
                f"data: {json.dumps({'model': model_id, 'choices': [{'index': 0, 'delta': {'content': 'Synthetic partial'}, 'finish_reason': None}]})}\n\n".encode()
            ]
        else:
            self.headers = (("content-type", "text/event-stream"),)
            frames = [
                {"model": model_id, "choices": [{"index": 0, "delta": {"content": "Synthetic "}, "finish_reason": None}]},
                {"model": model_id, "choices": [{"index": 0, "delta": {"content": "stream response."}, "finish_reason": None}]},
                {"model": model_id, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
            ]
            self.frames = [f"data: {json.dumps(frame)}\n\n".encode() for frame in frames] + [b"data: [DONE]\n\n"]
        self.model_id = model_id
        self.message = message
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        self.transport.streams_closed += 1

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.frames:
            return self.frames.pop(0)
        if "SYNTHETIC_SLOW_STREAM" in self.message:
            self.transport.slow_stream_started = True
            await asyncio.Future()
        raise StopAsyncIteration


@pytest.fixture
def synthetic_provider_transport() -> SyntheticProviderTransport:
    return SyntheticProviderTransport()


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
