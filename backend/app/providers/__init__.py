"""Provider-independent AURA contracts.

Importing this package is intentionally side-effect free: provider runtimes,
network clients, and credential backends are loaded only by later operations.
"""

from .contracts import (
    CapabilityEvidenceSource,
    CapabilityState,
    CapabilityValue,
    ChatChunk,
    ChatOptions,
    ChatRequest,
    ChatResult,
    ChatStreamEventType,
    EphemeralCredential,
    HealthResult,
    MessageRole,
    ModelCapabilities,
    ModelRole,
    ProviderAdapter,
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
from .errors import ProviderError, ProviderErrorCode, normalize_provider_error
from .registry import ProviderDefinition, ProviderRegistry

__all__ = [
    "CapabilityEvidenceSource",
    "CapabilityState",
    "CapabilityValue",
    "ChatChunk",
    "ChatOptions",
    "ChatRequest",
    "ChatResult",
    "ChatStreamEventType",
    "EphemeralCredential",
    "HealthResult",
    "MessageRole",
    "ModelCapabilities",
    "ModelRole",
    "ProviderAdapter",
    "ProviderConnectionContext",
    "ProviderDefinition",
    "ProviderError",
    "ProviderErrorCode",
    "ProviderId",
    "ProviderMessage",
    "ProviderModel",
    "ProviderRegistry",
    "SuccessfulChatFinishReason",
    "ToolCall",
    "ToolCallAssembler",
    "ToolCallDelta",
    "ToolDefinition",
    "normalize_provider_error",
]
