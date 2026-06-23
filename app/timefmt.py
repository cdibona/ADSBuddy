"""Per-user timezone formatting for templates.

Timestamps are stored in UTC. The current user's timezone is stashed on
``request.state.user_tz`` by the auth dependency; the ``localdt`` Jinja filter
reads it and converts. Server-side code (e.g. data baked into a <script>) can
use ``format_dt`` directly with a tz name.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import pass_context

# Curated list for the profile selector (label shown is the IANA name).
COMMON_TIMEZONES: tuple[str, ...] = (
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Phoenix",
    "America/Los_Angeles",
    "America/Anchorage",
    "Pacific/Honolulu",
    "America/Toronto",
    "America/Vancouver",
    "America/Mexico_City",
    "America/Sao_Paulo",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Madrid",
    "Europe/Moscow",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Australia/Sydney",
    "Pacific/Auckland",
)

DEFAULT_FMT = "%Y-%m-%d %H:%M:%S"


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo("UTC")


def is_valid_tz(name: str | None) -> bool:
    if not name:
        return False
    try:
        ZoneInfo(name)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return False


def format_dt(dt: datetime | None, tzname: str | None, fmt: str = DEFAULT_FMT) -> str:
    """Convert a (UTC-assumed) datetime to ``tzname`` and format it."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_zone(tzname)).strftime(fmt)


@pass_context
def _localdt(ctx, dt: datetime | None, fmt: str = DEFAULT_FMT) -> str:
    request = ctx.get("request")
    tzname = getattr(getattr(request, "state", None), "user_tz", "UTC") or "UTC"
    return format_dt(dt, tzname, fmt)


def register(templates) -> None:
    """Install the localdt filter and expose the tz list to templates."""
    templates.env.filters["localdt"] = _localdt
    templates.env.globals["common_timezones"] = COMMON_TIMEZONES
