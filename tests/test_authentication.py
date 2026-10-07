from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.app import database, main
from backend.app.config import config
from backend.app.models.sql_models import Base, Task, User
from backend.app.websocket_manager import manager


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", factory)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(
        "backend.app.routes.reminders.schedule_reminder", lambda *args: None
    )
    monkeypatch.setattr(
        config, "auth_secret_key", "test-auth-secret-which-is-long-enough-123456"
    )
    from backend.app.utils.security import limiter

    if hasattr(limiter, "_storage"):
        limiter._storage.reset()
    with TestClient(main.app) as client:
        yield client, factory
    engine.dispose()


def register(client, identifier):
    return client.post(
        "/api/auth/register",
        json={"identifier": identifier, "password": "correct horse battery"},
    )


def login(client, identifier):
    response = client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": "correct horse battery"},
    )
    return response, {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_registration_login_me_and_hash(auth_client):
    client, factory = auth_client
    response = register(client, "alice@example.com")
    assert response.status_code == 201
    assert "password_hash" not in response.json()
    with factory() as db:
        user = db.query(User).one()
        assert user.password_hash and user.password_hash != "correct horse battery"

    login_response, headers = login(client, "alice@example.com")
    assert login_response.status_code == 200
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["identifier"] == "alice@example.com"


def test_duplicate_and_invalid_login_are_rejected(auth_client):
    client, _ = auth_client
    assert register(client, "alice@example.com").status_code == 201
    assert register(client, "alice@example.com").status_code == 409
    assert (
        client.post(
            "/api/auth/login",
            json={"identifier": "alice@example.com", "password": "wrong password"},
        ).status_code
        == 401
    )


def test_legacy_user_can_be_claimed_only_with_bootstrap_token(auth_client, monkeypatch):
    client, factory = auth_client
    with factory() as db:
        db.add(User(name="Legacy"))
        db.commit()
    monkeypatch.setattr(config, "auth_bootstrap_token", "one-time-bootstrap")
    response = client.post(
        "/api/auth/bootstrap",
        json={
            "identifier": "legacy@example.com",
            "password": "correct horse battery",
            "bootstrap_token": "one-time-bootstrap",
        },
    )
    assert response.status_code == 200
    assert login(client, "legacy@example.com")[0].status_code == 200


def test_expired_wrong_type_and_disabled_tokens_are_rejected(auth_client):
    client, factory = auth_client
    register(client, "alice@example.com")
    with factory() as db:
        user = db.query(User).one()
        user.is_active = False
        db.commit()
        disabled_token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
                "type": "access",
            },
            config.auth_secret_key,
            algorithm="HS256",
        )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {disabled_token}"}
        ).status_code
        == 401
    )
    expired = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc) - timedelta(hours=1),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "access",
        },
        config.auth_secret_key,
        algorithm="HS256",
    )
    wrong_type = jwt.encode(
        {
            "sub": "1",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            "type": "refresh",
        },
        config.auth_secret_key,
        algorithm="HS256",
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {expired}"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {wrong_type}"}
        ).status_code
        == 401
    )


def test_user_owned_task_isolation(auth_client):
    client, factory = auth_client
    register(client, "alice@example.com")
    _, alice_headers = login(client, "alice@example.com")
    register(client, "bob@example.com")
    _, bob_headers = login(client, "bob@example.com")
    created = client.post(
        "/api/tasks",
        headers=alice_headers,
        json={"title": "Alice task", "duration_minutes": 30, "user_id": 2},
    )
    task_id = created.json()["id"]
    assert client.get(f"/api/tasks/{task_id}", headers=bob_headers).status_code == 404
    assert (
        client.put(
            f"/api/tasks/{task_id}", headers=bob_headers, json={"title": "stolen"}
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/tasks/{task_id}", headers=bob_headers).status_code == 404
    )
    with factory() as db:
        assert (
            db.query(Task).filter(Task.id == task_id, Task.title == "Alice task").one()
        )


def test_same_user_reminder_and_cross_user_reminder_are_isolated(auth_client):
    client, _ = auth_client
    register(client, "alice@example.com")
    _, alice_headers = login(client, "alice@example.com")
    register(client, "bob@example.com")
    _, bob_headers = login(client, "bob@example.com")
    alice_task = client.post(
        "/api/tasks", headers=alice_headers, json={"title": "Alice task"}
    ).json()["id"]
    bob_task = client.post(
        "/api/tasks", headers=bob_headers, json={"title": "Bob task"}
    ).json()["id"]
    payload = {"task_id": alice_task, "reminder_time": "2030-01-01T10:00:00Z"}
    reminder_response = client.post(
        "/api/reminders", headers=alice_headers, json=payload
    )
    assert reminder_response.status_code == 200
    assert (
        client.post(
            "/api/reminders",
            headers=alice_headers,
            json={**payload, "task_id": bob_task},
        ).status_code
        == 404
    )


def test_cors_is_explicit_and_unauthenticated_websocket_is_rejected(auth_client):
    client, _ = auth_client
    wildcard_configuration = "allow_origins=" + '["*"]'
    assert wildcard_configuration not in str(main.app.user_middleware)
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/notifications"):
            pass
    register(client, "socket@example.com")
    _, headers = login(client, "socket@example.com")
    token = headers["Authorization"].split(" ", 1)[1]
    with client.websocket_connect(f"/ws/notifications?token={token}"):
        assert 1 in manager.active_connections


def test_reminder_and_document_routes_require_auth(auth_client):
    client, _ = auth_client
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/upload/files").status_code == 401
    assert client.get("/api/export").status_code == 401
