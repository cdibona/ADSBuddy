"""add geofence columns to triggers

Lets a trigger fire only when the aircraft is within radius_miles of a center
(resolved from lat,lon / US ZIP / ICAO airport at save time).

Revision ID: 20260623_0007
Revises: 20260623_0006
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0007"
down_revision: Union[str, None] = "20260623_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "triggers",
        sa.Column("geofence_center", sa.Text(), nullable=False, server_default=""),
    )
    op.alter_column("triggers", "geofence_center", server_default=None)
    op.add_column("triggers", sa.Column("center_lat", sa.Float(), nullable=True))
    op.add_column("triggers", sa.Column("center_lon", sa.Float(), nullable=True))
    op.add_column("triggers", sa.Column("radius_miles", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("triggers", "radius_miles")
    op.drop_column("triggers", "center_lon")
    op.drop_column("triggers", "center_lat")
    op.drop_column("triggers", "geofence_center")
