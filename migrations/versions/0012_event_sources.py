"""Atomic future-only email/calendar source progress.

Revision ID: 0012
Revises: 0011
"""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating event sources")
    op.execute("""
    CREATE TABLE event_cursor (
    kind TEXT NOT NULL,
    account_id TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    enabled BOOLEAN,
    progress JSONB NOT NULL,
    next_poll_at TIMESTAMP WITH TIME ZONE,
    last_success_at TIMESTAMP WITH TIME ZONE,
    error JSONB,
    seen_inventory_scan UUID,
    CONSTRAINT pk_event_cursor PRIMARY KEY (kind,  account_id,  resource_id),
    CONSTRAINT ck_event_cursor_kind CHECK (kind IN ('gmail', 'calendar_list',
    'calendar_changes', 'calendar_upcoming')),
    CONSTRAINT ck_event_cursor_identity CHECK (octet_length(account_id) BETWEEN 1
    AND 1024 AND octet_length(resource_id) <= 1024),
    CONSTRAINT ck_event_cursor_scope CHECK (((kind IN ('gmail', 'calendar_list') AND
    resource_id = '' AND enabled IS NOT NULL AND seen_inventory_scan IS NULL) OR
    (kind IN ('calendar_changes', 'calendar_upcoming') AND resource_id <> '' AND
    enabled IS NULL AND seen_inventory_scan IS NOT NULL)) IS TRUE),
    CONSTRAINT ck_event_cursor_progress CHECK ((jsonb_typeof(progress) = 'object'
    AND CASE kind WHEN 'gmail' THEN progress ?& ARRAY['history_id', 'page_token',
    'consumed', 'prefix_sha256'] AND progress - ARRAY['history_id', 'page_token',
    'consumed', 'prefix_sha256'] = '{}'::jsonb AND
    jsonb_typeof(progress->'consumed')='number' AND (progress->>'consumed')::numeric
    BETWEEN 0 AND 9007199254740991 AND (progress->>'consumed')::numeric =
    trunc((progress->>'consumed')::numeric) AND ((progress->>'consumed')::numeric =
    0) = (progress->'prefix_sha256' = 'null'::jsonb) AND (progress->'prefix_sha256'
    = 'null'::jsonb OR progress->>'prefix_sha256' ~ '^[0-9a-f]{64}$') AND
    (progress->'history_id' <> 'null'::jsonb OR
    (progress->'page_token'='null'::jsonb AND (progress->>'consumed')::numeric=0))
    WHEN 'calendar_list' THEN progress ?& ARRAY['scan_id', 'page_token'] AND
    progress - ARRAY['scan_id', 'page_token'] = '{}'::jsonb AND (progress->'scan_id'
    <> 'null'::jsonb OR progress->'page_token'='null'::jsonb) WHEN
    'calendar_changes' THEN progress ?& ARRAY['sync_token', 'page_token'] AND
    progress - ARRAY['sync_token', 'page_token'] = '{}'::jsonb WHEN
    'calendar_upcoming' THEN progress ?& ARRAY['calendar_zone', 'scan'] AND progress
    - ARRAY['calendar_zone', 'scan'] = '{}'::jsonb AND (progress->'scan' =
    'null'::jsonb OR (jsonb_typeof(progress->'scan')='object' AND progress->'scan'
    ?& ARRAY['as_of', 'owner_zone', 'owner_date', 'time_min', 'time_max',
    'page_token'] AND (progress->'scan') - ARRAY['as_of', 'owner_zone',
    'owner_date', 'time_min', 'time_max', 'page_token'] = '{}'::jsonb)) ELSE false
    END) IS TRUE),
    CONSTRAINT ck_event_cursor_error CHECK ((error IS NULL OR
    (jsonb_typeof(error)='object' AND error ?& ARRAY['episode_id', 'code', 'since',
    'retry_count'] AND error - ARRAY['episode_id', 'code', 'since', 'retry_count'] =
    '{}'::jsonb AND error->>'code' IN ('TransportUnavailable', 'RateLimited',
    'AuthUnavailable', 'Forbidden', 'InvalidResponse', 'ResponseTooLarge',
    'CursorExpired') AND jsonb_typeof(error->'retry_count')='number' AND
    (error->>'retry_count')::numeric BETWEEN 1 AND 5 AND
    (error->>'retry_count')::numeric = trunc((error->>'retry_count')::numeric))) IS
    TRUE)
    );
    CREATE INDEX ix_event_cursor_due ON event_cursor (next_poll_at,  kind,
    resource_id) WHERE next_poll_at IS NOT NULL;
    GRANT SELECT,  INSERT,  UPDATE,  DELETE ON event_cursor TO jarvis_runtime;
    """)


def downgrade() -> None:
    raise RuntimeError("event sources require forward repair")
