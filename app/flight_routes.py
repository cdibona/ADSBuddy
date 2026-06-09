"""adsbdb.com callsign -> origin/destination lookup with a Postgres cache.

We only call out when a setting says to (`route_lookup_enabled`), and we
re-use cached rows until they exceed `route_cache_ttl_hours`. Negative
results are cached too so we don't keep asking about VFR / non-airline
callsigns the API doesn't know.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FlightRoute
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)

ADSBDB_BASE = "https://api.adsbdb.com/v0/callsign"


def _normalize(callsign: str) -> str:
    return callsign.strip().upper()


async def _lookup_remote(client: httpx.AsyncClient, callsign: str) -> tuple[str | None, str | None, bool]:
    """Return (origin_icao, destination_icao, found)."""
    url = f"{ADSBDB_BASE}/{callsign}"
    try:
        resp = await client.get(url, timeout=5.0, headers={"User-Agent": "ADSBuddy/0.1"})
    except httpx.RequestError as e:
        log.debug("adsbdb request failed for %s: %s", callsign, e)
        return None, None, False
    if resp.status_code == 404:
        return None, None, False
    if resp.status_code != 200:
        log.warning("adsbdb returned %s for %s", resp.status_code, callsign)
        return None, None, False
    try:
        payload = resp.json()
        route = payload["response"]["flightroute"]
        origin = route.get("origin", {}).get("icao_code")
        dest = route.get("destination", {}).get("icao_code")
        return origin, dest, True
    except (KeyError, TypeError, ValueError):
        return None, None, False


async def get_route(
    session: AsyncSession,
    client: httpx.AsyncClient,
    callsign: str,
) -> FlightRoute | None:
    """Return the cached or freshly-fetched route. None if disabled or unknown.

    Caller is responsible for committing — we add new rows but don't commit.
    """
    cs = _normalize(callsign)
    if not cs:
        return None

    enabled = (await get_setting(session, "route_lookup_enabled") or "true").lower() == "true"
    ttl_hours_raw = await get_setting(session, "route_cache_ttl_hours") or "24"
    try:
        ttl = timedelta(hours=max(1.0, float(ttl_hours_raw)))
    except ValueError:
        ttl = timedelta(hours=24)

    existing = (
        await session.execute(select(FlightRoute).where(FlightRoute.callsign == cs))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing is not None and (now - existing.fetched_at) < ttl:
        return existing if not existing.not_found else None

    if not enabled:
        return existing if (existing is not None and not existing.not_found) else None

    origin, dest, found = await _lookup_remote(client, cs)
    if existing is None:
        existing = FlightRoute(
            callsign=cs,
            origin_icao=origin,
            destination_icao=dest,
            not_found=not found,
            fetched_at=now,
        )
        session.add(existing)
    else:
        existing.origin_icao = origin
        existing.destination_icao = dest
        existing.not_found = not found
        existing.fetched_at = now
    return existing if found else None
