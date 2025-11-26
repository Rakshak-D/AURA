import html

def sanitize_input(text: str) -> str:
    """
    Sanitize input string to prevent XSS.
    Uses html.escape for basic sanitization.
    """
    if not text:
        return ""
    return html.escape(text)

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
except ImportError:
    print("⚠️ slowapi not installed. Rate limiting disabled.")
    class DummyLimiter:
        def limit(self, limit_value):
            def decorator(func):
                return func
            return decorator
    limiter = DummyLimiter()
