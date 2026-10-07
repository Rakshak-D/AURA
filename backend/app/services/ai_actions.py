"""Strict, server-owned action contracts for LLM-assisted operations."""

import json
from datetime import datetime, timezone
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from sqlalchemy import update
from sqlalchemy.orm import Session

from ..database import utc_now
from ..models.sql_models import Reminder, Task, User


class StrictAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CreateTaskAction(StrictAction):
    action: Literal["create_task"]
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: datetime | None = None
    duration_minutes: int = Field(default=30, ge=1, le=1440)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    category: str = Field(default="Personal", min_length=1, max_length=50)
    recurring: Literal["daily", "weekly", "monthly"] | None = None


class UpdateTaskAction(StrictAction):
    action: Literal["update_task"]
    task_id: int = Field(gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    due_date: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    recurring: Literal["daily", "weekly", "monthly"] | None = None


class CompleteTaskAction(StrictAction):
    action: Literal["complete_task"]
    task_id: int = Field(gt=0)


class DeleteTaskAction(StrictAction):
    action: Literal["delete_task"]
    task_id: int = Field(gt=0)


class CreateReminderAction(StrictAction):
    action: Literal["create_reminder"]
    task_id: int = Field(gt=0)
    reminder_time: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @field_validator("reminder_time")
    @classmethod
    def aware_reminder_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reminder_time must include a timezone offset")
        return value.astimezone(timezone.utc)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid timezone") from exc
        return value


class CancelReminderAction(StrictAction):
    action: Literal["cancel_reminder"]
    reminder_id: int = Field(gt=0)


class UpdateSettingsAction(StrictAction):
    action: Literal["update_settings"]
    username: str | None = Field(default=None, min_length=1, max_length=100)


class SearchDocumentsAction(StrictAction):
    action: Literal["search_documents"]
    query: str = Field(min_length=1, max_length=1000)


class SummarizeDocumentsAction(StrictAction):
    action: Literal["summarize_documents"]
    query: str = Field(default="", max_length=1000)


AIAction = Annotated[
    CreateTaskAction
    | UpdateTaskAction
    | CompleteTaskAction
    | DeleteTaskAction
    | CreateReminderAction
    | CancelReminderAction
    | UpdateSettingsAction
    | SearchDocumentsAction
    | SummarizeDocumentsAction,
    Field(discriminator="action"),
]
ACTION_ADAPTER = TypeAdapter(AIAction)


class ActionRejected(ValueError):
    """A proposed action was invalid or unauthorized."""


class ConfirmationRequired(ActionRejected):
    """A destructive action requires explicit user confirmation."""


def parse_json_object(raw: str, *, max_chars: int = 8000) -> dict:
    if not isinstance(raw, str) or len(raw) > max_chars:
        raise ActionRejected("model output is too large")
    text = raw.strip()
    if text.startswith("```"):
        try:
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        except IndexError as exc:
            raise ActionRejected("malformed action JSON") from exc
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ActionRejected("malformed action JSON") from exc
    if not isinstance(value, dict):
        raise ActionRejected("action must be a JSON object")
    return value


def parse_action(value: dict | str) -> AIAction:
    payload = parse_json_object(value) if isinstance(value, str) else value
    try:
        return ACTION_ADAPTER.validate_python(payload)
    except ValidationError as exc:
        raise ActionRejected("invalid or unsupported action") from exc


def _owned_task(db: Session, user_id: int, task_id: int) -> Task:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if task is None:
        raise ActionRejected("owned task was not found")
    return task


def _owned_reminder(db: Session, user_id: int, reminder_id: int) -> Reminder:
    reminder = (
        db.query(Reminder)
        .filter(Reminder.id == reminder_id, Reminder.user_id == user_id)
        .first()
    )
    if reminder is None:
        raise ActionRejected("owned reminder was not found")
    return reminder


def execute_action(
    action: AIAction, *, user_id: int, db: Session, confirmed: bool = False
) -> dict:
    if isinstance(action, CreateTaskAction):
        task = Task(
            user_id=user_id,
            title=action.title,
            description=action.description,
            due_date=action.due_date,
            duration_minutes=action.duration_minutes,
            priority=action.priority,
            category=action.category,
            recurring=action.recurring,
            tags="[]",
        )
        db.add(task)
        db.flush()
        return {"action": action.action, "task_id": task.id, "title": task.title}

    if isinstance(action, UpdateTaskAction):
        task = _owned_task(db, user_id, action.task_id)
        for field in (
            "title",
            "description",
            "due_date",
            "duration_minutes",
            "priority",
            "recurring",
        ):
            value = getattr(action, field)
            if value is not None:
                setattr(task, field, value)
        task.updated_at = utc_now()
        db.flush()
        return {"action": action.action, "task_id": task.id}

    if isinstance(action, CompleteTaskAction):
        task = _owned_task(db, user_id, action.task_id)
        task.completed = True
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        db.flush()
        return {"action": action.action, "task_id": task.id}

    if isinstance(action, DeleteTaskAction):
        if not confirmed:
            raise ConfirmationRequired("deleting a task requires confirmation")
        task = _owned_task(db, user_id, action.task_id)
        db.delete(task)
        db.flush()
        return {"action": action.action, "task_id": action.task_id}

    if isinstance(action, CreateReminderAction):
        task = _owned_task(db, user_id, action.task_id)
        reminder = Reminder(
            user_id=user_id,
            task_id=task.id,
            reminder_time=action.reminder_time,
            timezone=action.timezone,
            status="pending",
        )
        db.add(reminder)
        db.flush()
        return {"action": action.action, "reminder_id": reminder.id, "task_id": task.id}

    if isinstance(action, CancelReminderAction):
        if not confirmed:
            raise ConfirmationRequired("cancelling a reminder requires confirmation")
        result = db.execute(
            update(Reminder)
            .where(
                Reminder.id == action.reminder_id,
                Reminder.user_id == user_id,
                Reminder.status.in_(["pending", "failed"]),
            )
            .values(status="cancelled", updated_at=utc_now())
        )
        if result.rowcount == 1:
            db.flush()
            return {"action": action.action, "reminder_id": action.reminder_id}
        reminder = _owned_reminder(db, user_id, action.reminder_id)
        if reminder.status == "cancelled":
            return {"action": action.action, "reminder_id": reminder.id, "already_cancelled": True}
        raise ActionRejected("reminder cannot be cancelled in its current state")

    if isinstance(action, UpdateSettingsAction):
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ActionRejected("authenticated user was not found")
        if action.username is not None:
            user.name = action.username
        db.flush()
        return {"action": action.action, "updated": ["username"]}

    if isinstance(action, (SearchDocumentsAction, SummarizeDocumentsAction)):
        return {"action": action.action, "query": action.query}
    raise ActionRejected("action is not registered")


ACTION_REGISTRY = {
    name: execute_action
    for name in (
        "create_task",
        "update_task",
        "complete_task",
        "delete_task",
        "create_reminder",
        "cancel_reminder",
        "update_settings",
        "search_documents",
        "summarize_documents",
    )
}
