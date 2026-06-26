"""remove obsolete cloud-source settings (adsb.lol / FlightAware)

ADSBuddy works only with the local adsb-im radio (poll or push). Drop the
unused API-key settings rows from existing databases. Idempotent.

Revision ID: 20260626_0022
Revises: 20260625_0021
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260626_0022"
down_revision: Union[str, None] = "20260625_0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM settings WHERE key IN ('adsb_lol_api_key', 'flightaware_api_key')")
    )


def downgrade() -> None:
    # One-way: the keys are obsolete and re-seeding would re-add nothing useful.
    pass
