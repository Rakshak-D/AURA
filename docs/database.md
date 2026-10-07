# AURA Database and Data Integrity

## Schema overview

The SQLite database contains users, tasks, reminders, chat history, documents,
and routine events. User-owned records carry a non-null foreign key to
`users.id`. Tasks may have child tasks, reminders may reference tasks, and all
personal collections are exposed through SQLAlchemy relationships with
intentional delete cascades.

Documents use their database integer identity as their stable identity. The
filename is metadata and is only duplicate-checked within the resolved user;
it is not a global identity. Document indexing is represented in SQL with
`pending`, `indexed`, or `failed` and an optional non-sensitive failure marker.
SQLite and Chroma are separate systems and are not part of one transaction.

## Ownership model

Authentication is intentionally not implemented yet. Until Phase 3, routes use
`get_development_user()` / `get_development_user_id()` as the single ownership
boundary. The resolver selects the first seeded user rather than scattering a
literal current-user ID through route code. Phase 3 can replace this resolver
with an authenticated-user dependency without changing the owned tables.

## Timestamp policy

Persisted instants use aware UTC values. `UTCDateTime` normalizes legacy naive
inputs as UTC for compatibility with existing development data, stores UTC in
SQLite, and returns aware UTC values to Python. API/UI boundaries remain
responsible for converting UTC instants to a user display timezone.

Date-only concepts must remain dates. Routine `start_time` and
`days_of_week` are local wall-clock schedule metadata, not UTC instants. A
task/reminder trigger is an instant and must include or explicitly default its
timezone at the boundary.

## Transactions and sessions

Request sessions come from `get_db()`, which rolls back on exceptions and
always closes. Background work creates its own `SessionLocal` session.
Multi-step non-request operations can use `session_scope()` for one explicit
commit/rollback boundary. Chroma indexing is an external side effect: the SQL
document is committed as `pending`, and a separate state update records
`indexed` or `failed` after the Chroma operation.

## Constraints and indexes

Fresh databases enforce positive task/routine durations, supported task
priorities and recurrence values, coherent task completion timestamps,
supported reminder/indexing states, and foreign-key ownership. Indexes cover
common ownership plus due/completion, reminder trigger, document ownership,
and chat-history chronology queries.

## Initialization and migration

`Base.metadata.create_all()` creates missing tables for a fresh development
database. It is not treated as a schema migration. A small additive migration
step maintains `schema_version` and adds the Phase 2 document/reminder columns
and indexes to existing SQLite files without deleting data. Existing legacy
tables cannot gain every new SQLite CHECK/FK constraint without a table rebuild;
such destructive/rebuild migrations are deferred to an explicit future
migration step rather than being performed silently at startup.

## Test databases

Database tests create an isolated SQLite file under pytest's temporary
directory, enable foreign keys, create the schema from metadata, and dispose
the engine after each test. They never use the developer's `data/aura.db`.

## Export consistency

`/api/export` reads the development user's user, tasks, chat history,
documents, reminders, and routine events through one SQLAlchemy session. The
export contains document metadata and indexing state, not Chroma vectors or
binary storage. It is a logical application-data export, not a database backup.
