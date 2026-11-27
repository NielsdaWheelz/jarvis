from __future__ import annotations

from typing import cast

from pgvector.sqlalchemy import VECTOR  # pyright: ignore[reportMissingTypeStubs]
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
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

ASSISTANT_MEMORY_READS = 1
SERVICE_MEMORY_READS = READ_POOL_SIZE - ASSISTANT_MEMORY_READS

NAMING_CONVENTION = {
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
}

APPLICATION_SCHEMA_REVISION = "0029"

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
    Column("home", JSONB(none_as_null=True)),
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
    Column("native_retry_after", DateTime(timezone=True)),
    Column("memory_admitted", Boolean, nullable=False, server_default=text("false")),
    Column(
        "parent_request_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
    ),
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
    CheckConstraint(
        "length(text) > 0 OR (role = 'owner' AND source IN ('discord','web') AND "
        "jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE",
        name="text_nonempty",
    ),
    CheckConstraint(
        "NOT trace ? 'attachment_manifest' OR (role = 'owner' AND "
        "source IN ('discord','web') AND "
        "jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE",
        name="attachment_manifest",
    ),
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
owner_shown = Table(
    "owner_shown",
    metadata,
    Column(
        "message_id", UUID(as_uuid=True), ForeignKey("message.id"), primary_key=True
    ),
    Column(
        "shown_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("via", Text, nullable=False),
    CheckConstraint("via IN ('observed', 'cleared', 'cutover')", name="via"),
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
        "(status IN ('succeeded', 'failed', 'uncertain', 'cancelled')) "
        "= (completed_at IS NOT NULL)",
        name="terminal_completion",
    ),
    CheckConstraint(
        "result IS NULL OR jsonb_typeof(result) = 'object'",
        name="result_object",
    ),
)

home_notice = Table(
    "home_notice",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("kind", Text, nullable=False),
    Column("message_id", UUID(as_uuid=True), ForeignKey("message.id"), unique=True),
    Column("action_id", UUID(as_uuid=True), ForeignKey("action.id"), unique=True),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("provider_id", Text),
    Column("provider", Text),
    CheckConstraint(
        "(provider IS NULL AND provider_id IS NULL AND kind IN ('reply', 'question')) "
        "OR (provider IS NOT NULL AND provider_id IS NOT NULL "
        "AND provider IN ('discord', 'fcm') "
        "AND (provider = 'discord' OR kind IN ('reply', 'question')))",
        name="provider",
    ),
    CheckConstraint(
        "(kind IN ('reply','question') AND message_id IS NOT NULL "
        "AND action_id IS NULL) OR "
        "(kind = 'approval' AND message_id IS NULL AND action_id IS NOT NULL)",
        name="target",
    ),
)
Index(
    "ix_home_notice_pending",
    home_notice.c.created_at,
    home_notice.c.id,
    postgresql_where=home_notice.c.provider_id.is_(None),
)
Index("ix_action_status_execute_after", action.c.status, action.c.execute_after)


