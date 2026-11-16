from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
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
    login_identifier = Column(String(255), nullable=True, unique=True, index=True)
    password_hash = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    
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
    attempt_count = Column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at = Column(UTCDateTime, nullable=True)
    next_attempt_at = Column(UTCDateTime, nullable=True)
    last_error = Column(String(500), nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'sent', 'cancelled', 'failed')", name="ck_reminders_status"),
        CheckConstraint("attempt_count >= 0", name="ck_reminders_attempt_count"),
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
    # Existing vectors remain unidentified until explicitly re-indexed.
    embedding_model_id = Column(String(255), nullable=True)
    uploaded_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    user = relationship("User", back_populates="documents")
    __table_args__ = (
        CheckConstraint("indexing_state IN ('pending', 'indexed', 'failed')", name="ck_documents_indexing_state"),
        Index("ix_documents_user", "user_id"),
    )


class ProviderConnection(Base):
    """One named, user-owned provider configuration; secrets live separately."""

    __tablename__ = "provider_connections"
    id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    provider_type = Column(String(40), nullable=False)
    base_url = Column(String(2048), nullable=True)
    configuration = Column(JSON, nullable=False, default=dict, server_default="{}")
    config_revision = Column(Integer, nullable=False, default=0, server_default="0")
    deleted_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "id", name="uq_provider_connections_user_id_id"),
        UniqueConstraint("user_id", "name", name="uq_provider_connections_user_name"),
        CheckConstraint(
            "provider_type IN ('ollama', 'openai_compatible', 'legacy_gguf', 'anthropic', 'gemini', 'sentence_transformers')",
            name="ck_provider_connections_provider_type",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_provider_connections_name"),
        CheckConstraint("config_revision >= 0", name="ck_provider_connections_config_revision"),
        Index("ix_provider_connections_user", "user_id"),
    )

    credentials = relationship("ProviderCredential", back_populates="connection")
    role_selections = relationship("ModelRoleSelection", back_populates="connection")
    capability_cache = relationship("ProviderCapabilityCache", back_populates="connection")

    @classmethod
    def get_owned(cls, session, user_id: int, connection_id: str):
        """Fetch a connection only within the authenticated owner's scope."""
        return (
            session.query(cls)
            .filter_by(user_id=user_id, id=connection_id)
            .one_or_none()
        )

    def advance_config_revision(self) -> None:
        """Invalidate cache lookups tied to the previous configuration."""
        self.config_revision += 1

    def mark_removed(self, when: datetime | None = None) -> None:
        """Retain this connection as a tombstone for existing role references."""
        if self.deleted_at is None:
            self.deleted_at = when or utc_now()

    def current_capability_cache(self, session, model_id: str):
        """Return only the cache matching this owner's current revision."""
        return (
            session.query(ProviderCapabilityCache)
            .filter_by(
                user_id=self.user_id,
                connection_id=self.id,
                config_revision=self.config_revision,
                model_id=model_id,
            )
            .one_or_none()
        )


class ProviderCredential(Base):
    """Encrypted provider credential material; no plaintext or master key."""

    __tablename__ = "provider_credentials"
    credential_id = Column(String(64), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(String(64), nullable=False)
    format_version = Column(Integer, nullable=False)
    key_id = Column(String(64), nullable=False)
    nonce = Column(LargeBinary, nullable=False)
    ciphertext = Column(LargeBinary, nullable=False)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "connection_id", name="uq_provider_credentials_connection"),
        ForeignKeyConstraint(
            ["user_id", "connection_id"],
            ["provider_connections.user_id", "provider_connections.id"],
            ondelete="CASCADE",
            name="fk_provider_credentials_owned_connection",
        ),
        CheckConstraint("format_version > 0", name="ck_provider_credentials_format_version"),
        CheckConstraint("length(nonce) = 12", name="ck_provider_credentials_nonce"),
        CheckConstraint("length(ciphertext) >= 16", name="ck_provider_credentials_ciphertext"),
        Index("ix_provider_credentials_user_connection", "user_id", "connection_id"),
    )

    connection = relationship("ProviderConnection", back_populates="credentials")

    @classmethod
    def get_owned(cls, session, user_id: int, connection_id: str):
        """Fetch encrypted credential metadata within owner and connection scope."""
        return (
            session.query(cls)
            .filter_by(user_id=user_id, connection_id=connection_id)
            .one_or_none()
        )


