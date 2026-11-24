"""Cut native conversation capture at the existing checkpoints."""

import os

from alembic import op
from sqlalchemy import text, update
from universal_memory.archive import historical_workers
from universal_memory.schema import source_conversation

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


SOURCE_GUARD = """
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
            IF OLD.worker_excluded THEN
              IF NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'excluded worker progress is immutable';
              END IF;
            ELSIF NEW.worker_excluded THEN
              IF (to_jsonb(NEW) - 'worker_excluded') IS DISTINCT FROM
                 (to_jsonb(OLD) - 'worker_excluded') THEN
                RAISE EXCEPTION 'worker exclusion must freeze existing progress';
              END IF;
            ELSIF OLD.baseline_error IS NOT NULL THEN
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
                 'checkpoint_native_digest','checkpoint_capture_digest',
                 'last_read_at','capture_error'])
                 IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['checkpoint_event_id','checkpoint_native_digest',
                 'checkpoint_capture_digest','last_read_at','capture_error']) THEN
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
    """


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