workspace_block = Table(
    "workspace_block",
    metadata,
    Column("id", UUID(as_uuid=True), ForeignKey("message.id"), primary_key=True),
    Column("origin_kind", Text, nullable=False),
    Column("origin_id", UUID(as_uuid=True), nullable=False),
    Column("product", Text, nullable=False),
    Column("operation", Text, nullable=False),
    Column("target_key", Text, nullable=False),
    Column("reason", Text, nullable=False),
    Column("remedy", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("grant_id", UUID(as_uuid=True)),
    Column("operation_ref", JSONB(none_as_null=True), nullable=False),
    Column("revision", BigInteger, nullable=False, server_default=text("1")),
    Column("retry_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("notice_anchor", UUID(as_uuid=True), ForeignKey("message.id")),
    CheckConstraint(
        "origin_kind IN ('read','write','verification','source')", name="origin_kind"
    ),
    CheckConstraint("product IN ('gmail','calendar','drive','docs')", name="product"),
    CheckConstraint("length(operation) > 0 AND length(target_key) > 0", name="target"),
    CheckConstraint(
        "reason IN ('consent_required','consent_expired','approval_busy','denied',"
        "'rate_limited','temporary','grant_unavailable','scope_missing','policy_block',"
        "'withheld','partial','screened','not_found','invalid_response','unsupported',"
        "'uncertain','precondition_failed','source_changed','exhausted',"
        "'target_observed','target_differs','label_still_present')",
        name="reason",
    ),
    CheckConstraint(
        "remedy IN ('wait','answer_google','reconnect','verify','none')", name="remedy"
    ),
    CheckConstraint(
        "state IN ('waiting','needs_owner','checking','resolved',"
        "'denied','superseded')",
        name="state",
    ),
    CheckConstraint("jsonb_typeof(operation_ref) = 'object'", name="ref"),
    CheckConstraint("revision > 0", name="revision"),
)
Index(
    "uq_workspace_block_open_origin",
    workspace_block.c.origin_kind,
    workspace_block.c.origin_id,
    workspace_block.c.product,
    workspace_block.c.operation,
    workspace_block.c.target_key,
    unique=True,
    postgresql_where=workspace_block.c.state.in_(
        ("waiting", "needs_owner", "checking")
    ),
)


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
    Column("result", JSON(none_as_null=True)),
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
    Column(
        "stock_observations_pending",
        Boolean,
        nullable=False,
        server_default=text("false"),
    ),
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
    Column("recovery_pending", Boolean, nullable=False, server_default=text("false")),
    UniqueConstraint("conversation_id", "attempt_seq"),
    CheckConstraint("attempt_seq > 0", name="sequence_positive"),
    CheckConstraint("request_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint"),
    CheckConstraint(
        "NOT stock_observations_pending OR memory_admitted",
        name="stock_observation_admitted",
    ),
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
active_native_attempt = native_attempt.c.fenced_at.is_(
    None
) & native_attempt.c.product_outcome.is_(None)

Index(
    "uq_native_attempt_active",
    native_attempt.c.conversation_id,
    unique=True,
    postgresql_where=active_native_attempt,
)

Index(
    "ix_native_attempt_pending_loss",
    native_attempt.c.conversation_id,
    native_attempt.c.attempt_seq,
    postgresql_where=native_attempt.c.recovery_pending
    & native_attempt.c.fenced_at.is_not(None),
)

Index(
    "ix_native_attempt_unsettled_seal",
    native_attempt.c.conversation_id,
    native_attempt.c.attempt_seq,
    postgresql_include=["id"],
    postgresql_where=(
        native_attempt.c.terminal_at.is_not(None)
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
        "AND tool_id NOT IN ('memory.save_note', 'approval.respond')) "
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
    Column("was_waking", Boolean, nullable=False, server_default=text("false")),
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

# A start accepts its opening. A steer only joins the turn at its recorded item.
proven_native_delivery = (native_input_delivery.c.state == "recorded") | (
    (native_input_delivery.c.mode == "initial")
    & (native_input_delivery.c.state == "sent")
)


work = Table(
    "work",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("title", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("content", Text, nullable=False, server_default=text("''")),
    Column("due_date", Date),
    Column("wake_id", UUID(as_uuid=True), ForeignKey("action.id", ondelete="RESTRICT")),
    Column("wake_at", DateTime(timezone=True)),
    Column("repeat", JSONB(none_as_null=True)),
    Column("wake_until", Date),
    Column("wake_local_date", Date),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint(
        "state IN ('doing_now','blocked','next_up','backlog','done','cancelled')",
        name="state",
    ),
    CheckConstraint(
        "title ~ '[^[:space:]]' AND octet_length(title) <= 240", name="title"
    ),
    CheckConstraint("octet_length(content) <= 8192", name="content"),
    CheckConstraint(
        "wake_until IS NULL OR (wake_at IS NOT NULL AND repeat IS NOT NULL)",
        name="wake_until",
    ),
    CheckConstraint(
        "((wake_id IS NULL AND wake_at IS NULL AND repeat IS NULL "
        "AND wake_local_date IS NULL) OR (wake_id IS NOT NULL "
        "AND wake_at IS NOT NULL AND state NOT IN ('done','cancelled') "
        "AND ((repeat IS NULL AND wake_local_date IS NULL) "
        "OR (jsonb_typeof(repeat) = 'object' AND "
        "((repeat->>'type' = 'interval' AND wake_local_date IS NULL) "
        "OR (repeat->>'type' IN ('daily','weekly','monthly') "
        "AND wake_local_date IS NOT NULL)))))) IS TRUE",
        name="schedule",
    ),
)
Index(
    "ix_work_due",
    work.c.wake_at,
    work.c.id,
    postgresql_where=work.c.wake_at.is_not(None),
)


gmail_usage = Table(
    "gmail_usage",
    metadata,
    Column("project_id", Text, primary_key=True),
    Column("pacific_day", Date, nullable=False),
    Column("units", Integer, nullable=False),
    CheckConstraint("length(project_id) > 0", name="project_id"),
    CheckConstraint("units BETWEEN 0 AND 5000", name="units"),
)


mail_editor_operation = Table(
    "mail_editor_operation",
    metadata,
    Column("google_sub", Text, primary_key=True),
    Column("draft_id", Text, primary_key=True),
    Column("generation", BigInteger, nullable=False, server_default=text("0")),
    Column("operation_id", UUID(as_uuid=True), unique=True),
    Column("kind", Text),
    Column("request_digest", Text),
    Column("base_revision", Text),
    Column("desired_digest", Text),
    Column("state", Text),
    Column("provider_result", JSONB(none_as_null=True)),
    Column(
        "updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("length(google_sub) > 0 AND length(draft_id) > 0", name="identity"),
    CheckConstraint(
        "(generation = 0 AND operation_id IS NULL AND kind IS NULL "
        "AND request_digest IS NULL AND base_revision IS NULL AND desired_digest IS "
        "NULL "
        "AND state IS NULL AND provider_result IS NULL) OR "
        "(generation > 0 AND operation_id IS NOT NULL AND kind IS NOT NULL "
        "AND request_digest IS NOT NULL AND base_revision IS NOT NULL "
        "AND desired_digest IS NOT NULL AND state IS NOT NULL "
        "AND request_digest ~ '^[0-9a-f]{64}$' AND base_revision ~ '^[0-9a-f]{64}$' "
        "AND desired_digest ~ '^[0-9a-f]{64}$' AND "
        "((kind='save' AND state IN ('entered','saved','failed','save_unknown')) OR "
        "(kind='send' AND state IN ('entered','sent','failed','send_unknown'))))",
        name="operation",
    ),
    CheckConstraint(
        "(CASE WHEN state='saved' THEN jsonb_typeof(provider_result)='object' "
        "AND provider_result ?& ARRAY['message_id','version','files','confirmation'] "
        "AND provider_result - "
        "ARRAY['message_id','version','files','confirmation']='{}'::jsonb "
        "WHEN state='sent' THEN jsonb_typeof(provider_result)='object' "
        "AND provider_result ? 'message_id' AND provider_result - "
        "'message_id'='{}'::jsonb "
        "ELSE provider_result IS NULL OR (jsonb_typeof(provider_result)='object' "
        "AND provider_result - ARRAY['ack_id','reason','retry_after']='{}'::jsonb) "
        "END) IS TRUE",
        name="result",
    ),
)


# Gmail progress is independent of conversation history and stores no provider content.
event_cursor = Table(
    "event_cursor",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("enabled", Boolean, nullable=False),
    Column("progress", JSONB, nullable=False),
    Column("next_poll_at", DateTime(timezone=True)),
    Column("last_success_at", DateTime(timezone=True)),
    Column("error", JSONB(none_as_null=True)),
    CheckConstraint("octet_length(account_id) BETWEEN 1 AND 1024", name="identity"),
    CheckConstraint(
        "((jsonb_typeof(progress) = 'object' AND progress ?& "
        "ARRAY['history_id','page_token','consumed','prefix_sha256'] AND "
        "progress - "
        "ARRAY['history_id','page_token','consumed','prefix_sha256'] = "
        "'{}'::jsonb AND jsonb_typeof(progress->'consumed')='number' AND "
        "(progress->>'consumed')::numeric BETWEEN 0 AND 9007199254740991 "
        "AND (progress->>'consumed')::numeric = "
        "trunc((progress->>'consumed')::numeric) AND "
        "((progress->>'consumed')::numeric = 0) = "
        "(progress->'prefix_sha256' = 'null'::jsonb) AND "
        "(progress->'prefix_sha256' = 'null'::jsonb OR "
        "progress->>'prefix_sha256' ~ '^[0-9a-f]{64}$') AND "
        "(progress->'history_id' <> 'null'::jsonb OR "
        "(progress->'page_token'='null'::jsonb AND "
        "(progress->>'consumed')::numeric=0))) IS TRUE"
        " OR (jsonb_typeof(progress) = 'object' "
        "AND progress ?& ARRAY['grant_id','label_id','ack','residual'] "
        "AND progress - ARRAY['grant_id','label_id','ack','residual'] = '{}'::jsonb "
        "AND jsonb_typeof(progress->'grant_id')='string' AND progress->>'grant_id' "
        "~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' "
        "AND jsonb_typeof(progress->'label_id')='string' "
        "AND octet_length(progress->>'label_id') BETWEEN 1 AND 1024 "
        "AND (progress->'ack'='null'::jsonb OR (progress->'residual'='null'::jsonb "
        "AND jsonb_typeof(progress->'ack')='object' "
        "AND (progress->'ack') ?& ARRAY['message_id','phase'] "
        "AND (progress->'ack') - ARRAY['message_id','phase']='{}'::jsonb "
        "AND jsonb_typeof(progress#>'{ack,message_id}')='string' "
        "AND octet_length(progress#>>'{ack,message_id}') BETWEEN 1 AND 1024 "
        "AND progress#>>'{ack,phase}' IN ('ready','entered'))) "
        "AND (progress->'residual'='null'::jsonb OR "
        "(jsonb_typeof(progress->'residual')='object' "
        "AND (progress->'residual') ?& ARRAY['total','recheck_at'] "
        "AND (progress->'residual') - ARRAY['total','recheck_at']='{}'::jsonb "
        "AND jsonb_typeof(progress#>'{residual,total}')='number' "
        "AND progress#>>'{residual,total}' ~ '^[1-9][0-9]*$' "
        "AND jsonb_typeof(progress#>'{residual,recheck_at}')='string'))) IS TRUE)",
        name="progress",
    ),
    CheckConstraint(
        "(error IS NULL OR (jsonb_typeof(error)='object' AND error ?& "
        "ARRAY['episode_id','code','since','retry_count'] AND error - "
        "ARRAY['episode_id','code','since','retry_count'] = '{}'::jsonb "
        "AND error->>'code' IN "
        "('TransportUnavailable','RateLimited','AuthUnavailable','Forbidden',"
        "'InvalidResponse','ResponseTooLarge','CursorExpired','AckUncertain',"
        "'ConsentRequired','LabelUnavailable','Partial') "
        "AND jsonb_typeof(error->'retry_count')='number' AND "
        "(error->>'retry_count')::numeric BETWEEN 1 AND 5 AND "
        "(error->>'retry_count')::numeric = "
        "trunc((error->>'retry_count')::numeric))) IS TRUE",
        name="error",
    ),
)


attachment = Table(
    "attachment",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("source", JSONB, nullable=False),
    Column("source_key", Text, nullable=False),
    Column(
        "origin_message_id",
        UUID(as_uuid=True),
        ForeignKey("message.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "capture_action_id",
        UUID(as_uuid=True),
        ForeignKey("action.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column("filename", Text),
    Column("media_type", Text),
    Column("advertised_size", BigInteger),
    Column("size_bytes", BigInteger),
    Column("sha256", Text),
    Column("state", Text, nullable=False),
    Column("prior_put_entered_at", DateTime(timezone=True)),
    Column("stored_at", DateTime(timezone=True)),
    Column("deleted_at", DateTime(timezone=True)),
    Column(
        "delete_action_id",
        UUID(as_uuid=True),
        ForeignKey("action.id", ondelete="RESTRICT"),
    ),
    Column("drive_subject", Text),
    Column("drive_file_id", Text),
    Column(
        "filing_action_id",
        UUID(as_uuid=True),
        ForeignKey("action.id", ondelete="RESTRICT"),
        unique=True,
    ),
    Column("verified_at", DateTime(timezone=True)),
    Column("disposition", Text),
    Column("error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("jarvis_attachment_source_valid(source)", name="source"),
    CheckConstraint(
        "source_key = jarvis_attachment_source_key(source)", name="source_key"
    ),
    CheckConstraint(
        "media_type IS NULL OR octet_length(media_type) <= 255", name="media_type"
    ),
    CheckConstraint(
        "advertised_size IS NULL OR advertised_size >= 0", name="advertised_size"
    ),
    CheckConstraint(
        "error IS NULL OR error IN ('NotFound','TooLarge','ProviderResponseTooLarge',"
        "'SourceChanged','Unavailable','Pending','CaptureUnresolved','StorageConflict',"
        "'Deleting','DeleteUnresolved','CacheCleanupFailed','Deleted')",
        name="error",
    ),
    CheckConstraint(
        "CASE WHEN source->>'kind' = 'web' THEN capture_action_id IS NULL "
        "AND size_bytes IS NOT NULL "
        "AND advertised_size IS NOT DISTINCT FROM size_bytes "
        "ELSE capture_action_id IS NOT NULL OR source->>'kind' = 'discord' END",
        name="capture",
    ),
    CheckConstraint(
        "((size_bytes IS NULL AND sha256 IS NULL) OR (size_bytes BETWEEN 0 AND "
        "104857600 AND sha256 ~ '^[0-9a-f]{64}$')) IS TRUE",
        name="bytes",
    ),
    CheckConstraint(
        "(drive_subject IS NULL AND drive_file_id IS NULL) OR "
        "(length(drive_subject) <= 255 AND drive_subject ~ '^[A-Za-z0-9_-]+$' "
        "AND length(drive_file_id) <= 255 "
        "AND drive_file_id ~ '^[A-Za-z0-9_-]+$') IS TRUE",
        name="drive_pair",
    ),
    CheckConstraint(
        """
        CASE state
         WHEN 'staged' THEN filing_action_id IS NULL AND drive_file_id IS NULL
            AND verified_at IS NULL AND disposition IS NULL
         WHEN 'filing' THEN filing_action_id IS NOT NULL AND drive_file_id IS NULL
            AND verified_at IS NULL AND disposition IS NULL
         WHEN 'uncertain' THEN filing_action_id IS NOT NULL AND drive_file_id IS NULL
            AND verified_at IS NULL AND disposition IS NULL
         WHEN 'created' THEN filing_action_id IS NOT NULL AND drive_file_id IS NOT NULL
            AND verified_at IS NULL AND disposition IS NULL
         WHEN 'filed' THEN drive_file_id IS NOT NULL
            AND (filing_action_id IS NOT NULL OR stored_at IS NOT NULL)
            AND verified_at IS NOT NULL AND disposition IS NULL
         WHEN 'unavailable' THEN verified_at IS NULL AND disposition IN
            ('historical_deleted','historical_failed','abandoned','abandoned_uncertain')
         ELSE false END IS TRUE
        """,
        name="state",
    ),
)
Index(
    "uq_attachment_active_source",
    attachment.c.source_key,
    unique=True,
    postgresql_where=attachment.c.state != "unavailable",
)
Index(
    "ix_attachment_unfiled",
    attachment.c.created_at,
    attachment.c.id,
    postgresql_where=attachment.c.state.in_(
        ("staged", "filing", "uncertain", "created")
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


def create_engine(database_url: str, *, memory_reads: int = 0) -> AsyncEngine:
    return create_async_engine(
        normalize_database_url(database_url),
        pool_pre_ping=True,
        **(
            {
                "pool_size": memory_reads,
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
