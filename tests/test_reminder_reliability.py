import asyncio
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.app.config import config
from backend.app.models.pydantic_models import ReminderCreate
from backend.app.models.sql_models import Base, Reminder, Task, User
from backend.app.services import reminder_service
from backend.app.services.ai_actions import ActionRejected, execute_action, parse_action
from backend.app.websocket_manager import ConnectionManager


class FakeSocket:
    def __init__(self, *, failure=None, delay=0):
        self.failure = failure
        self.delay = delay
        self.messages = []

    async def accept(self):
        return None

    async def send_text(self, message):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.failure:
            raise self.failure
        self.messages.append(message)


@pytest.fixture
def running_manager(monkeypatch):
    manager = ConnectionManager()
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    manager.set_loop(loop)
    monkeypatch.setattr(config, "reminder_delivery_timeout_seconds", 0.05)
    yield manager
    asyncio.run_coroutine_threadsafe(manager.shutdown(), loop).result(timeout=1)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=1)
    loop.close()


def connect_fake(manager, socket, user_id):
    asyncio.run_coroutine_threadsafe(
        manager.connect(socket, user_id), manager.loop
    ).result(timeout=1)


def test_websocket_dispatch_requires_actual_success(running_manager):
    assert not running_manager.broadcast_sync("message", 1)
    good = FakeSocket()
    bad = FakeSocket(failure=RuntimeError("closed"))
    connect_fake(running_manager, good, 1)
    connect_fake(running_manager, bad, 1)
    assert running_manager.broadcast_sync("message", 1)
    assert good.messages == ["message"]
    assert bad not in running_manager.connection_users


def test_websocket_dispatch_failure_and_timeout_return_false(running_manager):
    failed = FakeSocket(failure=RuntimeError("send failed"))
    connect_fake(running_manager, failed, 2)
    assert not running_manager.broadcast_sync("message", 2)
    assert failed not in running_manager.connection_users

    slow = FakeSocket(delay=1)
    connect_fake(running_manager, slow, 3)
    assert not running_manager.broadcast_sync("message", 3)


def test_slow_connection_does_not_block_healthy_connection(running_manager):
    slow = FakeSocket(delay=1)
    healthy = FakeSocket()
    connect_fake(running_manager, slow, 4)
    connect_fake(running_manager, healthy, 4)
    assert running_manager.broadcast_sync("message", 4)
    assert healthy.messages == ["message"]
    threading.Event().wait(0.1)
    assert slow not in running_manager.connection_users


def test_outbound_queue_is_bounded_and_disconnect_cleans_items(running_manager, monkeypatch):
    monkeypatch.setattr(config, "websocket_outbound_queue_size", 1)
    slow = FakeSocket(delay=1)
    connect_fake(running_manager, slow, 5)
    state = running_manager._states[slow]
    assert state.queue.maxsize == 1
    assert running_manager.broadcast_sync("first", 5) is False
    running_manager.disconnect(slow)
    assert slow not in running_manager.connection_users
    assert state.queue.empty()


@pytest.fixture
def reminder_db(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'reminders.db'}", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        user = User(name="Reminder User", login_identifier="reminder@example.com")
        db.add(user)
        db.flush()
        task = Task(user_id=user.id, title="Important task", tags="[]")
        db.add(task)
        db.flush()
        reminder = Reminder(
            user_id=user.id,
            task_id=task.id,
            reminder_time=datetime.now(timezone.utc) - timedelta(minutes=1),
            timezone="UTC",
        )
        db.add(reminder)
        db.commit()
        reminder_id = reminder.id
    yield factory, reminder_id
    engine.dispose()


def test_atomic_claim_only_one_worker_wins(reminder_db):
    factory, reminder_id = reminder_db
    now = datetime.now(timezone.utc)
    assert reminder_service.claim_due_reminder(reminder_id, session_factory=factory, now=now)
    assert not reminder_service.claim_due_reminder(reminder_id, session_factory=factory, now=now)
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        assert reminder.status == "processing"
        assert reminder.attempt_count == 1


