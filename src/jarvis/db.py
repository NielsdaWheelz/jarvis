from __future__ import annotations

from typing import cast

from pgvector.sqlalchemy import VECTOR  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.types import TypeEngine

NAMING_CONVENTION = {
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
vector_1536 = cast(TypeEngine[object], VECTOR(1536))

message = Table(
    "message",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("role", Text, nullable=False),
    Column("text", Text, nullable=False),
    Column("source", Text, nullable=False),
    Column("source_conversation_id", Text, nullable=False),
    Column("source_message_id", Text),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("processed_at", DateTime(timezone=True)),
    Column(
        "processing_attempts",
        Integer,
        nullable=False,
        server_default=text("0"),
    ),
    Column("processing_parked_at", DateTime(timezone=True)),
    Column("remembered_at", DateTime(timezone=True)),
    Column(
        "trace",
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    ),
    CheckConstraint(
        "role IN ('owner', 'assistant', 'host')",
        name="role",
    ),
    CheckConstraint("length(text) > 0", name="text_nonempty"),
    CheckConstraint("length(source) > 0", name="source_nonempty"),
    CheckConstraint(
        "length(source_conversation_id) > 0",
        name="source_conversation_nonempty",
    ),
    CheckConstraint("processing_attempts >= 0", name="attempts_nonnegative"),
    CheckConstraint("jsonb_typeof(trace) = 'object'", name="trace_object"),
    CheckConstraint("pg_column_size(trace) <= 16384", name="trace_bounded"),
    UniqueConstraint(
        "source",
        "source_message_id",
        name="uq_message_source_identity",
    ),
)

Index(
    "ix_message_waking_pending",
    message.c.source_conversation_id,
    message.c.created_at,
    message.c.id,
    postgresql_where=(
        message.c.role.in_(("owner", "host"))
        & message.c.processed_at.is_(None)
        & message.c.processing_parked_at.is_(None)
    ),
)
Index(
    "ix_message_delivery_pending",
    message.c.created_at,
    message.c.id,
    postgresql_where=(
        (message.c.role == "assistant") & message.c.source_message_id.is_(None)
    ),
)

memory_log = Table(
    "memory_log",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("text", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("embedding", vector_1536),
    CheckConstraint("length(text) > 0", name="text_nonempty"),
)

Index(
    "ix_memory_log_search_english",
    func.to_tsvector(
        literal_column("'english'::regconfig"),
        memory_log.c.text,
    ),
    postgresql_using="gin",
    _table=memory_log,
)
Index(
    "ix_memory_log_search_simple",
    func.to_tsvector(
        literal_column("'simple'::regconfig"),
        memory_log.c.text,
    ),
    postgresql_using="gin",
    _table=memory_log,
)

memory_summary = Table(
    "memory_summary",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("text", Text, nullable=False),
    Column("source_memory_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("embedding", vector_1536),
    CheckConstraint("length(text) > 0", name="text_nonempty"),
    CheckConstraint(
        "cardinality(source_memory_ids) > 0",
        name="source_memory_ids_nonempty",
    ),
)

Index(
    "ix_memory_summary_search_english",
    func.to_tsvector(
        literal_column("'english'::regconfig"),
        memory_summary.c.text,
    ),
    postgresql_using="gin",
    _table=memory_summary,
)
Index(
    "ix_memory_summary_search_simple",
    func.to_tsvector(
        literal_column("'simple'::regconfig"),
        memory_summary.c.text,
    ),
    postgresql_using="gin",
    _table=memory_summary,
)
Index(
    "uq_memory_summary_source_memory_ids",
    memory_summary.c.source_memory_ids,
    unique=True,
)

action = Table(
    "action",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("tool_name", Text, nullable=False),
    Column("arguments", JSONB, nullable=False),
    Column("execution_contract", JSONB, nullable=False),
    Column("status", Text, nullable=False),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("execute_after", DateTime(timezone=True)),
    Column(
        "origin_message_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "approval_message_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("decided_at", DateTime(timezone=True)),
    Column("completed_at", DateTime(timezone=True)),
    Column("result", JSONB),
    CheckConstraint("length(tool_name) > 0", name="tool_name_nonempty"),
    CheckConstraint("jsonb_typeof(arguments) = 'object'", name="arguments_object"),
    CheckConstraint(
        "jsonb_typeof(execution_contract) = 'object'",
        name="execution_contract_object",
    ),
    CheckConstraint(
        "status IN ('queued', 'awaiting_approval', 'executing', "
        "'succeeded', 'failed', 'uncertain', 'cancelled')",
        name="status",
    ),
    CheckConstraint("attempts >= 0", name="attempts_nonnegative"),
    CheckConstraint(
        "status <> 'awaiting_approval' OR approval_message_id IS NOT NULL",
        name="approval_message_required",
    ),
    CheckConstraint(
        "(status IN ('succeeded', 'failed', 'uncertain', 'cancelled')) "
        "= (completed_at IS NOT NULL)",
        name="terminal_completion",
    ),
    CheckConstraint(
        "result IS NULL OR jsonb_typeof(result) = 'object'",
        name="result_object",
    ),
)

Index("ix_action_status_execute_after", action.c.status, action.c.execute_after)


model_decision = Table(
    "model_decision",
    metadata,
    Column("decision_id", Text, primary_key=True),
    Column("scope_key", Text, nullable=False),
    Column("thread_id", Text),
    Column(
        "first_input_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
    ),
    Column("ordinal", Integer, nullable=False),
    Column("request_fingerprint", Text, nullable=False),
    Column("request", JSONB, nullable=False),
    Column("terminal", JSONB),
    Column("host_evidence", JSONB),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("completed_at", DateTime(timezone=True)),
    UniqueConstraint("scope_key", "ordinal", name="uq_model_decision_scope_ordinal"),
    CheckConstraint("ordinal > 0", name="ordinal_positive"),
    CheckConstraint(
        "decision_id ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$'",
        name="fingerprints",
    ),
    CheckConstraint(
        "(thread_id IS NULL) = (first_input_id IS NULL)", name="thread_scope"
    ),
    CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
    CheckConstraint(
        "terminal IS NULL OR jsonb_typeof(terminal) = 'object'", name="terminal_object"
    ),
    CheckConstraint("(terminal IS NULL) = (completed_at IS NULL)", name="completion"),
)


read_position = Table(
    "read_position",
    metadata,
    Column("position", Text, primary_key=True),
    Column("contract", JSONB, nullable=False),
    Column("state", Text, nullable=False),
    Column("reservation", JSONB),
    Column("result", JSONB),
    Column("settlement", JSONB),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    CheckConstraint(
        "state IN ('prepared', 'dispatched', 'uncertain', 'completed')", name="state"
    ),
    CheckConstraint("jsonb_typeof(contract) = 'object'", name="contract_object"),
    CheckConstraint(
        "(state = 'completed') = (result IS NOT NULL AND settlement IS NOT NULL)",
        name="completion",
    ),
)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    msg = "database URL must use PostgreSQL with psycopg"
    raise ValueError(msg)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(database_url),
        pool_pre_ping=True,
    )
