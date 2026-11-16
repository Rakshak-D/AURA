"""Typed, provider-independent values used by the A1 model layer."""

from __future__ import annotations

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


class CapabilityState(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


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

    def __post_init__(self) -> None:
        try:
            role = MessageRole(self.role)
        except (TypeError, ValueError):
            raise ValueError("message role must be system, user, assistant, or tool") from None

        if not isinstance(self.content, str):
            raise ValueError("message content must be text")

        if role is MessageRole.TOOL:
            if not isinstance(self.tool_call_id, str) or not self.tool_call_id.strip():
                raise ValueError("tool messages require a non-empty tool_call_id")
        elif self.tool_call_id is not None:
            raise ValueError("tool_call_id is only valid for tool messages")

        object.__setattr__(self, "role", role)


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
    evidence: str | None = None

    def __post_init__(self) -> None:
        try:
            state = CapabilityState(self.state)
        except (TypeError, ValueError):
            raise ValueError("capability state must be supported, unsupported, or unknown") from None
        object.__setattr__(self, "state", state)


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
    source: str | None = None

    def __post_init__(self) -> None:
        try:
            provider_id = ProviderId(self.provider_id)
        except (TypeError, ValueError):
            raise ValueError("unsupported provider id") from None
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model id must be a non-empty string")
        if self.context_length is not None and self.context_length <= 0:
            raise ValueError("context_length must be positive when known")
        object.__setattr__(self, "provider_id", provider_id)


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

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be a non-empty string")
        messages = tuple(self.messages)
        if not messages:
            raise ValueError("chat requests require at least one structured message")
        if not all(isinstance(message, ProviderMessage) for message in messages):
            raise ValueError("chat messages must be ProviderMessage values")
        object.__setattr__(self, "messages", messages)


@dataclass(frozen=True, slots=True)
class ChatChunk:
    model_id: str
    delta: str
    finish_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ChatResult:
    model_id: str
    message: ProviderMessage
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


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
