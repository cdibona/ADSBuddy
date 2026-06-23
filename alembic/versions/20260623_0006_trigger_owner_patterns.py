"""add triggers.owner_patterns

Lets a trigger match on the aircraft owner/operator (substring, case-insensitive).

Revision ID: 20260623_0006
Revises: 20260623_0005
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0006"
down_revision: Union[str, None] = "20260623_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "triggers",
        sa.Column("owner_patterns", sa.Text(), nullable=False, server_default=""),
    )
    # Drop the server_default now that existing rows are backfilled; the ORM
    # supplies "" for new rows.
    op.alter_column("triggers", "owner_patterns", server_default=None)


def downgrade() -> None:
    op.drop_column("triggers", "owner_patterns")
