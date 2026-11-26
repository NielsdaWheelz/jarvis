"""Replace attachment bucket references with verified Drive custody."""

from alembic import op
from sqlalchemy import text

from jarvis.drive_cut import DRIVE_CUSTODY_SCHEMA, DriveCutManifest
from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = DRIVE_CUSTODY_SCHEMA
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before changing file custody")
    rows = (
        connection.execute(
            text("""
        SELECT id, state, source->>'kind' AS kind, filename, size_bytes, sha256,
               put_entered_at, error
        FROM attachment ORDER BY id
    """)
        )
        .mappings()
        .all()
    )
    declaration = op.get_context().config.attributes.get("drive_cut")
    if declaration is None and rows:
        raise RuntimeError("attachment migration requires the verified Drive map")
    manifest = (
        None if declaration is None else DriveCutManifest.model_validate(declaration)
    )
    unfinished = connection.execute(
        text("""
        SELECT id, tool_name, status FROM action
        WHERE tool_name IN ('attachment.retain','attachment.delete')
          AND status IN ('queued','awaiting_approval','executing')
        ORDER BY id LIMIT 1
    """)
    ).one_or_none()
    if unfinished is not None:
        raise RuntimeError(
            f"attachment action {unfinished.id} {unfinished.tool_name} is {unfinished.status}"
        )
    if connection.scalar(
        text("""
        SELECT EXISTS(SELECT FROM native_attempt WHERE product_outcome IS NULL
            AND (fenced_at IS NULL OR terminal_at IS NOT NULL OR recovery_pending))
        OR EXISTS(SELECT FROM read_position
            WHERE contract->>'tool_id'='attachment.open' AND state <> 'completed')
    """)
    ):
        raise RuntimeError(
            "settle pending native work and attachment reads before cutover"
        )
    unknown = set(
        connection.execute(
            text("""
        SELECT id FROM action WHERE tool_name IN ('attachment.retain','attachment.delete')
          AND status='uncertain'
    """)
        ).scalars()
    )
    dispositions = (
        set() if manifest is None else {item.id for item in manifest.retired_actions}
    )
    if unknown != dispositions:
        raise RuntimeError(
            "attachment uncertain actions require exact stopped dispositions"
        )
    entries = (
        {}
        if manifest is None
        else {entry.source_uuid: entry for entry in manifest.entries}
    )
    if entries.keys() != {row["id"] for row in rows}:
        raise RuntimeError("attachment map must match every stopped row")
    for row in rows:
        entry = entries[row["id"]]
        if (
            (entry.prior_state, entry.name, entry.size, entry.sha256)
            != (row["state"], row["filename"], row["size_bytes"], row["sha256"])
            or (
                entry.prior_state == "pending"
                and (row["kind"] != "web" or row["put_entered_at"] is not None)
            )
            or (entry.prior_state == "deleted" and entry.reason != "Deleted")
            or (entry.prior_state == "failed" and entry.reason != row["error"])
        ):
            raise RuntimeError(f"attachment {entry.source_uuid} does not match the map")
    op.execute("""
        DROP TRIGGER attachment_facts ON attachment;
        DROP INDEX uq_attachment_active_source;
        DROP INDEX ix_attachment_ingress_pending;
        ALTER TABLE attachment
            DROP CONSTRAINT ck_attachment_state,
            DROP CONSTRAINT ck_attachment_put,
            DROP CONSTRAINT ck_attachment_stored,
            DROP CONSTRAINT ck_attachment_deleted,
            DROP CONSTRAINT ck_attachment_delete_lineage,
            DROP CONSTRAINT ck_attachment_outcome,
            DROP COLUMN r2_account,
            DROP COLUMN bucket,
            ADD COLUMN drive_subject text,
            ADD COLUMN drive_file_id text,
            ADD COLUMN filing_action_id uuid UNIQUE REFERENCES action(id)
                ON DELETE RESTRICT,
            ADD COLUMN verified_at timestamptz,
            ADD COLUMN disposition text;
        ALTER TABLE attachment RENAME COLUMN put_entered_at TO prior_put_entered_at;
        REVOKE UPDATE (size_bytes,sha256,prior_put_entered_at,stored_at,deleted_at,
            delete_action_id,error) ON attachment FROM jarvis_runtime;
    """)
    for row in rows:
        entry = entries[row["id"]]
        assert manifest is not None
        state, disposition = {
            "ready": ("filed", None),
            "pending": ("staged", None),
            "deleted": ("unavailable", "historical_deleted"),
            "failed": ("unavailable", "historical_failed"),
        }[entry.prior_state]
        connection.execute(
            text("""
            UPDATE attachment SET state=:state, disposition=:disposition,
                drive_subject=:subject, drive_file_id=:file_id, verified_at=:verified
            WHERE id=:id
            """),
            {
                "id": entry.source_uuid,
                "state": state,
                "disposition": disposition,
                "subject": manifest.subject if entry.drive_id is not None else None,
                "file_id": entry.drive_id,
                "verified": entry.verified_at,
            },
        )
    op.execute("""
        ALTER TABLE attachment
            ADD CONSTRAINT ck_attachment_drive_pair CHECK (
                (drive_subject IS NULL AND drive_file_id IS NULL)
                OR (length(drive_subject) <= 255 AND drive_subject ~ '^[A-Za-z0-9_-]+$'
                    AND length(drive_file_id) <= 255
                    AND drive_file_id ~ '^[A-Za-z0-9_-]+$') IS TRUE
            ),
            ADD CONSTRAINT ck_attachment_state CHECK (
                CASE state
                 WHEN 'staged' THEN filing_action_id IS NULL AND drive_file_id IS NULL
                    AND verified_at IS NULL AND disposition IS NULL
                 WHEN 'filing' THEN filing_action_id IS NOT NULL
                    AND drive_file_id IS NULL
                    AND verified_at IS NULL AND disposition IS NULL
                 WHEN 'uncertain' THEN filing_action_id IS NOT NULL
                    AND drive_file_id IS NULL AND verified_at IS NULL
                    AND disposition IS NULL
                 WHEN 'created' THEN filing_action_id IS NOT NULL
                    AND drive_file_id IS NOT NULL AND verified_at IS NULL
                    AND disposition IS NULL
                 WHEN 'filed' THEN drive_file_id IS NOT NULL
                    AND (filing_action_id IS NOT NULL OR stored_at IS NOT NULL)
                    AND verified_at IS NOT NULL AND disposition IS NULL
                 WHEN 'unavailable' THEN verified_at IS NULL AND disposition IN
                    ('historical_deleted','historical_failed','abandoned',
                     'abandoned_uncertain')
                 ELSE false END IS TRUE
            );
        CREATE UNIQUE INDEX uq_attachment_active_source ON attachment(source_key)
            WHERE state <> 'unavailable';
        CREATE INDEX ix_attachment_unfiled ON attachment(created_at,id)
            WHERE state IN ('staged','filing','uncertain','created');

        GRANT UPDATE (state,drive_subject,drive_file_id,filing_action_id,
            verified_at,disposition) ON attachment TO jarvis_runtime;

        CREATE OR REPLACE FUNCTION jarvis_guard_attachment() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'attachment attribution is permanent';
            ELSIF TG_OP = 'INSERT' THEN
                IF NEW.state <> 'staged' OR NEW.source->>'kind' <> 'web'
                    OR NEW.prior_put_entered_at IS NOT NULL OR NEW.stored_at IS NOT NULL
                    OR NEW.deleted_at IS NOT NULL OR NEW.delete_action_id IS NOT NULL
                    OR NEW.error IS NOT NULL THEN
                    RAISE EXCEPTION 'new attachments must be staged owner submissions';
                END IF;
                RETURN NEW;
            END IF;
            IF (to_jsonb(NEW) - ARRAY['state','drive_subject','drive_file_id',
                    'filing_action_id','verified_at','disposition']) IS DISTINCT FROM
               (to_jsonb(OLD) - ARRAY['state','drive_subject','drive_file_id',
                    'filing_action_id','verified_at','disposition'])
                OR (OLD.drive_file_id IS NOT NULL AND
                    (NEW.drive_subject,NEW.drive_file_id) IS DISTINCT FROM
                    (OLD.drive_subject,OLD.drive_file_id))
                OR (OLD.filing_action_id IS NOT NULL AND NEW.state <> 'staged'
                    AND NEW.filing_action_id IS DISTINCT FROM OLD.filing_action_id)
                OR OLD.state IN ('filed','unavailable') THEN
                RAISE EXCEPTION 'attachment provenance is immutable';
            END IF;
            IF NOT (CASE OLD.state
                WHEN 'staged' THEN NEW.state IN ('filing','unavailable')
                WHEN 'filing' THEN NEW.state IN
                    ('staged','uncertain','created','unavailable')
                WHEN 'uncertain' THEN NEW.state = 'unavailable'
                WHEN 'created' THEN NEW.state IN ('filed','unavailable')
                ELSE false END) THEN
                RAISE EXCEPTION 'invalid attachment state transition';
            END IF;
            IF OLD.state = 'filing' AND NEW.state = 'staged' AND NOT EXISTS (
                SELECT FROM action WHERE id=OLD.filing_action_id
                   AND (
                    (status IN ('failed','cancelled') AND attempts=0)
                    OR (status='failed' AND result @>
                      '{"type":"Failure","error":{"type":"WorkspaceWriteFailure",
                        "known_no_effect":true}}'::jsonb)
                   )
            ) THEN
                RAISE EXCEPTION 'filing action non-entry is not proved';
            END IF;
            RETURN NEW;
        END $$;
        CREATE TRIGGER attachment_facts BEFORE INSERT OR UPDATE OR DELETE
            ON attachment FOR EACH ROW EXECUTE FUNCTION jarvis_guard_attachment();
    """)


def downgrade() -> None:
    raise RuntimeError("Drive file custody requires forward repair")
