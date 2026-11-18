"""Grant the independent memory writer its archive privileges."""

import os

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    channel_id = os.environ.get("JARVIS_DISCORD_CHANNEL_ID")
    if not channel_id:
        raise RuntimeError("JARVIS_DISCORD_CHANNEL_ID is required for the pause check")
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating memory grants")
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": channel_id},
    )
    if control != "pause":
        raise RuntimeError("memory grants require the canonical deployment pause")
    op.execute("""
        GRANT USAGE ON SCHEMA public TO jarvis_memory;
        GRANT SELECT ON alembic_version, memory_lane, source_conversation,
            source_record, memory_log, memory_summary, memory_leaf, memory_node,
            memory_state TO jarvis_memory;
        GRANT INSERT ON memory_lane, source_conversation, memory_leaf TO jarvis_memory;
        GRANT INSERT (id, text, agent_submission) ON memory_log TO jarvis_memory;
        GRANT INSERT (
            id, conversation_id, sequence, native_event_id, part, part_count,
            native_digest, turn_id, native_parent_id, role, kind, attributes,
            text, occurred_at, received_at
        ) ON source_record TO jarvis_memory;
        GRANT UPDATE (last_inventory_at) ON memory_lane TO jarvis_memory;
        GRANT UPDATE (leaf_count) ON memory_state TO jarvis_memory;
        GRANT UPDATE (
            checkpoint_event_id, checkpoint_native_digest, last_read_at,
            capture_error, baseline_error, capture_after_event_id, captured_from
        ) ON source_conversation TO jarvis_memory;
    """)


def downgrade() -> None:
    raise RuntimeError("independent memory serving requires forward repair")
