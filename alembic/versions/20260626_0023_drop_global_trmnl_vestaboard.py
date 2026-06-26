"""remove global TRMNL/Vestaboard transport settings (now per-channel)

TRMNL webhook URL and Vestaboard API key moved into each user's channel config,
so the old global settings rows are obsolete. Idempotent.

Revision ID: 20260626_0023
Revises: 20260626_0022
Create Date: 2026-06-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260626_0023"
down_revision: Union[str, None] = "20260626_0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text("DELETE FROM settings WHERE key IN ('trmnl_webhook_url', 'vestaboard_api_key')")
    )


def downgrade() -> None:
    pass
