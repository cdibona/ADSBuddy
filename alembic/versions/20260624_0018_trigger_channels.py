"""create trigger_channels (per-trigger channel allow-list)

No rows for a trigger => deliver to all the owner's active channels (default).

Revision ID: 20260624_0018
Revises: 20260624_0017
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0018"
down_revision: Union[str, None] = "20260624_0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trigger_channels",
        sa.Column("trigger_id", sa.Integer(), sa.ForeignKey("triggers.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("channel_id", sa.Integer(), sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), primary_key=True),
    )


def downgrade() -> None:
    op.drop_table("trigger_channels")
