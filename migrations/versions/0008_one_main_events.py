"""Common waking requests and conversational approval receipts.

Revision ID: 0008
Revises: 0007
"""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating common main inputs")
    op.execute("""
      ALTER TABLE message ADD COLUMN parent_request_id uuid
        REFERENCES message(id) ON DELETE RESTRICT;
      ALTER TABLE action DROP CONSTRAINT ck_action_approval_message_required;
      ALTER TABLE native_invocation DROP CONSTRAINT ck_native_invocation_write_origin;
      ALTER TABLE native_invocation ADD CONSTRAINT ck_native_invocation_write_origin
        CHECK ((validation = 'accepted' AND frozen_contract->>'effect' = 'Write'
          AND tool_id NOT IN ('memory.save_note', 'approval.respond'))
          IS NOT DISTINCT FROM (request_message_id IS NOT NULL));

      UPDATE message event SET parent_request_id = original.origin_message_id,
        trace = event.trace || jsonb_build_object('action_id', original.id::text)
      FROM action original JOIN message parent ON parent.id = original.origin_message_id
      WHERE event.role = 'host'
        AND event.source_conversation_id = parent.source_conversation_id
        AND parent.role IN ('owner', 'host') AND parent.control_kind IS NULL
        AND ((event.source = 'action' AND event.source_message_id IN (
          original.id::text || ':' || 'succeeded', original.id::text || ':' || 'failed',
          original.id::text || ':' || 'uncertain',
          original.id::text || ':' || 'cancelled',
          original.id::text || ':' || 'queued'))
          OR (event.source = 'schedule_wake'
            AND event.source_message_id = original.id::text));

      UPDATE message SET request_state = 'pending'
      WHERE role = 'host' AND request_state IS NULL AND processed_at IS NULL;

      UPDATE message event SET request_state = 'completed'
      WHERE event.role = 'host' AND event.request_state IS NULL
        AND event.processed_at IS NOT NULL AND EXISTS (
          SELECT 1 FROM native_input_delivery delivery
          JOIN native_attempt attempt ON attempt.id = delivery.attempt_id
          WHERE delivery.message_id = event.id
            AND delivery.state IN ('sent', 'queued', 'recorded')
            AND attempt.product_outcome->>'status' = 'committed');

      UPDATE message SET request_state = 'waiting', wait_reason = 'configuration',
        processed_at = NULL, processing_parked_at = CURRENT_TIMESTAMP,
        trace = trace || '{"repair_reason":"historical_host_settlement"}'::jsonb
      WHERE role = 'host' AND request_state IS NULL;

      UPDATE message SET request_state = 'waiting', wait_reason = 'configuration',
        processed_at = NULL, processing_parked_at = CURRENT_TIMESTAMP,
        trace = trace || '{"repair_reason":"historical_action_parent"}'::jsonb
      WHERE role = 'host' AND source IN ('action', 'schedule_wake')
        AND parent_request_id IS NULL;

      CREATE FUNCTION jarvis_guard_message_cause() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.parent_request_id IS DISTINCT FROM OLD.parent_request_id
          OR NEW.trace->'action_id' IS DISTINCT FROM OLD.trace->'action_id'
          OR NEW.trace->'observed_at' IS DISTINCT FROM OLD.trace->'observed_at' THEN
          RAISE EXCEPTION 'message cause and observation identity are immutable';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER message_cause BEFORE UPDATE ON message
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_message_cause();
    """)


def downgrade() -> None:
    raise RuntimeError("one-main cutover preserves canonical effects; repair forward")
