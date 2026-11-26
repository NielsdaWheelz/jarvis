"""Fence direct owner mail edits and sends on their exact Gmail draft."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating the mail editor")
    op.execute("""
        CREATE TABLE mail_editor_operation (
          google_sub text NOT NULL, draft_id text NOT NULL, generation bigint DEFAULT
            0 NOT NULL,
          operation_id uuid, kind text, request_digest text, base_revision text,
          desired_digest text, state text, provider_result jsonb, updated_at
            timestamptz DEFAULT now() NOT NULL,
          CONSTRAINT pk_mail_editor_operation PRIMARY KEY (google_sub,draft_id),
          CONSTRAINT uq_mail_editor_operation_operation_id UNIQUE (operation_id),
          CONSTRAINT ck_mail_editor_operation_identity CHECK (length(google_sub)>0 AND
            length(draft_id)>0),
          CONSTRAINT ck_mail_editor_operation_operation CHECK (
            (generation=0 AND operation_id IS NULL AND kind IS NULL AND request_digest
              IS NULL
             AND base_revision IS NULL AND desired_digest IS NULL AND state IS NULL
               AND provider_result IS NULL)
            OR (generation>0 AND operation_id IS NOT NULL AND kind IS NOT NULL AND
              state IS NOT NULL
             AND request_digest IS NOT NULL AND base_revision IS NOT NULL AND
               desired_digest IS NOT NULL
             AND request_digest ~ '^[0-9a-f]{64}$' AND base_revision ~
               '^[0-9a-f]{64}$'
             AND desired_digest ~ '^[0-9a-f]{64}$'
             AND ((kind='save' AND state IN
               ('entered','saved','failed','save_unknown'))
               OR (kind='send' AND state IN
                 ('entered','sent','failed','send_unknown'))))),
          CONSTRAINT ck_mail_editor_operation_result CHECK ((CASE
            WHEN state='saved' THEN jsonb_typeof(provider_result)='object'
             AND provider_result ?&
               ARRAY['message_id','version','files','confirmation']
             AND provider_result -
               ARRAY['message_id','version','files','confirmation']='{}'::jsonb
            WHEN state='sent' THEN jsonb_typeof(provider_result)='object'
             AND provider_result ? 'message_id' AND provider_result -
               'message_id'='{}'::jsonb
            ELSE provider_result IS NULL OR (jsonb_typeof(provider_result)='object'
             AND provider_result - ARRAY['ack_id','reason','retry_after']='{}'::jsonb)
               END) IS TRUE)
        );
        GRANT SELECT, INSERT, UPDATE ON mail_editor_operation TO jarvis_runtime;
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname='jarvis_backup') THEN
            GRANT SELECT ON mail_editor_operation TO jarvis_backup;
          END IF;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError(
        "owner mail receipts preserve effect uncertainty; repair forward"
    )