class ModelRoleSelection(Base):
    """An explicit role binding to one connection ID and exact model ID."""

    __tablename__ = "model_role_selections"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(16), nullable=False)
    connection_id = Column(String(64), nullable=False)
    model_id = Column(String(512), nullable=False)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        UniqueConstraint("user_id", "role", name="uq_model_role_selections_user_role"),
        ForeignKeyConstraint(
            ["user_id", "connection_id"],
            ["provider_connections.user_id", "provider_connections.id"],
            name="fk_model_role_selections_owned_connection",
        ),
        CheckConstraint(
            "role IN ('router', 'chat', 'embedding')",
            name="ck_model_role_selections_role",
        ),
        CheckConstraint("length(trim(model_id)) > 0", name="ck_model_role_selections_model_id"),
        Index("ix_model_role_selections_user", "user_id"),
    )

    connection = relationship("ProviderConnection", back_populates="role_selections")

    @classmethod
    def get_for_user(cls, session, user_id: int, role: str):
        """Resolve a role only for its authenticated owner."""
        return session.query(cls).filter_by(user_id=user_id, role=role).one_or_none()

    @property
    def is_available(self) -> bool:
        """A tombstoned connection remains referenced but is not usable."""
        return self.connection is not None and self.connection.deleted_at is None


class ProviderCapabilityCache(Base):
    """Safe, versioned capability facts scoped to one owner and connection."""

    __tablename__ = "provider_capability_cache"
    user_id = Column(Integer, primary_key=True)
    connection_id = Column(String(64), primary_key=True)
    config_revision = Column(Integer, primary_key=True)
    model_id = Column(String(512), primary_key=True)
    context_length = Column(Integer, nullable=True)
    tools = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    json_mode = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    vision = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    streaming = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    embeddings = Column(String(16), nullable=False, default="unknown", server_default="unknown")
    checked_at = Column(UTCDateTime, nullable=False, default=utc_now)

    __table_args__ = (
        ForeignKeyConstraint(
            ["user_id", "connection_id"],
            ["provider_connections.user_id", "provider_connections.id"],
            ondelete="CASCADE",
            name="fk_provider_capability_cache_owned_connection",
        ),
        CheckConstraint("config_revision >= 0", name="ck_provider_capability_cache_revision"),
        CheckConstraint(
            "context_length IS NULL OR context_length > 0",
            name="ck_provider_capability_cache_context_length",
        ),
        CheckConstraint(
            "tools IN ('supported', 'unsupported', 'unknown')",
            name="ck_provider_capability_cache_tools",
        ),
        CheckConstraint(
            "json_mode IN ('supported', 'unsupported', 'unknown')",
            name="ck_provider_capability_cache_json_mode",
        ),
        CheckConstraint(
            "vision IN ('supported', 'unsupported', 'unknown')",
            name="ck_provider_capability_cache_vision",
        ),
        CheckConstraint(
            "streaming IN ('supported', 'unsupported', 'unknown')",
            name="ck_provider_capability_cache_streaming",
        ),
        CheckConstraint(
            "embeddings IN ('supported', 'unsupported', 'unknown')",
            name="ck_provider_capability_cache_embeddings",
        ),
    )

    connection = relationship("ProviderConnection", back_populates="capability_cache")


class UserModelPreference(Base):
    """Per-user model policy; Local only is enabled unless explicitly changed."""

    __tablename__ = "user_model_preferences"
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    local_only = Column(Boolean, nullable=False, default=True, server_default="1")
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    @classmethod
    def get_or_default(cls, session, user_id: int):
        """Return stored preference or a non-persisted Local only default."""
        return session.get(cls, user_id) or cls(user_id=user_id, local_only=True)

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