def test_successful_delivery_marks_sent_with_stable_identity(reminder_db, monkeypatch):
    factory, reminder_id = reminder_db
    assert reminder_service.claim_due_reminder(reminder_id, session_factory=factory)
    messages = []
    monkeypatch.setattr(
        reminder_service.manager,
        "broadcast_sync",
        lambda message, user_id: messages.append((message, user_id)) or True,
    )
    assert reminder_service.deliver_reminder(reminder_id, session_factory=factory)
    with factory() as db:
        assert db.get(Reminder, reminder_id).status == "sent"
    assert str(reminder_id) in messages[0][0]


def test_failed_delivery_is_retryable_and_bounded(reminder_db, monkeypatch):
    factory, reminder_id = reminder_db
    monkeypatch.setattr(config, "reminder_max_attempts", 2)
    monkeypatch.setattr(reminder_service.manager, "broadcast_sync", lambda *_: False)
    assert reminder_service.process_due_reminders(session_factory=factory) == 1
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        assert reminder.status == "failed"
        assert reminder.attempt_count == 1
        assert reminder.next_attempt_at is not None
        reminder.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert reminder_service.process_due_reminders(session_factory=factory) == 1
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        assert reminder.status == "failed"
        assert reminder.attempt_count == 2
        assert reminder.next_attempt_at is None


def test_stale_processing_is_recovered(reminder_db, monkeypatch):
    factory, reminder_id = reminder_db
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        reminder.status = "processing"
        reminder.attempt_count = 1
        reminder.last_attempt_at = old
        db.commit()
    monkeypatch.setattr(config, "reminder_processing_timeout_seconds", 60)
    assert reminder_service.recover_stale_reminders(session_factory=factory) == 1
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        assert reminder.status == "failed"
        assert reminder.next_attempt_at is not None


def test_cancelled_reminder_is_never_claimed(reminder_db):
    factory, reminder_id = reminder_db
    with factory() as db:
        reminder = db.get(Reminder, reminder_id)
        reminder.status = "cancelled"
        db.commit()
    assert not reminder_service.claim_due_reminder(reminder_id, session_factory=factory)
    assert reminder_service.process_due_reminders(session_factory=factory) == 0


def test_llm_cancellation_uses_same_state_rules(reminder_db):
    factory, reminder_id = reminder_db
    with factory() as db:
        user_id = db.query(User.id).one()[0]
        action = parse_action({"action": "cancel_reminder", "reminder_id": reminder_id})
        result = execute_action(action, user_id=user_id, db=db, confirmed=True)
        db.commit()
        assert result["reminder_id"] == reminder_id
        reminder = db.get(Reminder, reminder_id)
        assert reminder.status == "cancelled"
        assert execute_action(action, user_id=user_id, db=db, confirmed=True)["already_cancelled"]

        reminder.status = "processing"
        db.commit()
        with pytest.raises(ActionRejected, match="current state"):
            execute_action(action, user_id=user_id, db=db, confirmed=True)


@pytest.mark.parametrize(
    "value",
    [
        "2030-01-01T10:00:00+00:00",
        "2030-01-01T10:00:00+05:30",
        "2030-07-01T10:00:00-04:00",
    ],
)
def test_reminder_input_requires_aware_time_and_valid_zone(value):
    reminder = ReminderCreate(task_id=1, reminder_time=value, timezone="Asia/Kolkata")
    assert reminder.reminder_time.tzinfo == timezone.utc


def test_naive_or_invalid_reminder_input_is_rejected():
    with pytest.raises(ValueError):
        ReminderCreate(task_id=1, reminder_time="2030-01-01T10:00:00")
    with pytest.raises(ValueError):
        ReminderCreate(
            task_id=1,
            reminder_time="2030-01-01T10:00:00Z",
            timezone="Not/AZone",
        )
