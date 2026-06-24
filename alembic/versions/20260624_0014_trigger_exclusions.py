"""add trigger exclusion fields (NOT conditions)

Lets a trigger exclude aircraft: "older than 70 years but NOT a DH Beaver"
becomes min_age_years=70 + exclude_type_codes=DHC2.

Revision ID: 20260624_0014
Revises: 20260624_0013
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0014"
down_revision: Union[str, None] = "20260624_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = ("exclude_tail_patterns", "exclude_flight_patterns",
         "exclude_type_codes", "exclude_owner_patterns")


def upgrade() -> None:
    for col in _COLS:
        op.add_column("triggers", sa.Column(col, sa.Text(), nullable=False, server_default=""))
        op.alter_column("triggers", col, server_default=None)


def downgrade() -> None:
    for col in reversed(_COLS):
        op.drop_column("triggers", col)
