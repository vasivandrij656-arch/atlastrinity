"""AtlasTrinity Database Schema
Uses SQLAlchemy 2.0+ (Async)
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (  # pyre-ignore
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship  # pyre-ignore

# Database-agnostic UUID and JSON support
from sqlalchemy.types import CHAR, TypeDecorator  # pyre-ignore


class GUID(TypeDecorator):
    """Platform-independent GUID type.
    Uses CHAR(36) for SQLite (default), or PostgreSQL's native UUID type.
    Stores UUIDs as canonical strings with hyphens.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as PG_UUID  # pyre-ignore

            return dialect.type_descriptor(PG_UUID())
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            return str(uuid.UUID(value))
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            return uuid.UUID(value)
        return value


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default={})

    tasks: Mapped[list["Task"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))

    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(50),
        default="PENDING",
    )  # PENDING, RUNNING, COMPLETED, FAILED
    golden_path: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Рекурсивний контекст: goal_stack, parent_goal, recursive_depth, parent_task_id
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default={})

    parent_task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)

    session: Mapped["Session"] = relationship(back_populates="tasks")
    steps: Mapped[list["TaskStep"]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
    )

    # Hierarchical support
    parent_task: Mapped["Task | None"] = relationship("Task", remote_side=[id], backref="sub_tasks")


class TaskStep(Base):
    __tablename__ = "task_steps"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"))

    sequence_number: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(String(100))

    status: Mapped[str] = mapped_column(String(50))  # SUCCESS, FAILED
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    task: Mapped["Task"] = relationship(back_populates="steps")
    tool_executions: Mapped[list["ToolExecution"]] = relationship(back_populates="step")


class ToolExecution(Base):
    __tablename__ = "tool_executions"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    step_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("task_steps.id"))

    # Direct task association for faster audits
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id"), nullable=True)

    server_name: Mapped[str] = mapped_column(String(100))
    tool_name: Mapped[str] = mapped_column(String(100))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="SUCCESS")  # SUCCESS, FAILED

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    step: Mapped["TaskStep"] = relationship(back_populates="tool_executions")


class LogEntry(Base):
    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    level: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50))
    message: Mapped[str] = mapped_column(Text)
    metadata_blob: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class ChatMessage(Base):
    """Stores full chat history for persistent session reconstruction"""

    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)

    role: Mapped[str] = mapped_column(String(20))  # human, ai, system
    content: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default={})


# Knowledge Graph Nodes (Vertices)
class KGNode(Base):
    __tablename__ = "kg_nodes"

    id: Mapped[str] = mapped_column(Text, primary_key=True)  # URI: file://..., task:uuid
    type: Mapped[str] = mapped_column(String(50))  # FILE, TASK, TOOL, CONCEPT, DATASET
    namespace: Mapped[str] = mapped_column(String(100), default="global", index=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("tasks.id"), nullable=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, default={})

    last_updated: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# Knowledge Graph Edges (Relationships)
class KGEdge(Base):
    __tablename__ = "kg_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("kg_nodes.id"))
    target_id: Mapped[str] = mapped_column(ForeignKey("kg_nodes.id"))
    relation: Mapped[str] = mapped_column(String(50))  # CREATED, MODIFIED, READ, USED
    namespace: Mapped[str] = mapped_column(String(100), default="global", index=True)
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSON, default={}, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


# Agent Message Bus - Typed inter-agent communication
class AgentMessage(Base):
    """Typed messages between agents for reliable communication"""

    __tablename__ = "agent_messages"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))

    from_agent: Mapped[str] = mapped_column(String(20))  # atlas, tetyana, grisha
    to_agent: Mapped[str] = mapped_column(String(20))
    message_type: Mapped[str] = mapped_column(String(50))  # rejection, help_request, feedback
    step_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


# Analytics for recursive healing
class RecoveryAttempt(Base):
    """Track recursive healing attempts for analytics"""

    __tablename__ = "recovery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    step_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("task_steps.id"))

    depth: Mapped[int] = mapped_column(Integer)  # recursion depth
    recovery_method: Mapped[str] = mapped_column(String(50))  # vibe, atlas_help, retry
    success: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    vibe_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_before: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ConversationSummary(Base):
    """Stores professional summaries of chat sessions for semantic recall"""

    __tablename__ = "conversation_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(100), index=True)

    summary: Mapped[str] = mapped_column(Text)
    key_entities: Mapped[list[str]] = mapped_column(JSON, default=[])  # List of names/concepts

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    metadata_blob: Mapped[dict[str, Any]] = mapped_column(JSON, default={})


class BehavioralDeviation(Base):
    """Stores logic deviations from original plans for auditing and analytics.
    Complements the vector-based memory in ChromaDB.
    """

    __tablename__ = "behavioral_deviations"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id"))
    step_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("task_steps.id"),
        nullable=True,
    )

    original_intent: Mapped[str] = mapped_column(Text)
    deviation: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    decision_factors: Mapped[dict[str, Any]] = mapped_column(JSON, default={})

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class KnowledgePromotion(Base):
    """Tracks the elevation of data from task-specific to global (Golden Fund).
    Provides an audit log for knowledge accumulation.
    """

    __tablename__ = "knowledge_promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[str] = mapped_column(ForeignKey("kg_nodes.id"))

    old_namespace: Mapped[str] = mapped_column(String(100))
    target_namespace: Mapped[str] = mapped_column(String(100), default="global")

    promoted_by: Mapped[str] = mapped_column(String(50))  # Agent name
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Discovery(Base):
    """Stores critical values discovered during task execution.
    Complements ChromaDB vector storage with structured SQL storage.
    Enables fast task-specific retrieval and auditing.
    """

    __tablename__ = "discoveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("tasks.id"), index=True)
    step_id: Mapped[str] = mapped_column(
        String(50), index=True
    )  # Hierarchical step ID (e.g., "1.2.3")

    key: Mapped[str] = mapped_column(String(100))  # Descriptive key (e.g., "mikrotik_ip")
    value: Mapped[str] = mapped_column(Text)  # The actual discovered value
    category: Mapped[str] = mapped_column(
        String(50)
    )  # ip_address, path, credential, identifier, other
    step_action: Mapped[str] = mapped_column(Text, nullable=True)  # Context of what step was doing

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class FileIndex(Base):
    """Indexes files in the workspace for fast retrieval by Vibe/Agents."""

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String(500), index=True, unique=True)
    name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(Integer, default=0)
    mtime: Mapped[float] = mapped_column(Float, default=0.0)
    is_dir: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    last_scanned: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class User(Base):
    """User model for authentication and role-based access.
    Satisfies generic queries to the 'users' table.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, inactive, suspended
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
