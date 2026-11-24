"""Keep accepted notice identities and cut pending delivery to Firebase."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    for key in (DEPLOYMENT_LOCK_KEY, MEMORY_LOCK_KEY):
        if not connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
        ):
            raise RuntimeError("stop both writers before migrating phone delivery")
    if connection.scalar(
        text("""
        SELECT EXISTS(SELECT FROM home_notice
            WHERE discord_message_id IS NULL AND kind <> 'reply')
        OR EXISTS(SELECT FROM action a JOIN home_notice n ON a.id = n.action_id
            WHERE n.kind = 'approval' AND a.status = 'awaiting_approval')
        OR EXISTS(SELECT FROM action WHERE status = 'executing')
        OR EXISTS(SELECT FROM native_attempt WHERE product_outcome IS NULL
            AND (terminal_at IS NOT NULL OR fenced_at IS NULL OR recovery_pending))
        """)
    ):
        raise RuntimeError(
            "settle legacy notices and entered work on the selected release"
        )
    op.execute("""
        DROP INDEX ix_home_notice_pending;
        ALTER TABLE home_notice RENAME COLUMN discord_message_id TO provider_id;
        ALTER TABLE home_notice ADD COLUMN provider text;
        UPDATE home_notice SET provider = 'discord' WHERE provider_id IS NOT NULL;
        ALTER TABLE home_notice ADD CONSTRAINT ck_home_notice_provider CHECK (
            (provider IS NULL AND provider_id IS NULL AND kind IN ('reply', 'question'))
            OR (provider IS NOT NULL AND provider_id IS NOT NULL
                AND provider IN ('discord', 'fcm')
                AND (provider = 'discord' OR kind IN ('reply', 'question'))));
        CREATE INDEX ix_home_notice_pending ON home_notice(created_at, id)
            WHERE provider_id IS NULL;
        GRANT UPDATE(provider) ON home_notice TO jarvis_runtime;
    """)


def downgrade() -> None:
    raise RuntimeError("phone delivery requires forward repair")
