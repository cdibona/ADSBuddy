"""add triggers.squawk_patterns

Lets a trigger match on transponder squawk codes (comma-separated, * wildcard);
includes the emergency codes 7500/7600/7700.

Revision ID: 20260624_0011
Revises: 20260623_0010
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0011"
down_revision: Union[str, None] = "20260623_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "triggers",
        sa.Column("squawk_patterns", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("triggers", "squawk_patterns", server_default=None)


def downgrade() -> None:
    op.drop_column("triggers", "squawk_patterns")
