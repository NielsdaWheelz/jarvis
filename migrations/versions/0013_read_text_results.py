"""Retain complete text in original read receipts.

Revision ID: 0013
Revises: 0012
"""

from alembic import op
from sqlalchemy import text

from jarvis.ownership import DEPLOYMENT_LOCK_KEY

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not op.get_bind().scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DEPLOYMENT_LOCK_KEY}
    ):
        raise RuntimeError("stop jarvis before migrating read text receipts")
    op.execute(
        "ALTER TABLE read_position ALTER COLUMN result TYPE json USING result::json"
    )


def downgrade() -> None:
    raise RuntimeError("read text receipts require forward repair")
