"""Move online vector writes to the memory service and index recent anchors."""

import os

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0018"
down_revision = "0017"
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
            raise RuntimeError("stop both writers before migrating memory freshness")
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": scope},
    )
    if control != "pause":
        raise RuntimeError("memory freshness requires the canonical deployment pause")
    op.execute("""
        GRANT UPDATE (embedding) ON source_record, memory_log, memory_summary
            TO jarvis_memory;
        REVOKE UPDATE (embedding) ON source_record, memory_log, memory_summary
            FROM jarvis_runtime;
        REVOKE INSERT ON source_record, memory_log FROM jarvis_runtime;
        GRANT INSERT (
            id, conversation_id, sequence, native_event_id, part, part_count,
            native_digest, turn_id, native_parent_id, role, kind, attributes,
            text, occurred_at, received_at
        ) ON source_record TO jarvis_runtime;
        GRANT INSERT (id, text, agent_submission, synthesis) ON memory_log
            TO jarvis_runtime;
        CREATE INDEX ix_source_record_recent_owner
            ON source_record (occurred_at DESC NULLS LAST, received_at DESC,
                              conversation_id, sequence DESC)
            WHERE role = 'owner' AND kind = 'text' AND part = 0;
    """)
    if not connection.scalar(
        text("""
            SELECT bool_and(
                has_column_privilege('jarvis_memory', name, 'embedding', 'UPDATE')
                AND NOT has_column_privilege(
                    'jarvis_runtime', name, 'embedding', 'UPDATE')
                AND NOT has_column_privilege(
                    'jarvis_memory', name, 'embedding', 'INSERT')
                AND NOT has_column_privilege(
                    'jarvis_runtime', name, 'embedding', 'INSERT')
                AND NOT has_table_privilege('jarvis_runtime', name, 'INSERT')
            )
            FROM (VALUES ('source_record'), ('memory_log'), ('memory_summary'))
                stores(name)
        """)
    ):
        raise RuntimeError("online vector writer privileges differ from the target")


def downgrade() -> None:
    raise RuntimeError("memory freshness requires forward repair")
