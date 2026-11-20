"""Private web conversation, uploads and notification links."""

import os

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0017"
down_revision = "0016"
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
            raise RuntimeError("stop both writers before migrating the private home")
    control = connection.scalar(
        text("""
            SELECT control_kind FROM message
            WHERE source_conversation_id = :scope AND control_kind IS NOT NULL
            ORDER BY control_sequence DESC LIMIT 1
        """),
        {"scope": scope},
    )
    if control != "pause":
        raise RuntimeError("the private home requires the canonical deployment pause")
    if connection.scalar(
        text("""
        SELECT EXISTS(SELECT FROM message WHERE source_conversation_id = :scope
            AND role = 'assistant' AND source_message_id IS NULL)
        OR EXISTS(SELECT FROM attachment WHERE source->>'kind' = 'discord'
                  AND state = 'pending')
        OR EXISTS(SELECT FROM action WHERE status IN
                  ('queued', 'awaiting_approval', 'executing'))
        OR EXISTS(SELECT FROM native_attempt WHERE product_outcome IS NULL
                  AND (fenced_at IS NULL OR terminal_at IS NOT NULL
                       OR recovery_pending))
    """),
        {"scope": scope},
    ):
        raise RuntimeError(
            "settle pending deliveries, captures, actions and native attempts"
            " before migration"
        )
    op.execute("""
      ALTER TABLE message ADD COLUMN home jsonb;
      DROP INDEX ix_message_delivery_pending;
      REVOKE UPDATE(source_message_id) ON message FROM jarvis_runtime;
      CREATE TABLE home_notice(
        id uuid CONSTRAINT pk_home_notice PRIMARY KEY, kind text NOT NULL,
        message_id uuid CONSTRAINT uq_home_notice_message_id UNIQUE
          CONSTRAINT fk_home_notice_message_id_message REFERENCES message,
        action_id uuid CONSTRAINT uq_home_notice_action_id UNIQUE
          CONSTRAINT fk_home_notice_action_id_action REFERENCES action,
        created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
        discord_message_id text,
        CONSTRAINT ck_home_notice_target CHECK (
          (kind IN ('reply','question') AND message_id IS NOT NULL
           AND action_id IS NULL)
          OR (kind='approval' AND message_id IS NULL AND action_id IS NOT NULL)));
      CREATE INDEX ix_home_notice_pending ON home_notice(created_at,id)
        WHERE discord_message_id IS NULL;
      GRANT SELECT, INSERT ON home_notice TO jarvis_runtime;
      GRANT UPDATE(discord_message_id) ON home_notice TO jarvis_runtime;
      CREATE OR REPLACE FUNCTION jarvis_attachment_source_valid(value jsonb)
      RETURNS boolean
      LANGUAGE plpgsql IMMUTABLE STRICT AS $$
      DECLARE field text; item jsonb;
      BEGIN
        IF jsonb_typeof(value) <> 'object' THEN RETURN false; END IF;
        IF value->>'kind' = 'web' THEN
          RETURN (value ?& ARRAY['kind','submission_id','slot']
            AND value - ARRAY['kind','submission_id','slot'] = '{}'::jsonb
            AND jsonb_typeof(value->'submission_id') = 'string'
            AND value->>'submission_id' ~ '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
            AND jsonb_typeof(value->'slot') = 'number'
            AND value->>'slot' ~ '^[0-9]$') IS TRUE;
        ELSIF value->>'kind' = 'discord' THEN
          IF NOT value ?& ARRAY['kind','guild_id','channel_id','message_id',
            'attachment_id'] OR value - ARRAY['kind','guild_id','channel_id',
            'message_id','attachment_id'] <> '{}'::jsonb THEN RETURN false; END IF;
          FOREACH field IN ARRAY ARRAY['guild_id','channel_id','message_id',
            'attachment_id'] LOOP
            IF jsonb_typeof(value->field) <> 'string'
              OR value->>field !~ '^[1-9][0-9]{0,19}$' THEN RETURN false; END IF;
            IF (value->>field)::numeric > 18446744073709551615
              THEN RETURN false; END IF;
          END LOOP;
          RETURN true;
        ELSIF value->>'kind' = 'gmail' THEN
          IF NOT value ?& ARRAY['kind','account','message_id','part_id'] OR
            value - ARRAY['kind','account','message_id','part_id'] <> '{}'::jsonb
            THEN RETURN false; END IF;
          FOREACH field IN ARRAY ARRAY['account','message_id','part_id'] LOOP
            item := value->field;
            IF jsonb_typeof(item) <> 'string' OR
              octet_length(value->>field) > 1024 OR
              (field <> 'part_id' AND octet_length(value->>field) = 0)
              THEN RETURN false; END IF;
          END LOOP;
          RETURN true;
        END IF;
        RETURN false;
      END $$;

      ALTER TABLE attachment DROP CONSTRAINT ck_attachment_capture;
      ALTER TABLE attachment ADD CONSTRAINT ck_attachment_capture CHECK (
        CASE WHEN source->>'kind' = 'web' THEN
          capture_action_id IS NULL AND size_bytes IS NOT NULL
          AND advertised_size IS NOT DISTINCT FROM size_bytes
        ELSE capture_action_id IS NOT NULL OR source->>'kind' = 'discord' END);
      ALTER TABLE message DROP CONSTRAINT ck_message_text_nonempty;
      ALTER TABLE message DROP CONSTRAINT ck_message_attachment_manifest;
      ALTER TABLE message ADD CONSTRAINT ck_message_attachment_manifest CHECK (
        NOT trace ? 'attachment_manifest' OR (role = 'owner' AND
          source IN ('discord','web') AND
          jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE);
      ALTER TABLE message ADD CONSTRAINT ck_message_text_nonempty CHECK (
        length(text) > 0 OR (role = 'owner' AND source IN ('discord','web') AND
          jarvis_attachment_manifest_valid(trace->'attachment_manifest')) IS TRUE);
    """)


def downgrade() -> None:
    raise RuntimeError("private web conversation requires forward repair")
