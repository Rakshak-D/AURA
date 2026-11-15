# A0 Security Regression Evidence

**Status: `PASS_SYNTHETIC`.** No existing authentication, ownership, action-validation, destructive-confirmation, reminder-retry, upload-validation, or WebSocket-ticket control was removed or relaxed. The existing security test modules were left intact.

The focused Python 3.11 run collected and passed all 50 tests across:

- `tests/test_ai_security.py` — strict action shape, ownership, destructive-action confirmation, intent injection, and server-supplied RAG ownership filtering.
- `tests/test_authentication.py` — password hashing, login, token validation, legacy-user claim rules, user isolation, reminder ownership, and unauthenticated WebSocket rejection.
- `tests/test_database_integrity.py` — SQLite constraints, transaction rollback, user ownership, migrations, recurrence, and cascades.
- `tests/test_reminder_reliability.py` — bounded retry, stale work recovery, cancellation state, atomic claims, and WebSocket delivery outcomes.
- `tests/test_web_security.py` — security headers/CORS, single-use WebSocket tickets, protocol limits, upload traversal/type/size checks, and safe model rendering.

Command: `python -m pytest -q tests/test_ai_security.py tests/test_authentication.py tests/test_database_integrity.py tests/test_reminder_reliability.py tests/test_web_security.py --tb=short`.

The same regression suite passed as part of the complete 97-test deterministic backend run on Windows Python 3.11.7 and 3.12.10. The browser suite also exercises the real authentication flow and guards external requests. The CSP no longer lists remote CDNs; same-origin connections and the existing inline-script allowance remain because the existing HTML uses inline event handlers. Server authorization and validation code was not changed.
