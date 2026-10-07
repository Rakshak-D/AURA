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

Existing Phase 2 development data is preserved. If its user has no login
identifier, set `AUTH_BOOTSTRAP_TOKEN` out of band and call
`POST /api/auth/bootstrap` once with the token, identifier, and a new password.
Bootstrap is rejected unless exactly one legacy user remains; no production
password is hard-coded.

Protected operations derive ownership exclusively from the authenticated user.
Client `user_id` values are not authority. SQL records and Chroma chunks are
scoped by that identity. Chroma metadata includes `user_id`, and vector reads
and deletes include the namespace.

The browser stores the short-lived token in `sessionStorage`, adds it in the
central API layer, clears it on a 401, and provides sign-in/register/logout
behavior. WebSockets authenticate with a bearer header or browser-compatible
`token` query parameter and are registered under one user; notifications are
not broadcast across users. `AUTH_SECRET_KEY` must be a unique random value of
at least 32 characters in production. `ALLOWED_ORIGINS` is an explicit comma-
separated list; wildcard origins with credentials are not supported. Login and
registration use the existing SlowAPI limiter.
