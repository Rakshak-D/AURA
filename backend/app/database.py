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

_chroma_client = None
_collection = None


class DatabaseIntegrityError(RuntimeError):
    """Raised when required database state is missing or inconsistent."""


def get_development_user(db):
    """Resolve the seeded development user until Phase 3 authentication exists.

    This is an ownership boundary, not a global current-user constant. Phase 3
    can replace this resolver with an authenticated-user dependency.
    """
    from .models.sql_models import User

    user = db.query(User).order_by(User.id.asc()).first()
    if user is None:
        raise DatabaseIntegrityError("No development user exists in the database")
    return user


def get_development_user_id(db) -> int:
    return get_development_user(db).id


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
    _apply_additive_schema_migrations()

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


def _apply_additive_schema_migrations() -> None:
    """Apply safe, additive migrations for existing development SQLite files.

    ``create_all`` creates missing tables but never upgrades existing ones. This
    phase intentionally uses small additive migrations instead of deleting or
    rebuilding user data. Fresh databases receive the complete model schema;
    legacy databases receive compatible columns and indexes where possible.
    """
    if engine.url.get_backend_name() != "sqlite":
        return

    from sqlalchemy import inspect, text

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"))
        if connection.execute(text("SELECT COUNT(*) FROM schema_version")).scalar() == 0:
            connection.execute(text("INSERT INTO schema_version(version) VALUES (0)"))

        additions = {
            "reminders": {
                "user_id": "INTEGER",
                "status": "VARCHAR(20) DEFAULT 'pending'",
                "timezone": "VARCHAR(64) DEFAULT 'UTC'",
                "updated_at": "DATETIME",
            },
            "documents": {
                "stored_path": "VARCHAR(500)",
                "indexing_state": "VARCHAR(20) DEFAULT 'pending'",
                "indexing_error": "TEXT",
                "updated_at": "DATETIME",
            },
        }
        for table, columns in additions.items():
            existing = {column["name"] for column in inspect(connection).get_columns(table)}
            for name, definition in columns.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {definition}'))

        first_user = connection.execute(text("SELECT id FROM users ORDER BY id LIMIT 1")).scalar()
        if first_user is not None:
            connection.execute(text("UPDATE reminders SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": first_user})
            connection.execute(text("UPDATE documents SET user_id = :user_id WHERE user_id IS NULL"), {"user_id": first_user})
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_user_due ON tasks (user_id, due_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_tasks_user_completed ON tasks (user_id, completed)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_history_user_timestamp ON chat_history (user_id, timestamp)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_documents_user ON documents (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_reminders_user_trigger ON reminders (user_id, reminder_time)"))
        connection.execute(text("UPDATE schema_version SET version = 1"))
