"""Safe, provider-neutral errors with no raw upstream details."""

from __future__ import annotations

import asyncio
from enum import StrEnum


class ProviderErrorCode(StrEnum):
    INCOMPLETE_CONFIGURATION = "incomplete_configuration"
    UNAVAILABLE = "unavailable"
    AUTHENTICATION_FAILED = "authentication_failed"
    MODEL_UNAVAILABLE = "model_unavailable"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    LOCAL_ONLY_BLOCKED = "local_only_blocked"
    ENDPOINT_BLOCKED = "endpoint_blocked"
    CONNECTION_REMOVED = "connection_removed"
    SECRET_STORE_UNAVAILABLE = "secret_store_unavailable"
    NEEDS_REENTRY = "needs_reentry"
    RATE_LIMITED = "rate_limited"
    INVALID_RESPONSE = "invalid_response"


_SAFE_MESSAGES = {
    ProviderErrorCode.INCOMPLETE_CONFIGURATION: "Provider connection is incomplete.",
    ProviderErrorCode.UNAVAILABLE: "Provider is unavailable.",
    ProviderErrorCode.AUTHENTICATION_FAILED: "Provider authentication failed.",
    ProviderErrorCode.MODEL_UNAVAILABLE: "The selected model is unavailable.",
    ProviderErrorCode.UNSUPPORTED_CAPABILITY: "The selected model does not support this operation.",
    ProviderErrorCode.TIMEOUT: "The provider request timed out.",
    ProviderErrorCode.CANCELLED: "The provider request was cancelled.",
    ProviderErrorCode.LOCAL_ONLY_BLOCKED: "Local only settings blocked this provider request.",
    ProviderErrorCode.ENDPOINT_BLOCKED: "The provider endpoint is blocked by destination policy.",
    ProviderErrorCode.CONNECTION_REMOVED: "The selected provider connection has been removed.",
    ProviderErrorCode.SECRET_STORE_UNAVAILABLE: "Secure credential storage is unavailable.",
    ProviderErrorCode.NEEDS_REENTRY: "Re-enter the credential for this provider connection.",
    ProviderErrorCode.RATE_LIMITED: "The provider rate limit was reached.",
    ProviderErrorCode.INVALID_RESPONSE: "The provider returned an invalid response.",
}


class ProviderError(Exception):
    """An error safe to expose to logs and API clients."""

    def __init__(
        self,
        code: ProviderErrorCode,
        *,
        retryable: bool = False,
    ) -> None:
        try:
            normalized_code = ProviderErrorCode(code)
        except (TypeError, ValueError):
            raise ValueError("unsupported provider error code") from None

        self.code = normalized_code
        self.safe_message = _SAFE_MESSAGES[normalized_code]
        self.retryable = retryable
        super().__init__(self.safe_message)


def normalize_provider_error(error: BaseException) -> ProviderError:
    """Map generic failures to safe categories without retaining their text."""

    if isinstance(error, ProviderError):
        return error
    if isinstance(error, asyncio.CancelledError):
        return ProviderError(ProviderErrorCode.CANCELLED)
    if isinstance(error, (TimeoutError, asyncio.TimeoutError)):
        return ProviderError(ProviderErrorCode.TIMEOUT, retryable=True)
    if isinstance(error, ConnectionError):
        return ProviderError(ProviderErrorCode.UNAVAILABLE, retryable=True)
    return ProviderError(ProviderErrorCode.INVALID_RESPONSE)
