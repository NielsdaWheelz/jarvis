"""Persist original paid inference decisions (ADR 0040).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_decision",
        sa.Column("decision_id", sa.Text(), primary_key=True),
        sa.Column("scope_key", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text()),
        sa.Column(
            "first_input_id",
            sa.UUID(),
            sa.ForeignKey("message.id", ondelete="RESTRICT"),
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        sa.Column("request", postgresql.JSONB(), nullable=False),
        sa.Column("terminal", postgresql.JSONB()),
        sa.Column("host_evidence", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "scope_key", "ordinal", name="uq_model_decision_scope_ordinal"
        ),
        sa.CheckConstraint("ordinal > 0", name="ordinal_positive"),
        sa.CheckConstraint(
            "decision_id ~ '^[0-9a-f]{64}$' AND request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="fingerprints",
        ),
        sa.CheckConstraint(
            "(thread_id IS NULL) = (first_input_id IS NULL)", name="thread_scope"
        ),
        sa.CheckConstraint("jsonb_typeof(request) = 'object'", name="request_object"),
        sa.CheckConstraint(
            "terminal IS NULL OR jsonb_typeof(terminal) = 'object'",
            name="terminal_object",
        ),
        sa.CheckConstraint(
            "(terminal IS NULL) = (completed_at IS NULL)", name="completion"
        ),
    )
    op.execute("GRANT SELECT, INSERT, DELETE ON model_decision TO jarvis_runtime")
    op.execute(
        "GRANT UPDATE (terminal, host_evidence, completed_at) "
        "ON model_decision TO jarvis_runtime"
    )

    op.create_table(
        "read_position",
        sa.Column("position", sa.Text(), primary_key=True),
        sa.Column("contract", postgresql.JSONB(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("reservation", postgresql.JSONB()),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("settlement", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "state IN ('prepared', 'dispatched', 'uncertain', 'completed')",
            name="state",
        ),
        sa.CheckConstraint("jsonb_typeof(contract) = 'object'", name="contract_object"),
        sa.CheckConstraint(
            "(state = 'completed') = (result IS NOT NULL AND settlement IS NOT NULL)",
            name="completion",
        ),
    )
    op.execute("GRANT SELECT, INSERT ON read_position TO jarvis_runtime")
    op.execute(
        "GRANT UPDATE (state, reservation, result, settlement, updated_at) "
        "ON read_position TO jarvis_runtime"
    )


def downgrade() -> None:
    op.drop_table("read_position")
    op.drop_table("model_decision")
