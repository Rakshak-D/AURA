"""Typed, provider-independent values used by the A1 model layer."""

from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from .errors import ProviderErrorCode


class ProviderId(StrEnum):
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"
    LEGACY_GGUF = "legacy_gguf"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    SENTENCE_TRANSFORMERS = "sentence_transformers"


class ModelRole(StrEnum):
    ROUTER = "router"
    CHAT = "chat"
    EMBEDDING = "embedding"


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatStreamEventType(StrEnum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_FRAGMENT = "tool_call_fragment"
    COMPLETION = "completion"


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class CapabilityEvidenceSource(StrEnum):
    CONTROLLED_PROBE = "controlled_probe"
    PROVIDER_METADATA = "provider_metadata"
    UNKNOWN = "unknown"


_MAX_TOOL_NAME_LENGTH = 64
_MAX_TOOL_CALL_ID_LENGTH = 128
_MAX_TOOL_PAYLOAD_BYTES = 65_536
_MAX_TOOL_COUNT = 128
_MAX_CUMULATIVE_TOOL_PAYLOAD_BYTES = 1_048_576


def _validate_identity(value: object, label: str, maximum_length: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum_length
        or any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError(f"{label} must be a bounded, non-whitespace identity")
    return value


def _validate_tool_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _MAX_TOOL_NAME_LENGTH
        or not value.isascii()
        or not all(character.isalnum() or character in "_.-" for character in value)
        or not any(character.isalnum() or character == "_" for character in value)
    ):
        raise ValueError("tool name must be a valid bounded identifier")
    return value


def _copy_json_value(value: object) -> object:
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("JSON object keys must be strings")
        return {key: _copy_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_json_value(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("tool payload must contain only finite JSON values")


def _copy_json_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a JSON object")
    try:
        copied = _copy_json_value(value)
        encoded = json.dumps(copied, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        payload_size = len(encoded.encode("utf-8"))
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError):
        raise ValueError(f"{label} must be a bounded JSON object") from None
    if payload_size > _MAX_TOOL_PAYLOAD_BYTES:
        raise ValueError(f"{label} exceeds the maximum size")
    return copied


def _reject_nonstandard_json_constant(_constant: str) -> None:
    raise ValueError("non-standard JSON constant")


def _validate_tool_arguments(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("tool arguments must be untrusted JSON text")
    try:
        if len(value.encode("utf-8")) > _MAX_TOOL_PAYLOAD_BYTES:
            raise ValueError("tool arguments exceed the maximum size")
        parsed = json.loads(
            value,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (RecursionError, TypeError, UnicodeDecodeError, UnicodeEncodeError, ValueError):
        raise ValueError("tool arguments must be bounded valid JSON") from None
    if not isinstance(parsed, dict):
        raise ValueError("tool arguments must be a JSON object")
    return value


@dataclass(frozen=True, slots=True)
class EphemeralCredential:
    """A transient secret value whose default representations are redacted."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value:
            raise ValueError("credential material must be a non-empty string")

    def __repr__(self) -> str:
        return "EphemeralCredential(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


@dataclass(frozen=True, slots=True)
class ProviderMessage:
    role: MessageRole
    content: str
    tool_call_id: str | None = None
    tool_calls: Sequence[ToolCall] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        try:
            role = MessageRole(self.role)
        except (TypeError, ValueError):
            raise ValueError("message role must be system, user, assistant, or tool") from None

        if not isinstance(self.content, str):
            raise ValueError("message content must be text")

        if role is MessageRole.TOOL:
            _validate_identity(self.tool_call_id, "tool_call_id", _MAX_TOOL_CALL_ID_LENGTH)
        elif self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool messages")

        tool_calls = tuple(self.tool_calls)
        if len(tool_calls) > _MAX_TOOL_COUNT:
            raise ValueError("assistant tool-call count exceeds the maximum")
        if not all(isinstance(call, ToolCall) for call in tool_calls):
            raise ValueError("assistant tool calls must be ToolCall values")
        call_ids = [call.call_id for call in tool_calls]
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("assistant tool-call ids must be unique")
        if tool_calls and role is not MessageRole.ASSISTANT:
            raise ValueError("tool calls are only valid on assistant messages")

        object.__setattr__(self, "role", role)
        object.__setattr__(self, "tool_calls", tool_calls)


@dataclass(frozen=True, slots=True)
class ProviderModel:
    id: str
    display_name: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("model id must be a non-empty string")


@dataclass(frozen=True, slots=True)
class CapabilityValue:
    state: CapabilityState = CapabilityState.UNKNOWN
    source: CapabilityEvidenceSource = CapabilityEvidenceSource.UNKNOWN

    def __post_init__(self) -> None:
        try:
            state = CapabilityState(self.state)
        except (TypeError, ValueError):
            raise ValueError("capability state must be supported, unsupported, or unknown") from None
        try:
            source = CapabilityEvidenceSource(self.source)
        except (TypeError, ValueError):
            raise ValueError("capability evidence source is not recognized") from None
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "source", source)


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    provider_id: ProviderId
    model_id: str
    context_length: int | None = None
    tools: CapabilityValue = field(default_factory=CapabilityValue)
    json_mode: CapabilityValue = field(default_factory=CapabilityValue)
    vision: CapabilityValue = field(default_factory=CapabilityValue)
    streaming: CapabilityValue = field(default_factory=CapabilityValue)
    embeddings: CapabilityValue = field(default_factory=CapabilityValue)
    checked_at: datetime | None = None
    context_length_source: CapabilityEvidenceSource = CapabilityEvidenceSource.UNKNOWN

    def __post_init__(self) -> None:
        try:
            provider_id = ProviderId(self.provider_id)
        except (TypeError, ValueError):
            raise ValueError("unsupported provider id") from None
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model id must be a non-empty string")
        if self.context_length is not None and self.context_length <= 0:
            raise ValueError("context_length must be positive when known")
        try:
            context_length_source = CapabilityEvidenceSource(self.context_length_source)
        except (TypeError, ValueError):
            raise ValueError("context_length evidence source is not recognized") from None
        object.__setattr__(self, "provider_id", provider_id)
        object.__setattr__(self, "context_length_source", context_length_source)


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Provider-neutral tool declaration; its schema remains inert JSON data."""

    name: str
    input_schema: Mapping[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        name = _validate_tool_name(self.name)
        schema = _copy_json_object(self.input_schema, "tool input schema")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "input_schema", schema)


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Provider-proposed call with bounded, untrusted arguments that are never executed here."""

    call_id: str
    name: str
    arguments_json: str = field(repr=False)

    def __post_init__(self) -> None:
        call_id = _validate_identity(self.call_id, "tool call id", _MAX_TOOL_CALL_ID_LENGTH)
        name = _validate_tool_name(self.name)
        arguments_json = _validate_tool_arguments(self.arguments_json)
        object.__setattr__(self, "call_id", call_id)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "arguments_json", arguments_json)


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """One inert partial tool-call event from a provider stream."""

    index: int
    call_id: str | None = None
    name_fragment: str | None = None
    arguments_fragment: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise ValueError("tool-call stream index must be a non-negative integer")
        if self.call_id is not None:
            _validate_identity(self.call_id, "tool call id", _MAX_TOOL_CALL_ID_LENGTH)
        if self.name_fragment is not None and (
            not isinstance(self.name_fragment, str)
            or len(self.name_fragment) > _MAX_TOOL_NAME_LENGTH
            or not self.name_fragment.isascii()
            or not all(character.isalnum() or character in "_.-" for character in self.name_fragment)
        ):
            raise ValueError("tool-call name fragment is malformed")
        if not isinstance(self.arguments_fragment, str):
            raise ValueError("tool-call argument fragment must be text")
        try:
            size = len(self.arguments_fragment.encode("utf-8"))
        except UnicodeEncodeError:
            raise ValueError("tool-call argument fragment is malformed") from None
        if size > _MAX_TOOL_PAYLOAD_BYTES:
            raise ValueError("tool-call argument fragment exceeds the maximum size")
        if self.call_id is None and not self.name_fragment and not self.arguments_fragment:
            raise ValueError("tool-call stream delta must contain data")


@dataclass(frozen=True, slots=True)
class ProviderConnectionContext:
    user_id: int
    connection_id: str
    provider_id: ProviderId
    config_revision: int
    local_only: bool = True
    base_url: str | None = field(default=None, repr=False)
    credential: EphemeralCredential | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.user_id <= 0:
            raise ValueError("user_id must be positive")
        if not isinstance(self.connection_id, str) or not self.connection_id.strip():
            raise ValueError("connection_id must be a non-empty string")
        if self.config_revision < 0:
            raise ValueError("config_revision cannot be negative")
        try:
            provider_id = ProviderId(self.provider_id)
        except (TypeError, ValueError):
            raise ValueError("unsupported provider id") from None
        object.__setattr__(self, "provider_id", provider_id)


@dataclass(frozen=True, slots=True)
class HealthResult:
    available: bool
    checked_at: datetime | None = None
    error_code: ProviderErrorCode | None = None

    def __post_init__(self) -> None:
        if self.error_code is not None:
            try:
                error_code = ProviderErrorCode(self.error_code)
            except (TypeError, ValueError):
                raise ValueError("health error_code must be a normalized provider error") from None
            object.__setattr__(self, "error_code", error_code)


@dataclass(frozen=True, slots=True)
class ChatOptions:
    max_tokens: int | None = None
    temperature: float | None = None
    json_mode: bool = False

    def __post_init__(self) -> None:
        if self.max_tokens is not None and self.max_tokens <= 0:
            raise ValueError("max_tokens must be positive when provided")
        if self.temperature is not None and self.temperature < 0:
            raise ValueError("temperature cannot be negative")


@dataclass(frozen=True, slots=True)
class ChatRequest:
    model_id: str
    messages: Sequence[ProviderMessage]
    options: ChatOptions = field(default_factory=ChatOptions)
    tools: Sequence[ToolDefinition] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        messages = tuple(self.messages)
        if not messages:
            raise ValueError("chat requests require at least one structured message")
        if not all(isinstance(message, ProviderMessage) for message in messages):
            raise ValueError("chat messages must be ProviderMessage values")
        tools = tuple(self.tools)
        if len(tools) > _MAX_TOOL_COUNT:
            raise ValueError("chat tool count exceeds the maximum")
        if not all(isinstance(tool, ToolDefinition) for tool in tools):
            raise ValueError("chat tools must be ToolDefinition values")
        tool_names = [tool.name for tool in tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("chat tool names must be unique")
        object.__setattr__(self, "messages", messages)
        object.__setattr__(self, "tools", tools)


@dataclass(frozen=True, slots=True)
class ChatChunk:
    model_id: str
    delta: str
    finish_reason: str | None = None
    tool_call_deltas: Sequence[ToolCallDelta] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("stream model_id must be a non-empty string")
        if not isinstance(self.delta, str):
            raise ValueError("stream text delta must be text")
        tool_call_deltas = tuple(self.tool_call_deltas)
        if len(tool_call_deltas) > _MAX_TOOL_COUNT:
            raise ValueError("stream tool-call count exceeds the maximum")
        if not all(isinstance(delta, ToolCallDelta) for delta in tool_call_deltas):
            raise ValueError("stream tool calls must be ToolCallDelta values")
        indexes = [delta.index for delta in tool_call_deltas]
        call_ids = [delta.call_id for delta in tool_call_deltas if delta.call_id is not None]
        if len(indexes) != len(set(indexes)) or len(call_ids) != len(set(call_ids)):
            raise ValueError("stream tool-call identities must be unique within a chunk")
        object.__setattr__(self, "tool_call_deltas", tool_call_deltas)

    @property
    def event_types(self) -> tuple[ChatStreamEventType, ...]:
        """Describe every event carried by this chunk, including mixed chunks."""
        events: list[ChatStreamEventType] = []
        if self.delta:
            events.append(ChatStreamEventType.TEXT_DELTA)
        if self.tool_call_deltas:
            events.append(ChatStreamEventType.TOOL_CALL_FRAGMENT)
        if self.finish_reason is not None:
            events.append(ChatStreamEventType.COMPLETION)
        return tuple(events)


@dataclass(slots=True)
class _ToolCallAssembly:
    call_id: str | None = None
    name: bytearray = field(default_factory=bytearray, repr=False)
    arguments: bytearray = field(default_factory=bytearray, repr=False)


class ToolCallAssembler:
    """Bounded assembler for inert, provider-proposed tool-call stream data."""

    def __init__(self) -> None:
        self._calls: dict[int, _ToolCallAssembly] = {}
        self._indexes_by_id: dict[str, int] = {}
        self._cumulative_payload_bytes = 0
        self._model_id: str | None = None
        self._finished = False
        self._failed = False

    def consume(self, chunk: ChatChunk) -> tuple[ToolCall, ...] | None:
        """Add one chunk; return reconstructed calls only on its completion event."""
        if self._finished or self._failed:
            raise ValueError("tool-call stream is already closed")
        if not isinstance(chunk, ChatChunk):
            self._failed = True
            self._discard_partial_calls()
            raise ValueError("tool-call stream requires ChatChunk values")

        try:
            return self._consume(chunk)
        except (UnicodeError, ValueError, RecursionError):
            self._failed = True
            self._discard_partial_calls()
            raise ValueError("invalid or incomplete tool-call stream") from None

    def _record_payload_size(self, size: int) -> None:
        if self._cumulative_payload_bytes + size > _MAX_CUMULATIVE_TOOL_PAYLOAD_BYTES:
            raise ValueError("cumulative tool-call payload exceeds the maximum")
        self._cumulative_payload_bytes += size

    def _discard_partial_calls(self) -> None:
        self._calls.clear()
        self._indexes_by_id.clear()
        self._cumulative_payload_bytes = 0

    def _consume(self, chunk: ChatChunk) -> tuple[ToolCall, ...] | None:
        if self._model_id is None:
            self._model_id = chunk.model_id
        elif self._model_id != chunk.model_id:
            raise ValueError("stream model changed")

        for delta in chunk.tool_call_deltas:
            if delta.index >= _MAX_TOOL_COUNT:
                raise ValueError("tool-call stream index exceeds the maximum")
            assembly = self._calls.get(delta.index)
            if assembly is None:
                if len(self._calls) >= _MAX_TOOL_COUNT:
                    raise ValueError("tool-call response exceeds the maximum call count")
                assembly = _ToolCallAssembly()
                self._calls[delta.index] = assembly

            if delta.call_id is not None:
                if assembly.call_id is not None and assembly.call_id != delta.call_id:
                    raise ValueError("tool-call identity changed during streaming")
                if assembly.call_id is None:
                    existing_index = self._indexes_by_id.get(delta.call_id)
                    if existing_index is not None and existing_index != delta.index:
                        raise ValueError("tool-call identity is assigned to multiple indexes")
                    self._record_payload_size(len(delta.call_id.encode("utf-8")))
                    assembly.call_id = delta.call_id
                    self._indexes_by_id[delta.call_id] = delta.index

            if delta.name_fragment is not None:
                name_bytes = delta.name_fragment.encode("ascii")
                if len(assembly.name) + len(name_bytes) > _MAX_TOOL_NAME_LENGTH:
                    raise ValueError("assembled tool name exceeds the maximum")
                self._record_payload_size(len(name_bytes))
                assembly.name.extend(name_bytes)

            argument_bytes = delta.arguments_fragment.encode("utf-8")
            if len(assembly.arguments) + len(argument_bytes) > _MAX_TOOL_PAYLOAD_BYTES:
                raise ValueError("assembled tool arguments exceed the maximum")
            self._record_payload_size(len(argument_bytes))
            assembly.arguments.extend(argument_bytes)

        if chunk.finish_reason is None:
            return None

        calls: list[ToolCall] = []
        for index in sorted(self._calls):
            assembly = self._calls[index]
            if assembly.call_id is None or not assembly.name or not assembly.arguments:
                raise ValueError("completed tool call is missing identity or payload")
            call = ToolCall(
                call_id=assembly.call_id,
                name=assembly.name.decode("ascii"),
                arguments_json=assembly.arguments.decode("utf-8"),
            )
            calls.append(call)
        self._finished = True
        self._discard_partial_calls()
        return tuple(calls)


@dataclass(frozen=True, slots=True)
class ChatResult:
    model_id: str
    message: ProviderMessage
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("result model_id must be a non-empty string")
        if not isinstance(self.message, ProviderMessage):
            raise ValueError("chat result message must be a ProviderMessage")


class ProviderAdapter(Protocol):
    async def list_models(
        self, context: ProviderConnectionContext
    ) -> Sequence[ProviderModel]: ...

    async def health_check(self, context: ProviderConnectionContext) -> HealthResult: ...

    async def get_capabilities(
        self, context: ProviderConnectionContext, model_id: str
    ) -> ModelCapabilities: ...

    async def chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> ChatResult: ...

    def stream_chat(
        self, context: ProviderConnectionContext, request: ChatRequest
    ) -> AsyncIterator[ChatChunk]: ...

    async def embed(
        self, context: ProviderConnectionContext, model_id: str, text: str
    ) -> Sequence[float]: ...
