from __future__ import annotations

import asyncio
import importlib
import json
import socket
import ssl
from collections.abc import Iterable

import httpcore
import pytest

from backend.app.providers.contracts import (
    CapabilityState,
    ChatOptions,
    ChatRequest,
    MessageRole,
    ProviderConnectionContext,
    ProviderId,
    ProviderMessage,
    ToolCall,
    ToolDefinition,
)
from backend.app.providers.endpoint_policy import EndpointPolicy
from backend.app.providers.errors import ProviderError, ProviderErrorCode
from backend.app.providers.transport import ProviderTransport, TransportLimits


class FakeResolver:
    def __init__(self, answers: Iterable[str] = ()) -> None:
        self.answers = tuple(answers)
        self.calls: list[tuple[str, int]] = []

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        self.calls.append((host, port))
        return self.answers


class FakeNetworkStream(httpcore.AsyncNetworkStream):
    def __init__(self, response: bytes, chunk_size: int) -> None:
        self.response = response
        self.chunk_size = chunk_size
        self.request_bytes = bytearray()
        self.closed = False
        self.tls_hostname: str | None = None
        self.ssl_context: ssl.SSLContext | None = None

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        count = min(max_bytes, self.chunk_size, len(self.response))
        value, self.response = self.response[:count], self.response[count:]
        return value

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.request_bytes.extend(buffer)

    async def aclose(self) -> None:
        self.closed = True

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> FakeNetworkStream:
        self.ssl_context = ssl_context
        self.tls_hostname = server_hostname
        return self

    def get_extra_info(self, info: str) -> object | None:
        return None


class FakeNetworkBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, responses: Iterable[bytes], *, chunk_size: int = 65_536) -> None:
        self.responses = list(responses)
        self.chunk_size = chunk_size
        self.connect_calls: list[tuple[str, int, float | None]] = []
        self.streams: list[FakeNetworkStream] = []

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ) -> FakeNetworkStream:
        self.connect_calls.append((host, port, timeout))
        response = self.responses.pop(0)
        stream = FakeNetworkStream(response, self.chunk_size)
        self.streams.append(stream)
        return stream

    async def connect_unix_socket(self, *args, **kwargs):
        raise AssertionError("provider transport must use the pinned TCP peer")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(0)


def _http_response(
    body: bytes,
    *,
    status: int = 200,
    content_type: str = "application/json",
    extra_headers: bytes = b"",
) -> bytes:
    return (
        f"HTTP/1.1 {status} Synthetic\r\n".encode("ascii")
        + f"Content-Type: {content_type}\r\n".encode("ascii")
        + extra_headers
        + f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode("ascii")
        + body
    )


def _make_transport(
    body: bytes,
    *,
    base_url: str = "http://127.0.0.1:11434",
    status: int = 200,
    content_type: str = "application/json",
    chunk_size: int = 65_536,
    resolver_answers: Iterable[str] = (),
    extra_headers: bytes = b"",
    limits: TransportLimits | None = None,
) -> tuple[ProviderTransport, FakeResolver, FakeNetworkBackend]:
    resolver = FakeResolver(resolver_answers)
    backend = FakeNetworkBackend(
        [
            _http_response(
                body,
                status=status,
                content_type=content_type,
                extra_headers=extra_headers,
            )
        ],
        chunk_size=chunk_size,
    )
    transport = ProviderTransport(
        endpoint_policy=EndpointPolicy(resolver=resolver),
        network_backend_factory=lambda: backend,
        limits=limits or TransportLimits(max_concurrent_requests=2),
    )
    return transport, resolver, backend


def _context(
    provider: ProviderId,
    base_url: str,
    *,
    local_only: bool = True,
    credential: str | None = None,
) -> ProviderConnectionContext:
    from backend.app.providers.contracts import EphemeralCredential

    return ProviderConnectionContext(
        user_id=11,
        connection_id="adapter-test-connection",
        provider_id=provider,
        config_revision=3,
        local_only=local_only,
        base_url=base_url,
        credential=None if credential is None else EphemeralCredential(credential),
    )


def _request_body(stream: FakeNetworkStream) -> dict[str, object]:
    raw = bytes(stream.request_bytes)
    headers, separator, body = raw.partition(b"\r\n\r\n")
    assert separator
    return json.loads(body)


def _raw_request(stream: FakeNetworkStream) -> bytes:
    return bytes(stream.request_bytes)


