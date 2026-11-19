"""Bound native reopening per waking input."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating native retry admission")
    op.execute("""
      ALTER TABLE message ADD COLUMN native_retry_after timestamptz;
      ALTER TABLE native_input_delivery
        ADD COLUMN was_waking boolean NOT NULL DEFAULT false;
      ALTER TABLE native_attempt
        ADD COLUMN recovery_pending boolean NOT NULL DEFAULT false;
      CREATE INDEX ix_native_attempt_pending_loss
        ON native_attempt(conversation_id,attempt_seq)
        WHERE recovery_pending AND fenced_at IS NOT NULL;
      GRANT UPDATE(native_retry_after) ON message TO jarvis_runtime;
      GRANT UPDATE(recovery_pending) ON native_attempt TO jarvis_runtime;
    """)


def downgrade() -> None:
    raise RuntimeError("native retry evidence requires forward repair")
