"""Database-authoritative reminder polling and delivery."""

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import or_, update

from .. import database
from ..config import config
from ..database import session_scope, utc_now
from ..models.sql_models import Reminder, Task
from ..websocket_manager import manager

logger = logging.getLogger(__name__)
scheduler = None
last_scheduler_tick: datetime | None = None


def _session_factory(session_factory):
    return session_factory or database.SessionLocal


def _get_scheduler():
    global scheduler
    if scheduler is not None:
        return scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError as exc:
        raise RuntimeError(
            "APScheduler is not installed. Install the scheduler dependency to use reminders."
        ) from exc
    scheduler = BackgroundScheduler(timezone="UTC")
    return scheduler


def recover_stale_reminders(*, session_factory=None, now: datetime | None = None) -> int:
    session_factory = _session_factory(session_factory)
    now = now or utc_now()
    cutoff = now - timedelta(seconds=config.reminder_processing_timeout_seconds)
    recovered = 0
    with session_scope(session_factory) as db:
        stale = db.query(Reminder).filter(
            Reminder.status == "processing",
            Reminder.last_attempt_at.is_not(None),
            Reminder.last_attempt_at < cutoff,
        ).all()
        for reminder in stale:
            reminder.status = "failed"
            reminder.next_attempt_at = now if reminder.attempt_count < config.reminder_max_attempts else None
            reminder.last_error = "processing timeout; recovered for retry"
            reminder.updated_at = now
            recovered += 1
            logger.warning(
                "Recovered stale reminder id=%s user_id=%s attempt=%s",
                reminder.id, reminder.user_id, reminder.attempt_count,
            )
    return recovered


def claim_due_reminder(
    reminder_id: int, *, session_factory=None, now: datetime | None = None
) -> bool:
    """Atomically claim one eligible reminder; exactly one concurrent caller wins."""
    session_factory = _session_factory(session_factory)
    now = now or utc_now()
    with session_scope(session_factory) as db:
        result = db.execute(
            update(Reminder)
            .where(
                Reminder.id == reminder_id,
                Reminder.status.in_(["pending", "failed"]),
                Reminder.reminder_time <= now,
                Reminder.attempt_count < config.reminder_max_attempts,
                or_(Reminder.next_attempt_at.is_(None), Reminder.next_attempt_at <= now),
            )
            .values(
                status="processing",
                attempt_count=Reminder.attempt_count + 1,
                last_attempt_at=now,
                last_error=None,
                updated_at=now,
            )
        )
        claimed = result.rowcount == 1
    if claimed:
        logger.info("Reminder claimed id=%s", reminder_id)
    return claimed


def _mark_failed(reminder_id: int, user_id: int, reason: str, *, session_factory=None) -> None:
    session_factory = _session_factory(session_factory)
    now = utc_now()
    safe_reason = " ".join(str(reason).split())[:500] or "delivery failed"
    with session_scope(session_factory) as db:
        reminder = db.query(Reminder).filter(
            Reminder.id == reminder_id,
            Reminder.user_id == user_id,
            Reminder.status == "processing",
        ).first()
        if reminder is None:
            return
        reminder.status = "failed"
        reminder.last_error = safe_reason
        reminder.next_attempt_at = (
            now + timedelta(seconds=config.reminder_retry_delay_seconds)
            if reminder.attempt_count < config.reminder_max_attempts
            else None
        )
        reminder.updated_at = now
        logger.warning(
            "Reminder failed id=%s user_id=%s attempt=%s retry=%s",
            reminder_id, user_id, reminder.attempt_count, reminder.next_attempt_at is not None,
        )


def deliver_reminder(reminder_id: int, *, session_factory=None) -> bool:
    """Dispatch a claimed reminder, then persist sent/failed state."""
    session_factory = _session_factory(session_factory)
    with session_factory() as db:
        reminder = db.query(Reminder).filter(
            Reminder.id == reminder_id,
            Reminder.status == "processing",
        ).first()
        if reminder is None:
            return False
        user_id = reminder.user_id
        task = db.query(Task).filter(Task.id == reminder.task_id, Task.user_id == user_id).first()
        if task is None:
            _mark_failed(reminder_id, user_id, "associated task was not found", session_factory=session_factory)
            return False
        message = json.dumps({
            "protocol_version": 1,
            "type": "notification",
            "event_id": f"reminder:{reminder.id}",
            "created_at": utc_now().isoformat(),
            "data": {
                "kind": "reminder",
                "reminder_id": reminder.id,
                "task_id": task.id,
                "task": task.title,
            },
        })

    if not manager.broadcast_sync(message, user_id):
        _mark_failed(reminder_id, user_id, "no active notification connection", session_factory=session_factory)
        return False

    now = utc_now()
    with session_scope(session_factory) as db:
        result = db.execute(
            update(Reminder)
            .where(
                Reminder.id == reminder_id,
                Reminder.user_id == user_id,
                Reminder.status == "processing",
            )
            .values(status="sent", next_attempt_at=None, last_error=None, updated_at=now)
        )
        sent = result.rowcount == 1
    if sent:
        logger.info("Reminder sent id=%s user_id=%s", reminder_id, user_id)
    return sent


def process_due_reminders(*, session_factory=None, now: datetime | None = None) -> int:
    session_factory = _session_factory(session_factory)
    global last_scheduler_tick
    now = now or utc_now()
    last_scheduler_tick = now
    recover_stale_reminders(session_factory=session_factory, now=now)
    with session_factory() as db:
        ids = [row[0] for row in db.query(Reminder.id).filter(
            Reminder.status.in_(["pending", "failed"]),
            Reminder.reminder_time <= now,
            Reminder.attempt_count < config.reminder_max_attempts,
            or_(Reminder.next_attempt_at.is_(None), Reminder.next_attempt_at <= now),
        ).order_by(Reminder.reminder_time).limit(100).all()]
    processed = 0
    for reminder_id in ids:
        if claim_due_reminder(reminder_id, session_factory=session_factory, now=now):
            deliver_reminder(reminder_id, session_factory=session_factory)
            processed += 1
    return processed


def schedule_reminder(task_id: int, user_id: int, reminder_time: datetime):
    """Compatibility hook: durable reminders are discovered by the poller."""
    try:
        start_scheduler()
    except RuntimeError:
        logger.warning("Reminder poller unavailable; reminder remains durable in SQLite")


def start_scheduler():
    active_scheduler = _get_scheduler()
    if active_scheduler.running:
        return
    active_scheduler.add_job(
        process_due_reminders,
        "interval",
        seconds=config.reminder_poll_interval_seconds,
        id="aura-reminder-poller",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    active_scheduler.start()
    logger.info("Reminder scheduler started interval_seconds=%s", config.reminder_poll_interval_seconds)


def stop_scheduler():
    global scheduler
    if scheduler is not None and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Reminder scheduler stopped")
    scheduler = None
