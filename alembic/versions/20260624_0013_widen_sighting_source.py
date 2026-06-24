"""widen sightings.source to 64 chars

A sighting's source is now a RadioSource name (varchar 64); widen the column so
a long source name can't truncate/error on insert. Increasing a varchar length
is a metadata-only change in PostgreSQL (no table rewrite).

Revision ID: 20260624_0013
Revises: 20260624_0012
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0013"
down_revision: Union[str, None] = "20260624_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sightings", "source",
        existing_type=sa.String(32), type_=sa.String(64), existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sightings", "source",
        existing_type=sa.String(64), type_=sa.String(32), existing_nullable=False,
    )
