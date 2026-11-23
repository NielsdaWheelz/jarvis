"""Retire calendar polling and retain one Gmail cursor per verified account."""

import os

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0019"
down_revision = "0018"
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
            raise RuntimeError("stop both writers before retiring calendar polling")
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": scope},
    )
    if control != "pause":
        raise RuntimeError("retiring calendar polling requires the canonical pause")

    op.execute("""
        DELETE FROM event_cursor
            WHERE kind IN ('calendar_list', 'calendar_changes', 'calendar_upcoming');
        DROP INDEX ix_event_cursor_due;
        ALTER TABLE event_cursor
            DROP CONSTRAINT pk_event_cursor,
            DROP CONSTRAINT ck_event_cursor_kind,
            DROP CONSTRAINT ck_event_cursor_identity,
            DROP CONSTRAINT ck_event_cursor_scope,
            DROP CONSTRAINT ck_event_cursor_progress,
            DROP COLUMN kind,
            DROP COLUMN resource_id,
            DROP COLUMN seen_inventory_scan,
            ALTER COLUMN enabled SET NOT NULL,
            ADD CONSTRAINT pk_event_cursor PRIMARY KEY (account_id),
            ADD CONSTRAINT ck_event_cursor_identity
                CHECK (octet_length(account_id) BETWEEN 1 AND 1024),
            ADD CONSTRAINT ck_event_cursor_progress CHECK ((
                jsonb_typeof(progress) = 'object'
                AND progress ?&
                    ARRAY['history_id', 'page_token', 'consumed', 'prefix_sha256']
                AND progress -
                    ARRAY['history_id', 'page_token', 'consumed', 'prefix_sha256']
                    = '{}'::jsonb
                AND jsonb_typeof(progress->'consumed') = 'number'
                AND (progress->>'consumed')::numeric BETWEEN 0 AND 9007199254740991
                AND (progress->>'consumed')::numeric
                    = trunc((progress->>'consumed')::numeric)
                AND ((progress->>'consumed')::numeric = 0)
                    = (progress->'prefix_sha256' = 'null'::jsonb)
                AND (progress->'prefix_sha256' = 'null'::jsonb
                     OR progress->>'prefix_sha256' ~ '^[0-9a-f]{64}$')
                AND (progress->'history_id' <> 'null'::jsonb
                     OR (progress->'page_token' = 'null'::jsonb
                         AND (progress->>'consumed')::numeric = 0))
            ) IS TRUE);
    """)


def downgrade() -> None:
    raise RuntimeError("the Gmail-only cursor requires forward repair")
