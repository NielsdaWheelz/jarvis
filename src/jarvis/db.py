from __future__ import annotations

from typing import cast

from pgvector.sqlalchemy import VECTOR  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Sequence,
    Table,
    Text,
    UniqueConstraint,
    func,
    literal_column,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.types import TypeEngine
from universal_memory.policy import (
    EMBEDDING_DIMENSIONS,
    READ_POOL_SIZE,
    READ_STATEMENT_SECONDS,
)
from universal_memory.schema import MEMORY_TABLES

NAMING_CONVENTION = {
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}

MEMORY_SCHEMA_REVISION = "0006"

metadata = MetaData(naming_convention=NAMING_CONVENTION)
vector_1536 = cast(TypeEngine[object], VECTOR(EMBEDDING_DIMENSIONS))

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
    Column("memory_admitted", Boolean, nullable=False, server_default=text("false")),
    Column("request_state", Text),
    Column("wait_reason", Text),
    Column("control_kind", Text),
    Column("control_sequence", Integer, unique=True),
    Column("control_targets", ARRAY(UUID(as_uuid=True))),
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
    CheckConstraint(
        "request_state IS NULL OR request_state IN "
        "('pending', 'waiting', 'completed', 'stopped')",
        name="request_state",
    ),
    CheckConstraint(
        "(request_state IS NOT DISTINCT FROM 'waiting') = (wait_reason IS NOT NULL)",
        name="wait_reason_required",
    ),
    CheckConstraint(
        "wait_reason IS NULL OR wait_reason IN "
        "('approval', 'external_reconciliation', 'owner_input', 'configuration')",
        name="wait_reason",
    ),
    CheckConstraint(
        "(control_kind IS NULL AND control_sequence IS NULL "
        "AND control_targets IS NULL) "
        "OR (control_kind IN ('stop', 'pause', 'resume') AND control_sequence > 0 "
        "AND control_targets IS NOT NULL)",
        name="control",
    ),
    UniqueConstraint(
        "source",
        "source_message_id",
        name="uq_message_source_identity",
    ),
)

control_sequence = Sequence("message_control_sequence", metadata=metadata)
Index(
    "ix_message_unresolved_request",
    message.c.source_conversation_id,
    message.c.created_at,
    message.c.id,
    postgresql_where=message.c.request_state.in_(("pending", "waiting")),
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
    Column("agent_submission", JSONB(none_as_null=True)),
    Column("synthesis", JSONB(none_as_null=True)),
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
    Column("result", JSONB(none_as_null=True)),
    Column(
        "supersedes_action_id",
        UUID(as_uuid=True),
        ForeignKey("action.id", ondelete="RESTRICT"),
        unique=True,
    ),
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
    Column("terminal", JSONB(none_as_null=True)),
    Column("submission", JSONB(none_as_null=True)),
    Column("host_evidence", JSONB(none_as_null=True)),
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
    CheckConstraint("terminal IS NULL OR submission IS NULL", name="exclusive_outcome"),
    CheckConstraint(
        "submission IS NULL OR jsonb_typeof(submission) = 'object'",
        name="submission_object",
    ),
)


