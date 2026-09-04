"""Create the four-table v1 schema.

Revision ID: 0001
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_conversation_id", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "processing_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "processing_parked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("remembered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "trace",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "processing_attempts >= 0",
            name=op.f("ck_message_attempts_nonnegative"),
        ),
        sa.CheckConstraint(
            "length(source_conversation_id) > 0",
            name=op.f("ck_message_source_conversation_nonempty"),
        ),
        sa.CheckConstraint(
            "length(source) > 0",
            name=op.f("ck_message_source_nonempty"),
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'assistant', 'host')",
            name=op.f("ck_message_role"),
        ),
        sa.CheckConstraint(
            "length(text) > 0",
            name=op.f("ck_message_text_nonempty"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(trace) = 'object'",
            name=op.f("ck_message_trace_object"),
        ),
        sa.CheckConstraint(
            "pg_column_size(trace) <= 16384",
            name=op.f("ck_message_trace_bounded"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message")),
        sa.UniqueConstraint(
            "source",
            "source_message_id",
            name="uq_message_source_identity",
        ),
    )
    op.create_index(
        "ix_message_delivery_pending",
        "message",
        ["created_at", "id"],
        unique=False,
        postgresql_where=sa.text("role = 'assistant' AND source_message_id IS NULL"),
    )
    op.create_index(
        "ix_message_waking_pending",
        "message",
        ["source_conversation_id", "created_at", "id"],
        unique=False,
        postgresql_where=sa.text(
            "role IN ('owner', 'host') AND processed_at IS NULL "
            "AND processing_parked_at IS NULL"
        ),
    )

    op.create_table(
        "memory_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.VECTOR(dim=1536),
            nullable=True,
        ),
        sa.CheckConstraint(
            "length(text) > 0",
            name=op.f("ck_memory_log_text_nonempty"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_log")),
    )
    op.create_table(
        "memory_summary",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "source_memory_ids",
            postgresql.ARRAY(sa.UUID()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "embedding",
            pgvector.sqlalchemy.VECTOR(dim=1536),
            nullable=True,
        ),
        sa.CheckConstraint(
            "cardinality(source_memory_ids) > 0",
            name=op.f("ck_memory_summary_source_memory_ids_nonempty"),
        ),
        sa.CheckConstraint(
            "length(text) > 0",
            name=op.f("ck_memory_summary_text_nonempty"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_summary")),
    )
    op.create_table(
        "action",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tool_name", sa.Text(), nullable=False),
        sa.Column(
            "arguments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "execution_contract",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("execute_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("origin_message_id", sa.UUID(), nullable=False),
        sa.Column("approval_message_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.CheckConstraint(
            "status <> 'awaiting_approval' OR approval_message_id IS NOT NULL",
            name=op.f("ck_action_approval_message_required"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(arguments) = 'object'",
            name=op.f("ck_action_arguments_object"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_action_attempts_nonnegative"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(execution_contract) = 'object'",
            name=op.f("ck_action_execution_contract_object"),
        ),
        sa.CheckConstraint(
            "result IS NULL OR jsonb_typeof(result) = 'object'",
            name=op.f("ck_action_result_object"),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'awaiting_approval', 'executing', "
            "'succeeded', 'failed', 'uncertain', 'cancelled')",
            name=op.f("ck_action_status"),
        ),
        sa.CheckConstraint(
            "(status IN ('succeeded', 'failed', 'uncertain', 'cancelled')) "
            "= (completed_at IS NOT NULL)",
            name=op.f("ck_action_terminal_completion"),
        ),
        sa.CheckConstraint(
            "length(tool_name) > 0",
            name=op.f("ck_action_tool_name_nonempty"),
        ),
        sa.ForeignKeyConstraint(
            ["approval_message_id"],
            ["message.id"],
            name=op.f("fk_action_approval_message_id_message"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["origin_message_id"],
            ["message.id"],
            name=op.f("fk_action_origin_message_id_message"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_action")),
        sa.UniqueConstraint(
            "approval_message_id",
            name=op.f("uq_action_approval_message_id"),
        ),
    )
    op.create_index(
        "ix_action_status_execute_after",
        "action",
        ["status", "execute_after"],
        unique=False,
    )

    op.execute(
        """
        CREATE FUNCTION jarvis_guard_memory_log() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
            RAISE EXCEPTION 'memory_log rows are append-only';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.text IS DISTINCT FROM OLD.text
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'memory_log canonical fields are immutable';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_log_append_only
        BEFORE UPDATE OR DELETE ON memory_log
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_memory_log()
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_log_no_truncate
        BEFORE TRUNCATE ON memory_log
        FOR EACH STATEMENT EXECUTE FUNCTION jarvis_guard_memory_log()
        """
    )
    op.execute(
        """
        CREATE FUNCTION jarvis_guard_action_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF NEW.tool_name IS DISTINCT FROM OLD.tool_name
             OR NEW.arguments IS DISTINCT FROM OLD.arguments
             OR NEW.execution_contract IS DISTINCT FROM OLD.execution_contract
             OR NEW.origin_message_id IS DISTINCT FROM OLD.origin_message_id THEN
            RAISE EXCEPTION 'action identity fields are immutable';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER action_identity_immutable
        BEFORE UPDATE ON action
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_action_identity()
        """
    )
    op.execute("REVOKE DELETE, TRUNCATE ON TABLE memory_log FROM PUBLIC")
    op.execute("REVOKE UPDATE (id, text, created_at) ON TABLE memory_log FROM PUBLIC")
    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO jarvis_runtime")
    op.execute("GRANT SELECT, INSERT ON TABLE message TO jarvis_runtime")
    op.execute(
        "GRANT UPDATE (source_message_id, processed_at, processing_attempts, "
        "processing_parked_at, remembered_at, trace) ON TABLE message "
        "TO jarvis_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON TABLE memory_log TO jarvis_runtime")
    op.execute("GRANT UPDATE (embedding) ON TABLE memory_log TO jarvis_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE memory_summary "
        "TO jarvis_runtime"
    )
    op.execute("GRANT SELECT, INSERT ON TABLE action TO jarvis_runtime")
    op.execute(
        "GRANT UPDATE (status, attempts, approval_message_id, decided_at, "
        "completed_at, result) ON TABLE action TO jarvis_runtime"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER action_identity_immutable ON action")
    op.execute("DROP FUNCTION jarvis_guard_action_identity()")
    op.execute("DROP TRIGGER memory_log_no_truncate ON memory_log")
    op.execute("DROP TRIGGER memory_log_append_only ON memory_log")
    op.execute("DROP FUNCTION jarvis_guard_memory_log()")
    op.drop_index("ix_action_status_execute_after", table_name="action")
    op.drop_table("action")
    op.drop_table("memory_summary")
    op.drop_table("memory_log")
    op.drop_index("ix_message_waking_pending", table_name="message")
    op.drop_index("ix_message_delivery_pending", table_name="message")
    op.drop_table("message")
