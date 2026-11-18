"""Small shared parsing primitives for provider-specific adapters."""

from __future__ import annotations

import json

from .errors import ProviderError, ProviderErrorCode


def _reject_constant(_value: str) -> None:
    raise ValueError("non-standard JSON constant")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON property")
        result[key] = value
    return result


def decode_provider_json(data: bytes | str) -> object:
    """Decode bounded transport data while rejecting ambiguous JSON objects."""

    try:
        return json.loads(
            data,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, TypeError, ValueError):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None


def encode_provider_json(value: object) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8")
    except (RecursionError, TypeError, UnicodeEncodeError, ValueError):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE) from None


def require_json_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return value


def require_provider_text(value: object, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return value


def require_provider_identifier(value: object) -> str:
    value = require_provider_text(value, allow_empty=False)
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ProviderError(ProviderErrorCode.INVALID_RESPONSE)
    return value
