from typing import Any, Dict, Optional


def success_response(data: Any = None, message: Optional[str] = None) -> Dict[str, Any]:
    """
    Standard success envelope used by JSON endpoints.

    Structure:
    {
        "success": true,
        "data": ...,
        "message": "optional human readable message",
        "error": null
    }
    """
    return {
        "success": True,
        "data": data,
        "message": message,
        "error": None,
    }


def error_response(
    message: str,
    code: str = "ERROR",
    *,
    details: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Standard error envelope for JSON endpoints that choose to respond
    with 200 and a structured error payload (to avoid breaking clients
    that don't handle non-2xx responses gracefully).

    Structure:
    {
        "success": false,
        "data": null,
        "message": "short description",
        "error": {
            "code": "ERROR_CODE",
            "message": "short description",
            "details": {...}
        }
    }
    """
    return {
        "success": False,
        "data": None,
        "message": message,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }


