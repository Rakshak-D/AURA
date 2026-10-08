# Web and browser security

The browser, HTTP responses, uploaded files, and WebSocket
handshakes as security boundaries.

## XSS and untrusted content

Task fields, usernames, filenames, search results, chat history, retrieved
documents, notifications, and LLM responses are data. The shared
`frontend/js/safe-dom.js` helper uses `textContent` and DOM node construction.
Chat output is deliberately rendered as plain text; Markdown or raw HTML from
the model is not executed. Upload, search, task, calendar, and chat views do
not interpolate API-controlled strings into HTML templates.

The existing page still has static inline event handlers and inline styles. The
CSP therefore permits the compatibility exceptions currently required
(`unsafe-inline`) while prohibiting objects, framing, non-self connections,
and unsafe resource types. Removing those legacy inline handlers is the next
opportunity to tighten the policy further.

## Tokens and WebSockets

HTTP bearer tokens are read and attached only by the central `apiFetch`
function. They are not put in DOM content, error messages, or ordinary URLs.
The browser stores the short-lived token in `sessionStorage`, which protects it
from persistent disk storage but not from same-origin script compromise.

Browser WebSockets use a one-use, 30-second ticket from
`POST /api/auth/ws-ticket`. The ticket is invalidated on the first handshake.
Authorization headers are supported for non-browser clients. The legacy
long-lived `?token=` form is retained temporarily for compatibility and must
not be used by browser code.

## HTTP headers and CORS

Responses include `Content-Security-Policy`, `X-Content-Type-Options`,
`X-Frame-Options`, `Referrer-Policy`, and a restrictive `Permissions-Policy`.
Authentication responses are marked `Cache-Control: no-store`. CORS uses the
explicit `ALLOWED_ORIGINS` configuration and does not enable wildcard origins
with credentials.

## Upload boundary

Uploads require an allowlisted extension and compatible content type, reject
path separators and oversized bodies, normalize names, and are parsed from an
in-memory bounded byte buffer. A user filename is never used as a filesystem
path. Document records and Chroma operations remain user-scoped by the
authenticated ownership boundary.

## Error and logging behavior

Clients receive generic internal-error responses. Authentication failures do
not return credentials or tokens. Server diagnostics use controlled messages;
request bodies, bearer tokens, and secrets must not be logged.

Remaining risks include the temporary legacy WebSocket query-token compatibility
path and the page's legacy inline handlers. Neither should be exposed as a
reason to weaken origin controls or token lifetime.
