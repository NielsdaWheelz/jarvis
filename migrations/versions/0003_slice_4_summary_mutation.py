"""Enforce the Slice 4 summary mutation boundary.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1
            FROM memory_summary AS summary
            CROSS JOIN LATERAL unnest(summary.source_memory_ids) AS source(id)
            WHERE source.id IS NULL
               OR NOT EXISTS (
                    SELECT 1 FROM memory_log AS raw WHERE raw.id = source.id
                  )
               OR EXISTS (
                    SELECT 1
                    FROM memory_summary AS nested
                    WHERE nested.id = source.id
                  )
          ) OR EXISTS (
            SELECT 1
            FROM memory_summary AS summary
            WHERE cardinality(summary.source_memory_ids) <>
                  (
                    SELECT count(DISTINCT source.id)
                    FROM unnest(summary.source_memory_ids) AS source(id)
                  )
               OR summary.source_memory_ids IS DISTINCT FROM
                  (
                    SELECT array_agg(source.id ORDER BY source.id)
                    FROM unnest(summary.source_memory_ids) AS source(id)
                  )
          ) THEN
            RAISE EXCEPTION 'existing memory_summary lineage is invalid';
          END IF;
        END;
        $$
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT source_memory_ids
            FROM memory_summary
            GROUP BY source_memory_ids
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'existing memory_summary lineage is duplicated';
          END IF;
        END;
        $$
        """
    )
    op.create_index(
        "uq_memory_summary_source_memory_ids",
        "memory_summary",
        ["source_memory_ids"],
        unique=True,
    )
    op.execute(
        """
        CREATE FUNCTION jarvis_guard_memory_summary() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'TRUNCATE' THEN
            RAISE EXCEPTION 'memory_summary cannot be truncated';
          END IF;
          IF TG_OP = 'UPDATE'
             AND (NEW.id IS DISTINCT FROM OLD.id
                  OR NEW.text IS DISTINCT FROM OLD.text
                  OR NEW.source_memory_ids IS DISTINCT FROM OLD.source_memory_ids
                  OR NEW.created_at IS DISTINCT FROM OLD.created_at) THEN
            RAISE EXCEPTION 'memory_summary canonical fields are immutable';
          END IF;
          IF TG_OP IN ('INSERT', 'UPDATE') THEN
            IF array_position(NEW.source_memory_ids, NULL) IS NOT NULL
               OR cardinality(NEW.source_memory_ids) <>
                  (
                    SELECT count(DISTINCT source.id)
                    FROM unnest(NEW.source_memory_ids) AS source(id)
                  )
               OR NEW.source_memory_ids IS DISTINCT FROM
                  (
                    SELECT array_agg(source.id ORDER BY source.id)
                    FROM unnest(NEW.source_memory_ids) AS source(id)
                  )
               OR EXISTS (
                    SELECT 1
                    FROM unnest(NEW.source_memory_ids) AS source(id)
                    WHERE NOT EXISTS (
                      SELECT 1 FROM memory_log AS raw WHERE raw.id = source.id
                    )
                  )
               OR EXISTS (
                    SELECT 1
                    FROM unnest(NEW.source_memory_ids) AS source(id)
                    JOIN memory_summary AS nested ON nested.id = source.id
                  ) THEN
              RAISE EXCEPTION 'memory_summary lineage must contain unique raw IDs';
            END IF;
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_summary_canonical
        BEFORE INSERT OR UPDATE ON memory_summary
        FOR EACH ROW EXECUTE FUNCTION jarvis_guard_memory_summary()
        """
    )
    op.execute(
        """
        CREATE TRIGGER memory_summary_no_truncate
        BEFORE TRUNCATE ON memory_summary
        FOR EACH STATEMENT EXECUTE FUNCTION jarvis_guard_memory_summary()
        """
    )
    op.execute("REVOKE ALL PRIVILEGES ON TABLE memory_summary FROM jarvis_runtime")
    op.execute("GRANT SELECT, INSERT, DELETE ON TABLE memory_summary TO jarvis_runtime")
    op.execute("GRANT UPDATE (embedding) ON TABLE memory_summary TO jarvis_runtime")


def downgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON TABLE memory_summary FROM jarvis_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLE memory_summary "
        "TO jarvis_runtime"
    )
    op.execute("DROP TRIGGER memory_summary_no_truncate ON memory_summary")
    op.execute("DROP TRIGGER memory_summary_canonical ON memory_summary")
    op.execute("DROP FUNCTION jarvis_guard_memory_summary()")
    op.drop_index(
        "uq_memory_summary_source_memory_ids",
        table_name="memory_summary",
    )
