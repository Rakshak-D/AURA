import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import config

Base = declarative_base()
logger = logging.getLogger(__name__)

# Database Connection
# For SQLite we keep a single file-based database with check_same_thread disabled
# so sessions can be used across FastAPI workers safely.
engine = create_engine(
    config.resolved_database_url,
    connect_args={"check_same_thread": False} if config.resolved_database_url.startswith("sqlite") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_chroma_client = None
_collection = None


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
        if not db.query(User).filter_by(id=1).first():
            user = User(
                id=1, 
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

def get_db():
    """Dependency for getting database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
