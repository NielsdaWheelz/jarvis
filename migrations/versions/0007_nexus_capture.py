"""Add explicit nexus source identity without changing retained evidence."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    if not connection.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("nexus capture adoption requires a stopped deployment")
    op.execute("""
      ALTER TABLE source_conversation
        ADD COLUMN capture_id uuid,
        ALTER COLUMN machine DROP NOT NULL,
        ALTER COLUMN account DROP NOT NULL,
        DROP CONSTRAINT ck_source_conversation_provider,
        ADD CONSTRAINT ck_source_conversation_provider
          CHECK (provider IN ('codex','claude','jarvis','nexus')),
        ADD CONSTRAINT ck_source_conversation_source_variant CHECK (
          (provider = 'nexus' AND capture_id IS NOT NULL
            AND machine IS NULL AND account IS NULL AND relation IS NULL
            AND parent_native_id IS NULL AND working_directory IS NULL)
          OR (provider <> 'nexus' AND capture_id IS NULL
            AND machine IS NOT NULL AND account IS NOT NULL)
        );
    """)
    # Existing table-level INSERT and column-specific UPDATE grants are sufficient.
    # The original guard already makes every non-progress field immutable.


def downgrade() -> None:
    raise RuntimeError("nexus capture retains originals; repair forward")
