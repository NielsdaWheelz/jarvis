"""Admit desktop as a native memory host."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before admitting a memory host")
    op.execute("""
        ALTER TABLE memory_lane
          DROP CONSTRAINT ck_memory_lane_machine,
          ADD CONSTRAINT ck_memory_lane_machine CHECK (
            machine IN ('macbook', 'arch', 'devbox', 'desktop')
          )
    """)


def downgrade() -> None:
    raise RuntimeError("native memory retains originals; repair forward")