def _load_adapter(module_name: str, class_name: str):
    try:
        module = importlib.import_module(module_name)
        return getattr(module, class_name)
    except (ModuleNotFoundError, AttributeError) as error:
        pytest.fail(
            f"expected provider adapter {module_name}.{class_name} is missing ({type(error).__name__})",
            pytrace=False,
        )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_health_check_uses_shared_transport_for_model_listing():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, resolver, backend = _make_transport(b'{"models":[]}')
    adapter = adapter_type(transport)

    result = await adapter.health_check(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
    )

    assert result.available is True
    assert backend.connect_calls == [("127.0.0.1", 11434, 5.0)]
    assert resolver.calls == []
    request = bytes(backend.streams[0].request_bytes).split(b"\r\n", 1)[0]
    assert request == b"GET /api/tags HTTP/1.1"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_lists_installed_models_without_inventing_empty_results():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, backend = _make_transport(
        b'{"models":[{"name":"qwen2.5:latest","model":"qwen2.5:latest"}]}'
    )

    models = await adapter_type(transport).list_models(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
    )

    assert [(model.id, model.display_name) for model in models] == [
        ("qwen2.5:latest", "qwen2.5:latest")
    ]
    assert _raw_request(backend.streams[0]).startswith(b"GET /api/tags HTTP/1.1")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_preserves_only_bounded_installed_model_metadata():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    payload = {
        "models": [
            {
                "model": "qwen3:4b",
                "name": "qwen3:4b",
                "digest": "sha256:" + "a" * 64,
                "size": 4_210_000_000,
                "modified_at": "2026-11-17T10:00:00Z",
                "details": {"personal": "must not be copied"},
            },
            {
                "model": "invalid-metadata:latest",
                "digest": "x" * 129,
                "size": True,
                "modified_at": "bad\nvalue",
            },
        ]
    }
    transport, _, _ = _make_transport(
        json.dumps(payload).encode(), base_url="http://127.0.0.1:11434"
    )

    models = await adapter_type(transport).list_models(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
    )

    assert models[0].metadata == {
        "digest": "sha256:" + "a" * 64,
        "size": 4_210_000_000,
        "modified_at": "2026-11-17T10:00:00Z",
    }
    assert models[1].metadata == {}
    assert "personal" not in repr(models)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_health_check_normalizes_timeout():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    resolver = FakeResolver()

    class TimeoutBackend(FakeNetworkBackend):
        async def connect_tcp(
            self, host, port, timeout=None, local_address=None, socket_options=None
        ):
            raise httpcore.ConnectTimeout("synthetic timeout")

    backend = TimeoutBackend([])
    transport = ProviderTransport(
        endpoint_policy=EndpointPolicy(resolver=resolver),
        network_backend_factory=lambda: backend,
    )

    result = await adapter_type(transport).health_check(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
    )

    assert result.available is False
    assert result.error_code is ProviderErrorCode.TIMEOUT
    assert resolver.calls == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_normalizes_explicitly_unsupported_json_mode():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = b'{"error":"this model does not support the requested format"}'
    transport, _, _ = _make_transport(
        body, base_url="http://127.0.0.1:11434", status=400
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
            ChatRequest(
                "qwen3:4b",
                (ProviderMessage(MessageRole.USER, "json please"),),
                ChatOptions(json_mode=True),
            ),
        )

    assert error.value.code is ProviderErrorCode.UNSUPPORTED_CAPABILITY
    assert "requested format" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_rejects_malformed_model_metadata():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(b'{"models":[{"size":12}]}')

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_chat_preserves_structured_messages_and_selected_model():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    response = {
        "model": "qwen2.5:7b",
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": "ready"},
    }
    transport, _, backend = _make_transport(json.dumps(response).encode())
    request = ChatRequest(
        "qwen2.5:7b",
        (
            ProviderMessage(MessageRole.SYSTEM, "system context"),
            ProviderMessage(MessageRole.USER, "question"),
        ),
        ChatOptions(max_tokens=24, temperature=0.25),
    )

    result = await adapter_type(transport).chat(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
    )

    assert (result.model_id, result.message.role, result.message.content) == (
        "qwen2.5:7b",
        MessageRole.ASSISTANT,
        "ready",
    )
    body = _request_body(backend.streams[0])
    assert body["model"] == "qwen2.5:7b"
    assert body["messages"] == [
        {"role": "system", "content": "system context"},
        {"role": "user", "content": "question"},
    ]
    assert body["options"] == {"num_predict": 24, "temperature": 0.25}
    assert body["stream"] is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_chat_maps_native_tool_calls_to_inert_normalized_ids():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    response = {
        "model": "qwen2.5:7b",
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"function": {"name": "lookup", "arguments": {"query": "x"}}}
            ],
        },
    }
    transport, _, backend = _make_transport(json.dumps(response).encode())
    request = ChatRequest(
        "qwen2.5:7b",
        (ProviderMessage(MessageRole.USER, "lookup x"),),
        tools=(ToolDefinition("lookup", {"type": "object", "properties": {"query": {"type": "string"}}}),),
    )

    result = await adapter_type(transport).chat(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
    )

    assert len(result.message.tool_calls) == 1
    call = result.message.tool_calls[0]
    assert call.call_id.startswith("ollama-")
    assert call.name == "lookup"
    assert json.loads(call.arguments_json) == {"query": "x"}
    assert "ollama-" not in _raw_request(backend.streams[0]).decode("latin-1")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_maps_json_mode_and_correlates_tool_reply_names():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    response = {
        "model": "m1",
        "done": True,
        "done_reason": "stop",
        "message": {"role": "assistant", "content": "{}"},
    }
    transport, _, backend = _make_transport(json.dumps(response).encode())
    prior_call = ToolCall("ollama-call-1", "lookup", '{"query":"x"}')
    request = ChatRequest(
        "m1",
        (
            ProviderMessage(MessageRole.ASSISTANT, "", tool_calls=(prior_call,)),
            ProviderMessage(MessageRole.TOOL, "found", tool_call_id="ollama-call-1"),
            ProviderMessage(MessageRole.USER, "return json"),
        ),
        ChatOptions(json_mode=True),
    )

    await adapter_type(transport).chat(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
    )

    body = _request_body(backend.streams[0])
    assert body["format"] == "json"
    assert body["messages"] == [
        {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "lookup", "arguments": {"query": "x"}}}
        ]},
        {"role": "tool", "content": "found", "tool_name": "lookup"},
        {"role": "user", "content": "return json"},
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_missing_model_fails_without_pull_or_model_substitution():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, backend = _make_transport(b'{"error":"model not found"}', status=404)
    request = ChatRequest("never-pull-this", (ProviderMessage(MessageRole.USER, "hi"),))

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        )

    assert error.value.code is ProviderErrorCode.MODEL_UNAVAILABLE
    raw = _raw_request(backend.streams[0])
    assert raw.startswith(b"POST /api/chat HTTP/1.1")
    assert _request_body(backend.streams[0])["model"] == "never-pull-this"
    assert b"/api/pull" not in raw


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_capabilities_use_reported_metadata_and_leave_other_fields_unknown():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    metadata = {
        "capabilities": ["completion", "tools", "vision", "embedding"],
        "model_info": {"llama.context_length": 32768},
    }
    transport, _, backend = _make_transport(json.dumps(metadata).encode())

    result = await adapter_type(transport).get_capabilities(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), "m1"
    )

    assert result.tools.state is CapabilityState.SUPPORTED
    assert result.tools.source.value == "provider_metadata"
    assert result.vision.state is CapabilityState.SUPPORTED
    assert result.embeddings.state is CapabilityState.SUPPORTED
    assert result.context_length == 32768
    assert result.context_length_source.value == "provider_metadata"
    assert result.json_mode.state is CapabilityState.UNKNOWN
    assert result.streaming.state is CapabilityState.UNKNOWN
    assert _raw_request(backend.streams[0]).startswith(b"POST /api/show HTTP/1.1")


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_explicit_capability_list_reports_absent_features_as_unsupported():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(b'{"capabilities":["completion"]}')

    result = await adapter_type(transport).get_capabilities(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), "m1"
    )

    assert result.tools.state is CapabilityState.UNSUPPORTED
    assert result.tools.source.value == "provider_metadata"
    assert result.json_mode.state is CapabilityState.UNKNOWN


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_health_check_reports_unavailable_service_safely():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(b'{"error":"synthetic private response"}', status=503)

    result = await adapter_type(transport).health_check(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
    )

    assert result.available is False
    assert result.error_code is ProviderErrorCode.UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_embedding_validates_shape_and_finite_values():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, backend = _make_transport(b'{"embeddings":[[0.25,-0.5,1]]}')

    values = await adapter_type(transport).embed(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), "embed-v1", "text"
    )

    assert values == (0.25, -0.5, 1.0)
    assert _raw_request(backend.streams[0]).startswith(b"POST /api/embed HTTP/1.1")


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [b'{"embeddings":[]}', b'{"embeddings":[[]]}', b'{"embeddings":[[NaN]]}'],
)
async def test_ollama_rejects_empty_or_nonfinite_embeddings(body):
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(body)

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).embed(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), "embed-v1", "text"
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_parses_fragmented_utf8_ndjson_and_requires_done_reason():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = (
        '{"model":"m1","message":{"role":"assistant","content":"Héllo"},"done":false}\n'
        '{"model":"m1","done":true,"done_reason":"stop"}\n'
    ).encode("utf-8")
    transport, _, _ = _make_transport(
        body, chunk_size=1, content_type="application/x-ndjson"
    )
    request = ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hi"),))

    chunks = [
        chunk
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        )
    ]

    assert [(chunk.delta, chunk.finish_reason) for chunk in chunks] == [
        ("Héllo", None),
        ("", "stop"),
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_accepts_terminal_event_without_message_payload():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(
        b'{"done":true,"done_reason":"stop"}\n',
        content_type="application/x-ndjson",
    )

    chunks = [
        chunk
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
            ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hi"),)),
        )
    ]

    assert len(chunks) == 1
    assert chunks[0].delta == ""
    assert chunks[0].finish_reason == "stop"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_emits_native_tool_proposals_without_executing_them():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = (
        '{"message":{"role":"assistant","content":"","tool_calls":['
        '{"function":{"name":"lookup","arguments":{"query":"x"}}}]},"done":false}\n'
        '{"done":true,"done_reason":"stop"}\n'
    ).encode()
    transport, _, backend = _make_transport(body, chunk_size=3)
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "find x"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )

    chunks = [
        chunk
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        )
    ]

    assert len(chunks) == 2
    proposal = chunks[0].tool_call_deltas[0]
    assert proposal.index == 0
    assert proposal.call_id and proposal.call_id.startswith("ollama-")
    assert proposal.name_fragment == "lookup"
    assert json.loads(proposal.arguments_fragment) == {"query": "x"}
    assert chunks[1].finish_reason == "tool_calls"
    assert len(backend.connect_calls) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_discards_partial_calls_on_unexpected_eof():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = (
        '{"message":{"role":"assistant","content":"","tool_calls":['
        '{"function":{"name":"lookup","arguments":{"query":"x"}}}]},"done":false}\n'
    ).encode()
    transport, _, _ = _make_transport(body)
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "find x"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )
    seen = []

    with pytest.raises(ProviderError) as error:
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        ):
            seen.append(chunk)

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert seen and all(chunk.finish_reason is None for chunk in seen)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_cancellation_closes_the_transport_response():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = b'{"message":{"role":"assistant","content":"partial"},"done":false}\n'
    transport, _, backend = _make_transport(body, chunk_size=1)
    stream = adapter_type(transport).stream_chat(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
        ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),)),
    )

    first = await stream.__anext__()
    await stream.aclose()

    assert first.delta == "partial"
    assert backend.streams[0].closed is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_rejects_non_success_completion_reason():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = b'{"done":true,"done_reason":"length"}\n'
    transport, _, _ = _make_transport(body, content_type="application/x-ndjson")

    with pytest.raises(ProviderError) as error:
        async for _chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
            ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),)),
        ):
            pass

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_provider_error_is_normalized_without_body_text():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(b'{"error":"synthetic-secret leaked"}', status=401)

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434")
        )

    assert error.value.code is ProviderErrorCode.AUTHENTICATION_FAILED
    assert "synthetic-secret" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("base_url", "expected_path"),
    [
        ("http://127.0.0.1:1234/v1", "/v1/models"),
        ("http://127.0.0.1:1234", "/v1/models"),
        ("http://127.0.0.1:1234/gateway/v1/", "/gateway/v1/models"),
        ("http://127.0.0.1:1234/gateway", "/gateway/v1/models"),
    ],
)
async def test_openai_compatible_model_endpoint_preserves_base_path(
    base_url: str, expected_path: str
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, backend = _make_transport(b'{"data":[{"id":"local-model"}]}', base_url=base_url)

    models = await adapter_type(transport).list_models(
        _context(ProviderId.OPENAI_COMPATIBLE, base_url)
    )

    assert [model.id for model in models] == ["local-model"]
    assert bytes(backend.streams[0].request_bytes).split(b"\r\n", 1)[0] == (
        f"GET {expected_path} HTTP/1.1".encode()
    )


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    "base_url",
    [
        "http://user:password@127.0.0.1:1234/v1",
        "http://127.0.0.1:1234/v1?api_key=secret",
        "http://127.0.0.1:1234/proxy/%2e%2e/v1",
        "http://127.0.0.1:1234/v1#fragment",
    ],
)
async def test_openai_compatible_rejects_unsafe_base_url_before_dns(base_url: str):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, resolver, backend = _make_transport(b'{"data":[]}', base_url=base_url)

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OPENAI_COMPATIBLE, base_url)
        )

    assert error.value.code in {
        ProviderErrorCode.ENDPOINT_BLOCKED,
        ProviderErrorCode.INCOMPLETE_CONFIGURATION,
    }
    assert resolver.calls == [] and backend.connect_calls == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_empty_discovery_returns_no_invented_models():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(
        b'{"object":"list","data":[]}', base_url="http://127.0.0.1:1234/v1"
    )

    models = await adapter_type(transport).list_models(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
    )

    assert models == ()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_maps_unsupported_discovery_distinctly():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(
        b'{"error":"not available"}',
        base_url="http://127.0.0.1:1234/v1",
        status=404,
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
        )

    assert error.value.code is ProviderErrorCode.UNSUPPORTED_CAPABILITY


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_rejects_malformed_model_discovery():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(
        b'{"data":[{"object":"model"}]}', base_url="http://127.0.0.1:1234/v1"
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_chat_maps_messages_tools_json_mode_and_auth():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_lookup_1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"query":"x"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    transport, _, backend = _make_transport(
        json.dumps(response).encode(),
        base_url="https://api.example.com/v1",
        resolver_answers=("93.184.216.34",),
    )
    request = ChatRequest(
        "gpt-compatible-1",
        (
            ProviderMessage(MessageRole.SYSTEM, "rules"),
            ProviderMessage(MessageRole.USER, "find x"),
            ProviderMessage(
                MessageRole.ASSISTANT,
                "",
                tool_calls=(ToolCall("prior-call", "lookup", '{"query":"initial"}'),),
            ),
            ProviderMessage(
                MessageRole.TOOL,
                '{"answer":"initial result"}',
                tool_call_id="prior-call",
            ),
            ProviderMessage(MessageRole.USER, "find x again"),
        ),
        ChatOptions(max_tokens=50, temperature=0.2, json_mode=True),
        tools=(ToolDefinition("lookup", {"type": "object", "properties": {"query": {"type": "string"}}}),),
    )
    secret = "synthetic-api-key-do-not-log"

    result = await adapter_type(transport).chat(
        _context(
            ProviderId.OPENAI_COMPATIBLE,
            "https://api.example.com/v1",
            local_only=False,
            credential=secret,
        ),
        request,
    )

    assert (result.model_id, result.finish_reason) == ("gpt-compatible-1", "tool_calls")
    assert result.input_tokens == 12 and result.output_tokens == 3
    call = result.message.tool_calls[0]
    assert call.call_id == "call_lookup_1"
    assert json.loads(call.arguments_json) == {"query": "x"}
    raw = _raw_request(backend.streams[0])
    assert b"authorization: bearer synthetic-api-key-do-not-log" in raw.lower()
    body = _request_body(backend.streams[0])
    assert body["model"] == "gpt-compatible-1"
    assert body["messages"] == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "find x"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "prior-call",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"query":"initial"}'},
                }
            ],
        },
        {
            "role": "tool",
            "content": '{"answer":"initial result"}',
            "tool_call_id": "prior-call",
        },
        {"role": "user", "content": "find x again"},
    ]
    assert body["max_tokens"] == 50
    assert "max_completion_tokens" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert body["tools"][0]["function"]["name"] == "lookup"
    assert secret not in result.message.content
    assert backend.connect_calls[0][0] == "93.184.216.34"
    assert backend.streams[0].tls_hostname == "api.example.com"
    assert backend.streams[0].ssl_context is not None
    assert backend.streams[0].ssl_context.check_hostname is True
    assert backend.streams[0].ssl_context.verify_mode == ssl.CERT_REQUIRED
    assert b"host: api.example.com" in raw.lower()


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("feature", "error_param"),
    [("json_mode", "response_format"), ("tools", "tools")],
)
async def test_openai_compatible_normalizes_explicitly_unsupported_chat_features(
    feature: str, error_param: str
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    secret_sentinel = "provider-internal-sentinel"
    body = json.dumps(
        {"error": {"param": error_param, "message": secret_sentinel}}
    ).encode()
    transport, _, _ = _make_transport(
        body, base_url="http://127.0.0.1:1234/v1", status=400
    )
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "hello"),),
        ChatOptions(json_mode=feature == "json_mode"),
        tools=(ToolDefinition("lookup", {"type": "object"}),)
        if feature == "tools"
        else (),
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            request,
        )

    assert error.value.code is ProviderErrorCode.UNSUPPORTED_CAPABILITY
    assert secret_sentinel not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_normalizes_unsupported_json_mode():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    body = b'{"error":{"param":"response_format","message":"synthetic"}}'
    transport, _, backend = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        status=400,
        content_type="application/json",
    )
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "json please"),),
        ChatOptions(json_mode=True),
    )

    with pytest.raises(ProviderError) as error:
        async for _chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            request,
        ):
            pass

    assert error.value.code is ProviderErrorCode.UNSUPPORTED_CAPABILITY
    assert backend.streams[0].closed is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_local_server_is_credentialless():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, backend = _make_transport(
        b'{"data":[{"id":"local"}]}', base_url="http://127.0.0.1:1234/v1"
    )

    await adapter_type(transport).list_models(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
    )

    assert b"authorization:" not in _raw_request(backend.streams[0]).lower()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_model_capabilities_remain_unknown_without_metadata():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, resolver, backend = _make_transport(
        b"", base_url="https://api.example.com/v1", resolver_answers=("93.184.216.34",)
    )

    capabilities = await adapter_type(transport).get_capabilities(
        _context(
            ProviderId.OPENAI_COMPATIBLE,
            "https://api.example.com/v1",
            local_only=False,
        ),
        "unknown-model",
    )

    assert capabilities.tools.state is CapabilityState.UNKNOWN
    assert capabilities.json_mode.state is CapabilityState.UNKNOWN
    assert capabilities.streaming.state is CapabilityState.UNKNOWN
    assert capabilities.embeddings.state is CapabilityState.UNKNOWN
    assert resolver.calls == [] and backend.connect_calls == []


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, ProviderErrorCode.AUTHENTICATION_FAILED),
        (429, ProviderErrorCode.RATE_LIMITED),
    ],
)
async def test_openai_compatible_normalizes_authentication_and_rate_limit(status, code):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    sentinel = "synthetic-provider-error-secret"
    transport, _, _ = _make_transport(
        f'{{"error":"{sentinel}"}}'.encode(),
        base_url="http://127.0.0.1:1234/v1",
        status=status,
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
        )

    assert error.value.code is code
    assert sentinel not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_auth_secret_is_not_logged_or_exposed_on_failure(caplog):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    secret = "synthetic-secret-never-in-errors"
    transport, _, _ = _make_transport(
        b'{"error":"invalid credentials"}',
        base_url="http://127.0.0.1:1234/v1",
        status=401,
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(
                ProviderId.OPENAI_COMPATIBLE,
                "http://127.0.0.1:1234/v1",
                credential=secret,
            )
        )

    assert error.value.code is ProviderErrorCode.AUTHENTICATION_FAILED
    assert secret not in str(error.value)
    assert secret not in caplog.text


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_chat_maps_missing_model_to_safe_error():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(
        b'{"error":"model does not exist"}',
        base_url="http://127.0.0.1:1234/v1",
        status=404,
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest("missing-model", (ProviderMessage(MessageRole.USER, "hello"),)),
        )

    assert error.value.code is ProviderErrorCode.MODEL_UNAVAILABLE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_rejects_redirect_to_private_destination():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, resolver, backend = _make_transport(
        b"",
        base_url="http://127.0.0.1:1234/v1",
        status=302,
        extra_headers=b"Location: http://169.254.169.254/latest/meta-data\r\n",
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
        )

    assert error.value.code is ProviderErrorCode.ENDPOINT_BLOCKED
    assert resolver.calls == []
    assert len(backend.connect_calls) == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_local_only_blocks_before_dns_or_connection():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, resolver, backend = _make_transport(
        b"", base_url="https://api.example.com/v1", resolver_answers=("93.184.216.34",)
    )
    secret = "sentinel-must-not-transmit"

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).list_models(
            _context(
                ProviderId.OPENAI_COMPATIBLE,
                "https://api.example.com/v1",
                local_only=True,
                credential=secret,
            )
        )

    assert error.value.code is ProviderErrorCode.LOCAL_ONLY_BLOCKED
    assert resolver.calls == []
    assert backend.connect_calls == []
    assert not backend.streams


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("finish_reason", "valid"),
    [("stop", True), ("length", False), ("content_filter", False)],
)
async def test_openai_compatible_chat_accepts_only_successful_finish_reasons(
    finish_reason: str, valid: bool
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "done"},
                "finish_reason": finish_reason,
            }
        ]
    }
    transport, _, _ = _make_transport(
        json.dumps(response).encode(), base_url="http://127.0.0.1:1234/v1"
    )
    adapter = adapter_type(transport)
    request = ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),))
    operation = adapter.chat(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), request
    )

    if valid:
        result = await operation
        assert result.finish_reason == finish_reason
    else:
        with pytest.raises(ProviderError) as error:
            await operation
        assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("body", [b'{"choices":[]}', b'{"choices":[{"message":{"role":"user"},"finish_reason":"stop"}]}'])
