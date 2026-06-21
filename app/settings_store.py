"""Typed accessor for the Postgres-backed `settings` key/value table.

Anything that is *not* required to boot the app belongs here, not in `.env`.
Defaults are defined in DEFAULT_SETTINGS and seeded on first run.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting


@dataclass(frozen=True)
class SettingSpec:
    key: str
    default: str
    description: str
    secret: bool = False


DEFAULT_SETTINGS: tuple[SettingSpec, ...] = (
    SettingSpec(
        key="radio_base_url",
        default="http://100.107.148.119:8080",
        description=(
            "Base URL of the local adsb.im / tar1090 radio. The map page "
            "iframes <radio_base_url>/ and the ingester polls "
            "<radio_base_url>/data/aircraft.json."
        ),
    ),
    SettingSpec(
        key="ingest_interval_seconds",
        default="5",
        description="How often the background ingester polls aircraft.json.",
    ),
    SettingSpec(
        key="adsb_lol_api_key",
        default="",
        description="Optional adsb.lol API key (leave blank to skip that source).",
        secret=True,
    ),
    SettingSpec(
        key="flightaware_api_key",
        default="",
        description="Optional FlightAware AeroAPI key (leave blank to skip).",
        secret=True,
    ),
    SettingSpec(
        key="site_title",
        default="ADSBuddy",
        description="Shown in the header / browser tab.",
    ),
    SettingSpec(
        key="store_raw_sightings",
        default="false",
        description=(
            "When true, every sighting row also stores the full raw "
            "aircraft.json entry as JSONB (lets us replay or extract fields "
            "we forgot to call out as columns). Adds ~50-100 MB/day at the "
            "default 5-second poll. Use 'true' or 'false'."
        ),
    ),
    SettingSpec(
        key="route_lookup_enabled",
        default="true",
        description=(
            "When true, ingester queries https://api.adsbdb.com for "
            "callsign -> origin/destination routes and caches them. "
            "Required for origin/destination triggers to match anything."
        ),
    ),
    SettingSpec(
        key="route_cache_ttl_hours",
        default="24",
        description=(
            "How long to trust a cached adsbdb.com lookup before re-querying."
        ),
    ),
    # ---- Notification dispatch ---------------------------------------------
    SettingSpec(
        key="notifications_enabled",
        default="true",
        description=(
            "Master switch. When false, trigger firings are still recorded "
            "but no channels are dispatched (useful for debugging or maintenance)."
        ),
    ),
    SettingSpec(
        key="smtp_host",
        default="",
        description="SMTP server host for the 'email' channel kind (blank = email disabled).",
    ),
    SettingSpec(
        key="smtp_port",
        default="587",
        description="SMTP server port. 587 for STARTTLS, 465 for SMTPS, 25 for plaintext.",
    ),
    SettingSpec(
        key="smtp_username",
        default="",
        description="SMTP auth username (blank = no auth).",
    ),
    SettingSpec(
        key="smtp_password",
        default="",
        description="SMTP auth password.",
        secret=True,
    ),
    SettingSpec(
        key="smtp_from",
        default="",
        description="From: address used on outgoing notification emails.",
    ),
    SettingSpec(
        key="smtp_use_tls",
        default="true",
        description="Use STARTTLS on submit (true/false). Set false for plaintext (port 25) only.",
    ),
    SettingSpec(
        key="twilio_account_sid",
        default="",
        description="Twilio Account SID for the 'sms_twilio' channel kind.",
    ),
    SettingSpec(
        key="twilio_auth_token",
        default="",
        description="Twilio Auth Token.",
        secret=True,
    ),
    SettingSpec(
        key="twilio_from_number",
        default="",
        description="Twilio sender phone number in E.164 (e.g. +15551234567).",
    ),
    SettingSpec(
        key="sightings_retention_days",
        default="30",
        description=(
            "How many days of sightings to retain. The background ingester prunes "
            "rows older than this threshold once per hour. Set to 0 or leave blank "
            "to disable automatic cleanup. Default: 30."
        ),
    ),
)


async def seed_defaults(session: AsyncSession) -> None:
    """Insert any missing default settings. Idempotent."""
    existing = {
        row[0]
        for row in (await session.execute(select(Setting.key))).all()
    }
    for spec in DEFAULT_SETTINGS:
        if spec.key in existing:
            continue
        session.add(
            Setting(
                key=spec.key,
                value=spec.default,
                description=spec.description,
                secret=spec.secret,
            )
        )
    await session.commit()


async def get(session: AsyncSession, key: str) -> str | None:
    row = await session.execute(select(Setting.value).where(Setting.key == key))
    return row.scalar_one_or_none()


async def get_required(session: AsyncSession, key: str) -> str:
    value = await get(session, key)
    if value is None:
        raise KeyError(f"Setting {key!r} is missing — was seed_defaults() ever run?")
    return value


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    row = await session.execute(select(Setting).where(Setting.key == key))
    setting = row.scalar_one_or_none()
    if setting is None:
        # Allow admins to add brand-new settings rows from the UI.
        session.add(Setting(key=key, value=value, description="", secret=False))
    else:
        setting.value = value
    await session.commit()
