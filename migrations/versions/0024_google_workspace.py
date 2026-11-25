"""Add checked standing rules and durable project usage without rewriting history."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating workspace access")
    op.execute("""
        CREATE FUNCTION jarvis_workspace_check_valid(rule jsonb) RETURNS boolean
        LANGUAGE sql IMMUTABLE STRICT
        SET search_path = pg_catalog
        AS $$
            SELECT (
                jsonb_typeof(rule) = 'object'
                AND rule ?& ARRAY['gmail_query','calendar','until','grant_id']
                AND rule - ARRAY['gmail_query','calendar','until','grant_id']
                    = '{}'::jsonb
                AND jsonb_typeof(rule->'grant_id') = 'string'
                AND rule->>'grant_id' ~
                    '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                AND (rule->'until' = 'null' OR (
                    jsonb_typeof(rule->'until') = 'string'
                    AND rule->>'until' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                    AND pg_input_is_valid(rule->>'until', 'date')
                ))
                AND (rule->'calendar' <> 'null' OR rule->'gmail_query' <> 'null')
                AND (rule->'gmail_query' = 'null' OR (
                    jsonb_typeof(rule->'gmail_query') = 'string'
                    AND octet_length(rule->>'gmail_query') <= 512
                    AND rule->>'gmail_query' ~ '[^[:space:]]'
                ))
                AND (rule->'calendar' = 'null' OR (
                    jsonb_typeof(rule->'calendar') = 'object'
                    AND (rule->'calendar') ?& ARRAY['ids','days_ahead']
                    AND (rule->'calendar') - ARRAY['ids','days_ahead'] = '{}'::jsonb
                    AND jsonb_typeof(rule#>'{calendar,days_ahead}') = 'number'
                    AND rule#>>'{calendar,days_ahead}' ~ '^([1-9]|[12][0-9]|3[01])$'
                    AND CASE WHEN jsonb_typeof(rule#>'{calendar,ids}') = 'array'
                         THEN (SELECT count(*) BETWEEN 1 AND 20
                            AND count(DISTINCT id) = count(*)
                            AND bool_and(jsonb_typeof(id) = 'string'
                                AND octet_length(id#>>'{}') <= 1024
                                AND id#>>'{}' ~ '[^[:space:]]')
                            FROM jsonb_array_elements(rule#>'{calendar,ids}')
                                AS parts(id))
                         ELSE false END
                ))
            ) IS TRUE
        $$;
        ALTER TABLE work ADD COLUMN workspace_check jsonb;
        ALTER TABLE work ADD CONSTRAINT ck_work_workspace_check CHECK (
            workspace_check IS NULL OR (wake_id IS NOT NULL AND wake_at IS NOT NULL
                AND repeat IS NOT NULL AND content ~ '[^[:space:]]'
                AND jarvis_workspace_check_valid(workspace_check)) IS TRUE
        );
        CREATE TABLE gmail_usage (
            project_id text CONSTRAINT pk_gmail_usage PRIMARY KEY,
            pacific_day date NOT NULL,
            units integer NOT NULL,
            CONSTRAINT ck_gmail_usage_project_id CHECK (length(project_id) > 0),
            CONSTRAINT ck_gmail_usage_units CHECK (units BETWEEN 0 AND 5000)
        );
        GRANT SELECT, INSERT, UPDATE ON gmail_usage TO jarvis_runtime;
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'jarvis_backup') THEN
                GRANT SELECT ON gmail_usage TO jarvis_backup;
            END IF;
        END $$;
        ALTER TABLE event_cursor DROP CONSTRAINT ck_event_cursor_progress,
            DROP CONSTRAINT ck_event_cursor_error;
    """)
    op.execute("""
        ALTER TABLE event_cursor ADD CONSTRAINT ck_event_cursor_error
            CHECK ((error IS NULL OR (jsonb_typeof(error)='object' AND error ?&
                ARRAY['episode_id','code','since','retry_count'] AND error -
                ARRAY['episode_id','code','since','retry_count'] = '{}'::jsonb AND
                error->>'code' IN
                ('TransportUnavailable','RateLimited','AuthUnavailable','Forbidden','InvalidResponse','ResponseTooLarge','CursorExpired','AckUncertain','ConsentRequired','LabelUnavailable')
                AND jsonb_typeof(error->'retry_count')='number' AND
                (error->>'retry_count')::numeric BETWEEN 1 AND 5 AND
                (error->>'retry_count')::numeric =
                trunc((error->>'retry_count')::numeric))) IS TRUE);
        ALTER TABLE event_cursor ADD CONSTRAINT ck_event_cursor_progress
            CHECK (((jsonb_typeof(progress) = 'object' AND progress ?&
                ARRAY['history_id','page_token','consumed','prefix_sha256'] AND
                progress - ARRAY['history_id','page_token','consumed','prefix_sha256']
                = '{}'::jsonb AND jsonb_typeof(progress->'consumed')='number' AND
                (progress->>'consumed')::numeric BETWEEN 0 AND 9007199254740991 AND
                (progress->>'consumed')::numeric =
                trunc((progress->>'consumed')::numeric) AND
                ((progress->>'consumed')::numeric = 0) = (progress->'prefix_sha256' =
                'null'::jsonb) AND (progress->'prefix_sha256' = 'null'::jsonb OR
                progress->>'prefix_sha256' ~ '^[0-9a-f]{64}$') AND
                (progress->'history_id' <> 'null'::jsonb OR
                (progress->'page_token'='null'::jsonb AND
                (progress->>'consumed')::numeric=0))) IS TRUE OR
                (jsonb_typeof(progress) = 'object' AND progress ?&
                ARRAY['grant_id','label_id','ack','residual'] AND progress -
                ARRAY['grant_id','label_id','ack','residual'] = '{}'::jsonb AND
                jsonb_typeof(progress->'grant_id')='string' AND progress->>'grant_id' ~
                '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' AND
                jsonb_typeof(progress->'label_id')='string' AND
                octet_length(progress->>'label_id') BETWEEN 1 AND 1024 AND
                (progress->'ack'='null'::jsonb OR (progress->'residual'='null'::jsonb
                AND jsonb_typeof(progress->'ack')='object' AND (progress->'ack') ?&
                ARRAY['message_id','phase'] AND (progress->'ack') -
                ARRAY['message_id','phase']='{}'::jsonb AND
                jsonb_typeof(progress#>'{ack,message_id}')='string' AND
                octet_length(progress#>>'{ack,message_id}') BETWEEN 1 AND 1024 AND
                progress#>>'{ack,phase}' IN ('ready','entered'))) AND
                (progress->'residual'='null'::jsonb OR
                (jsonb_typeof(progress->'residual')='object' AND (progress->'residual')
                ?& ARRAY['total','recheck_at'] AND (progress->'residual') -
                ARRAY['total','recheck_at']='{}'::jsonb AND
                jsonb_typeof(progress#>'{residual,total}')='number' AND
                progress#>>'{residual,total}' ~ '^[1-9][0-9]*$' AND
                jsonb_typeof(progress#>'{residual,recheck_at}')='string'))) IS TRUE));
    """)


def downgrade() -> None:
    raise RuntimeError("the Workspace connector cut requires forward repair")