async def test_openai_compatible_rejects_malformed_chat_responses(body: bytes):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(body, base_url="http://127.0.0.1:1234/v1")

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),)),
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_rejects_duplicate_keys_in_tool_arguments():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = {
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": '{"query":"first","query":"second"}',
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ]
    }
    transport, _, _ = _make_transport(
        json.dumps(response).encode(), base_url="http://127.0.0.1:1234/v1"
    )
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "lookup"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            request,
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_parses_fragmented_sse_and_utf8():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    body = (
        b": keepalive\r\n\r\n"
        b'data: {"choices":[{"index":0,"delta":{"content":"H\xc3\xa9llo"},"finish_reason":null}]}\r\n\r\n'
        b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\r\n\r\n'
        b"data: [DONE]\r\n\r\n"
    )
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
        chunk_size=2,
    )
    request = ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),))

    chunks = [
        chunk
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), request
        )
    ]

    assert [(chunk.delta, chunk.finish_reason) for chunk in chunks] == [
        ("Héllo", None),
        ("", "stop"),
    ]


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_cancellation_closes_the_transport_response():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    body = (
        b'data: {"choices":[{"index":0,"delta":{"content":"partial"},"finish_reason":null}]}\n\n'
        b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        b"data: [DONE]\n\n"
    )
    transport, _, backend = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
        chunk_size=1,
    )
    stream = adapter_type(transport).stream_chat(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
        ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),)),
    )

    first = await stream.__anext__()
    await stream.aclose()

    assert first.delta == "partial"
    assert backend.streams[0].closed is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_assembles_interleaved_tool_call_deltas():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    frames = [
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "call_a", "type": "function", "function": {"name": "look", "arguments": '{"q":'}},
                            {"index": 1, "id": "call_b", "type": "function", "function": {"name": "up", "arguments": '{"text":'}},
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "function": {"name": "up", "arguments": '"x"}'}},
                            {"index": 1, "function": {"name": "per", "arguments": '"hi"}'}},
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    body = b"".join(b"data: " + json.dumps(frame).encode() + b"\n\n" for frame in frames)
    body += b"data: [DONE]\n\n"
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
        chunk_size=7,
    )
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "lookup and uppercase"),),
        tools=(ToolDefinition("lookup", {"type": "object"}), ToolDefinition("upper", {"type": "object"})),
    )

    chunks = [
        chunk
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), request
        )
    ]

    assert [delta.index for chunk in chunks for delta in chunk.tool_call_deltas] == [0, 1, 0, 1]
    assert chunks[-1].finish_reason == "tool_calls"
    assert not any("executed" in chunk.delta for chunk in chunks)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_rejects_duplicate_keys_in_completed_tool_arguments():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    frames = [
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"query":"first","query":"second"}',
                                },
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        },
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
    ]
    body = b"".join(b"data: " + json.dumps(frame).encode() + b"\n\n" for frame in frames)
    body += b"data: [DONE]\n\n"
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
    )
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "lookup"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )

    with pytest.raises(ProviderError) as error:
        async for _chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            request,
        ):
            pass

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (b"data: [DONE]\n\n", ProviderErrorCode.INVALID_RESPONSE),
        (b'data: {"choices":[{"index":0,"delta":{"content":"partial"},"finish_reason":null}]}\n\n', ProviderErrorCode.INVALID_RESPONSE),
        (b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"length"}]}\n\n', ProviderErrorCode.INVALID_RESPONSE),
    ],
)
async def test_openai_compatible_rejects_incomplete_or_unsuccessful_sse(
    body: bytes, expected_code: ProviderErrorCode
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
    )
    request = ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),))

    with pytest.raises(ProviderError) as error:
        async for _chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), request
        ):
            pass

    assert error.value.code is expected_code


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_embeddings_validate_shape_and_finite_values():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, backend = _make_transport(
        b'{"data":[{"index":0,"embedding":[0.1,0.2]}]}',
        base_url="http://127.0.0.1:1234/v1",
    )

    vector = await adapter_type(transport).embed(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), "e1", "text"
    )

    assert vector == (0.1, 0.2)
    assert bytes(backend.streams[0].request_bytes).split(b"\r\n", 1)[0] == (
        b"POST /v1/embeddings HTTP/1.1"
    )


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_response_limit_is_enforced_by_shared_transport():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    body = b'data: {"choices":[{"index":0,"delta":{"content":"' + b"x" * 128 + b'"},"finish_reason":null}]}\n\n'
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
        limits=TransportLimits(max_streamed_response_bytes=64),
    )

    with pytest.raises(ProviderError) as error:
        async for _chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest("m1", (ProviderMessage(MessageRole.USER, "hello"),)),
        ):
            pass

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    "body",
    [b'{"data":[]}', b'{"data":[{"index":1,"embedding":[1]}]}', b'{"data":[{"index":0,"embedding":[Infinity]}]}'],
)
async def test_openai_compatible_rejects_invalid_embeddings(body: bytes):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, _ = _make_transport(body, base_url="http://127.0.0.1:1234/v1")

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).embed(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"), "e1", "text"
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.unit
def test_provider_adapters_import_without_network_activity(monkeypatch):
    def reject_network(*_args, **_kwargs):
        raise AssertionError("adapter import attempted network activity")

    monkeypatch.setattr(socket, "getaddrinfo", reject_network)
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)

    for module_name in (
        "backend.app.providers.ollama",
        "backend.app.providers.openai_compatible",
    ):
        module = importlib.import_module(module_name)
        assert importlib.reload(module)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_chat_normalizes_oversized_tool_arguments_without_returning_proposal():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    sentinel = "SENSITIVE-OLLAMA-ARGUMENT"
    response = {
        "model": "m1",
        "done": True,
        "done_reason": "stop",
        "message": {
            "role": "assistant",
            "content": "must not become a successful result",
            "tool_calls": [
                {"function": {"name": "lookup", "arguments": {"value": sentinel + "x" * 70_000}}}
            ],
        },
    }
    transport, _, _ = _make_transport(json.dumps(response).encode())
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "lookup"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert str(error.value) == "The provider returned an invalid response."
    assert sentinel not in str(error.value)
    assert "x" * 128 not in str(error.value)
    assert "must not become a successful result" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_normalizes_oversized_tool_arguments_before_emitting_proposal():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    sentinel = "SENSITIVE-OLLAMA-STREAM-ARGUMENT"
    event = {
        "model": "m1",
        "message": {
            "role": "assistant",
            "content": "partial text must not accompany a rejected call",
            "tool_calls": [
                {"function": {"name": "lookup", "arguments": {"value": sentinel + "x" * 70_000}}}
            ],
        },
        "done": False,
    }
    body = (
        json.dumps(event)
        + '\n{"model":"m1","done":true,"done_reason":"stop"}\n'
    ).encode()
    transport, _, _ = _make_transport(body, content_type="application/x-ndjson")
    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "lookup"),),
        tools=(ToolDefinition("lookup", {"type": "object"}),),
    )
    emitted = []

    with pytest.raises(ProviderError) as error:
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"), request
        ):
            emitted.append(chunk)

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert emitted == []
    assert str(error.value) == "The provider returned an invalid response."
    assert sentinel not in str(error.value)
    assert "x" * 128 not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_chat_rejects_reported_model_mismatch():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(
        b'{"model":"different-model","done":true,"done_reason":"stop",'
        b'"message":{"role":"assistant","content":"wrong model"}}'
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
            ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert "different-model" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_stream_rejects_reported_model_mismatch_before_success():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    body = (
        b'{"model":"different-model","message":{"role":"assistant","content":"wrong"},"done":false}\n'
        b'{"model":"requested-model","done":true,"done_reason":"stop"}\n'
    )
    transport, _, _ = _make_transport(body, content_type="application/x-ndjson")
    emitted = []

    with pytest.raises(ProviderError) as error:
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
            ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
        ):
            emitted.append(chunk)

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert emitted == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_ollama_chat_accepts_omitted_reported_model_identity():
    adapter_type = _load_adapter("backend.app.providers.ollama", "OllamaAdapter")
    transport, _, _ = _make_transport(
        b'{"done":true,"done_reason":"stop","message":{"role":"assistant","content":"ok"}}'
    )

    result = await adapter_type(transport).chat(
        _context(ProviderId.OLLAMA, "http://127.0.0.1:11434"),
        ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
    )

    assert result.model_id == "requested-model"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_chat_rejects_reported_model_mismatch():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = {
        "model": "different-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "wrong"}, "finish_reason": "stop"}],
    }
    transport, _, _ = _make_transport(
        json.dumps(response).encode(), base_url="http://127.0.0.1:1234/v1"
    )

    with pytest.raises(ProviderError) as error:
        await adapter_type(transport).chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert "different-model" not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_stream_rejects_reported_model_mismatch_before_success():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    body = (
        b'data: {"model":"different-model","choices":[{"index":0,"delta":{"content":"wrong"},"finish_reason":null}]}\n\n'
        b'data: {"model":"requested-model","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        b"data: [DONE]\n\n"
    )
    transport, _, _ = _make_transport(
        body,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream",
    )
    emitted = []

    with pytest.raises(ProviderError) as error:
        async for chunk in adapter_type(transport).stream_chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
        ):
            emitted.append(chunk)

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert emitted == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_openai_compatible_chat_accepts_omitted_reported_model_identity():
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = {
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]
    }
    transport, _, _ = _make_transport(
        json.dumps(response).encode(), base_url="http://127.0.0.1:1234/v1"
    )

    result = await adapter_type(transport).chat(
        _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
        ChatRequest("requested-model", (ProviderMessage(MessageRole.USER, "hi"),)),
    )

    assert result.model_id == "requested-model"


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize(
    ("token_limit_parameter", "expected_key"),
    [("max_tokens", "max_tokens"), ("max_completion_tokens", "max_completion_tokens")],
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_openai_compatible_uses_explicit_token_limit_parameter(
    token_limit_parameter: str, expected_key: str, streaming: bool
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    response = (
        b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}\n\n'
        b"data: [DONE]\n\n"
        if streaming
        else json.dumps(
            {
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ]
            }
        ).encode()
    )
    transport, _, backend = _make_transport(
        response,
        base_url="http://127.0.0.1:1234/v1",
        content_type="text/event-stream" if streaming else "application/json",
    )
    adapter = adapter_type(transport, token_limit_parameter=token_limit_parameter)

    request = ChatRequest(
        "m1",
        (ProviderMessage(MessageRole.USER, "hi"),),
        ChatOptions(max_tokens=37),
    )
    context = _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1")
    if streaming:
        async for _chunk in adapter.stream_chat(context, request):
            pass
    else:
        await adapter.chat(context, request)

    body = _request_body(backend.streams[0])
    assert body[expected_key] == 37
    assert {key for key in ("max_tokens", "max_completion_tokens") if key in body} == {
        expected_key
    }


