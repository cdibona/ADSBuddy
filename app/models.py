"""SQLAlchemy ORM models for ADSBuddy."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Per-user profile preferences.
    email: Mapped[str | None] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    triggers: Mapped[list["Trigger"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    channels: Mapped[list["NotificationChannel"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Setting(Base):
    """Key/value runtime config editable by admins from the UI."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class RadioSource(Base):
    """A feed ADSBuddy ingests from.

    kind='poll' → we GET <url>/data/aircraft.json on each tick.
    kind='push' → a feeder POSTs aircraft.json-shaped data to /ingest/<token>.
    Sightings are tagged with the source's name. receiver_lat/lon is the
    station location (learned from the radio's receiver.json for poll sources).
    """

    __tablename__ = "radio_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="poll")
    url: Mapped[str | None] = mapped_column(Text)
    token: Mapped[str | None] = mapped_column(String(64), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    receiver_lat: Mapped[float | None] = mapped_column(Float)
    receiver_lon: Mapped[float | None] = mapped_column(Float)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )


class Aircraft(Base):
    """One row per ICAO hex ever seen. Slowly-changing facts only."""

    __tablename__ = "aircraft"

    icao_hex: Mapped[str] = mapped_column(String(8), primary_key=True)
    registration: Mapped[str | None] = mapped_column(String(16), index=True)
    type_code: Mapped[str | None] = mapped_column(String(8), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    owner_op: Mapped[str | None] = mapped_column(Text, index=True)
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Sighting(Base):
    """Time-series of position fixes pulled from aircraft.json."""

    __tablename__ = "sightings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    icao_hex: Mapped[str] = mapped_column(
        ForeignKey("aircraft.icao_hex", ondelete="CASCADE"), nullable=False
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    flight: Mapped[str | None] = mapped_column(String(16))

    # Position / motion
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    altitude_baro: Mapped[int | None] = mapped_column(Integer)
    altitude_geom: Mapped[int | None] = mapped_column(Integer)
    ground_speed: Mapped[float | None] = mapped_column(Float)
    track: Mapped[float | None] = mapped_column(Float)
    baro_rate: Mapped[int | None] = mapped_column(Integer)
    geom_rate: Mapped[int | None] = mapped_column(Integer)

    # Identification / state
    squawk: Mapped[str | None] = mapped_column(String(8))
    category: Mapped[str | None] = mapped_column(String(4))
    emergency: Mapped[str | None] = mapped_column(String(16))
    nav_heading: Mapped[float | None] = mapped_column(Float)

    # Route enrichment (populated when adsbdb.com lookup succeeds)
    origin_icao: Mapped[str | None] = mapped_column(String(4), index=True)
    destination_icao: Mapped[str | None] = mapped_column(String(4), index=True)

    # Signal / metadata
    rssi: Mapped[float | None] = mapped_column(Float)
    seen_age: Mapped[float | None] = mapped_column(Float)  # `seen` field — staleness in s
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="local_radio")

    # Full raw entry — only populated when settings.store_raw_sightings is on.
    # Lets us replay or extract fields we forgot to call out as columns.
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_sightings_hex_seen", "icao_hex", "seen_at"),
        Index("ix_sightings_seen_at", "seen_at"),
    )