read_position = Table(
    "read_position",
    metadata,
    Column("position", Text, primary_key=True),
    Column("contract", JSONB, nullable=False),
    Column("state", Text, nullable=False),
    Column("reservation", JSONB(none_as_null=True)),
    Column("result", JSONB(none_as_null=True)),
    Column("settlement", JSONB(none_as_null=True)),
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

native_attempt = Table(
    "native_attempt",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("conversation_id", Text, nullable=False),
    Column("attempt_seq", Integer, nullable=False),
    Column("owner_epoch", Text, nullable=False),
    Column("memory_admitted", Boolean, nullable=False, server_default=text("false")),
    Column("request_fingerprint", Text, nullable=False),
    Column("request", JSONB, nullable=False),
    Column("native_binding", JSONB(none_as_null=True)),
    Column("submission_evidence", JSONB(none_as_null=True)),
    Column("local_outcome", JSONB(none_as_null=True)),
    Column("terminal", JSONB(none_as_null=True)),
    Column("product_outcome", JSONB(none_as_null=True)),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("armed_at", DateTime(timezone=True), nullable=False),
    Column("fenced_at", DateTime(timezone=True)),
    Column("terminal_at", DateTime(timezone=True)),
    UniqueConstraint("conversation_id", "attempt_seq"),
    CheckConstraint("attempt_seq > 0", name="sequence_positive"),
    CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
    CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
    CheckConstraint("(terminal IS NULL) = (terminal_at IS NULL)", name="terminal_time"),
    CheckConstraint(
        "product_outcome IS NULL OR terminal IS NOT NULL", name="product_terminal"
    ),
    *(
        CheckConstraint(
            f"{name} IS NULL OR jsonb_typeof({name}) = 'object'", name=f"{name}_object"
        )
        for name in (
            "native_binding",
            "submission_evidence",
            "local_outcome",
            "terminal",
            "product_outcome",
        )
    ),
)
Index(
    "uq_native_attempt_active",
    native_attempt.c.conversation_id,
    unique=True,
    postgresql_where=(
        native_attempt.c.fenced_at.is_(None)
        & native_attempt.c.product_outcome.is_(None)
    ),
)

native_invocation = Table(
    "native_invocation",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "attempt_id",
        UUID(as_uuid=True),
        ForeignKey("native_attempt.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("native_call_id", Text, nullable=False),
    Column(
        "request_message_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
    ),
    Column("tool_id", Text, nullable=False),
    Column("proposal_digest", Text, nullable=False),
    Column("proposal", JSONB, nullable=False),
    Column("frozen_contract", JSONB, nullable=False),
    Column("validation", Text, nullable=False),
    Column("validation_error", JSONB(none_as_null=True)),
    Column(
        "read_position", Text, ForeignKey("read_position.position", ondelete="RESTRICT")
    ),
    Column(
        "action_id", UUID(as_uuid=True), ForeignKey("action.id", ondelete="RESTRICT")
    ),
    Column("reply_receipt", JSONB(none_as_null=True)),
    Column("reply_recorded_at", DateTime(timezone=True)),
    UniqueConstraint("attempt_id", "native_call_id", name="uq_native_invocation_call"),
    UniqueConstraint("attempt_id", "ordinal", name="uq_native_invocation_ordinal"),
    CheckConstraint("ordinal > 0", name="ordinal_positive"),
    CheckConstraint("proposal_digest ~ '^[0-9a-f]{64}$'", name="digest"),
    CheckConstraint("jsonb_typeof(proposal) = 'object'", name="proposal_object"),
    CheckConstraint("jsonb_typeof(frozen_contract) = 'object'", name="contract_object"),
    CheckConstraint("validation IN ('accepted', 'rejected')", name="validation"),
    CheckConstraint(
        "(validation = 'rejected') = (validation_error IS NOT NULL)",
        name="validation_error",
    ),
    CheckConstraint("read_position IS NULL OR action_id IS NULL", name="one_execution"),
    CheckConstraint(
        "(validation = 'accepted' AND frozen_contract->>'effect' = 'Write' "
        "AND tool_id <> 'memory.save_note') "
        "IS NOT DISTINCT FROM (request_message_id IS NOT NULL)",
        name="write_origin",
    ),
    CheckConstraint(
        "validation <> 'rejected' OR "
        "(read_position IS NULL AND action_id IS NULL AND request_message_id IS NULL)",
        name="rejected_execution",
    ),
    CheckConstraint(
        "(reply_receipt IS NULL) = (reply_recorded_at IS NULL)", name="reply_time"
    ),
)

native_input_delivery = Table(
    "native_input_delivery",
    metadata,
    Column(
        "attempt_id",
        UUID(as_uuid=True),
        ForeignKey("native_attempt.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "message_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("ordinal", Integer, nullable=False),
    Column("delivery_id", Text, nullable=False),
    Column("mode", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("provider_evidence", JSONB(none_as_null=True)),
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
    UniqueConstraint("attempt_id", "ordinal"),
    CheckConstraint("ordinal > 0", name="ordinal_positive"),
    CheckConstraint("mode IN ('initial', 'steer')", name="mode"),
    CheckConstraint(
        "state IN ('prepared', 'sent', 'queued', 'recorded', 'rejected')", name="state"
    ),
)


for memory_table in MEMORY_TABLES:
    memory_table.to_metadata(metadata)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    msg = "database URL must use PostgreSQL with psycopg"
    raise ValueError(msg)


def create_engine(database_url: str, *, memory_reads: bool = False) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(database_url),
        pool_pre_ping=True,
        **(
            {
                "pool_size": READ_POOL_SIZE,
                "max_overflow": 0,
                "connect_args": {
                    "options": "-c default_transaction_read_only=on "
                    f"-c statement_timeout={READ_STATEMENT_SECONDS * 1000}"
                },
            }
            if memory_reads
            else {}
        ),
    )
