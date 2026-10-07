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

The required database schema version is `4`. Readiness validates the actual
SQLite schema and does not report the database as ready when this version or
its required constraints are missing.

## Ownership model

Authentication is now the ownership boundary. Routes use the authenticated
user dependency rather than a development-user resolver. Legacy data remains
owned by its existing user and can be claimed through the documented bootstrap
flow without changing table ownership.

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
priorities and recurrence values, and the exact task completion invariant:
incomplete tasks have no completion timestamp and completed tasks have one.
Composite foreign keys ensure a task parent and its child share an owner, and
that a reminder's task and user match. Indexes cover
common ownership plus due/completion, reminder trigger, document ownership,
and chat-history chronology queries.

Reminder `status` is the only authoritative delivery state. It is one of
`pending`, `processing`, `sent`, `cancelled`, or `failed`; persistent attempt
metadata supports bounded retries and stale-processing recovery. The former
mutable `sent` boolean is removed by the migration and is not used as a second
source of truth.

## Initialization and migration

`Base.metadata.create_all()` creates missing tables for a fresh development
database, but it is not treated as a schema migration. Existing legacy SQLite
databases at version 1 are transactionally rebuilt for the affected task,
reminder, and document tables. Primary keys and valid values are preserved;
missing ownership is assigned to the first seeded user, cross-owner legacy
links are detached or aligned to the referenced task owner, invalid task
completion combinations are normalized deterministically, and legacy reminder
`sent` values are converted into `status`. The schema version advances only
after the rebuilt schema validates. Re-running the migration is idempotent;
failure leaves the version unchanged and does not silently claim completion.
Version 4 adds reminder attempt metadata and the processing-state constraint.

## Test databases

Database tests create an isolated SQLite file under pytest's temporary
directory, enable foreign keys, create the schema from metadata, and dispose
the engine after each test. They never use the developer's `data/aura.db`.

## Export consistency

`/api/export` reads the authenticated user's tasks, chat history,
documents, reminders, and routine events through one SQLAlchemy session. The
export contains document metadata and indexing state, not Chroma vectors or
binary storage. It is a logical application-data export, not a database backup.
