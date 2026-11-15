"""Mutable todos and their current schedules.

Revision ID: 0010
Revises: 0009
"""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating work records")
    op.execute("""
      CREATE TABLE work (
        id uuid PRIMARY KEY,
        title text NOT NULL CONSTRAINT ck_work_title
          CHECK (title ~ '[^[:space:]]' AND octet_length(title) <= 240),
        state text NOT NULL CONSTRAINT ck_work_state
          CHECK (state IN (
            'doing_now','blocked','next_up','backlog','done','cancelled')),
        content text NOT NULL DEFAULT '' CONSTRAINT ck_work_content
          CHECK (octet_length(content) <= 8192),
        due_date date,
        wake_id uuid REFERENCES action(id) ON DELETE RESTRICT,
        wake_at timestamptz,
        repeat jsonb,
        wake_local_date date,
        created_at timestamptz NOT NULL,
        updated_at timestamptz NOT NULL,
        CONSTRAINT ck_work_schedule CHECK ((
          (wake_id IS NULL AND wake_at IS NULL AND repeat IS NULL
            AND wake_local_date IS NULL)
          OR (wake_id IS NOT NULL AND wake_at IS NOT NULL
            AND state NOT IN ('done','cancelled') AND
            ((repeat IS NULL AND wake_local_date IS NULL)
            OR (jsonb_typeof(repeat) = 'object' AND
              ((repeat->>'type' = 'interval' AND wake_local_date IS NULL)
              OR (repeat->>'type' IN ('daily','weekly','monthly')
                AND wake_local_date IS NOT NULL)))))
        ) IS TRUE)
      );
      CREATE INDEX ix_work_due ON work (wake_at,id) WHERE wake_at IS NOT NULL;
      GRANT SELECT, INSERT, UPDATE, DELETE ON work TO jarvis_runtime;
    """)


def downgrade() -> None:
    raise RuntimeError("work records require forward repair")
