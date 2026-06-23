"""add squawk and emergency snapshot columns to trigger_firings

Revision ID: 20260623_0010
Revises: 20260623_0009
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260623_0010"
down_revision: Union[str, None] = "20260623_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trigger_firings", sa.Column("squawk", sa.String(8), nullable=True))
    op.add_column("trigger_firings", sa.Column("emergency", sa.String(16), nullable=True))


def downgrade() -> None:
    op.drop_column("trigger_firings", "emergency")
    op.drop_column("trigger_firings", "squawk")
