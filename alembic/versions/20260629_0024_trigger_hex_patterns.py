"""add triggers.hex_patterns (match on ICAO hex)

Revision ID: 20260629_0024
Revises: 20260626_0023
Create Date: 2026-06-29
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260629_0024"
down_revision: Union[str, None] = "20260626_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "triggers",
        sa.Column("hex_patterns", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("triggers", "hex_patterns")
