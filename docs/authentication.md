# Authentication and authorization

AURA uses local username/email identifiers, Argon2id password hashes through
`pwdlib`, and short-lived HS256 bearer access tokens. Passwords and hashes are
never returned by API responses or exports.

`POST /api/auth/register` creates a user; `POST /api/auth/login` returns a
bearer token; `GET /api/auth/me` returns the safe profile. Send the token as
`Authorization: Bearer <token>` to protected APIs. Tokens contain only a user
subject, issued-at, expiry, and `access` purpose. Each request resolves the
subject against SQLite, so disabled users are rejected immediately. Tokens are
stateless with no refresh/revocation store yet; keep their lifetime short.

Existing pre-authentication development data is preserved. If its user has no login
identifier, set `AUTH_BOOTSTRAP_TOKEN` out of band and call
`POST /api/auth/bootstrap` once with the token, identifier, and a new password.
Bootstrap is rejected unless exactly one legacy user remains; no production
password is hard-coded.

Protected operations derive ownership exclusively from the authenticated user.
Client `user_id` values are not authority. SQL records and Chroma chunks are
scoped by that identity. Chroma metadata includes `user_id`, and vector reads
and deletes include the namespace.

The browser stores the short-lived token in `sessionStorage`, adds it only in
the central API layer, clears it on a 401/logout, and provides
sign-in/register/logout behavior. This limits persistence but does not protect
against a same-origin XSS compromise; AURA therefore renders API and model
content as text and applies a browser security policy.

Browser WebSockets obtain `POST /api/auth/ws-ticket` with the bearer header.
The returned ticket is one-use and expires after 30 seconds; it is the only
credential placed in the browser WebSocket URL. Direct bearer headers remain
supported for non-browser clients. The legacy `?token=` query form remains
temporarily for compatibility and should not be used by browser code because
URLs can appear in proxy or diagnostic logs.

`AUTH_SECRET_KEY` must be a unique random value of at least 32 characters in
production. `ALLOWED_ORIGINS` is an explicit comma-separated list; wildcard
origins with credentials are not supported. Login, registration, and ticket
issuance use the existing SlowAPI limiter.
