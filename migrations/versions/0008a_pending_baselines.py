"""Establish each native conversation baseline independently."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0008a"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError(
            "pending memory baseline adoption requires a stopped deployment"
        )
    op.execute("""
      ALTER TABLE source_conversation
        ADD COLUMN baseline_error text,
        ADD CONSTRAINT ck_source_conversation_baseline_error CHECK (
          baseline_error IS NULL OR baseline_error IN
            ('unavailable','unsupported','event_too_large','history_changed',
             'activation_boundary_lost','source_conflict')),
        ADD CONSTRAINT ck_source_conversation_pending_baseline CHECK (
          baseline_error IS NULL OR (provider IN ('codex','claude')
            AND capture_after_event_id IS NULL AND checkpoint_event_id IS NULL
            AND checkpoint_native_digest IS NULL AND last_read_at IS NULL
            AND capture_error IS NULL));
      GRANT UPDATE(baseline_error,capture_after_event_id,captured_from)
        ON source_conversation TO jarvis_runtime;
    """)
    # Freeze this revision's guard; later library changes need their own migration.
    op.execute("""
        CREATE OR REPLACE FUNCTION memory_guard_original() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP IN ('DELETE','TRUNCATE') THEN
            RAISE EXCEPTION 'memory originals are append-only';
          END IF;
          IF TG_OP = 'INSERT' THEN
            IF TG_TABLE_NAME = 'memory_log' THEN
              IF (NEW.agent_submission IS NULL) = (NEW.synthesis IS NULL) THEN
                RAISE EXCEPTION 'new notes require exactly one provenance variant';
              END IF;
            END IF;
            RETURN NEW;
          END IF;
          IF TG_TABLE_NAME = 'memory_lane' THEN
            IF (to_jsonb(NEW) - 'last_inventory_at') IS DISTINCT FROM
               (to_jsonb(OLD) - 'last_inventory_at') THEN
              RAISE EXCEPTION 'memory lane identity is immutable';
            END IF;
          ELSIF TG_TABLE_NAME = 'source_conversation' THEN
            IF OLD.baseline_error IS NOT NULL THEN
              IF NEW.baseline_error IS NOT NULL THEN
                IF (to_jsonb(NEW) - 'baseline_error') IS DISTINCT FROM
                   (to_jsonb(OLD) - 'baseline_error') THEN
                  RAISE EXCEPTION 'pending baseline permits only an error update';
                END IF;
              ELSIF (to_jsonb(NEW) - ARRAY['baseline_error','capture_after_event_id',
                       'captured_from']) IS DISTINCT FROM
                    (to_jsonb(OLD) - ARRAY['baseline_error','capture_after_event_id',
                       'captured_from']) THEN
                RAISE EXCEPTION 'baseline resolution cannot change source progress';
              END IF;
            ELSIF (to_jsonb(NEW) - ARRAY['checkpoint_event_id',
                 'checkpoint_native_digest','last_read_at','capture_error'])
                 IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['checkpoint_event_id','checkpoint_native_digest',
                 'last_read_at','capture_error']) THEN
              RAISE EXCEPTION 'source conversation identity is immutable';
            END IF;
          ELSIF TG_TABLE_NAME IN ('source_record','memory_log') THEN
            IF (to_jsonb(NEW) - 'embedding') IS DISTINCT FROM
               (to_jsonb(OLD) - 'embedding') THEN
              RAISE EXCEPTION 'memory original is immutable';
            END IF;
          ELSE
            RAISE EXCEPTION 'memory leaf links are immutable';
          END IF;
          RETURN NEW;
        END $$
    """)


def downgrade() -> None:
    raise RuntimeError("native memory retains originals and cuts; repair forward")
