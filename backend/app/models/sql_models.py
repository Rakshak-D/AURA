from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from ..database import Base

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    preferences = Column(Text, default='{}')
    settings = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    tasks = relationship("Task", back_populates="user", order_by="Task.due_date")

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
    is_flexible = Column(Boolean, default=False)
    conflict_flag = Column(Boolean, default=False)
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

class RoutineEvent(Base):
    __tablename__ = 'routine_events'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    event_type = Column(String) # 'class', 'work', 'meal'
    start_time = Column(String) # "09:00"
    duration_minutes = Column(Integer)
    days_of_week = Column(String) # "0,1,2,3,4" (Mon-Fri)
    user_id = Column(Integer, ForeignKey('users.id'))
