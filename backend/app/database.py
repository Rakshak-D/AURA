from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime
from .config import config
import chromadb
import json

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    preferences = Column(Text, default='{}')
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False)
    priority = Column(String(20), default='medium')
    category = Column(String(50), default='Personal')
    duration_minutes = Column(Integer, default=30)
    tags = Column(Text, default='[]')
    recurring = Column(String(50), nullable=True)
    recurring_end_date = Column(DateTime, nullable=True)
    parent_task_id = Column(Integer, ForeignKey('tasks.id'), nullable=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    user = relationship("User", back_populates="tasks")
    subtasks = relationship("Task", backref="parent", remote_side=[id])

User.tasks = relationship("Task", back_populates="user", order_by=Task.due_date)

class Reminder(Base):
    __tablename__ = 'reminders'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey('tasks.id'))
    reminder_time = Column(DateTime, nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    task = relationship("Task")

class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    role = Column(String(20))
    content = Column(Text)
    intent = Column(String(50), nullable=True)
    meta_data = Column(JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), default=1)
    filename = Column(String(200))
    content = Column(Text)
    file_type = Column(String(50))
    uploaded_at = Column(DateTime, default=datetime.utcnow)

# Database Connection
engine = create_engine(
    f'sqlite:///{config.DB_PATH}',
    connect_args={"check_same_thread": False}
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