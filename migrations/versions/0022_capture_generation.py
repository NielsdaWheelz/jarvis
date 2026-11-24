"""Fence native capture mutations across selected-history rewinds."""

import os

from alembic import op
from sqlalchemy import text
from universal_memory.schema import SOURCE_GUARD

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    scope = os.environ.get("JARVIS_OWNER_SCOPE")
    if not scope:
        raise RuntimeError("JARVIS_OWNER_SCOPE is required for the pause check")
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating native capture")
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": scope},
    )
    if control != "pause":
        raise RuntimeError("native capture migration requires the canonical pause")

    op.execute("""
        ALTER TABLE source_conversation
            ADD COLUMN capture_generation bigint NOT NULL DEFAULT 0,
            ADD CONSTRAINT ck_source_conversation_capture_generation CHECK (
                capture_generation >= 0
                AND (capture_generation = 0
                     OR (provider IN ('codex','claude') AND baseline_error IS NULL))
            );
        GRANT UPDATE (capture_generation) ON source_conversation TO jarvis_memory;
    """)
    op.execute(SOURCE_GUARD)


def downgrade() -> None:
    raise RuntimeError("native capture requires forward repair")