class FlightRoute(Base):
    """Cache of callsign -> origin/destination from adsbdb.com.

    `not_found` means we asked and the API didn't know; we still cache the
    negative result so we don't keep re-querying.
    """

    __tablename__ = "flight_routes"

    callsign: Mapped[str] = mapped_column(String(16), primary_key=True)
    origin_icao: Mapped[str | None] = mapped_column(String(4))
    destination_icao: Mapped[str | None] = mapped_column(String(4))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    not_found: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Trigger(Base):
    """A user-defined alert rule. All non-empty fields are AND-combined.

    String pattern fields (`tail_patterns`, `flight_patterns`, `type_codes`,
    `owner_patterns`, `origin_icaos`, `destination_icaos`) hold comma-separated
    values; matching is case-insensitive. `tail_patterns` and `flight_patterns`
    accept `*` as a wildcard. `owner_patterns` matches as a case-insensitive
    substring (so "United" matches "United Air Lines Inc"), and also accepts
    `*`/`?` wildcards.
    """

    __tablename__ = "triggers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")

    tail_patterns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    flight_patterns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    type_codes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_patterns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    squawk_patterns: Mapped[str] = mapped_column(Text, nullable=False, default="")
    origin_icaos: Mapped[str] = mapped_column(Text, nullable=False, default="")
    destination_icaos: Mapped[str] = mapped_column(Text, nullable=False, default="")

    min_year: Mapped[int | None] = mapped_column(Integer)
    max_year: Mapped[int | None] = mapped_column(Integer)
    min_age_years: Mapped[int | None] = mapped_column(Integer)
    max_age_years: Mapped[int | None] = mapped_column(Integer)

    # Geofence: fire only when the aircraft is within radius_miles of the center.
    # geofence_center is the raw user input (lat,lon / US ZIP / ICAO airport),
    # resolved to center_lat/center_lon at save time. An unresolved center
    # (lat/lon NULL) leaves the geofence inactive until re-saved.
    geofence_center: Mapped[str] = mapped_column(Text, nullable=False, default="")
    center_lat: Mapped[float | None] = mapped_column(Float)
    center_lon: Mapped[float | None] = mapped_column(Float)
    radius_miles: Mapped[float | None] = mapped_column(Float)

    cooldown_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    owner: Mapped[User] = relationship(back_populates="triggers")
    firings: Mapped[list["TriggerFiring"]] = relationship(
        back_populates="trigger", cascade="all, delete-orphan", passive_deletes=True
    )


class TriggerFiring(Base):
    """One row per trigger match. Subject to per-(trigger, aircraft) cooldown."""

    __tablename__ = "trigger_firings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger_id: Mapped[int] = mapped_column(
        ForeignKey("triggers.id", ondelete="CASCADE"), nullable=False
    )
    icao_hex: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    # Snapshot of useful context at fire time (so we don't need to join later).
    callsign: Mapped[str | None] = mapped_column(String(16))
    registration: Mapped[str | None] = mapped_column(String(16))
    type_code: Mapped[str | None] = mapped_column(String(8))
    squawk: Mapped[str | None] = mapped_column(String(8))
    emergency: Mapped[str | None] = mapped_column(String(16))
    year: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    altitude_baro: Mapped[int | None] = mapped_column(Integer)
    origin_icao: Mapped[str | None] = mapped_column(String(4))
    destination_icao: Mapped[str | None] = mapped_column(String(4))

    trigger: Mapped[Trigger] = relationship(back_populates="firings")

    __table_args__ = (
        Index("ix_trigger_firings_trigger_fired", "trigger_id", "fired_at"),
        Index("ix_trigger_firings_fired", "fired_at"),
    )


# ---- Notifications ---------------------------------------------------------

CHANNEL_KINDS = ("discord", "email", "webhook", "sms_twilio")


class NotificationChannel(Base):
    """A per-user delivery destination. `config` is kind-specific JSON.

    - discord:    {"webhook_url": "...", "username": "ADSBuddy"}
    - email:      {"to_address": "user@example.com"}
    - webhook:    {"url": "...", "auth_header": "Bearer ..." (optional)}
    - sms_twilio: {"to_phone": "+15551234567"}
    """

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    user: Mapped[User] = relationship(back_populates="channels")


class NotificationDelivery(Base):
    """One row per delivery attempt — success or failure."""

    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Null when this delivery was a "send test", not tied to a firing.
    # Indexed: the ON DELETE SET NULL fires for every cascade-deleted firing
    # when a trigger is removed, so an unindexed firing_id meant a full-table
    # scan per firing (deletes hung for minutes on large delivery tables).
    firing_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("trigger_firings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "sent" | "failed"
    error: Mapped[str | None] = mapped_column(Text)
    is_test: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    __table_args__ = (
        Index("ix_notification_deliveries_channel_at", "channel_id", "created_at"),
    )
