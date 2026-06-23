"""add per-user profile prefs (email, timezone)

Revision ID: 20260623_0008
Revises: 20260623_0007
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0008"
down_revision: Union[str, None] = "20260623_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
    )
    op.alter_column("users", "timezone", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "timezone")
    op.drop_column("users", "email")
