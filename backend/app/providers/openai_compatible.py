"""OpenAI-compatible Chat Completions adapter over the shared provider transport."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from typing import Literal
from urllib.parse import unquote, urlsplit, urlunsplit

from .adapter_utils import (
    decode_provider_json as _decode_json,
    encode_provider_json as _json_body,
    require_json_object as _object,
    require_provider_identifier as _identifier,
    require_provider_text as _text,
)
from .contracts import (
    ChatChunk,
    ChatRequest,
    ChatResult,
    CapabilityState,
    CapabilityValue,
    HealthResult,
    MessageRole,
    ModelCapabilities,
    ProviderConnectionContext,
    ProviderId,
    ProviderMessage,
    ProviderModel,
    SuccessfulChatFinishReason,
    ToolCall,
    ToolCallAssembler,
    ToolCallDelta,
    ToolDefinition,
)
from .errors import ProviderError, ProviderErrorCode
from .transport import ProviderStreamResponse, ProviderTransport

_MAX_SSE_FRAME_BYTES = 1_048_576
_MAX_MODEL_IDENTIFIER_CHARS = 512
TokenLimitParameter = Literal["max_tokens", "max_completion_tokens"]


def _nonnegative_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return value


def _endpoint_url(base_url: str, endpoint: str) -> str:
    if not isinstance(base_url, str) or not base_url:
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
    versioned_path = path if path.endswith("/v1") else f"{path}/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{versioned_path}/{endpoint}", "", ""))


def _check_status(
    status: int,
    *,
    model_lookup: bool = False,
    discovery: bool = False,
    error_body: bytes | None = None,
    requested_features: frozenset[str] = frozenset(),
) -> None:
    if 200 <= status < 300:
        return
    if status in {400, 422} and _reports_unsupported_feature(
        error_body, requested_features
    ):
        code = ProviderErrorCode.UNSUPPORTED_CAPABILITY
    elif status in {401, 403}:
        code = ProviderErrorCode.AUTHENTICATION_FAILED
    elif discovery and status in {404, 405, 501}:
        code = ProviderErrorCode.UNSUPPORTED_CAPABILITY
    elif status == 404 and model_lookup:
        code = ProviderErrorCode.MODEL_UNAVAILABLE
    elif status == 429:
        code = ProviderErrorCode.RATE_LIMITED
    elif status >= 500:
        code = ProviderErrorCode.UNAVAILABLE
    else:
        code = ProviderErrorCode.INVALID_RESPONSE
    raise ProviderError(
        code,
        retryable=code in {ProviderErrorCode.UNAVAILABLE, ProviderErrorCode.RATE_LIMITED},
    )


def _reports_unsupported_feature(
    body: bytes | None, requested_features: frozenset[str]
) -> bool:
    if not body or not requested_features:
        return False
    try:
        payload = _object(_decode_json(body))
    except ProviderError:
        return False
    error = payload.get("error")
    if not isinstance(error, dict):
        return False
    parameter = error.get("param")
    if not isinstance(parameter, str):
        return False
    return (
        ("tools" in requested_features and parameter in {"tools", "tool_choice", "functions", "function_call"})
        or ("json_mode" in requested_features and parameter == "response_format")
    )


async def _read_limited_error_body(
    response: ProviderStreamResponse, max_bytes: int
) -> bytes | None:
    body = bytearray()
    async for chunk in response:
        if len(body) + len(chunk) > max_bytes:
            return None
        body.extend(chunk)
    return bytes(body)


def _authorization(context: ProviderConnectionContext) -> dict[str, str]:
    if context.credential is None:
        return {}
    return {"authorization": f"Bearer {context.credential.value}"}


def _request_messages(messages: tuple[ProviderMessage, ...]) -> list[dict[str, object]]:
    known_call_ids: set[str] = set()
    result: list[dict[str, object]] = []
    for message in messages:
        item: dict[str, object] = {"role": message.role.value, "content": message.content}
        if message.role is MessageRole.ASSISTANT and message.tool_calls:
            calls: list[dict[str, object]] = []
            for call in message.tool_calls:
                known_call_ids.add(call.call_id)
                calls.append(
                    {
                        "id": call.call_id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments_json,
                        },
                    }
                )
            item["tool_calls"] = calls
        elif message.role is MessageRole.TOOL:
            if message.tool_call_id not in known_call_ids:
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            item["tool_call_id"] = message.tool_call_id
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


def _validated_tool_arguments(value: object) -> str:
    arguments = _text(value, allow_empty=False)
    _object(_decode_json(arguments))
    return arguments


def _validate_reported_model(payload: dict[str, object], requested_model: str) -> None:
    if "model" not in payload:
        return
    try:
        reported_model = _identifier(payload["model"])
    except ProviderError:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    if len(reported_model) > _MAX_MODEL_IDENTIFIER_CHARS or reported_model != requested_model:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)


def _read_chat_result(value: object, request: ChatRequest) -> ChatResult:
    payload = _object(value)
    _validate_reported_model(payload, request.model_id)
    choices = payload.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    choice = _object(choices[0])
    if _nonnegative_integer(choice.get("index", 0)) != 0:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    raw_reason = choice.get("finish_reason")
    try:
        finish_reason = SuccessfulChatFinishReason(raw_reason)
    except (TypeError, ValueError):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    message = _object(choice.get("message"))
    if message.get("role") != MessageRole.ASSISTANT.value or "function_call" in message:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    content = message.get("content")
    if content is None:
        content = ""
    content = _text(content)
    raw_calls = message.get("tool_calls", [])
    if not isinstance(raw_calls, list) or len(raw_calls) > 128:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    allowed_names = {tool.name for tool in request.tools}
    calls: list[ToolCall] = []
    for raw_call in raw_calls:
        call = _object(raw_call)
        if call.get("type", "function") != "function":
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        function = _object(call.get("function"))
        name = _identifier(function.get("name"))
        if name not in allowed_names:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        arguments = _validated_tool_arguments(function.get("arguments"))
        try:
            calls.append(ToolCall(_identifier(call.get("id")), name, arguments))
        except ValueError:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    if bool(calls) != (finish_reason is SuccessfulChatFinishReason.TOOL_CALLS):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)

    input_tokens = output_tokens = None
    if "usage" in payload and payload["usage"] is not None:
        usage = _object(payload["usage"])
        input_tokens = _nonnegative_integer(usage.get("prompt_tokens"))
        output_tokens = _nonnegative_integer(usage.get("completion_tokens"))
    return ChatResult(
        model_id=request.model_id,
        message=ProviderMessage(MessageRole.ASSISTANT, content, tool_calls=tuple(calls)),
        finish_reason=finish_reason.value,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def _tool_deltas(value: object) -> tuple[ToolCallDelta, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > 128:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    deltas: list[ToolCallDelta] = []
    for raw_call in value:
        call = _object(raw_call)
        index = call.get("index")
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        call_id = call.get("id")
        if call_id is not None:
            call_id = _identifier(call_id)
        if call.get("type", "function") != "function":
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        function_value = call.get("function")
        name: str | None = None
        arguments = ""
        if function_value is not None:
            function = _object(function_value)
            if function.get("name") is not None:
                name = _text(function["name"])
            if function.get("arguments") is not None:
                arguments = _text(function["arguments"])
        try:
            deltas.append(
                ToolCallDelta(
                    index=index,
                    call_id=call_id,
                    name_fragment=name,
                    arguments_fragment=arguments,
                )
            )
        except ValueError:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    return tuple(deltas)


def _choice_chunk(value: object, request: ChatRequest) -> ChatChunk | None:
    payload = _object(value)
    _validate_reported_model(payload, request.model_id)
    if "error" in payload:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    choices = payload.get("choices")
    if choices == []:
        return None
    if not isinstance(choices, list) or len(choices) != 1:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    choice = _object(choices[0])
    if _nonnegative_integer(choice.get("index", 0)) != 0:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    delta_value = _object(choice.get("delta", {}))
    content = delta_value.get("content")
    if content is None:
        content = ""
    content = _text(content)
    tool_calls = _tool_deltas(delta_value.get("tool_calls"))
    raw_reason = choice.get("finish_reason")
    if raw_reason is None:
        finish_reason = None
    else:
        try:
            finish_reason = SuccessfulChatFinishReason(raw_reason).value
        except (TypeError, ValueError):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    if not content and not tool_calls and finish_reason is None:
        return None
    try:
        chunk = ChatChunk(
            model_id=request.model_id,
            delta=content,
            finish_reason=finish_reason,
            tool_call_deltas=tool_calls,
        )
    except ValueError:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    return chunk


async def _sse_frames(
    response: ProviderStreamResponse, max_frame_bytes: int
) -> AsyncIterator[bytes]:
    pending = bytearray()
    async for chunk in response:
        if not isinstance(chunk, bytes):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        pending.extend(chunk)
        while True:
            separators = [
                (pending.find(b"\r\n\r\n"), 4),
                (pending.find(b"\n\n"), 2),
                (pending.find(b"\r\r"), 2),
            ]
            separators = [(position, size) for position, size in separators if position >= 0]
            if not separators:
                if len(pending) > max_frame_bytes:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                break
            position, separator_size = min(separators, key=lambda pair: pair[0])
            frame = bytes(pending[:position])
            del pending[: position + separator_size]
            if len(frame) > max_frame_bytes:
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            yield frame
    if pending:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)


def _sse_data(frame: bytes) -> str | None:
    try:
        text = frame.decode("utf-8")
    except UnicodeDecodeError:
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
    data_lines: list[str] = []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if not line or line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if field == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)
        elif field in {"event", "id", "retry"} and not separator:
            continue
    if not data_lines:
        return None
    return "\n".join(data_lines)


class OpenAICompatibleAdapter:
    """Adapter for connection-scoped OpenAI-compatible API prefixes."""

    def __init__(
        self,
        transport: ProviderTransport,
        *,
        token_limit_parameter: TokenLimitParameter = "max_tokens",
    ) -> None:
        if token_limit_parameter not in ("max_tokens", "max_completion_tokens"):
            raise ValueError("unsupported token-limit parameter")
        self._transport = transport
        self._token_limit_parameter = token_limit_parameter

    @staticmethod
    def _validate_context(context: ProviderConnectionContext) -> None:
        if (
            not isinstance(context, ProviderConnectionContext)
            or context.provider_id is not ProviderId.OPENAI_COMPATIBLE
            or not context.base_url
        ):
            raise ProviderError(ProviderErrorCode.INCOMPLETE_CONFIGURATION)

    def _url(self, context: ProviderConnectionContext, endpoint: str) -> str:
        self._validate_context(context)
        return _endpoint_url(context.base_url or "", endpoint)

    def _headers(self, context: ProviderConnectionContext, *, json_body: bool) -> dict[str, str]:
        headers = _authorization(context)
        if json_body:
            headers["content-type"] = "application/json"
        return headers

    async def _request_json(
        self,
        method: str,
        context: ProviderConnectionContext,
        endpoint: str,
        payload: object | None = None,
        *,
        discovery: bool = False,
        model_lookup: bool = False,
        requested_features: frozenset[str] = frozenset(),
    ) -> object:
        body = None if payload is None else _json_body(payload)
        response = await self._transport.request(
            method,
            self._url(context, endpoint),
            context=context,
            headers=self._headers(context, json_body=body is not None),
            body=body,
        )
        _check_status(
            response.status_code,
            model_lookup=model_lookup,
            discovery=discovery,
            error_body=response.body,
            requested_features=requested_features,
        )
        value = _decode_json(response.body)
        if isinstance(value, dict) and "error" in value:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        return value

    async def list_models(
        self, context: ProviderConnectionContext
    ) -> tuple[ProviderModel, ...]:
        payload = _object(
            await self._request_json("GET", context, "models", discovery=True)
        )
        raw_models = payload.get("data")
        if not isinstance(raw_models, list):
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        models: list[ProviderModel] = []
        for raw_model in raw_models:
            model = _object(raw_model)
            models.append(
                ProviderModel(
                    id=_identifier(model.get("id")),
                    display_name=(
                        _identifier(model["name"]) if model.get("name") is not None else None
                    ),
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
        self._validate_context(context)
        model_id = _identifier(model_id)
        unknown = CapabilityValue(CapabilityState.UNKNOWN)
        return ModelCapabilities(
            provider_id=ProviderId.OPENAI_COMPATIBLE,
            model_id=model_id,
            tools=unknown,
            json_mode=unknown,
            vision=unknown,
            streaming=unknown,
            embeddings=unknown,
        )

    def _chat_payload(self, request: ChatRequest, *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model_id,
            "messages": _request_messages(tuple(request.messages)),
            "stream": stream,
        }
        if request.options.max_tokens is not None:
            payload[self._token_limit_parameter] = request.options.max_tokens
        if request.options.temperature is not None:
            payload["temperature"] = request.options.temperature
        if request.options.json_mode:
            payload["response_format"] = {"type": "json_object"}
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
        self, response: ProviderStreamResponse, request: ChatRequest
    ) -> None:
        features = self._requested_features(request)
        error_body: bytes | None = None
        if response.status_code in {400, 422} and features:
            error_body = await _read_limited_error_body(
                response, min(self._transport.limits.max_response_bytes, 65_536)
            )
        _check_status(
            response.status_code,
            model_lookup=True,
            error_body=error_body,
            requested_features=features,
        )

    async def chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> ChatResult:
        self._validate_context(context)
        value = await self._request_json(
            "POST",
            context,
            "chat/completions",
            self._chat_payload(request, stream=False),
            model_lookup=True,
            requested_features=self._requested_features(request),
        )
        return _read_chat_result(value, request)

    async def stream_chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> AsyncIterator[ChatChunk]:
        self._validate_context(context)
        url = self._url(context, "chat/completions")
        body = _json_body(self._chat_payload(request, stream=True))
        assembler = ToolCallAssembler()
        pending_terminal: ChatChunk | None = None
        assembled_calls: tuple[ToolCall, ...] | None = None
        saw_done = False
        async with self._transport.stream(
            "POST",
            url,
            context=context,
            headers=self._headers(context, json_body=True),
            body=body,
        ) as response:
            await self._check_stream_status(response, request)
            max_frame = min(_MAX_SSE_FRAME_BYTES, self._transport.limits.max_streamed_response_bytes)
            async for frame in _sse_frames(response, max_frame):
                if not frame:
                    continue
                data = _sse_data(frame)
                if data is None:
                    continue
                if saw_done:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                if data == "[DONE]":
                    if pending_terminal is None or assembled_calls is None:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    saw_done = True
                    continue
                if pending_terminal is not None:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                payload = _decode_json(data)
                chunk = _choice_chunk(payload, request)
                if chunk is None:
                    continue
                try:
                    completed = assembler.consume(chunk)
                except ValueError:
                    raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None
                if chunk.finish_reason is not None:
                    if completed is None:
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    assembled_calls = completed
                    if bool(assembled_calls) != (
                        chunk.finish_reason == SuccessfulChatFinishReason.TOOL_CALLS.value
                    ):
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    allowed_names = {tool.name for tool in request.tools}
                    if any(call.name not in allowed_names for call in assembled_calls):
                        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
                    for call in assembled_calls:
                        _validated_tool_arguments(call.arguments_json)
                    pending_terminal = chunk
                else:
                    yield chunk
        if not saw_done or pending_terminal is None or assembled_calls is None:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        yield pending_terminal

    async def embed(
        self, context: ProviderConnectionContext, model_id: str, text: str
    ) -> tuple[float, ...]:
        self._validate_context(context)
        model_id = _identifier(model_id)
        if not isinstance(text, str) or not text:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        payload = _object(
            await self._request_json(
                "POST",
                context,
                "embeddings",
                {"model": model_id, "input": text},
                model_lookup=True,
            )
        )
        data = payload.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        embedding = _object(data[0])
        if _nonnegative_integer(embedding.get("index")) != 0:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        raw_vector = embedding.get("embedding")
        if not isinstance(raw_vector, list) or not raw_vector:
            raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
        vector: list[float] = []
        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            number = float(value)
            if not math.isfinite(number):
                raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
            vector.append(number)
        return tuple(vector)
