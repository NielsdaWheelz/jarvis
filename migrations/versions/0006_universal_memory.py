"""Admitted archive, shared memory tree and canonical publication eligibility."""

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

from alembic import op
from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import Connection
from universal_memory.schema import (
    MEMORY_TABLES,
    guard_statements,
    memory_lane,
    memory_leaf,
    memory_log,
    memory_node,
    memory_state,
    memory_summary,
    source_conversation,
    source_record,
)

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _original_digests(connection: Connection) -> tuple[tuple[int, str], ...]:
    originals = (
        "SELECT jsonb_build_array(id, role, text, source, source_conversation_id, "
        "source_message_id, created_at, processed_at)::text FROM message ORDER BY id",
        "SELECT jsonb_build_array(id, text, created_at)::text "
        "FROM memory_log ORDER BY id",
        "SELECT jsonb_build_array(id, text, created_at, source_memory_ids)::text "
        "FROM memory_summary ORDER BY id",
    )
    values: list[tuple[int, str]] = []
    for query in originals:
        digest, count = hashlib.sha256(), 0
        for row in connection.execute(text(query)):
            value = row[0].encode()
            digest.update(len(value).to_bytes(8, "big"))
            digest.update(value)
            count += 1
        values.append((count, digest.hexdigest()))
    return tuple(values)


