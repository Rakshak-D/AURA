# Persistent reminders

Reminders are durable SQLite records. APScheduler is only a polling mechanism;
an in-memory job may disappear during a restart because startup and every poll
rediscover due rows from the database.

## State machine

```text
pending   -> processing -> sent
                         -> failed -> processing
pending   -> cancelled
failed    -> cancelled
```

Cancelled rows are never claimed and sent rows are not reopened. Each claim
increments `attempt_count` and records `last_attempt_at`. Delivery failures
store bounded `last_error` text and schedule `next_attempt_at` until
`REMINDER_MAX_ATTEMPTS` is reached. Processing rows older than
`REMINDER_PROCESSING_TIMEOUT_SECONDS` are recovered to failed/retry state.

## Scheduling and delivery

The poller runs every `REMINDER_POLL_INTERVAL_SECONDS`, finds due pending or
retryable failed rows, and atomically updates one row to `processing`. The
conditional database update means concurrent workers cannot claim the same
row. Every worker uses its own SQLAlchemy session.

The current policy is B: an authenticated user must have an active WebSocket
connection for dispatch to be accepted. No connection leaves the reminder
retryable; after the attempt limit it remains `failed`. Notifications contain
`reminder_id` and `task_id`, providing a stable identity for client-side
deduplication. Delivery is at-least-once: a crash after dispatch but before
persisting `sent` can produce a duplicate.

## Timezones

API input must contain an aware timestamp and a valid IANA `timezone`. The
timestamp is normalized to UTC before persistence. The timezone identifies the
user's intended display/local-time context; the scheduler compares only UTC
instants. Naive timestamps and invalid zone names are rejected. Python
`zoneinfo` handles DST conversion at the API boundary.

Chat-created reminders use the same typed action and durable database path as
direct API reminders. Scheduler registration is not part of the commit and
cannot make a persisted reminder disappear.

## Lifecycle and diagnostics

The application starts one interval poller after database initialization in
non-test environments and stops it during shutdown. Startup recovers stale
processing rows. Starting the poller repeatedly is idempotent. `/ready`
reports scheduler state, last tick, and reminder workload; zero pending
reminders is healthy and distinct from an unavailable scheduler.
