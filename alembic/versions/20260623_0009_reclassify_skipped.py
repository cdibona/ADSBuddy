"""reclassify historical 'not configured' delivery failures as 'skipped'

Before the skipped status existed, deliveries to unconfigured channels (SMTP
not set up, a channel missing its destination) were recorded as 'failed'.
Reclassify those so they aren't counted as errors. Real failures (network,
HTTP errors, etc.) don't match these patterns and are left as 'failed'.

Revision ID: 20260623_0009
Revises: 20260623_0008
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260623_0009"
down_revision: Union[str, None] = "20260623_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE notification_deliveries
           SET status = 'skipped'
         WHERE status = 'failed'
           AND (error ILIKE '%not configured%' OR error ILIKE '%is missing %')
        """
    )


def downgrade() -> None:
    # Not reversible: we can't tell which 'skipped' rows were originally 'failed'.
    pass
