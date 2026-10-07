import pytest
from backend.app import main
from backend.app.config import config
from backend.app.models.sql_models import Document


def test_security_headers_and_auth_cache_policy(auth_client):
    client, _ = auth_client
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]

    auth_response = client.post(
        "/api/auth/login",
        json={"identifier": "missing@example.com", "password": "wrong password"},
    )
    assert auth_response.headers["Cache-Control"] == "no-store"
    assert "wrong password" not in auth_response.text
    assert "access_token" not in auth_response.text


def test_cors_rejects_unconfigured_origin(auth_client):
    client, _ = auth_client
    response = client.options(
        "/api/auth/login",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers.get("access-control-allow-origin") is None


def test_search_response_contract_is_grouped_for_frontend(auth_client):
    client, _ = auth_client
    client.post("/api/auth/register", json={"identifier": "search@example.com", "password": "correct horse battery"})
    token = client.post("/api/auth/login", json={"identifier": "search@example.com", "password": "correct horse battery"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    client.post("/api/tasks", headers=headers, json={"title": "Searchable contract task"})
    response = client.get("/api/search?q=Searchable", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert "tasks" in body and "knowledge" in body
    assert "results" not in body
    assert body["tasks"][0]["title"] == "Searchable contract task"


def test_browser_websocket_ticket_is_single_use(auth_client):
    client, _ = auth_client
    response = client.post("/api/auth/register", json={"identifier": "ws@example.com", "password": "correct horse battery"})
    assert response.status_code == 201
    login = client.post("/api/auth/login", json={"identifier": "ws@example.com", "password": "correct horse battery"})
    token = login.json()["access_token"]
    ticket_response = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"})
    assert ticket_response.status_code == 200
    ticket = ticket_response.json()["ticket"]
    with client.websocket_connect(f"/ws/notifications?ticket={ticket}"):
        pass
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws/notifications?ticket={ticket}"):
            pass


def test_websocket_protocol_ready_ping_and_pong(auth_client):
    client, _ = auth_client
    client.post("/api/auth/register", json={"identifier": "protocol@example.com", "password": "correct horse battery"})
    token = client.post("/api/auth/login", json={"identifier": "protocol@example.com", "password": "correct horse battery"}).json()["access_token"]
    ticket = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
    with client.websocket_connect(f"/ws/notifications?ticket={ticket}") as websocket:
        ready = websocket.receive_json()
        assert ready["type"] == "ready"
        assert ready["protocol_version"] == 1
        websocket.send_json({"type": "ping"})
        assert websocket.receive_json()["type"] == "pong"


def test_websocket_protocol_rejects_unknown_and_oversized_messages(auth_client, monkeypatch):
    client, _ = auth_client
    client.post("/api/auth/register", json={"identifier": "protocol-errors@example.com", "password": "correct horse battery"})
    token = client.post("/api/auth/login", json={"identifier": "protocol-errors@example.com", "password": "correct horse battery"}).json()["access_token"]

    ticket = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
    with client.websocket_connect(f"/ws/notifications?ticket={ticket}") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "execute", "command": "unexpected"})
        assert websocket.receive_json()["data"]["code"] == "unknown_message_type"

    monkeypatch.setattr(config, "websocket_max_message_bytes", 8)
    ticket = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
    with client.websocket_connect(f"/ws/notifications?ticket={ticket}") as websocket:
        websocket.receive_json()
        websocket.send_text('{"type":"ping"}')
        assert websocket.receive_json()["data"]["code"] == "message_too_large"


def test_websocket_protocol_rejects_malformed_json(auth_client):
    client, _ = auth_client
    client.post("/api/auth/register", json={"identifier": "malformed@example.com", "password": "correct horse battery"})
    token = client.post("/api/auth/login", json={"identifier": "malformed@example.com", "password": "correct horse battery"}).json()["access_token"]
    ticket = client.post("/api/auth/ws-ticket", headers={"Authorization": f"Bearer {token}"}).json()["ticket"]
    with client.websocket_connect(f"/ws/notifications?ticket={ticket}") as websocket:
        websocket.receive_json()
        websocket.send_text("not-json")
        assert websocket.receive_json()["data"]["code"] == "invalid_json"


def test_upload_rejects_path_traversal_oversize_and_unsupported_type(auth_client, monkeypatch):
    client, factory = auth_client
    client.post("/api/auth/register", json={"identifier": "upload@example.com", "password": "correct horse battery"})
    login = client.post("/api/auth/login", json={"identifier": "upload@example.com", "password": "correct horse battery"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    traversal = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("../escape.txt", b"safe", "text/plain")},
    )
    assert traversal.status_code == 400

    unsupported = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("run.exe", b"MZ", "application/octet-stream")},
    )
    assert unsupported.status_code == 415

    monkeypatch.setattr(config, "max_upload_size", 3)
    oversized = client.post(
        "/api/upload",
        headers=headers,
        files={"file": ("large.txt", b"too large", "text/plain")},
    )
    assert oversized.status_code == 413
    with factory() as db:
        assert db.query(Document).count() == 0


def test_frontend_uses_text_only_model_rendering():
    root = main.config.frontend_dir
    chat = (root / "js" / "chat.js").read_text(encoding="utf-8")
    search = (root / "js" / "search.js").read_text(encoding="utf-8")
    upload = (root / "js" / "upload.js").read_text(encoding="utf-8")
    assert "marked.parse" not in chat
    assert "${content}" not in chat
    assert "${item.title}" not in search
    assert "${file.filename}" not in upload
    assert "safe-dom.js" in (root / "index.html").read_text(encoding="utf-8")
