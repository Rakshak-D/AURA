import sqlite3
import chromadb
from chromadb.config import Settings
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from .config import config  # Relative import

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    description = Column(Text)
    due_date = Column(DateTime)
    completed = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship("User")

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    preferences = Column(Text)  # JSON string

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    filename = Column(String(200))
    content = Column(Text)
    embedding_id = Column(String(100))
    uploaded_at = Column(DateTime, default=datetime.utcnow)

# SQLite args required for FastAPI multithreading
engine = create_engine(
    f'sqlite:///{config.DB_PATH}', 
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# FIXED: Restore the init_db function required by main.py
def init_db():
    Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ChromaDB
chroma_client = chromadb.PersistentClient(path=config.CHROMA_PATH)
collection = chroma_client.get_or_create_collection(name="documents")