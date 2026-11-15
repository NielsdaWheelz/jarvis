"""Common waking requests and conversational approval receipts.

Revision ID: 0009
Revises: 0008
"""

import json
from uuid import NAMESPACE_URL, UUID, uuid5

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0009"
down_revision = "0008"
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

    """)
    # Pre-native turns bound their delivered conclusion to the original claim,
    # captured inputs and exact prose. Preserve that proof before clearing an
    # ambiguous host's processed_at; migration history must not import runtime codecs.
    conclusions = (
        op.get_bind()
        .execute(
            text("""
      SELECT original.execution_contract->'input_message_ids' AS input_ids,
        original.execution_contract->>'claim_id' AS claim_id,
        original.execution_contract->>'through_checkpoint' AS checkpoint,
        origin.source_conversation_id AS scope,
        origin.trace->'settlement'->>'run_id' AS run_id,
        conclusion.id AS conclusion_id,
        encode(sha256(convert_to(conclusion.text, 'UTF8')), 'hex') AS digest
      FROM action original
      JOIN message origin ON origin.id = original.origin_message_id
      JOIN message conclusion ON conclusion.id::text =
        origin.trace->'settlement'->>'conclusion_message_id'
      WHERE original.status IN ('succeeded', 'failed')
        AND original.approval_message_id IS NULL
        AND origin.trace->'settlement'->>'conclusion_kind' = 'conversation'
        AND origin.trace->'settlement'->>'outcome' = 'answered'
        AND origin.trace->'settlement'->>'through_checkpoint' =
          original.execution_contract->>'through_checkpoint'
        AND jsonb_typeof(origin.trace->'settlement'->'run_id') = 'string'
        AND conclusion.role = 'assistant' AND conclusion.source = 'discord'
        AND conclusion.source_conversation_id = origin.source_conversation_id
        AND conclusion.source_message_id IS NOT NULL
        AND conclusion.processed_at = conclusion.created_at
        AND original.completed_at <= conclusion.created_at
        AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements_text(
            original.execution_contract->'input_message_ids') AS captured(value)
          LEFT JOIN message input ON input.id::text = captured.value
          WHERE input.id IS NULL OR input.role NOT IN ('owner', 'host')
            OR input.source_conversation_id <> origin.source_conversation_id
            OR input.processed_at IS DISTINCT FROM conclusion.created_at
            OR input.trace->'settlement' IS DISTINCT FROM origin.trace->'settlement'
        )
    """)
        )
        .mappings()
    )
    for row in conclusions:
        identity = json.dumps(
            [
                row["scope"],
                row["run_id"],
                row["claim_id"],
                row["checkpoint"],
                "conversation",
                "answered",
                row["digest"],
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if (
            uuid5(NAMESPACE_URL, f"jarvis-conclusion-v1:{identity}")
            != row["conclusion_id"]
        ):
            continue
        op.get_bind().execute(
            text("""UPDATE message SET request_state = 'completed'
              WHERE id = ANY(:input_ids) AND role = 'host'
                AND request_state IS NULL"""),
            {"input_ids": [UUID(value) for value in row["input_ids"]]},
        )
    op.execute("""
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
