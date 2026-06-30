"""add notification_channels.consecutive_failures + disabled_reason

Revision ID: 20260629_0025
Revises: 20260629_0024
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260629_0025"
down_revision: Union[str, None] = "20260629_0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notification_channels",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "notification_channels",
        sa.Column("disabled_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_channels", "disabled_reason")
    op.drop_column("notification_channels", "consecutive_failures")
