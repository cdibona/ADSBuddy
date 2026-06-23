"""index notification_deliveries.firing_id

Without this index, the FK ``notification_deliveries.firing_id -> trigger_firings.id``
(ON DELETE SET NULL) forces a sequential scan of notification_deliveries for
every trigger_firings row removed by a trigger's cascade delete. With hundreds
of thousands of delivery rows this made deleting (or, via lock convoy, pausing)
a trigger hang for many minutes. The index makes the SET NULL a fast lookup.

Revision ID: 20260623_0005
Revises: 20260618_0004
Create Date: 2026-06-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260623_0005"
down_revision: Union[str, None] = "20260618_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_notification_deliveries_firing_id
        ON notification_deliveries (firing_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notification_deliveries_firing_id")
