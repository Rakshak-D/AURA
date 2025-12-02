from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import config
import chromadb

Base = declarative_base()

# Database Connection
# For SQLite we keep a single file-based database with check_same_thread disabled
# so sessions can be used across FastAPI workers safely.
engine = create_engine(
    f"sqlite:///{config.DB_PATH}",
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ChromaDB Client
try:
    chroma_client = chromadb.PersistentClient(path=str(config.CHROMA_PATH))
    collection = chroma_client.get_or_create_collection(name="documents")
except Exception as e:
    print(f"ChromaDB initialization error: {e}")
    collection = None

def init_db():
    """Initialize database with tables and default data"""
    # Import models here to ensure they are registered with Base.metadata
    from .models.sql_models import User, Task, Reminder, ChatHistory, Document, RoutineEvent
    
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
            print("✅ Default user created")
    except Exception as e:
        print(f"Error creating default user: {e}")
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