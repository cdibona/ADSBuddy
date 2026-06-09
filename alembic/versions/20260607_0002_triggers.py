"""triggers, route cache, wider sightings

Revision ID: 20260607_0002
Revises: 20260606_0001
Create Date: 2026-06-07
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260607_0002"
down_revision: Union[str, None] = "20260606_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- widen sightings -----------------------------------------------------
    op.add_column("sightings", sa.Column("altitude_geom", sa.Integer(), nullable=True))
    op.add_column("sightings", sa.Column("baro_rate", sa.Integer(), nullable=True))
    op.add_column("sightings", sa.Column("geom_rate", sa.Integer(), nullable=True))
    op.add_column("sightings", sa.Column("category", sa.String(length=4), nullable=True))
    op.add_column("sightings", sa.Column("emergency", sa.String(length=16), nullable=True))
    op.add_column("sightings", sa.Column("nav_heading", sa.Float(), nullable=True))
    op.add_column(
        "sightings", sa.Column("origin_icao", sa.String(length=4), nullable=True)
    )
    op.add_column(
        "sightings", sa.Column("destination_icao", sa.String(length=4), nullable=True)
    )
    op.add_column("sightings", sa.Column("rssi", sa.Float(), nullable=True))
    op.add_column("sightings", sa.Column("seen_age", sa.Float(), nullable=True))
    op.add_column(
        "sightings", sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )
    op.create_index("ix_sightings_origin_icao", "sightings", ["origin_icao"])
    op.create_index("ix_sightings_destination_icao", "sightings", ["destination_icao"])

    # --- flight route cache --------------------------------------------------
    op.create_table(
        "flight_routes",
        sa.Column("callsign", sa.String(length=16), primary_key=True),
        sa.Column("origin_icao", sa.String(length=4), nullable=True),
        sa.Column("destination_icao", sa.String(length=4), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("not_found", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    # --- triggers ------------------------------------------------------------
    op.create_table(
        "triggers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("tail_patterns", sa.Text(), nullable=False, server_default=""),
        sa.Column("flight_patterns", sa.Text(), nullable=False, server_default=""),
        sa.Column("type_codes", sa.Text(), nullable=False, server_default=""),
        sa.Column("origin_icaos", sa.Text(), nullable=False, server_default=""),
        sa.Column("destination_icaos", sa.Text(), nullable=False, server_default=""),
        sa.Column("min_year", sa.Integer(), nullable=True),
        sa.Column("max_year", sa.Integer(), nullable=True),
        sa.Column("min_age_years", sa.Integer(), nullable=True),
        sa.Column("max_age_years", sa.Integer(), nullable=True),
        sa.Column("cooldown_seconds", sa.Integer(), nullable=False, server_default="3600"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_triggers_owner_id", "triggers", ["owner_id"])

    op.create_table(
        "trigger_firings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "trigger_id",
            sa.Integer(),
            sa.ForeignKey("triggers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("icao_hex", sa.String(length=8), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("callsign", sa.String(length=16), nullable=True),
        sa.Column("registration", sa.String(length=16), nullable=True),
        sa.Column("type_code", sa.String(length=8), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("altitude_baro", sa.Integer(), nullable=True),
        sa.Column("origin_icao", sa.String(length=4), nullable=True),
        sa.Column("destination_icao", sa.String(length=4), nullable=True),
    )
    op.create_index(
        "ix_trigger_firings_trigger_fired",
        "trigger_firings",
        ["trigger_id", "fired_at"],
    )
    op.create_index("ix_trigger_firings_fired", "trigger_firings", ["fired_at"])
    op.create_index("ix_trigger_firings_icao_hex", "trigger_firings", ["icao_hex"])


def downgrade() -> None:
    op.drop_index("ix_trigger_firings_icao_hex", table_name="trigger_firings")
    op.drop_index("ix_trigger_firings_fired", table_name="trigger_firings")
    op.drop_index("ix_trigger_firings_trigger_fired", table_name="trigger_firings")
    op.drop_table("trigger_firings")
    op.drop_index("ix_triggers_owner_id", table_name="triggers")
    op.drop_table("triggers")
    op.drop_table("flight_routes")
    op.drop_index("ix_sightings_destination_icao", table_name="sightings")
    op.drop_index("ix_sightings_origin_icao", table_name="sightings")
    for col in (
        "raw",
        "seen_age",
        "rssi",
        "destination_icao",
        "origin_icao",
        "nav_heading",
        "emergency",
        "category",
        "geom_rate",
        "baro_rate",
        "altitude_geom",
    ):
        op.drop_column("sightings", col)