def upgrade() -> None:
    connection = op.get_bind()
    if not connection.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("universal memory cutover requires a stopped deployment")
    # This is the old sweep's predicate, including its damaged-trace fallback.
    # Parked rows remain in the selection and therefore block destructive cutover.
    pending = connection.scalar(
        text("""
      SELECT id FROM message
      WHERE role = 'owner' AND processed_at IS NOT NULL AND remembered_at IS NULL
      AND (
        trace->'settlement' @> '{"conclusion_kind":"conversation"}'::jsonb
          AND trace->'settlement'->>'outcome' IN
              ('answered','partial','needs_input','failed','host_fallback','waiting')
        OR trace->'settlement' @>
          '{"conclusion_kind":"silent","outcome":"silent"}'::jsonb
        OR trace->'settlement' @>
          '{"conclusion_kind":"suspension","outcome":"user"}'::jsonb
        OR NOT coalesce(
          jsonb_typeof(trace->'settlement') = 'object'
          AND jsonb_typeof(trace->'settlement'->'run_id') = 'string'
          AND length(trace->'settlement'->>'run_id') > 0
          AND jsonb_typeof(trace->'settlement'->'through_checkpoint') = 'string'
          AND length(trace->'settlement'->>'through_checkpoint') > 0
          AND (trace->'settlement'->'conclusion_message_id' IS NULL
            OR jsonb_typeof(trace->'settlement'->'conclusion_message_id') = 'null'
            OR (jsonb_typeof(trace->'settlement'->'conclusion_message_id') = 'string'
              AND length(trace->'settlement'->>'conclusion_message_id') > 0))
          AND jsonb_typeof(trace->'settlement'->'conclusion_kind') = 'string'
          AND length(trace->'settlement'->>'conclusion_kind') > 0
          AND jsonb_typeof(trace->'settlement'->'outcome') = 'string'
          AND length(trace->'settlement'->>'outcome') > 0,
          false)
      ) LIMIT 1
    """)
    )
    if pending is not None:
        raise RuntimeError(
            "drain the old rememberer sweep before universal memory cutover"
        )
    unresolved = connection.scalar(
        text("""
      SELECT decision_id FROM model_decision
      WHERE (request->>'operation_id' LIKE 'jarvis-remember:%'
          OR request->>'operation_id' LIKE 'jarvis-dream:%'
          OR request->>'operation_id' LIKE 'jarvis-recall:%')
        AND terminal IS NULL AND submission IS NULL LIMIT 1
    """)
    )
    if unresolved is not None:
        raise RuntimeError(
            "unresolved old memory cognition blocks universal memory cutover"
        )

    originals = _original_digests(connection)

    op.execute("""
      ALTER TABLE message ADD COLUMN memory_admitted boolean NOT NULL DEFAULT false;
      ALTER TABLE native_attempt
        ADD COLUMN memory_admitted boolean NOT NULL DEFAULT false;
      ALTER TABLE memory_log
        ADD COLUMN agent_submission jsonb, ADD COLUMN synthesis jsonb;
      ALTER TABLE memory_log ADD CONSTRAINT ck_memory_log_provenance_variant
        CHECK (NOT (agent_submission IS NOT NULL AND synthesis IS NOT NULL));
      ALTER TABLE native_invocation DROP CONSTRAINT ck_native_invocation_write_origin;
      ALTER TABLE native_invocation ADD CONSTRAINT ck_native_invocation_write_origin
        CHECK ((validation = 'accepted' AND frozen_contract->>'effect' = 'Write'
          AND tool_id <> 'memory.save_note') IS NOT DISTINCT FROM
          (request_message_id IS NOT NULL));
      REVOKE UPDATE(remembered_at) ON message FROM jarvis_runtime;
      ALTER TABLE message DROP COLUMN remembered_at;
      REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON memory_summary FROM jarvis_runtime;
      GRANT UPDATE(embedding) ON memory_summary TO jarvis_runtime;
    """)
    for table in MEMORY_TABLES:
        table.create(connection)
    for table in (memory_log, memory_summary, source_record):
        for index in table.indexes:
            index.create(connection, checkfirst=True)
    connection.execute(insert(memory_state).values(id=1))
    # A stopped declaration owns the initial internal lane. Later admission can
    # activate its empty baseline without admitting any pre-cutover canonical row.
    configuration = os.environ.get("JARVIS_MEMORY_CONFIG_PATH")
    if configuration is None:
        raise RuntimeError(
            "JARVIS_MEMORY_CONFIG_PATH is required for universal memory cutover"
        )
    from jarvis.memory_config import MemoryConfig

    if MemoryConfig.load(Path(configuration)).jarvis_admitted:
        connection.execute(
            insert(memory_lane).values(
                machine="devbox",
                account="jarvis",
                provider="jarvis",
                activated_at=datetime.now(UTC),
                last_inventory_at=datetime.now(UTC),
            )
        )
    for statement in guard_statements():
        op.execute(statement)
    op.execute("""
      CREATE FUNCTION jarvis_guard_memory_eligibility() RETURNS trigger
      LANGUAGE plpgsql AS $$
      BEGIN
        IF NEW.memory_admitted IS DISTINCT FROM OLD.memory_admitted THEN
          RAISE EXCEPTION 'memory publication eligibility is immutable';
        END IF;
        RETURN NEW;
      END $$;
      CREATE TRIGGER message_memory_eligibility BEFORE UPDATE ON message
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_memory_eligibility();
      CREATE TRIGGER attempt_memory_eligibility BEFORE UPDATE ON native_attempt
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_memory_eligibility();
      GRANT SELECT, INSERT ON
        memory_lane, source_conversation, source_record, memory_leaf TO jarvis_runtime;
      GRANT UPDATE(last_inventory_at) ON memory_lane TO jarvis_runtime;
      GRANT UPDATE(
        checkpoint_event_id,checkpoint_native_digest,last_read_at,capture_error)
        ON source_conversation TO jarvis_runtime;
      GRANT UPDATE(embedding) ON source_record TO jarvis_runtime;
      GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON memory_node TO jarvis_runtime;
      GRANT SELECT, UPDATE ON memory_state TO jarvis_runtime;
    """)
    if connection.scalar(select(memory_state.c.leaf_count)) != 0:
        raise RuntimeError("universal memory cutover must begin with an empty tree")
    for table in (source_conversation, source_record, memory_leaf, memory_node):
        if connection.scalar(select(func.count()).select_from(table)) != 0:
            raise RuntimeError(
                "universal memory cutover must begin with an empty archive"
            )
    if _original_digests(connection) != originals:
        raise RuntimeError("universal memory cutover changed canonical originals")


def downgrade() -> None:
    raise RuntimeError(
        "restore the stopped cutover snapshot before first start; "
        "otherwise repair forward"
    )
