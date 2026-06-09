"""initial schema

Revision ID: 20260606_0001
Revises:
Create Date: 2026-06-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260606_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=False)

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"], unique=False)

    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=128), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("secret", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "aircraft",
        sa.Column("icao_hex", sa.String(length=8), primary_key=True),
        sa.Column("registration", sa.String(length=16), nullable=True),
        sa.Column("type_code", sa.String(length=8), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_op", sa.Text(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_aircraft_registration", "aircraft", ["registration"])
    op.create_index("ix_aircraft_type_code", "aircraft", ["type_code"])
    op.create_index("ix_aircraft_owner_op", "aircraft", ["owner_op"])
    op.create_index("ix_aircraft_year", "aircraft", ["year"])

    op.create_table(
        "sightings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "icao_hex",
            sa.String(length=8),
            sa.ForeignKey("aircraft.icao_hex", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("flight", sa.String(length=16), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lon", sa.Float(), nullable=True),
        sa.Column("altitude_baro", sa.Integer(), nullable=True),
        sa.Column("ground_speed", sa.Float(), nullable=True),
        sa.Column("track", sa.Float(), nullable=True),
        sa.Column("squawk", sa.String(length=8), nullable=True),
        sa.Column(
            "source", sa.String(length=32), nullable=False, server_default="local_radio"
        ),
    )
    op.create_index("ix_sightings_hex_seen", "sightings", ["icao_hex", "seen_at"])
    op.create_index("ix_sightings_seen_at", "sightings", ["seen_at"])


def downgrade() -> None:
    op.drop_index("ix_sightings_seen_at", table_name="sightings")
    op.drop_index("ix_sightings_hex_seen", table_name="sightings")
    op.drop_table("sightings")
    op.drop_index("ix_aircraft_year", table_name="aircraft")
    op.drop_index("ix_aircraft_owner_op", table_name="aircraft")
    op.drop_index("ix_aircraft_type_code", table_name="aircraft")
    op.drop_index("ix_aircraft_registration", table_name="aircraft")
    op.drop_table("aircraft")
    op.drop_table("settings")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
