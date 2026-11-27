"""Cut over to ordinary scheduled work and durable workspace blocks."""

import json

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


# JSON string literals preserve the query and opaque calendar identifiers exactly.
CONVERTED_WORK_ROWS = """(
    SELECT id, title, state,
        content || CASE WHEN workspace_check IS NULL THEN '' ELSE
            E'\\n\\n' || concat_ws(E'\\n',
                'Use this Gmail query exactly ' ||
                    NULLIF(workspace_check->'gmail_query', 'null'::jsonb)::text,
                'Use these calendar IDs exactly ' ||
                    (workspace_check#>'{calendar,ids}')::text ||
                    '. Check from local midnight today through the next ' ||
                    (workspace_check#>>'{calendar,days_ahead}') ||
                    ' days, ending at local midnight.'
            )
        END AS content,
        due_date, wake_id, wake_at, repeat,
        (workspace_check->>'until')::date AS wake_until,
        wake_local_date, created_at, updated_at
    FROM public.work
)"""

INCOMPATIBLE_WORK = (
    """
    SELECT 'action' AS kind, id::text AS id, tool_name AS operation, status
    FROM action WHERE status IN ('queued','awaiting_approval','executing')
    UNION ALL
    SELECT 'human_mail', operation_id::text, kind, state
    FROM mail_editor_operation WHERE state = 'entered'
    UNION ALL
    SELECT 'attempt', id::text, 'native', 'unsealed' FROM native_attempt
    WHERE product_outcome IS NULL
        AND (fenced_at IS NULL OR recovery_pending OR terminal_at IS NOT NULL)
    UNION ALL
    SELECT 'input', id::text, source, coalesce(request_state,'undelivered')
    FROM message WHERE request_state IN ('pending','waiting')
        AND (source = 'recovery_catchup' OR home ? 'workspace_refresh'
             OR wait_reason = 'approval' OR native_retry_after IS NOT NULL
             OR (processing_parked_at IS NOT NULL
                 AND trace->>'failure_code' = 'native protocol requires repair')
             OR CASE WHEN source = 'work_wake' AND pg_input_is_valid(text, 'jsonb')
                      THEN (text::jsonb #> '{record,workspace_check}') <> 'null'::jsonb
                 END)
    UNION ALL
    SELECT 'source_ack', progress#>>'{ack,message_id}', 'gmail', 'entered'
    FROM event_cursor WHERE progress#>>'{ack,phase}' = 'entered'
    UNION ALL
    SELECT 'attachment', id::text, 'drive', state
    FROM attachment WHERE state IN ('filing', 'created')
    UNION ALL
    SELECT 'schedule', id::text, 'work', 'grant_unverified'
    FROM work WHERE workspace_check IS NOT NULL AND
        (workspace_check->>'grant_id') IS DISTINCT FROM :workspace_grant
    UNION ALL
    SELECT 'schedule', id::text, 'work', 'content_too_large'
    FROM """
    + CONVERTED_WORK_ROWS
    + """ AS work
    WHERE octet_length(content) > 8192
    ORDER BY 1,2
"""
)


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before the one-main cut")
    grant = op.get_context().config.attributes.get("workspace_grant")
    incompatible = [
        dict(row)
        for row in connection.execute(
            text(INCOMPATIBLE_WORK), {"workspace_grant": grant}
        ).mappings()
    ]
    if incompatible:
        raise RuntimeError(
            "settle incompatible predecessor work: " + json.dumps(incompatible)
        )
    op.execute("ALTER TABLE work ADD COLUMN wake_until date")
    op.execute(f"""
        UPDATE work SET content = converted.content, wake_until = converted.wake_until
        FROM {CONVERTED_WORK_ROWS} AS converted
        WHERE work.id = converted.id AND work.workspace_check IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE work DROP CONSTRAINT ck_work_workspace_check,
            DROP COLUMN workspace_check,
            ADD CONSTRAINT ck_work_wake_until CHECK
                (wake_until IS NULL OR (wake_at IS NOT NULL AND repeat IS NOT NULL));
        DROP FUNCTION jarvis_workspace_check_valid(jsonb);
        ALTER TABLE event_cursor DROP CONSTRAINT ck_event_cursor_error,
          ADD CONSTRAINT ck_event_cursor_error CHECK (
            (error IS NULL OR (jsonb_typeof(error)='object' AND error ?&
             ARRAY['episode_id','code','since','retry_count'] AND error -
             ARRAY['episode_id','code','since','retry_count'] = '{}'::jsonb AND
             error->>'code' IN ('TransportUnavailable','RateLimited','AuthUnavailable',
                 'Forbidden','InvalidResponse','ResponseTooLarge','CursorExpired',
                 'AckUncertain','ConsentRequired','LabelUnavailable','Partial')
             AND jsonb_typeof(error->'retry_count')='number'
             AND (error->>'retry_count')::numeric BETWEEN 1 AND 5
             AND (error->>'retry_count')::numeric
                 = trunc((error->>'retry_count')::numeric))) IS TRUE);


        CREATE TABLE workspace_block (
            id uuid CONSTRAINT pk_workspace_block PRIMARY KEY
                CONSTRAINT fk_workspace_block_id_message REFERENCES message(id),
            origin_kind text NOT NULL,
            origin_id uuid NOT NULL,
            product text NOT NULL,
            operation text NOT NULL,
            target_key text NOT NULL,
            reason text NOT NULL,
            remedy text NOT NULL,
            state text NOT NULL,
            grant_id uuid,
            operation_ref jsonb NOT NULL,
            revision bigint NOT NULL DEFAULT 1,
            retry_at timestamptz,
            updated_at timestamptz NOT NULL,
            notice_anchor uuid CONSTRAINT fk_workspace_block_notice_anchor_message
                REFERENCES message(id),
            CONSTRAINT ck_workspace_block_origin_kind CHECK
                (origin_kind IN ('read','write','verification','source')),
            CONSTRAINT ck_workspace_block_product CHECK
                (product IN ('gmail','calendar','drive','docs')),
            CONSTRAINT ck_workspace_block_target CHECK
                (length(operation) > 0 AND length(target_key) > 0),
            CONSTRAINT ck_workspace_block_reason CHECK
                (reason IN ('consent_required','consent_expired','approval_busy',
                    'denied',
                    'rate_limited','temporary','grant_unavailable','scope_missing',
                    'policy_block','withheld','partial','screened','not_found',
                    'invalid_response','unsupported','uncertain','precondition_failed',
                    'source_changed','exhausted','target_observed','target_differs',
                    'label_still_present')),
            CONSTRAINT ck_workspace_block_remedy CHECK
                (remedy IN ('wait','answer_google','reconnect','verify','none')),
            CONSTRAINT ck_workspace_block_state CHECK
                (state IN ('waiting','needs_owner','checking','resolved',
                    'denied','superseded')),
            CONSTRAINT ck_workspace_block_ref CHECK
                (jsonb_typeof(operation_ref) = 'object'),
            CONSTRAINT ck_workspace_block_revision CHECK (revision > 0)
        );
        CREATE UNIQUE INDEX uq_workspace_block_open_origin
            ON workspace_block(origin_kind, origin_id, product, operation, target_key)
            WHERE state IN ('waiting','needs_owner','checking');
        GRANT SELECT, INSERT ON workspace_block TO jarvis_runtime;
        GRANT UPDATE(reason, remedy, state, grant_id, operation_ref, revision,
                     retry_at, updated_at, notice_anchor)
            ON workspace_block TO jarvis_runtime;
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'jarvis_backup') THEN
                GRANT SELECT ON workspace_block TO jarvis_backup;
            END IF;
        END $$;

    """)


def downgrade() -> None:
    raise RuntimeError("one-main cut requires forward repair")
