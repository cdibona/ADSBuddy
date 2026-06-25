"""snapshot ADS-B emitter category on firings (for kind icons)

Revision ID: 20260625_0019
Revises: 20260624_0018
Create Date: 2026-06-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260625_0019"
down_revision: Union[str, None] = "20260624_0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trigger_firings", sa.Column("category", sa.String(4), nullable=True))


def downgrade() -> None:
    op.drop_column("trigger_firings", "category")
