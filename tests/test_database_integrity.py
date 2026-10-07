from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    Base,
    UTCDateTime,
    get_development_user_id,
    session_scope,
    utc_now,
)
from backend.app.models.sql_models import (
    ChatHistory,
    Document,
    Reminder,
    RoutineEvent,
    Task,
    User,
)


@pytest.fixture
def db_session(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    session.add_all([User(name="A"), User(name="B")])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_isolated_database_uses_temp_path_and_multiple_users_are_separate(db_session):
    user_a, user_b = db_session.query(User).order_by(User.id).all()
    db_session.add_all(
        [
            Task(title="A task", user_id=user_a.id),
            Task(title="B task", user_id=user_b.id),
            ChatHistory(user_id=user_a.id, role="user", content="A message"),
            Document(user_id=user_b.id, filename="same.txt", content="B", file_type="text/plain"),
        ]
    )
    db_session.commit()

    assert [task.title for task in db_session.query(Task).filter_by(user_id=user_a.id)] == ["A task"]
    assert db_session.query(Task).filter_by(user_id=user_a.id).count() == 1
    assert db_session.query(Document).filter_by(user_id=user_a.id).count() == 0
    assert get_development_user_id(db_session) == user_a.id


def test_transaction_rolls_back_partial_mutation(db_session):
    factory = db_session.get_bind()

    def local_factory():
        return db_session.__class__(bind=factory, autoflush=False, expire_on_commit=False)

    with pytest.raises(RuntimeError), session_scope(local_factory) as session:
        session.add(Task(title="not committed", user_id=1))
        raise RuntimeError("fail unit of work")

    assert db_session.query(Task).filter_by(title="not committed").count() == 0

    with session_scope(local_factory) as session:
        session.add(Task(title="committed", user_id=1))

    assert db_session.query(Task).filter_by(title="committed").count() == 1


def test_foreign_keys_and_task_constraints_are_database_enforced(db_session):
    with pytest.raises(IntegrityError):
        db_session.add(Task(title="orphan", user_id=999))
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(Task(title="bad duration", user_id=1, duration_minutes=0))
        db_session.commit()
    db_session.rollback()

    with pytest.raises(IntegrityError):
        db_session.add(Task(title="bad priority", user_id=1, priority="critical"))
        db_session.commit()
    db_session.rollback()


def test_task_completion_and_recurrence_invariants(db_session):
    task = Task(
        title="completed",
        user_id=1,
        completed=True,
        completed_at=utc_now(),
        recurring="weekly",
    )
    db_session.add(task)
    db_session.commit()
    assert task.completed_at.tzinfo == timezone.utc

    db_session.add(Task(title="bad recurrence", user_id=1, recurring="hourly"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_routines_reminders_documents_and_cascades(db_session):
    user = db_session.query(User).first()
    task = Task(title="owned", user_id=user.id)
    db_session.add(task)
    db_session.flush()
    reminder = Reminder(
        user_id=user.id,
        task_id=task.id,
        reminder_time=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    event = RoutineEvent(
        user_id=user.id,
        title="work",
        event_type="work",
        start_time="09:00",
        duration_minutes=60,
        days_of_week="0,1,2,3,4",
    )
    first = Document(user_id=user.id, filename="notes.txt", content="one", file_type="text/plain")
    second = Document(user_id=user.id, filename="notes.txt", content="two", file_type="text/plain")
    db_session.add_all([reminder, event, first, second])
    db_session.commit()

    assert reminder.status == "pending"
    assert reminder.reminder_time.tzinfo == timezone.utc
    assert first.id != second.id
    assert first.indexing_state == "pending"

    db_session.delete(user)
    db_session.commit()
    assert db_session.query(Task).count() == 0
    assert db_session.query(Reminder).count() == 0
    assert db_session.query(RoutineEvent).count() == 0
    assert db_session.query(Document).count() == 0


def test_utc_datetime_type_normalizes_naive_legacy_values():
    type_ = UTCDateTime()
    value = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None)
    normalized = type_.process_bind_param(value, None)
    assert normalized.tzinfo is None
    restored = type_.process_result_value(normalized, None)
    assert restored.tzinfo == timezone.utc
    assert restored.hour == 12
