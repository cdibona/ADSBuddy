"""add notification_channels mode + per-channel summary cadence

mode: 'everything' (default) | 'emergency' | 'summary'.

Revision ID: 20260625_0021
Revises: 20260625_0020
Create Date: 2026-06-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260625_0021"
down_revision: Union[str, None] = "20260625_0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notification_channels", sa.Column("mode", sa.String(16), nullable=False, server_default="everything"))
    op.alter_column("notification_channels", "mode", server_default=None)
    op.add_column("notification_channels", sa.Column("summary_interval_minutes", sa.Integer(), nullable=False, server_default="15"))
    op.alter_column("notification_channels", "summary_interval_minutes", server_default=None)
    op.add_column("notification_channels", sa.Column("last_summary_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("notification_channels", "last_summary_at")
    op.drop_column("notification_channels", "summary_interval_minutes")
    op.drop_column("notification_channels", "mode")
