"""Ollama API adapter using the shared policy-enforcing provider transport."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator, Mapping
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import uuid4

from .adapter_utils import (
    decode_provider_json as _decode_json,
    encode_provider_json as _json_body,
    require_json_object as _object,
    require_provider_identifier as _identifier,
    require_provider_text as _text,
)
from .contracts import (
    CapabilityEvidenceSource,
    CapabilityState,
    CapabilityValue,
    ChatChunk,
    ChatRequest,
    ChatResult,
    HealthResult,
    MessageRole,
    ModelCapabilities,
    ProviderConnectionContext,
    ProviderId,
    ProviderMessage,
    ProviderModel,
    ToolCall,
    ToolCallAssembler,
    ToolCallDelta,
    ToolDefinition,
)
from .errors import ProviderError, ProviderErrorCode
from .transport import ProviderResponse, ProviderStreamResponse, ProviderTransport

_MAX_NDJSON_FRAME_BYTES = 1_048_576
_MAX_MODEL_IDENTIFIER_CHARS = 512


def _safe_metadata_string(value: object, max_chars: int) -> str | None:
    if (
        isinstance(value, str)
        and value
        and len(value) <= max_chars
        and all(32 <= ord(char) <= 126 for char in value)
    ):
        return value
    return None


def _installed_model_metadata(item: Mapping[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    digest = _safe_metadata_string(item.get("digest"), 128)
    if digest is not None:
        metadata["digest"] = digest
    size = item.get("size")
    if isinstance(size, int) and not isinstance(size, bool) and 0 <= size <= 2**63 - 1:
        metadata["size"] = size
    modified_at = _safe_metadata_string(item.get("modified_at"), 64)
    if modified_at is not None:
        metadata["modified_at"] = modified_at
    return metadata


def _positive_count(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return value


def _safe_path(base_url: str, endpoint: str) -> str:
    if not isinstance(base_url, str) or not base_url or not endpoint:
        raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError:
        raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED) from None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or "\\" in parsed.path
        or any(ord(char) < 32 or ord(char) == 127 for char in base_url)
    ):
        raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
    path = parsed.path.rstrip("/")
    for segment in path.split("/"):
        decoded = unquote(segment)
        if (
            decoded in {".", ".."}
            or "/" in decoded
            or "\\" in decoded
            or any(ord(char) < 32 or ord(char) == 127 for char in decoded)
        ):
            raise ProviderError(ProviderErrorCode.ENDPOINT_BLOCKED)
    api_prefix = path if path.endswith("/api") else f"{path}/api"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{api_prefix}/{endpoint}", "", ""))


def _unsupported_feature_response(
    body: bytes | None, features: frozenset[str]
) -> bool:
    if not body or not features:
        return False
    try:
        payload = _object(_decode_json(body))
    except ProviderError:
        return False
    error = payload.get("error")
    if isinstance(error, dict):
        error = error.get("message")
    if not isinstance(error, str):
        return False
    message = error.casefold()
    unsupported = any(
        marker in message for marker in ("unsupported", "not supported", "does not support")
    )
    if not unsupported:
        return False
    return (
        ("tools" in features and "tool" in message)
        or ("json_mode" in features and ("json" in message or "format" in message))
    )


def _check_status(
    status: int,
    *,
    model_lookup: bool = False,
    error_body: bytes | None = None,
    features: frozenset[str] = frozenset(),
) -> None:
    if 200 <= status < 300:
        return
    if status in {400, 422} and _unsupported_feature_response(error_body, features):
        code = ProviderErrorCode.UNSUPPORTED_CAPABILITY
    elif status in {401, 403}:
        code = ProviderErrorCode.AUTHENTICATION_FAILED
    elif status == 404 and model_lookup:
        code = ProviderErrorCode.MODEL_UNAVAILABLE
    elif status == 404:
        code = ProviderErrorCode.UNSUPPORTED_CAPABILITY
    elif status == 429:
        code = ProviderErrorCode.RATE_LIMITED
    elif status >= 500:
        code = ProviderErrorCode.UNAVAILABLE
    else:
        code = ProviderErrorCode.INVALID_RESPONSE
    raise ProviderError(code, retryable=code in {ProviderErrorCode.UNAVAILABLE, ProviderErrorCode.RATE_LIMITED})


def _model_id(value: object) -> str:
    try:
        model_id = _identifier(value)
    except ProviderError:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    if len(model_id) > _MAX_MODEL_IDENTIFIER_CHARS:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return model_id


def _validate_reported_model(payload: Mapping[str, object], requested_model: str) -> None:
    if "model" not in payload:
        return
    reported_model = _model_id(payload["model"])
    if reported_model != requested_model:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)


def _tool_arguments(value: object) -> str:
    if not isinstance(value, Mapping):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return _json_body(value).decode("utf-8")


def _request_messages(messages: tuple[ProviderMessage, ...]) -> list[dict[str, object]]:
    call_names: dict[str, str] = {}
    result: list[dict[str, object]] = []
    for message in messages:
        item: dict[str, object] = {"role": message.role.value, "content": message.content}
        if message.role is MessageRole.ASSISTANT and message.tool_calls:
            calls: list[dict[str, object]] = []
            for call in message.tool_calls:
                call_names[call.call_id] = call.name
                arguments = _decode_json(call.arguments_json)
                calls.append(
                    {"function": {"name": call.name, "arguments": _object(arguments)}}
                )
            item["tool_calls"] = calls
        elif message.role is MessageRole.TOOL:
            name = call_names.get(message.tool_call_id or "")
            if name is None:
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            item["tool_name"] = name
        result.append(item)
    return result


def _request_tools(tools: tuple[ToolDefinition, ...]) -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {"name": tool.name, "parameters": dict(tool.input_schema)},
        }
        for tool in tools
    ]


def _read_output_message(value: object, request: ChatRequest) -> ProviderMessage:
    message = _object(value)
    if message.get("role") != MessageRole.ASSISTANT.value:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    content = message.get("content", "")
    if content is None:
        content = ""
    content = _text(content)
    raw_calls = message.get("tool_calls", [])
    if not isinstance(raw_calls, list) or len(raw_calls) > 128:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    allowed_names = {tool.name for tool in request.tools}
    calls: list[ToolCall] = []
    for index, raw_call in enumerate(raw_calls):
        call = _object(raw_call)
        function = _object(call.get("function"))
        name = _text(function.get("name"), allow_empty=False)
        arguments = _tool_arguments(function.get("arguments"))
        if name not in allowed_names:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        try:
            calls.append(ToolCall(f"ollama-{index}-{uuid4().hex}", name, arguments))
        except ValueError:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    return ProviderMessage(MessageRole.ASSISTANT, content, tool_calls=tuple(calls))


def _capability(values: set[str] | None, name: str) -> CapabilityValue:
    if values is None:
        return CapabilityValue()
    state = CapabilityState.SUPPORTED if name in values else CapabilityState.UNSUPPORTED
    return CapabilityValue(state, CapabilityEvidenceSource.PROVIDER_METADATA)


def _context_length(model_info: object) -> int | None:
    if not isinstance(model_info, dict):
        return None
    candidates = [
        value
        for key, value in model_info.items()
        if isinstance(key, str)
        and key.endswith(".context_length")
        and isinstance(value, int)
        and not isinstance(value, bool)
        and value > 0
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


async def _ndjson_records(
    response: ProviderStreamResponse, max_frame_bytes: int
) -> AsyncIterator[bytes]:
    pending = bytearray()
    async for chunk in response:
        if not isinstance(chunk, bytes):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        pending.extend(chunk)
        while True:
            newline = pending.find(b"\n")
            if newline < 0:
                if len(pending) > max_frame_bytes:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                break
            line = bytes(pending[:newline]).removesuffix(b"\r")
            del pending[: newline + 1]
            if len(line) > max_frame_bytes:
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            if line:
                yield line
    if pending:
        if len(pending) > max_frame_bytes:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        yield bytes(pending).removesuffix(b"\r")


class OllamaAdapter:
    """Adapter for Ollama's native `/api` endpoints.

    Tool-call IDs are adapter-generated UUIDs because the native Ollama chat
    response does not provide a provider call ID. Proposed calls remain inert.
    """

    def __init__(self, transport: ProviderTransport) -> None:
        self._transport = transport

    @staticmethod
    def _validate_context(context: ProviderConnectionContext) -> None:
        if (
            not isinstance(context, ProviderConnectionContext)
            or context.provider_id is not ProviderId.OLLAMA
            or not context.base_url
        ):
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)

    def _url(self, context: ProviderConnectionContext, endpoint: str) -> str:
        self._validate_context(context)
        return _safe_path(context.base_url or "", endpoint)

    async def _request_json(
        self,
        method: str,
        context: ProviderConnectionContext,
        endpoint: str,
        payload: object | None = None,
        *,
        model_lookup: bool = False,
        unsupported_features: frozenset[str] = frozenset(),
    ) -> object:
        body = None if payload is None else _json_body(payload)
        headers = {} if body is None else {"content-type": "application/json"}
        response = await self._transport.request(
            method,
            self._url(context, endpoint),
            context=context,
            headers=headers,
            body=body,
        )
        return self._decode_response(
            response,
            model_lookup=model_lookup,
            unsupported_features=unsupported_features,
        )

    @staticmethod
    def _decode_response(
        response: ProviderResponse,
        *,
        model_lookup: bool = False,
        unsupported_features: frozenset[str] = frozenset(),
    ) -> object:
        _check_status(
            response.status_code,
            model_lookup=model_lookup,
            error_body=response.body,
            features=unsupported_features,
        )
        value = _decode_json(response.body)
        if isinstance(value, dict) and "error" in value:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        return value

    async def list_models(
        self, context: ProviderConnectionContext
    ) -> tuple[ProviderModel, ...]:
        payload = _object(await self._request_json("GET", context, "tags"))
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        models: list[ProviderModel] = []
        for item in raw_models:
            model = _object(item)
            model_id = model.get("model", model.get("name"))
            display_name = model.get("name", model_id)
            validated_id = _model_id(model_id)
            validated_name = _model_id(display_name)
            models.append(
                ProviderModel(
                    id=validated_id,
                    display_name=validated_name,
                    metadata=_installed_model_metadata(model),
                )
            )
        return tuple(models)

    async def health_check(self, context: ProviderConnectionContext) -> HealthResult:
        try:
            await self.list_models(context)
        except ProviderError as error:
            return HealthResult(False, error_code=error.code)
        return HealthResult(True)

    async def get_capabilities(
        self, context: ProviderConnectionContext, model_id: str
    ) -> ModelCapabilities:
        model_id = _model_id(model_id)
        payload = _object(
            await self._request_json(
                "POST", context, "show", {"model": model_id}, model_lookup=True
            )
        )
        raw_capabilities = payload.get("capabilities")
        if raw_capabilities is None:
            capabilities: set[str] | None = None
        elif isinstance(raw_capabilities, list) and all(
            isinstance(value, str) for value in raw_capabilities
        ):
            capabilities = set(raw_capabilities)
        else:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        length = _context_length(payload.get("model_info"))
        return ModelCapabilities(
            provider_id=ProviderId.OLLAMA,
            model_id=model_id,
            context_length=length,
            context_length_source=(
                CapabilityEvidenceSource.PROVIDER_METADATA
                if length is not None
                else CapabilityEvidenceSource.UNKNOWN
            ),
            tools=_capability(capabilities, "tools"),
            vision=_capability(capabilities, "vision"),
            embeddings=_capability(capabilities, "embedding"),
        )

    def _chat_payload(
        self, request: ChatRequest, *, stream: bool
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model_id,
            "messages": _request_messages(tuple(request.messages)),
            "stream": stream,
        }
        options: dict[str, object] = {}
        if request.options.max_tokens is not None:
            options["num_predict"] = request.options.max_tokens
        if request.options.temperature is not None:
            options["temperature"] = request.options.temperature
        if options:
            payload["options"] = options
        if request.options.json_mode:
            payload["format"] = "json"
        if request.tools:
            payload["tools"] = _request_tools(tuple(request.tools))
        return payload

    @staticmethod
    def _requested_features(request: ChatRequest) -> frozenset[str]:
        features: set[str] = set()
        if request.tools:
            features.add("tools")
        if request.options.json_mode:
            features.add("json_mode")
        return frozenset(features)

    async def _check_stream_status(
        self,
        response: ProviderStreamResponse,
        *,
        model_lookup: bool,
        features: frozenset[str],
    ) -> None:
        error_body: bytes | None = None
        if response.status_code in {400, 422} and features:
            body = bytearray()
            limit = min(self._transport.limits.max_response_bytes, 65_536)
            async for chunk in response:
                if len(body) + len(chunk) > limit:
                    break
                body.extend(chunk)
            error_body = bytes(body)
        _check_status(
            response.status_code,
            model_lookup=model_lookup,
            error_body=error_body,
            features=features,
        )

    async def chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> ChatResult:
        self._validate_context(context)
        payload = _object(
            await self._request_json(
                "POST",
                context,
                "chat",
                self._chat_payload(request, stream=False),
                model_lookup=True,
                unsupported_features=self._requested_features(request),
            )
        )
        _validate_reported_model(payload, request.model_id)
        if payload.get("done") is not True or payload.get("done_reason") != "stop":
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        message = _read_output_message(payload.get("message"), request)
        input_tokens = _positive_count(payload.get("prompt_eval_count"))
        output_tokens = _positive_count(payload.get("eval_count"))
        return ChatResult(
            model_id=request.model_id,
            message=message,
            finish_reason="tool_calls" if message.tool_calls else "stop",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def stream_chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> AsyncIterator[ChatChunk]:
        self._validate_context(context)
        assembler = ToolCallAssembler()
        next_tool_index = 0
        saw_tool_calls = False
        terminal_chunk: ChatChunk | None = None
        url = self._url(context, "chat")
        body = _json_body(self._chat_payload(request, stream=True))
        async with self._transport.stream(
            "POST",
            url,
            context=context,
            headers={"content-type": "application/json"},
            body=body,
        ) as response:
            await self._check_stream_status(
                response,
                model_lookup=True,
                features=self._requested_features(request),
            )
            max_frame = min(_MAX_NDJSON_FRAME_BYTES, self._transport.limits.max_streamed_response_bytes)
            async for raw_record in _ndjson_records(response, max_frame):
                if terminal_chunk is not None:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                payload = _object(_decode_json(raw_record))
                if "error" in payload:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                _validate_reported_model(payload, request.model_id)
                done = payload.get("done")
                if type(done) is not bool:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                raw_message = payload.get("message")
                delta = ""
                deltas: list[ToolCallDelta] = []
                if raw_message is not None:
                    message = _object(raw_message)
                    if message.get("role") != MessageRole.ASSISTANT.value:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    content = message.get("content", "")
                    if content is None:
                        content = ""
                    delta = _text(content)
                    raw_calls = message.get("tool_calls", [])
                    if not isinstance(raw_calls, list) or next_tool_index + len(raw_calls) > 128:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    allowed_names = {tool.name for tool in request.tools}
                    for raw_call in raw_calls:
                        call = _object(raw_call)
                        function = _object(call.get("function"))
                        name = _text(function.get("name"), allow_empty=False)
                        if name not in allowed_names:
                            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                        arguments = _tool_arguments(function.get("arguments"))
                        try:
                            deltas.append(
                                ToolCallDelta(
                                    index=next_tool_index,
                                    call_id=f"ollama-{next_tool_index}-{uuid4().hex}",
                                    name_fragment=name,
                                    arguments_fragment=arguments,
                                )
                            )
                        except ValueError:
                            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
                        next_tool_index += 1
                saw_tool_calls = saw_tool_calls or bool(deltas)
                if done:
                    if payload.get("done_reason") != "stop":
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    terminal_chunk = ChatChunk(
                        model_id=request.model_id,
                        delta=delta,
                        finish_reason="tool_calls" if saw_tool_calls else "stop",
                        tool_call_deltas=tuple(deltas),
                    )
                    try:
                        completed = assembler.consume(terminal_chunk)
                    except ValueError:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
                    if completed is None or any(call.name not in allowed_names for call in completed):
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    continue
                if delta or deltas:
                    chunk = ChatChunk(
                        model_id=request.model_id,
                        delta=delta,
                        tool_call_deltas=tuple(deltas),
                    )
                    try:
                        assembler.consume(chunk)
                    except ValueError:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
                    yield chunk
        if terminal_chunk is None:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        yield terminal_chunk

    async def embed(
        self, context: ProviderConnectionContext, model_id: str, text: str
    ) -> tuple[float, ...]:
        model_id = _model_id(model_id)
        if not isinstance(text, str) or not text:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        payload = _object(
            await self._request_json(
                "POST", context, "embed", {"model": model_id, "input": text}, model_lookup=True
            )
        )
        raw_embeddings = payload.get("embeddings")
        if not isinstance(raw_embeddings, list) or len(raw_embeddings) != 1:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        vector = raw_embeddings[0]
        if not isinstance(vector, list) or not vector:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        values: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            number = float(value)
            if not math.isfinite(number):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            values.append(number)
        return tuple(values)
