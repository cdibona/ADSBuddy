"""create radio_sources table

Enrolls multiple ingest feeds (poll or push). The existing single radio
(radio_base_url setting) is migrated into one 'poll' source named "Local radio"
at startup by app.bootstrap.

Revision ID: 20260624_0012
Revises: 20260624_0011
Create Date: 2026-06-24
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260624_0012"
down_revision: Union[str, None] = "20260624_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "radio_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False, server_default="poll"),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("token", sa.String(64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("receiver_lat", sa.Float(), nullable=True),
        sa.Column("receiver_lon", sa.Float(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_radio_sources_token", "radio_sources", ["token"])


def downgrade() -> None:
    op.drop_index("ix_radio_sources_token", table_name="radio_sources")
    op.drop_table("radio_sources")
