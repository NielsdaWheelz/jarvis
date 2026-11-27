"""Start the shared owner display receipts from the stopped transcript."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating shown receipts")
    op.execute("""
        CREATE TABLE owner_shown (
            message_id uuid CONSTRAINT pk_owner_shown PRIMARY KEY
                CONSTRAINT fk_owner_shown_message_id_message REFERENCES message(id),
            shown_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
            via text NOT NULL CONSTRAINT ck_owner_shown_via
                CHECK (via IN ('observed', 'cleared', 'cutover'))
        );
        INSERT INTO owner_shown (message_id, via)
        SELECT id, 'cutover' FROM message WHERE role = 'assistant';
        GRANT SELECT, INSERT ON owner_shown TO jarvis_runtime;
        DO $$ BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname='jarvis_backup') THEN
                GRANT SELECT ON owner_shown TO jarvis_backup;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    raise RuntimeError("shown receipts require forward repair")
