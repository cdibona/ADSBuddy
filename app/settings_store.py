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


# Settings that configure notification transports — shown on the admin
# "Notifications" tab. Auth/OAuth settings show on the "Users" tab. Everything
# else shows on "System".
_NOTIFICATION_KEYS = frozenset({
    "notifications_enabled",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
    "smtp_from", "smtp_use_tls",
    "twilio_account_sid", "twilio_auth_token", "twilio_from_number",
    "vestaboard_api_key", "trmnl_webhook_url",
})
_AUTH_KEYS = frozenset({
    "oauth_google_client_id", "oauth_google_client_secret",
    "oauth_github_client_id", "oauth_github_client_secret",
    "oauth_auto_provision",
})
_SUMMARY_KEYS = frozenset({
    "summary_enabled", "summary_interval_minutes", "summary_window_minutes",
    "summary_to_trmnl", "summary_to_vestaboard", "summary_news_lookback_hours",
})


def setting_category(key: str) -> str:
    """Return the admin tab a setting belongs to: 'notifications', 'auth', 'summary', or 'system'."""
    if key in _NOTIFICATION_KEYS:
        return "notifications"
    if key in _AUTH_KEYS:
        return "auth"
    if key in _SUMMARY_KEYS:
        return "summary"
    return "system"


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
        key="vestaboard_api_key",
        default="",
        description=(
            "Vestaboard Read-Write API key. Powers the 'Vestaboard' channel kind; "
            "blank = unavailable. One key targets one board."
        ),
        secret=True,
    ),
    SettingSpec(
        key="trmnl_webhook_url",
        default="",
        description=(
            "TRMNL webhook URL (Private Plugin → Webhook, e.g. "
            "https://trmnl.com/api/custom_plugins/<uuid>). Powers the 'TRMNL' "
            "channel kind; blank = unavailable. We POST {\"merge_variables\": {...}}."
        ),
        secret=True,
    ),
    # ---- Receiver / station location (for the aircraft-detail map) ---------
    SettingSpec(
        key="receiver_lat",
        default="",
        description=(
            "Latitude of the receiving station, shown as the 'found here' marker "
            "on the aircraft-detail map. Auto-filled by the ingester from the "
            "radio's /data/receiver.json when blank; override here if needed."
        ),
    ),
    SettingSpec(
        key="receiver_lon",
        default="",
        description="Longitude of the receiving station (see receiver_lat).",
    ),
    SettingSpec(
        key="receiver_label",
        default="Local radio",
        description="Name shown for the receiving station on the aircraft-detail map.",
    ),
    SettingSpec(
        key="delivery_retention_days",
        default="30",
        description=(
            "How many days of notification-delivery log rows (sent/failed/skipped) "
            "to retain. The background ingester prunes older rows hourly, and admins "
            "can purge on demand from Diagnostics. 0 or blank disables auto-prune. "
            "Default: 30."
        ),
    ),
    SettingSpec(
        key="sighting_min_interval_seconds",
        default="180",
        description=(
            "Per aircraft per source, store at most one sighting every this many "
            "seconds (plus the first one after a gap). Dramatically reduces storage "
            "vs. saving every poll. Trigger evaluation still runs every tick. "
            "Whole seconds; 0 or blank stores every position. Default: 180 (3 min)."
        ),
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
    SettingSpec(
        key="site_base_url",
        default="",
        description=(
            "Absolute base URL (e.g. https://webstag.tail41807.ts.net:8443) used to "
            "build links in notifications and OAuth redirect URIs. Blank = links omitted."
        ),
    ),
    # ---- Airspace summary (periodic digest for TRMNL/Vestaboard) -----------
    SettingSpec(
        key="summary_enabled",
        default="false",
        description="Master switch for the periodic airspace summary push. 'true'/'false'.",
    ),
    SettingSpec(
        key="summary_interval_minutes",
        default="15",
        description="How often to push the airspace summary (minutes). Default 15 (TRMNL refresh).",
    ),
    SettingSpec(
        key="summary_window_minutes",
        default="15",
        description="How far back the summary looks for the aircraft count (minutes). Default 15.",
    ),
    SettingSpec(
        key="summary_to_trmnl",
        default="true",
        description="Push the summary to the TRMNL transport (if configured). 'true'/'false'.",
    ),
    SettingSpec(
        key="summary_to_vestaboard",
        default="false",
        description="Push the summary to the Vestaboard transport (if configured). 'true'/'false'.",
    ),
    SettingSpec(
        key="summary_news_lookback_hours",
        default="6",
        description=(
            "If no 'qualifying' trigger fired within the summary window, the news line "
            "falls back to 'time since last <name>'. This is how far back to look for that "
            "last event before giving up. Default 6 hours."
        ),
    ),
    SettingSpec(
        key="summary_last_run",
        default="",
        description="Internal: ISO timestamp of the last summary push (managed automatically).",
    ),
    # ---- OAuth / SSO (optional; blank = disabled) --------------------------
    SettingSpec(
        key="oauth_google_client_id",
        default="",
        description="Google OAuth client ID. Blank disables Google sign-in. Redirect URI: <site_base_url>/auth/oauth/google/callback",
    ),
    SettingSpec(
        key="oauth_google_client_secret",
        default="",
        description="Google OAuth client secret.",
        secret=True,
    ),
    SettingSpec(
        key="oauth_github_client_id",
        default="",
        description="GitHub OAuth client ID. Blank disables GitHub sign-in. Callback URL: <site_base_url>/auth/oauth/github/callback",
    ),
    SettingSpec(
        key="oauth_github_client_secret",
        default="",
        description="GitHub OAuth client secret.",
        secret=True,
    ),
    SettingSpec(
        key="oauth_auto_provision",
        default="false",
        description=(
            "When true, a successful OAuth login with an unknown email auto-creates "
            "a non-admin user. When false (default), OAuth only logs in users whose "
            "email already matches an existing account. 'true'/'false'."
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
