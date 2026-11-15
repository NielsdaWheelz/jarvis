"""Admit the configured claude-work2 account and expose runtime schema identity."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if not connection.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError(
            "native memory profile adoption requires a stopped deployment"
        )
    op.execute("""
      ALTER TABLE memory_lane
        DROP CONSTRAINT ck_memory_lane_account,
        ADD CONSTRAINT ck_memory_lane_account CHECK (
          account IN ('codex-personal','codex-work','codex-work2',
            'claude-personal','claude-work','claude-work2','jarvis')
        );
      GRANT SELECT ON alembic_version TO jarvis_runtime;
    """)


def downgrade() -> None:
    raise RuntimeError("native memory retains originals; repair forward")
