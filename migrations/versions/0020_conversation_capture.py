"""Cut native conversation capture at the existing checkpoints."""

import os

from alembic import op
from sqlalchemy import text, update
from universal_memory.archive import historical_workers
from universal_memory.schema import SOURCE_GUARD, source_conversation

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0020"
down_revision = "0019"
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
            raise RuntimeError(
                "stop both writers before migrating conversation capture"
            )
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": scope},
    )
    if control != "pause":
        raise RuntimeError("conversation capture requires the canonical pause")

    op.execute("""
        ALTER TABLE source_conversation
            ADD COLUMN checkpoint_capture_digest text,
            ADD COLUMN worker_excluded boolean NOT NULL DEFAULT false,
            ADD CONSTRAINT ck_source_conversation_capture_digest CHECK (
                checkpoint_capture_digest IS NULL OR (provider IN ('codex','claude')
                AND checkpoint_event_id IS NOT NULL
                AND checkpoint_capture_digest ~ '^[0-9a-f]{64}$')
            ),
            ADD CONSTRAINT ck_source_conversation_worker_excluded CHECK (
                NOT worker_excluded OR provider IN ('codex','claude')
            );
        ALTER TABLE native_attempt
            ADD COLUMN stock_observations_pending boolean NOT NULL DEFAULT false,
            ADD CONSTRAINT ck_native_attempt_stock_observation_admitted CHECK (
                NOT stock_observations_pending OR memory_admitted
            );
        GRANT UPDATE (checkpoint_capture_digest, worker_excluded)
            ON source_conversation TO jarvis_memory;
        GRANT UPDATE (stock_observations_pending)
            ON native_attempt TO jarvis_runtime;
    """)
    op.execute(SOURCE_GUARD)
    connection.execute(
        update(source_conversation)
        .where(source_conversation.c.id.in_(historical_workers()))
        .values(worker_excluded=True)
    )


def downgrade() -> None:
    raise RuntimeError("conversation capture requires forward repair")
