from __future__ import annotations

import json

import pytest

from backend.app import main
from backend.app.providers.secret_store import MasterKeyMaterial, SecretStore
from backend.app.providers.service import ProviderService, get_provider_service


class MemoryProtector:
    def __init__(self) -> None:
        self.key = b"S" * 32

    def active_key(self):
        return MasterKeyMaterial("synthetic-key", self.key)

    def load_key(self, key_id: str):
        return self.key if key_id == "synthetic-key" else None

    def create_key(self):
        return MasterKeyMaterial("synthetic-key", self.key)


class SyntheticTransport:
    """Deterministic upstream responses; never opens a network connection."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object]] = []

    async def request(self, method, url, *, context, headers=None, body=None):
        if context.local_only and context.provider_id.value == "openai_compatible":
            from backend.app.providers.endpoint_policy import EndpointPolicy

            EndpointPolicy().preflight_local_only(context)
        self.calls.append((method, url, context))
        path = url.split("?", 1)[0]
        if path.endswith("/api/tags"):
            value = {"models": [{"name": "qwen2.5:latest", "model": "qwen2.5:latest"}]}
        elif path.endswith("/api/show"):
            value = {"capabilities": ["tools", "embedding"], "model_info": {"x.context_length": 8192}}
        elif path.endswith("/v1/models"):
            value = {"data": [{"id": "gpt-test"}]}
        else:
            raise AssertionError(f"Unexpected synthetic provider path: {path}")

        class Response:
            status_code = 200
            headers = (("content-type", "application/json"),)
            body = json.dumps(value).encode()

        return Response()


@pytest.fixture
def model_api(auth_client, monkeypatch):
    client, factory = auth_client
    identifier = "model-settings@example.test"
    assert client.post(
        "/api/auth/register",
        json={"identifier": identifier, "password": "synthetic-password-123"},
    ).status_code == 201
    login = client.post(
        "/api/auth/login",
        json={"identifier": identifier, "password": "synthetic-password-123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    transport = SyntheticTransport()
    service = ProviderService(
        transport=transport,
        secret_store=SecretStore(MemoryProtector()),
    )
    main.app.dependency_overrides[get_provider_service] = lambda: service
    yield client, headers, factory, service
    main.app.dependency_overrides.pop(get_provider_service, None)


def test_model_settings_requires_authentication(model_api):
    client, _headers, _factory, _service = model_api
    assert client.get("/api/settings/models").status_code == 401
    assert client.get("/api/settings/models/provider-types").status_code == 401


def test_model_settings_supports_multiple_exact_connections_and_tombstones(model_api):
    client, headers, _factory, service = model_api
    initial = client.get("/api/settings/models", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["local_only"] is True
    assert initial.json()["roles"]["chat"] is None

    created = []
    for name, base_url in (
        ("Primary", "http://127.0.0.1:9001/v1"),
        ("Secondary", "http://127.0.0.1:9002/v1"),
    ):
        response = client.post(
            "/api/settings/models/connections",
            headers=headers,
            json={"name": name, "provider_type": "openai_compatible", "base_url": base_url},
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    assert created[0]["id"] != created[1]["id"]
    assert created[0]["base_url"] != created[1]["base_url"]

    models = client.get(
        f"/api/settings/models/connections/{created[0]['id']}/models",
        headers=headers,
    )
    assert models.status_code == 200
    assert [model["id"] for model in models.json()["models"]] == ["gpt-test"]

    selected = client.put(
        "/api/settings/models/roles/chat",
        headers=headers,
        json={"connection_id": created[1]["id"], "model_id": "gpt-test"},
    )
    assert selected.status_code == 200
    assert selected.json()["connection_id"] == created[1]["id"]

    calls_before_removal = len(service.transport.calls)
    removed = client.delete(
        f"/api/settings/models/connections/{created[1]['id']}",
        headers=headers,
    )
    assert removed.status_code == 200
    snapshot = client.get("/api/settings/models", headers=headers).json()
    assert snapshot["roles"]["chat"]["connection_id"] == created[1]["id"]
    assert snapshot["roles"]["chat"]["available"] is False
    assert snapshot["roles"]["chat"]["connection_name"] == "Secondary"
    assert all(connection["id"] != created[1]["id"] for connection in snapshot["connections"] if not connection["removed"])
    assert len(service.transport.calls) == calls_before_removal


def test_local_only_prevents_remote_probe_and_secrets_are_write_only(model_api):
    client, headers, _factory, service = model_api
    connection = client.post(
        "/api/settings/models/connections",
        headers=headers,
        json={"name": "Remote test", "provider_type": "openai_compatible", "base_url": "https://api.example.test/v1"},
    ).json()
    blocked = client.post(
        f"/api/settings/models/connections/{connection['id']}/test",
        headers=headers,
    )
    assert blocked.status_code == 200
    assert blocked.json()["status"] == "blocked_by_local_only"
    assert blocked.json()["error_code"] == "local_only_blocked"
    assert service.transport.calls == []

    changed = client.put(
        "/api/settings/models/local-only",
        headers=headers,
        json={"enabled": False},
    )
    assert changed.status_code == 200
    assert changed.json()["local_only"] is False

    secret = "SYNTHETIC-API-KEY-DO-NOT-RETURN"
    stored = client.put(
        f"/api/settings/models/connections/{connection['id']}/credential",
        headers=headers,
        json={"api_key": secret},
    )
    assert stored.status_code == 200
    assert stored.json() == {"has_api_key": True}
    snapshot = client.get("/api/settings/models", headers=headers)
    assert secret not in snapshot.text
    assert snapshot.json()["connections"][0]["has_api_key"] is True

    tested = client.post(
        f"/api/settings/models/connections/{connection['id']}/test",
        headers=headers,
    )
    assert tested.status_code == 200
    assert tested.json()["status"] == "connected"
    assert service.transport.calls
    request_context = service.transport.calls[-1][2]
    assert request_context.local_only is False

    deleted = client.delete(
        f"/api/settings/models/connections/{connection['id']}/credential",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"has_api_key": False}


def test_cross_user_connection_and_role_access_is_rejected(model_api):
    client, headers, _factory, _service = model_api
    connection = client.post(
        "/api/settings/models/connections",
        headers=headers,
        json={"name": "Local", "provider_type": "ollama"},
    ).json()
    second_identifier = "other-model-user@example.test"
    assert client.post(
        "/api/auth/register",
        json={"identifier": second_identifier, "password": "synthetic-password-123"},
    ).status_code == 201
    second_login = client.post(
        "/api/auth/login",
        json={"identifier": second_identifier, "password": "synthetic-password-123"},
    )
    other_headers = {"Authorization": f"Bearer {second_login.json()['access_token']}"}

    forbidden = client.put(
        "/api/settings/models/roles/chat",
        headers=other_headers,
        json={"connection_id": connection["id"], "model_id": "qwen2.5:latest"},
    )
    assert forbidden.status_code == 404
    inaccessible = client.get(
        f"/api/settings/models/connections/{connection['id']}/models",
        headers=other_headers,
    )
    assert inaccessible.status_code == 404


def test_capabilities_are_cached_with_provider_metadata_provenance_and_embedding_fallback(model_api):
    client, headers, _factory, service = model_api
    connection = client.post(
        "/api/settings/models/connections",
        headers=headers,
        json={"name": "Ollama local", "provider_type": "ollama"},
    ).json()
    selected = client.put(
        "/api/settings/models/roles/chat",
        headers=headers,
        json={"connection_id": connection["id"], "model_id": "qwen2.5:latest"},
    )
    assert selected.status_code == 200

    path = (
        f"/api/settings/models/connections/{connection['id']}"
        "/models/qwen2.5:latest/capabilities"
    )
    first = client.get(path, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["tools"] == {"state": "supported", "source": "provider_metadata"}
    assert first.json()["embeddings"] == {"state": "supported", "source": "provider_metadata"}
    calls_after_probe = len(service.transport.calls)
    second = client.get(path, headers=headers)
    assert second.json() == first.json()
    assert len(service.transport.calls) == calls_after_probe

    resolved = client.get("/api/settings/models", headers=headers).json()["resolved_roles"]
    assert resolved["embedding"]["fallback"] is True
    assert resolved["embedding"]["connection_id"] == connection["id"]
