from __future__ import annotations

import json

import pytest

from backend.app import main
from backend.app.models.sql_models import ChatHistory
from backend.app.providers.service import ProviderService, get_provider_service
from backend.app.providers.secret_store import MasterKeyMaterial, SecretStore

NO_MODEL_RESPONSE = "No AI model is available right now, so I can't answer general chat messages."


class MemoryProtector:
    key = b"K" * 32

    def active_key(self):
        return MasterKeyMaterial("chat-test-key", self.key)

    def load_key(self, key_id):
        return self.key if key_id == "chat-test-key" else None

    def create_key(self):
        return MasterKeyMaterial("chat-test-key", self.key)


@pytest.fixture
def chat_api(auth_client, synthetic_provider_transport):
    client, factory = auth_client
    identifier = "streaming-chat@example.test"
    assert client.post(
        "/api/auth/register",
        json={"identifier": identifier, "password": "synthetic-password-123"},
    ).status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": "synthetic-password-123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    service = ProviderService(
        transport=synthetic_provider_transport,
        secret_store=SecretStore(MemoryProtector()),
    )
    main.app.dependency_overrides[get_provider_service] = lambda: service
    yield client, headers, factory, service
    main.app.dependency_overrides.pop(get_provider_service, None)


def _configure_chat(client, headers, provider="ollama", base_url=None, model="qwen2.5:latest"):
    payload = {"name": "Browser local" if provider == "ollama" else "Chat cloud", "provider_type": provider}
    if base_url is not None:
        payload["base_url"] = base_url
    connection = client.post("/api/settings/models/connections", headers=headers, json=payload)
    assert connection.status_code == 201, connection.text
    selected = client.put(
        "/api/settings/models/roles/chat",
        headers=headers,
        json={"connection_id": connection.json()["id"], "model_id": model},
    )
    assert selected.status_code == 200, selected.text
    return connection.json()


def _events(text: str) -> list[tuple[str, dict[str, object]]]:
    result = []
    event_name = None
    data_lines: list[str] = []
    for line in text.splitlines() + [""]:
        if line.startswith("event: "):
            event_name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))
        elif not line and event_name is not None:
            result.append((event_name, json.loads("\n".join(data_lines))))
            event_name = None
            data_lines = []
    return result


def test_no_model_chat_fallback_is_exact_and_history_is_not_duplicated(chat_api):
    client, headers, factory, _service = chat_api
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"message": "Please tell me something useful."},
    )
    assert response.status_code == 200
    assert response.json()["response"] == NO_MODEL_RESPONSE
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with factory() as db:
        rows = db.query(ChatHistory).filter_by(user_id=user_id).order_by(ChatHistory.id).all()
    assert [(row.role, row.content) for row in rows] == [
        ("user", "Please tell me something useful."),
        ("assistant", NO_MODEL_RESPONSE),
    ]


def test_configured_chat_uses_selected_provider_and_minimal_messages(chat_api):
    client, headers, _factory, service = chat_api
    connection = _configure_chat(client, headers)
    sentinel = "CURRENT-MESSAGE-SENTINEL"
    response = client.post(
        "/api/chat",
        headers=headers,
        json={"message": sentinel, "context": {"private": "MUST-NOT-LEAVE-DEVICE"}},
    )
    assert response.status_code == 200
    assert response.json()["response"] == "Synthetic provider response."
    assert response.json()["data"]["provider_type"] == "ollama"
    assert response.json()["data"]["locality"] == "local"
    request = service.transport.requests[-1]
    assert request["context"].connection_id == connection["id"]
    payload = json.loads(request["body"])
    assert [item["role"] for item in payload["messages"]] == ["system", "user"]
    assert payload["messages"][-1]["content"] == sentinel
    serialized = json.dumps(payload)
    assert "MUST-NOT-LEAVE-DEVICE" not in serialized
    assert "chat history" not in serialized.casefold()


def test_authenticated_sse_stream_completes_with_correlation_and_history(chat_api):
    client, headers, factory, service = chat_api
    _configure_chat(client, headers)
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "Stream a synthetic answer."},
    )
    assert response.status_code == 200
    events = _events(response.text)
    names = [event for event, _data in events]
    assert names[0] == "started"
    assert names[-1] == "completed", f"{response.text}\nrequests={service.transport.requests!r}"
    assert "text_delta" in names
    request_id = events[0][1]["request_id"]
    assert all(payload["request_id"] == request_id for _event, payload in events)
    completed = events[-1][1]
    assert completed["model_id"] == "qwen2.5:latest"
    assert completed["provider_type"] == "ollama"
    assert completed["locality"] == "local"
    assert "Synthetic stream response." == "".join(
        payload["delta"] for event, payload in events if event == "text_delta"
    )
    assert service.transport.streams_opened == service.transport.streams_closed == 1
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with factory() as db:
        rows = db.query(ChatHistory).filter_by(user_id=user_id).order_by(ChatHistory.id).all()
    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[-1].content == "Synthetic stream response."


