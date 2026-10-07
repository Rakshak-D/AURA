from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ..database import Base, UTCDateTime, utc_now


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, default="User")
    preferences = Column(Text, nullable=False, default='{}')
    settings = Column(JSON, nullable=False, default=dict)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    
    tasks = relationship("Task", back_populates="user", order_by="Task.due_date", passive_deletes=True)
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    chat_history = relationship("ChatHistory", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    documents = relationship("Document", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    routine_events = relationship("RoutineEvent", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    due_date = Column(UTCDateTime, nullable=True)
    completed = Column(Boolean, nullable=False, default=False)
    priority = Column(String(20), nullable=False, default='medium')
    category = Column(String(50), nullable=False, default='Personal')
    duration_minutes = Column(Integer, nullable=False, default=30)
    is_flexible = Column(Boolean, nullable=False, default=False)
    conflict_flag = Column(Boolean, nullable=False, default=False)
    tags = Column(Text, nullable=False, default='[]')
    recurring = Column(String(50), nullable=True)
    recurring_end_date = Column(UTCDateTime, nullable=True)
    parent_task_id = Column(Integer, nullable=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = Column(UTCDateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_tasks_duration_positive"),
        CheckConstraint("priority IN ('low', 'medium', 'high', 'urgent')", name="ck_tasks_priority"),
        CheckConstraint(
            "(completed = 0 AND completed_at IS NULL) OR (completed = 1 AND completed_at IS NOT NULL)",
            name="ck_tasks_completion_time",
        ),
        CheckConstraint("recurring IS NULL OR recurring IN ('daily', 'weekly', 'monthly')", name="ck_tasks_recurring"),
        UniqueConstraint("id", "user_id", name="uq_tasks_id_user"),
        ForeignKeyConstraint(
            ["parent_task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            ondelete="CASCADE",
            name="fk_tasks_parent_same_user",
        ),
        Index("ix_tasks_user_due", "user_id", "due_date"),
        Index("ix_tasks_user_completed", "user_id", "completed"),
    )
    
    user = relationship("User", back_populates="tasks")
    parent = relationship("Task", remote_side=[id], back_populates="subtasks", overlaps="user,tasks")
    subtasks = relationship("Task", back_populates="parent", cascade="all, delete-orphan", overlaps="user,tasks")

class Reminder(Base):
    __tablename__ = 'reminders'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    task_id = Column(Integer, nullable=True, index=True)
    reminder_time = Column(UTCDateTime, nullable=False, index=True)
    status = Column(String(20), nullable=False, default='pending')
    timezone = Column(String(64), nullable=False, default='UTC')
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'sent', 'cancelled', 'failed')", name="ck_reminders_status"),
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            ondelete="CASCADE",
            name="fk_reminders_task_same_user",
        ),
    )
    
    task = relationship("Task", overlaps="user,reminders")
    user = relationship("User", back_populates="reminders", overlaps="task")

class ChatHistory(Base):
    __tablename__ = 'chat_history'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    intent = Column(String(50), nullable=True)
    meta_data = Column(JSON, nullable=False, default=dict)
    timestamp = Column(UTCDateTime, nullable=False, default=utc_now, index=True)

    user = relationship("User", back_populates="chat_history")
    __table_args__ = (Index("ix_chat_history_user_timestamp", "user_id", "timestamp"),)

class Document(Base):
    __tablename__ = 'documents'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    filename = Column(String(200), nullable=False)
    stored_path = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)
    file_type = Column(String(50), nullable=False)
    indexing_state = Column(String(20), nullable=False, default='pending')
    indexing_error = Column(Text, nullable=True)
    uploaded_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="documents")
    __table_args__ = (
        CheckConstraint("indexing_state IN ('pending', 'indexed', 'failed')", name="ck_documents_indexing_state"),
        Index("ix_documents_user", "user_id"),
    )

class RoutineEvent(Base):
    __tablename__ = 'routine_events'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    event_type = Column(String, nullable=False) # 'class', 'work', 'meal'
    start_time = Column(String, nullable=False) # "09:00"
    duration_minutes = Column(Integer, nullable=False)
    days_of_week = Column(String, nullable=False) # "0,1,2,3,4" (Mon-Fri)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)

    user = relationship("User", back_populates="routine_events")
    __table_args__ = (CheckConstraint("duration_minutes > 0", name="ck_routine_events_duration_positive"),)