@pytest.mark.asyncio
@pytest.mark.unit
@pytest.mark.parametrize("token_limit_parameter", ["max_tokens", "max_completion_tokens"])
async def test_openai_compatible_does_not_retry_rejected_token_parameter(
    token_limit_parameter: str,
):
    adapter_type = _load_adapter(
        "backend.app.providers.openai_compatible", "OpenAICompatibleAdapter"
    )
    transport, _, backend = _make_transport(
        b'{"error":{"message":"synthetic rejected parameter"}}',
        base_url="http://127.0.0.1:1234/v1",
        status=400,
    )
    adapter = adapter_type(transport, token_limit_parameter=token_limit_parameter)

    with pytest.raises(ProviderError) as error:
        await adapter.chat(
            _context(ProviderId.OPENAI_COMPATIBLE, "http://127.0.0.1:1234/v1"),
            ChatRequest(
                "m1",
                (ProviderMessage(MessageRole.USER, "hi"),),
                ChatOptions(max_tokens=37),
            ),
        )

    assert error.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert len(backend.connect_calls) == 1
    assert len(backend.streams) == 1
    body = _request_body(backend.streams[0])
    assert body[token_limit_parameter] == 37
    other_parameter = "max_tokens" if token_limit_parameter == "max_completion_tokens" else "max_completion_tokens"
    assert other_parameter not in body