def test_interrupted_provider_stream_is_failed_and_partial_answer_is_not_saved(chat_api):
    client, headers, factory, _service = chat_api
    _configure_chat(client, headers)
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "SYNTHETIC_STREAM_INTERRUPTED"},
    )
    assert response.status_code == 200
    events = _events(response.text)
    assert events[-1][0] == "failed"
    assert events[-1][1]["code"] == "invalid_response"
    assert all(event != "completed" for event, _payload in events)
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with factory() as db:
        rows = db.query(ChatHistory).filter_by(user_id=user_id).order_by(ChatHistory.id).all()
    assert [row.role for row in rows] == ["user"]


def test_stream_requires_authentication_and_keeps_exact_no_model_fallback(chat_api):
    client, headers, factory, service = chat_api
    assert client.post("/api/chat/stream", json={"message": "hello"}).status_code == 401
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "A general message with no model."},
    )
    events = _events(response.text)
    assert events[-1] == (
        "failed",
        {
            "request_id": events[0][1]["request_id"],
            "code": "no_model_available",
            "message": NO_MODEL_RESPONSE,
            "incomplete": False,
        },
    )
    assert service.transport.requests == []
    assert "provider_type" not in events[0][1]
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    with factory() as db:
        rows = db.query(ChatHistory).filter_by(user_id=user_id).order_by(ChatHistory.id).all()
    assert [row.role for row in rows] == ["user", "assistant"]
    assert rows[-1].content == NO_MODEL_RESPONSE


def test_cloud_stream_is_blocked_before_synthetic_transport_when_local_only(chat_api):
    client, headers, _factory, service = chat_api
    _configure_chat(
        client,
        headers,
        provider="openai_compatible",
        base_url="https://api.example.test/v1",
        model="gpt-test",
    )
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "Cloud must stay blocked."},
    )
    events = _events(response.text)
    assert events[-1][0] == "failed"
    assert events[-1][1]["code"] == "local_only_blocked"
    assert service.transport.requests == []
    assert service.transport.streams_opened == 0


def test_remote_stream_contains_only_current_message_and_redacts_key(chat_api):
    client, headers, _factory, service = chat_api
    connection = _configure_chat(
        client,
        headers,
        provider="openai_compatible",
        base_url="https://api.example.test/v1",
        model="gpt-test",
    )
    assert client.put(
        "/api/settings/models/local-only", headers=headers, json={"enabled": False}
    ).status_code == 200
    secret = "SYNTHETIC-CLOUD-KEY-NEVER-RETURN"
    stored = client.put(
        f"/api/settings/models/connections/{connection['id']}/credential",
        headers=headers,
        json={"api_key": secret},
    )
    assert stored.status_code == 200

    current_message = "REMOTE-CURRENT-MESSAGE-ONLY"
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": current_message, "context": {"hidden": "PRIVATE-CLIENT-CONTEXT"}},
    )
    assert response.status_code == 200
    assert "completed" in response.text
    assert secret not in response.text
    assert "PRIVATE-CLIENT-CONTEXT" not in response.text
    request = service.transport.requests[-1]
    assert request["context"].local_only is False
    assert request["headers"]["authorization"] == f"Bearer {secret}"
    payload = json.loads(request["body"])
    assert [message["role"] for message in payload["messages"]] == ["system", "user"]
    assert payload["messages"][-1]["content"] == current_message
    assert "PRIVATE-CLIENT-CONTEXT" not in json.dumps(payload)
    assert "history" not in json.dumps(payload).casefold()


def test_selected_chat_preserves_deterministic_schedule_and_rejects_model_task_parsing(chat_api):
    client, headers, _factory, service = chat_api
    _configure_chat(client, headers)
    schedule = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "Show my schedule for today."},
    )
    assert _events(schedule.text)[-1][0] == "completed"
    task = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "Add task buy milk"},
    )
    task_events = _events(task.text)
    assert task_events[-1][0] == "completed"
    assert task_events[-1][1]["action_taken"] == "unavailable"
    assert "Tasks view" in "".join(
        payload.get("delta", "") for event, payload in task_events if event == "text_delta"
    )
    assert service.transport.requests == []


def test_configured_chat_treats_broad_help_requests_as_chat(chat_api):
    client, headers, _factory, service = chat_api
    _configure_chat(client, headers)
    response = client.post(
        "/api/chat/stream",
        headers=headers,
        json={"message": "Help me write a short poem."},
    )
    assert response.status_code == 200
    assert _events(response.text)[-1][0] == "completed"
    assert "Help me write a short poem." in service.transport.requests[-1]["body"].decode()
