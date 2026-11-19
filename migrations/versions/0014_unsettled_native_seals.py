"""Index only sealed attempts awaiting product settlement."""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating native recovery")
    op.create_index(
        "ix_native_attempt_unsettled_seal",
        "native_attempt",
        ["conversation_id", "attempt_seq"],
        postgresql_include=["id"],
        postgresql_where=text("terminal_at IS NOT NULL AND product_outcome IS NULL"),
    )


def downgrade() -> None:
    raise RuntimeError("native recovery requires forward repair")
