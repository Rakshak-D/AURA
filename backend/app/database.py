import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import DateTime, TypeDecorator

from .config import config

Base = declarative_base()
logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return an aware UTC instant for persisted timestamps."""
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Store UTC consistently on databases, including SQLite."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            # Legacy callers supplied naive values; interpret those as UTC while
            # making the persisted policy explicit and deterministic.
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)

# Database Connection
# For SQLite we keep a single file-based database with check_same_thread disabled
# so sessions can be used across FastAPI workers safely.
engine = create_engine(
    config.resolved_database_url,
    connect_args={"check_same_thread": False} if config.resolved_database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if engine.url.get_backend_name() == "sqlite":
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
REQUIRED_SCHEMA_VERSION = 4

_chroma_client = None
_collection = None


class DatabaseIntegrityError(RuntimeError):
    """Raised when required database state is missing or inconsistent."""


@contextmanager
def session_scope(session_factory=SessionLocal) -> Iterator:
    """Run a unit of database work with explicit commit/rollback/close."""
    db = session_factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_chroma_collection():
    """Initialize Chroma only when a RAG/search feature explicitly needs it."""
    global _chroma_client, _collection
    if _collection is not None:
        return _collection
    try:
        import chromadb
    except ImportError as exc:
        raise RuntimeError(
            "ChromaDB is not installed. Install the optional RAG dependencies to use document search."
        ) from exc
    try:
        _chroma_client = chromadb.PersistentClient(path=str(config.chroma_path))
        _collection = _chroma_client.get_or_create_collection(name="documents")
        return _collection
    except Exception as exc:
        logger.exception("ChromaDB initialization failed")
        raise RuntimeError("ChromaDB could not be initialized; check the vector-store configuration.") from exc


def reset_chroma_for_tests() -> None:
    global _chroma_client, _collection
    _chroma_client = None
    _collection = None

def init_db():
    """Initialize database with tables and default data"""
    # Import models here to ensure they are registered with Base.metadata
    from .models import sql_models as _sql_models
    User = _sql_models.User
    
    Base.metadata.create_all(engine)
    
    # Create default user if not exists
    db = SessionLocal()
    try:
        if not db.query(User).first():
            user = User(
                name="User", 
                preferences='{}',
                settings={
                    'theme': 'light',
                    'notifications_enabled': True,
                    'default_reminder_time': '09:00'
                }
            )
            db.add(user)
            db.commit()
            logger.info("Default user created")
    except Exception:
        logger.exception("Error creating default user")
        db.rollback()
    finally:
        db.close()
    _apply_schema_migrations()

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _table_columns(connection, table: str) -> set[str]:
    from sqlalchemy import inspect

    return {column["name"] for column in inspect(connection).get_columns(table)}


def _apply_schema_migrations(target_engine=engine) -> None:
    """Upgrade SQLite schemas transactionally to the enforced Phase 2 model."""
    if target_engine.url.get_backend_name() != "sqlite":
        return

    from sqlalchemy import text

    with target_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        connection.commit()
        transaction = connection.begin()
        try:
            connection.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"))
            if connection.execute(text("SELECT COUNT(*) FROM schema_version")).scalar() == 0:
                connection.execute(text("INSERT INTO schema_version(version) VALUES (0)"))
            version = connection.execute(text("SELECT version FROM schema_version LIMIT 1")).scalar() or 0
            if version >= REQUIRED_SCHEMA_VERSION:
                if not schema_status(target_engine)["ready"]:
                    raise DatabaseIntegrityError("Database schema version is marked complete but validation failed")
                transaction.commit()
                return

            existing_missing = schema_status(target_engine)["missing"]
            if version == 0 and all(item in {"table:schema_version", "schema_version"} for item in existing_missing):
                connection.execute(text("UPDATE schema_version SET version = :version"), {"version": REQUIRED_SCHEMA_VERSION})
                transaction.commit()
                return

            first_user = connection.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
            if first_user is None:
                raise DatabaseIntegrityError("Cannot migrate an ownership schema without a user")

            _rebuild_tasks(connection, first_user)
            _rebuild_reminders(connection, first_user)
            _rebuild_documents(connection, first_user)
            _create_integrity_indexes(connection)
            _migrate_user_authentication(connection)
            connection.execute(text("UPDATE schema_version SET version = :version"), {"version": REQUIRED_SCHEMA_VERSION})
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise
        finally:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")

    result = schema_status(target_engine)
    if not result["ready"]:
        raise DatabaseIntegrityError("Database migration completed without a valid authentication schema")


def _rebuild_tasks(connection, first_user: int) -> None:
    from sqlalchemy import text

    if "tasks" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}:
        return
    if "tasks_legacy" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and _table_has_sql(connection, "tasks", "fk_tasks_parent_same_user"):
        return
    if "tasks_legacy" in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and _table_has_sql(connection, "tasks", "fk_tasks_parent_same_user"):
        if connection.execute(text("SELECT COUNT(*) FROM tasks_legacy")).scalar() != connection.execute(text("SELECT COUNT(*) FROM tasks")).scalar():
            raise DatabaseIntegrityError("Unfinished task migration contains data that cannot be safely discarded")
        connection.execute(text("DROP TABLE tasks_legacy"))
        return
    columns = _table_columns(connection, "tasks")
    connection.execute(text("ALTER TABLE tasks RENAME TO tasks_legacy"))
    connection.exec_driver_sql(
        """CREATE TABLE tasks (
            id INTEGER PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            due_date DATETIME,
            completed BOOLEAN NOT NULL DEFAULT 0,
            priority VARCHAR(20) NOT NULL DEFAULT 'medium',
            category VARCHAR(50) NOT NULL DEFAULT 'Personal',
            duration_minutes INTEGER NOT NULL DEFAULT 30,
            is_flexible BOOLEAN NOT NULL DEFAULT 0,
            conflict_flag BOOLEAN NOT NULL DEFAULT 0,
            tags TEXT NOT NULL DEFAULT '[]',
            recurring VARCHAR(50),
            recurring_end_date DATETIME,
            parent_task_id INTEGER,
            user_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            completed_at DATETIME,
            CONSTRAINT ck_tasks_duration_positive CHECK (duration_minutes > 0),
            CONSTRAINT ck_tasks_priority CHECK (priority IN ('low', 'medium', 'high', 'urgent')),
            CONSTRAINT ck_tasks_completion_time CHECK ((completed = 0 AND completed_at IS NULL) OR (completed = 1 AND completed_at IS NOT NULL)),
            CONSTRAINT ck_tasks_recurring CHECK (recurring IS NULL OR recurring IN ('daily', 'weekly', 'monthly')),
            CONSTRAINT uq_tasks_id_user UNIQUE (id, user_id),
            CONSTRAINT fk_tasks_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_tasks_parent_same_user FOREIGN KEY (parent_task_id, user_id) REFERENCES tasks(id, user_id) ON DELETE CASCADE
        )"""
    )
    def col(name, fallback):
        return f't."{name}"' if name in columns else fallback
    connection.execute(text(f"""INSERT INTO tasks
        (id,title,description,due_date,completed,priority,category,duration_minutes,is_flexible,conflict_flag,tags,recurring,recurring_end_date,parent_task_id,user_id,created_at,updated_at,completed_at)
        SELECT t.id, COALESCE(t.title, ''), t.description, {col('due_date', 'NULL')},
            CASE WHEN COALESCE(t.completed, 0) <> 0 THEN 1 ELSE 0 END,
            CASE WHEN {col('priority', "'medium'")} IN ('low','medium','high','urgent') THEN {col('priority', "'medium'")} ELSE 'medium' END,
            COALESCE({col('category', "'Personal'")}, 'Personal'),
            CASE WHEN COALESCE({col('duration_minutes', '30')}, 30) > 0 THEN COALESCE({col('duration_minutes', '30')}, 30) ELSE 30 END,
            COALESCE({col('is_flexible', '0')}, 0), COALESCE({col('conflict_flag', '0')}, 0), COALESCE({col('tags', "'[]'")}, '[]'),
            CASE WHEN {col('recurring', 'NULL')} IN ('daily','weekly','monthly') THEN {col('recurring', 'NULL')} ELSE NULL END,
            {col('recurring_end_date', 'NULL')},
            CASE WHEN p.id IS NOT NULL AND p.user_id = COALESCE(t.user_id, :first_user) THEN t.parent_task_id ELSE NULL END,
            COALESCE(u.id, :first_user), COALESCE({col('created_at', 'CURRENT_TIMESTAMP')}, CURRENT_TIMESTAMP),
            COALESCE({col('updated_at', col('created_at', 'CURRENT_TIMESTAMP'))}, CURRENT_TIMESTAMP),
            CASE WHEN COALESCE(t.completed, 0) <> 0 THEN COALESCE({col('completed_at', 'NULL')}, {col('updated_at', col('created_at', 'CURRENT_TIMESTAMP'))}, CURRENT_TIMESTAMP) ELSE NULL END
        FROM tasks_legacy t
        LEFT JOIN users u ON u.id = t.user_id
        LEFT JOIN tasks_legacy p ON p.id = t.parent_task_id"""), {"first_user": first_user})
    connection.execute(text("DROP TABLE tasks_legacy"))


def _rebuild_reminders(connection, first_user: int) -> None:
    from sqlalchemy import text

    if "reminders" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}:
        return
    reminder_schema_complete = (
        _table_has_sql(connection, "reminders", "fk_reminders_task_same_user")
        and _table_has_sql(connection, "reminders", "'processing'")
        and {"attempt_count", "last_attempt_at", "next_attempt_at", "last_error"}.issubset(
            _table_columns(connection, "reminders")
        )
    )
    if "reminders_legacy" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and reminder_schema_complete:
        return
    if "reminders_legacy" in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and reminder_schema_complete:
        if connection.execute(text("SELECT COUNT(*) FROM reminders_legacy")).scalar() != connection.execute(text("SELECT COUNT(*) FROM reminders")).scalar():
            raise DatabaseIntegrityError("Unfinished reminder migration contains data that cannot be safely discarded")
        connection.execute(text("DROP TABLE reminders_legacy"))
        return
    columns = _table_columns(connection, "reminders")
    if "status" in columns:
        legacy_sent = " WHEN COALESCE(r.sent,0) <> 0 THEN 'sent'" if "sent" in columns else ""
        status_expr = f"CASE WHEN r.status IN ('pending','processing','sent','cancelled','failed') THEN r.status{legacy_sent} ELSE 'pending' END"
    else:
        status_expr = "CASE WHEN COALESCE(r.sent,0) <> 0 THEN 'sent' ELSE 'pending' END" if "sent" in columns else "'pending'"
    user_expr = "COALESCE(t.user_id, u.id, :first_user)" if "user_id" in columns else "COALESCE(t.user_id, :first_user)"
    connection.execute(text("ALTER TABLE reminders RENAME TO reminders_legacy"))
    connection.exec_driver_sql(
        """CREATE TABLE reminders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            task_id INTEGER,
            reminder_time DATETIME NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            timezone VARCHAR(64) NOT NULL DEFAULT 'UTC',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_attempt_at DATETIME,
            next_attempt_at DATETIME,
            last_error VARCHAR(500),
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT ck_reminders_status CHECK (status IN ('pending','processing','sent','cancelled','failed')),
            CONSTRAINT ck_reminders_attempt_count CHECK (attempt_count >= 0),
            CONSTRAINT fk_reminders_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_reminders_task_same_user FOREIGN KEY (task_id, user_id) REFERENCES tasks(id, user_id) ON DELETE CASCADE
        )"""
    )
    def col(name, fallback):
        return f'r."{name}"' if name in columns else fallback
    connection.execute(text(f"""INSERT INTO reminders
        (id,user_id,task_id,reminder_time,status,timezone,attempt_count,last_attempt_at,next_attempt_at,last_error,created_at,updated_at)
        SELECT r.id, {user_expr}, CASE WHEN t.id IS NULL THEN NULL ELSE t.id END,
            r.reminder_time, {status_expr}, COALESCE({col('timezone', "'UTC'")}, 'UTC'),
            MAX(COALESCE({col('attempt_count', '0')}, 0), 0), {col('last_attempt_at', 'NULL')},
            {col('next_attempt_at', 'NULL')}, {col('last_error', 'NULL')},
            COALESCE({col('created_at', 'CURRENT_TIMESTAMP')}, CURRENT_TIMESTAMP),
            COALESCE({col('updated_at', col('created_at', 'CURRENT_TIMESTAMP'))}, CURRENT_TIMESTAMP)
        FROM reminders_legacy r
        LEFT JOIN tasks t ON t.id = r.task_id
        LEFT JOIN users u ON u.id = r.user_id"""), {"first_user": first_user})
    connection.execute(text("DROP TABLE reminders_legacy"))


def _rebuild_documents(connection, first_user: int) -> None:
    from sqlalchemy import text

    if "documents" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}:
        return
    if "documents_legacy" not in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and _table_has_sql(connection, "documents", "ck_documents_indexing_state"):
        return
    if "documents_legacy" in {row[0] for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))} and _table_has_sql(connection, "documents", "ck_documents_indexing_state"):
        if connection.execute(text("SELECT COUNT(*) FROM documents_legacy")).scalar() != connection.execute(text("SELECT COUNT(*) FROM documents")).scalar():
            raise DatabaseIntegrityError("Unfinished document migration contains data that cannot be safely discarded")
        connection.execute(text("DROP TABLE documents_legacy"))
        return
    columns = _table_columns(connection, "documents")
    connection.execute(text("ALTER TABLE documents RENAME TO documents_legacy"))
    connection.exec_driver_sql(
        """CREATE TABLE documents (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            filename VARCHAR(200) NOT NULL,
            stored_path VARCHAR(500),
            content TEXT NOT NULL,
            file_type VARCHAR(50) NOT NULL,
            indexing_state VARCHAR(20) NOT NULL DEFAULT 'pending',
            indexing_error TEXT,
            uploaded_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT ck_documents_indexing_state CHECK (indexing_state IN ('pending','indexed','failed')),
            CONSTRAINT fk_documents_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )"""
    )
    def col(name, fallback):
        return f'd."{name}"' if name in columns else fallback
    connection.execute(text(f"""INSERT INTO documents
        (id,user_id,filename,stored_path,content,file_type,indexing_state,indexing_error,uploaded_at,updated_at)
        SELECT d.id, COALESCE(u.id, :first_user), COALESCE(d.filename, 'unnamed'), {col('stored_path', 'NULL')},
            COALESCE(d.content, ''), COALESCE(d.file_type, 'application/octet-stream'),
            CASE WHEN {col('indexing_state', "'pending'")} IN ('pending','indexed','failed') THEN {col('indexing_state', "'pending'")} ELSE 'pending' END,
            {col('indexing_error', 'NULL')}, COALESCE({col('uploaded_at', 'CURRENT_TIMESTAMP')}, CURRENT_TIMESTAMP),
            COALESCE({col('updated_at', col('uploaded_at', 'CURRENT_TIMESTAMP'))}, CURRENT_TIMESTAMP)
        FROM documents_legacy d LEFT JOIN users u ON u.id = d.user_id"""), {"first_user": first_user})
    connection.execute(text("DROP TABLE documents_legacy"))


def _create_integrity_indexes(connection) -> None:
    for sql in (
        "CREATE INDEX IF NOT EXISTS ix_tasks_user_due ON tasks (user_id, due_date)",
        "CREATE INDEX IF NOT EXISTS ix_tasks_user_completed ON tasks (user_id, completed)",
        "CREATE INDEX IF NOT EXISTS ix_chat_history_user_timestamp ON chat_history (user_id, timestamp)",
        "CREATE INDEX IF NOT EXISTS ix_documents_user ON documents (user_id)",
        "CREATE INDEX IF NOT EXISTS ix_reminders_user_trigger ON reminders (user_id, reminder_time)",
    ):
        connection.exec_driver_sql(sql)


def _table_has_sql(connection, table: str, fragment: str) -> bool:
    row = connection.exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).first()
    return row is not None and fragment.lower() in (row[0] or "").lower()


def _migrate_user_authentication(connection) -> None:
    """Add credential columns without changing legacy user identity or data."""
    columns = _table_columns(connection, "users")
    if "login_identifier" not in columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN login_identifier VARCHAR(255)")
    if "password_hash" not in columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)")
    if "is_active" not in columns:
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_login_identifier ON users (login_identifier)"
    )


def schema_status(target_engine=engine) -> dict:
    """Validate the actual active SQLite schema, not only ORM declarations."""
    from sqlalchemy import inspect, text

    if target_engine.url.get_backend_name() != "sqlite":
        return {"ready": True, "version": REQUIRED_SCHEMA_VERSION, "missing": []}
    missing = []
    inspector = inspect(target_engine)
    tables = set(inspector.get_table_names())
    required_tables = {"users", "tasks", "reminders", "documents", "chat_history", "routine_events", "schema_version"}
    missing.extend(f"table:{table}" for table in sorted(required_tables - tables))
    version = None
    if "schema_version" in tables:
        with target_engine.connect() as connection:
            version = connection.execute(text("SELECT version FROM schema_version LIMIT 1")).scalar()
    if version is None or version < REQUIRED_SCHEMA_VERSION:
        missing.append("schema_version")

    def columns(table):
        return {item["name"]: item for item in inspector.get_columns(table)} if table in tables else {}
    if columns("reminders").get("sent"):
        missing.append("reminders:sent_removed")
    for column in ("attempt_count", "last_attempt_at", "next_attempt_at", "last_error"):
        if column not in columns("reminders"):
            missing.append(f"reminders:{column}")
    for table, column in (("tasks", "user_id"), ("reminders", "user_id"), ("documents", "user_id")):
        if column not in columns(table) or not columns(table)[column]["nullable"] is False:
            missing.append(f"{table}:{column}_not_null")
    for column in ("login_identifier", "password_hash", "is_active"):
        if column not in columns("users"):
            missing.append(f"users:{column}")

    with target_engine.connect() as connection:
        for table, target, expected_from in (
            ("tasks", "tasks", {"parent_task_id", "user_id"}),
            ("reminders", "tasks", {"task_id", "user_id"}),
        ):
            groups = {}
            for row in connection.exec_driver_sql(f"PRAGMA foreign_key_list('{table}')"):
                groups.setdefault(row[0], []).append(row)
            if not any(
                rows[0][2] == target and {row[3] for row in rows} == expected_from
                for rows in groups.values()
            ):
                missing.append(f"{table}:same_owner_foreign_key")
        sql_rows = connection.execute(text("SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('tasks','reminders')")).all()
        sql_by_name = {row[0]: (row[1] or "").lower() for row in sql_rows}
        if "completed = 1" not in sql_by_name.get("tasks", "") or "completed_at is not null" not in sql_by_name.get("tasks", ""):
            missing.append("tasks:completion_check")
        if "status in" not in sql_by_name.get("reminders", "") or "processing" not in sql_by_name.get("reminders", ""):
            missing.append("reminders:status_check")
        if "attempt_count >= 0" not in sql_by_name.get("reminders", ""):
            missing.append("reminders:attempt_count_check")
        if "indexing_state in" not in (connection.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='documents'")).scalar() or "").lower():
            missing.append("documents:indexing_state_check")
    return {"ready": not missing, "version": version, "missing": missing}
