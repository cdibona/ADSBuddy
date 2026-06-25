"""add trigger altitude band + emitter category conditions

Enables "under 1000 ft" (max_altitude_ft) and "helicopters" (categories=A7).

Revision ID: 20260624_0016
Revises: 20260624_0015
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0016"
down_revision: Union[str, None] = "20260624_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("triggers", sa.Column("categories", sa.Text(), nullable=False, server_default=""))
    op.alter_column("triggers", "categories", server_default=None)
    op.add_column("triggers", sa.Column("min_altitude_ft", sa.Integer(), nullable=True))
    op.add_column("triggers", sa.Column("max_altitude_ft", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("triggers", "max_altitude_ft")
    op.drop_column("triggers", "min_altitude_ft")
    op.drop_column("triggers", "categories")
