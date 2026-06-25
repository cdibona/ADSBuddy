"""add triggers.summary_priority (newsworthy in the airspace summary)

Revision ID: 20260625_0020
Revises: 20260625_0019
Create Date: 2026-06-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260625_0020"
down_revision: Union[str, None] = "20260625_0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("triggers", sa.Column("summary_priority", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("triggers", "summary_priority", server_default=None)


def downgrade() -> None:
    op.drop_column("triggers", "summary_priority")
