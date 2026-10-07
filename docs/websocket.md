# WebSocket and browser streaming boundary

## Notification protocol

`/ws/notifications` is an authenticated, process-local notification socket.
Browser clients first call `POST /api/auth/ws-ticket` with the normal bearer
header. The resulting single-use ticket expires quickly and is used only as
the WebSocket URL's `ticket` query parameter; the long-lived access token is
never placed in that URL. Non-browser clients may use an Authorization bearer
header. The legacy query-token compatibility path is retained only for older
non-browser clients and is not used by the frontend.

Every server message is a JSON envelope with `protocol_version: 1`, `type`,
`created_at`, and `data`. The server sends `ready`, `notification`, `pong`, and
`error`. Clients may send only `{"type":"ping"}` or `{"type":"pong"}`.
Malformed, unknown, or oversized messages are rejected and the connection is
closed. Inbound messages are bounded by `WEBSOCKET_MAX_MESSAGE_BYTES`.

Clients send heartbeats using the interval advertised in `ready`. A socket
that does not provide inbound traffic for two intervals is closed. The
browser client reconnects with bounded exponential backoff while authenticated
and stops reconnecting on logout or a 401 response. Multiple sockets remain
isolated by authenticated user ID.

Reminder notifications use a stable `event_id` (`reminder:<id>`) and include
`reminder_id` and `task_id`. Client deduplication is bounded and delivery is
still at-least-once: a process crash after sending but before the database
records `sent` can produce a duplicate.

## Chat and voice

The current chat API returns a complete response. The old timer-based fake
streaming implementation has been removed; AURA does not claim server-side
chat streaming until a real bounded stream is implemented. Responses remain
plain text through the safe DOM boundary.

Voice input is browser-provided Web Speech recognition only. It is user
triggered, uses one recognition instance, and sends only the resulting
transcript to the existing chat API. Browser/platform support and microphone
permission are required; AURA does not provide offline or backend voice
processing.
