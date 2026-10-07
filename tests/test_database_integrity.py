from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend.app.database import (
    REQUIRED_SCHEMA_VERSION,
    Base,
    UTCDateTime,
    _apply_schema_migrations,
    schema_status,
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


@pytest.mark.parametrize(
    "completed, completed_at",
    [(False, utc_now()), (True, None)],
)
def test_both_invalid_task_completion_states_are_rejected(db_session, completed, completed_at):
    db_session.add(
        Task(
            title="invalid completion",
            user_id=1,
            completed=completed,
            completed_at=completed_at,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_composite_ownership_foreign_keys_reject_cross_user_links(db_session):
    user_a, user_b = db_session.query(User).order_by(User.id).all()
    parent = Task(title="A parent", user_id=user_a.id)
    other = Task(title="B task", user_id=user_b.id)
    db_session.add_all([parent, other])
    db_session.commit()

    db_session.add(Reminder(user_id=user_b.id, task_id=parent.id, reminder_time=utc_now()))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(Task(title="B child", user_id=user_b.id, parent_task_id=parent.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_same_user_relationships_and_authoritative_reminder_status(db_session):
    user = db_session.query(User).first()
    parent = Task(title="parent", user_id=user.id)
    db_session.add(parent)
    db_session.flush()
    child = Task(title="child", user_id=user.id, parent_task_id=parent.id)
    reminder = Reminder(user_id=user.id, task_id=parent.id, reminder_time=utc_now())
    db_session.add_all([child, reminder])
    db_session.commit()

    assert child.parent_task_id == parent.id
    assert reminder.status == "pending"
    reminder.status = "sent"
    db_session.commit()
    assert reminder.status == "sent"
    assert "sent" not in {column["name"] for column in __import__("sqlalchemy").inspect(db_session.get_bind()).get_columns("reminders")}


def _create_legacy_database(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100), preferences TEXT, settings JSON, created_at DATETIME)")
        connection.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY, title VARCHAR(200), description TEXT, due_date DATETIME, completed BOOLEAN, priority VARCHAR(20), category VARCHAR(50), duration_minutes INTEGER, is_flexible BOOLEAN, conflict_flag BOOLEAN, tags TEXT, recurring VARCHAR(50), recurring_end_date DATETIME, parent_task_id INTEGER, user_id INTEGER, created_at DATETIME, updated_at DATETIME, completed_at DATETIME, FOREIGN KEY(parent_task_id) REFERENCES tasks(id), FOREIGN KEY(user_id) REFERENCES users(id))")
        connection.exec_driver_sql("CREATE TABLE reminders (id INTEGER PRIMARY KEY, task_id INTEGER, user_id INTEGER, reminder_time DATETIME, status VARCHAR(20), sent BOOLEAN, created_at DATETIME, FOREIGN KEY(task_id) REFERENCES tasks(id), FOREIGN KEY(user_id) REFERENCES users(id))")
        connection.exec_driver_sql("CREATE TABLE documents (id INTEGER PRIMARY KEY, user_id INTEGER, filename VARCHAR(200), content TEXT, file_type VARCHAR(50), uploaded_at DATETIME, FOREIGN KEY(user_id) REFERENCES users(id))")
        connection.exec_driver_sql("CREATE TABLE chat_history (id INTEGER PRIMARY KEY, user_id INTEGER, role VARCHAR(20), content TEXT, intent VARCHAR(50), meta_data JSON, timestamp DATETIME)")
        connection.exec_driver_sql("CREATE TABLE routine_events (id INTEGER PRIMARY KEY, title VARCHAR, event_type VARCHAR, start_time VARCHAR, duration_minutes INTEGER, days_of_week VARCHAR, user_id INTEGER)")
        connection.exec_driver_sql("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        connection.exec_driver_sql("INSERT INTO schema_version(version) VALUES (1)")
        connection.exec_driver_sql("INSERT INTO users VALUES (1,'A','{}','{}','2026-01-01 00:00:00'), (2,'B','{}','{}','2026-01-01 00:00:00')")
        connection.exec_driver_sql("INSERT INTO tasks VALUES (10,'parent',NULL,NULL,0,'medium','Personal',30,0,0,'[]',NULL,NULL,NULL,1,'2026-01-01','2026-01-01',NULL), (11,'cross child',NULL,NULL,0,'medium','Personal',30,0,0,'[]',NULL,NULL,10,2,'2026-01-01','2026-01-01',NULL), (12,'completed',NULL,NULL,1,'medium','Personal',30,0,0,'[]',NULL,NULL,NULL,1,'2026-01-01','2026-01-01',NULL)")
        connection.exec_driver_sql("INSERT INTO reminders VALUES (20,10,2,'2026-01-02 00:00:00','pending',0,'2026-01-01 00:00:00')")
        connection.exec_driver_sql("INSERT INTO documents VALUES (30,2,'notes.txt','data','text/plain','2026-01-01 00:00:00')")


def test_legacy_migration_preserves_data_enforces_constraints_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    _create_legacy_database(engine)
    _apply_schema_migrations(engine)

    with engine.connect() as connection:
        assert connection.execute(text("SELECT version FROM schema_version")).scalar() == REQUIRED_SCHEMA_VERSION
        assert connection.execute(text("SELECT COUNT(*) FROM tasks")).scalar() == 3
        assert connection.execute(text("SELECT COUNT(*) FROM reminders")).scalar() == 1
        assert connection.execute(text("SELECT user_id FROM reminders WHERE id=20")).scalar() == 1
        assert connection.execute(text("SELECT parent_task_id FROM tasks WHERE id=11")).scalar() is None
        assert connection.execute(text("SELECT completed_at IS NOT NULL FROM tasks WHERE id=12")).scalar() == 1
        assert "sent" not in {column["name"] for column in __import__("sqlalchemy").inspect(engine).get_columns("reminders")}
        assert {"attempt_count", "last_attempt_at", "next_attempt_at", "last_error"}.issubset(
            {column["name"] for column in __import__("sqlalchemy").inspect(engine).get_columns("reminders")}
        )
        reminder_sql = connection.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='reminders'")
        ).scalar().lower()
        assert "processing" in reminder_sql
        assert "attempt_count >= 0" in reminder_sql
        assert {"login_identifier", "password_hash", "is_active"}.issubset(
            {column["name"] for column in __import__("sqlalchemy").inspect(engine).get_columns("users")}
        )

    assert schema_status(engine)["ready"] is True
    _apply_schema_migrations(engine)
    assert schema_status(engine)["ready"] is True
    engine.dispose()


def test_schema_readiness_rejects_incomplete_schema(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'incomplete.db'}")
    Base.metadata.create_all(engine)
    assert schema_status(engine)["ready"] is False
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        connection.exec_driver_sql("INSERT INTO schema_version VALUES (1)")
    assert schema_status(engine)["ready"] is False
    engine.dispose()


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
