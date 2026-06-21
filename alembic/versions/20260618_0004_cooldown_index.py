"""cooldown composite index

Revision ID: 20260618_0004
Revises: 20260609_0003
Create Date: 2026-06-18
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260618_0004"
down_revision: Union[str, None] = "20260609_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_trigger_firings_cooldown
        ON trigger_firings (trigger_id, icao_hex, fired_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trigger_firings_cooldown")
