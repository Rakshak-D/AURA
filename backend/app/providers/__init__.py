"""Provider-independent AURA contracts.

Importing this package is intentionally side-effect free: provider runtimes,
network clients, and credential backends are loaded only by later operations.
"""

from .contracts import (
    CapabilityState,
    CapabilityValue,
    ChatChunk,
    ChatOptions,
    ChatRequest,
    ChatResult,
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
)
from .errors import ProviderError, ProviderErrorCode, normalize_provider_error
from .registry import ProviderDefinition, ProviderRegistry

__all__ = [
    "CapabilityState",
    "CapabilityValue",
    "ChatChunk",
    "ChatOptions",
    "ChatRequest",
    "ChatResult",
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
    "normalize_provider_error",
]
