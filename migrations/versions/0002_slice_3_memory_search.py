"""Add the Slice 3 memory search representations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table_name in ("memory_log", "memory_summary"):
        op.create_index(
            f"ix_{table_name}_search_english",
            table_name,
            [sa.text("to_tsvector('english'::regconfig, text)")],
            unique=False,
            postgresql_using="gin",
        )
        op.create_index(
            f"ix_{table_name}_search_simple",
            table_name,
            [sa.text("to_tsvector('simple'::regconfig, text)")],
            unique=False,
            postgresql_using="gin",
        )


def downgrade() -> None:
    for table_name in ("memory_summary", "memory_log"):
        op.drop_index(
            f"ix_{table_name}_search_simple",
            table_name=table_name,
        )
        op.drop_index(
            f"ix_{table_name}_search_english",
            table_name=table_name,
        )
