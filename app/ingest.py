"""Background poller for the radio's tar1090 aircraft.json feed.

Per tick we: pull aircraft.json, upsert one row per ICAO hex into
`aircraft`, append one row per position-bearing entry into `sightings`
(capturing every column the model defines plus, optionally, the raw entry
as JSONB), enrich callsigns with origin/destination from the adsbdb.com
cache, and evaluate active triggers.

Radio URL and interval are read fresh each tick from the settings table
so admins can retune without restarting the app.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import flight_routes, notifications, triggers as trigger_engine
from app.database import SessionLocal
from app.models import Aircraft, Sighting, TriggerFiring
from app.settings_store import get as get_setting
from app.settings_store import set_value

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 5.0
_CLEANUP_INTERVAL = 3600.0  # run at most once per hour
_last_cleanup: float = 0.0


def _coerce_int(value: Any) -> int | None:
    if value in (None, "", "ground"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _strip(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_retention_days(raw: str | None) -> int | None:
    """Parse sightings_retention_days setting.

    Returns None if cleanup is disabled (value <= 0).
    Falls back to 30 days on invalid/missing input.
    """
    if raw is None or raw.strip() == "":
        return 30
    try:
        days = int(raw.strip())
    except ValueError:
        return 30
    if days <= 0:
        return None  # disabled
    return days


async def _maybe_cleanup_sightings() -> None:
    """Prune old sightings rows — at most once per ``_CLEANUP_INTERVAL`` seconds.

    Runs in its own session, independent of the ingest tick session.
    Failure is non-fatal: logs a warning and resets the timer for a retry.
    """
    global _last_cleanup
    now = time.monotonic()
    if now - _last_cleanup < _CLEANUP_INTERVAL:
        return
    _last_cleanup = now

    t0 = time.monotonic()
    total_deleted = 0
    cutoff: datetime | None = None
    try:
        async with SessionLocal() as session:
            raw = await get_setting(session, "sightings_retention_days")
            days = _parse_retention_days(raw)
            if days is None:
                log.debug("Sightings retention disabled; skipping cleanup.")
                return
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            batch_size = 5_000
            while True:
                # Two-step batch delete: select IDs first, then delete.
                # Avoids the PostgreSQL restriction on mutating a table
                # that appears in a subquery of the same DELETE statement.
                id_rows = (
                    await session.execute(
                        select(Sighting.id)
                        .where(Sighting.seen_at < cutoff)
                        .limit(batch_size)
                    )
                ).scalars().all()
                if not id_rows:
                    break
                result = await session.execute(
                    delete(Sighting).where(Sighting.id.in_(id_rows))
                )
                total_deleted += result.rowcount
                await session.commit()
    except Exception:
        log.warning("Sightings cleanup failed; will retry next cycle.", exc_info=True)
        _last_cleanup = 0.0  # reset so we retry sooner
        return

    elapsed = time.monotonic() - t0
    cutoff_str = cutoff.strftime("%Y-%m-%d") if cutoff else "?"
    if total_deleted:
        log.info(
            "Sightings cleanup: deleted %d rows older than %s (%.1fs).",
            total_deleted,
            cutoff_str,
            elapsed,
        )
    else:
        log.debug("Sightings cleanup: nothing to prune (cutoff %s).", cutoff_str)


async def _upsert_aircraft(session: AsyncSession, entry: dict[str, Any]) -> Aircraft | None:
    hex_id = _strip(entry.get("hex"))
    if not hex_id:
        return None
    hex_id = hex_id.lower()

    reg = _strip(entry.get("r"))
    type_code = _strip(entry.get("t"))
    description = _strip(entry.get("desc"))
    owner = _strip(entry.get("ownOp"))
    year = _coerce_int(entry.get("year"))

    aircraft = (
        await session.execute(select(Aircraft).where(Aircraft.icao_hex == hex_id))
    ).scalar_one_or_none()
    if aircraft is None:
        aircraft = Aircraft(
            icao_hex=hex_id,
            registration=reg,
            type_code=type_code,
            description=description,
            owner_op=owner,
            year=year,
        )
        session.add(aircraft)
    else:
        # Backfill missing facts but don't overwrite good data with None.
        if reg and not aircraft.registration:
            aircraft.registration = reg
        if type_code and not aircraft.type_code:
            aircraft.type_code = type_code
        if description and not aircraft.description:
            aircraft.description = description
        if owner and not aircraft.owner_op:
            aircraft.owner_op = owner
        if year and not aircraft.year:
            aircraft.year = year
    return aircraft


def _build_sighting(
    hex_id: str,
    entry: dict[str, Any],
    origin: str | None,
    destination: str | None,
    store_raw: bool,
) -> Sighting | None:
    lat = _coerce_float(entry.get("lat"))
    lon = _coerce_float(entry.get("lon"))
    if lat is None or lon is None:
        return None
    return Sighting(
        icao_hex=hex_id,
        flight=_strip(entry.get("flight")),
        lat=lat,
        lon=lon,
        altitude_baro=_coerce_int(entry.get("alt_baro")),
        altitude_geom=_coerce_int(entry.get("alt_geom")),
        ground_speed=_coerce_float(entry.get("gs")),
        track=_coerce_float(entry.get("track")),
        baro_rate=_coerce_int(entry.get("baro_rate")),
        geom_rate=_coerce_int(entry.get("geom_rate")),
        squawk=_strip(entry.get("squawk")),
        category=_strip(entry.get("category")),
        emergency=_strip(entry.get("emergency")),
        nav_heading=_coerce_float(entry.get("nav_heading")),
        origin_icao=origin,
        destination_icao=destination,
        rssi=_coerce_float(entry.get("rssi")),
        seen_age=_coerce_float(entry.get("seen")),
        raw=entry if store_raw else None,
    )


async def _store_receiver_location_if_missing(
    client: httpx.AsyncClient, session: AsyncSession, radio: str
) -> None:
    """One-time bootstrap of the receiver's lat/lon from the radio.

    Runs only while ``receiver_lat`` is blank; once stored (or admin-set) the
    cheap settings check below short-circuits and we never refetch. Failure is
    non-fatal — we just try again next tick.
    """
    existing = await get_setting(session, "receiver_lat")
    if existing and existing.strip():
        return
    try:
        resp = await client.get(radio.rstrip("/") + "/data/receiver.json", timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is None or lon is None:
            return
        await set_value(session, "receiver_lat", str(lat))
        await set_value(session, "receiver_lon", str(lon))
        log.info("Learned receiver location from receiver.json: %s, %s", lat, lon)
    except Exception:
        log.debug("Could not fetch receiver.json for location; will retry.", exc_info=True)


async def _tick(client: httpx.AsyncClient, session: AsyncSession) -> int:
    radio = await get_setting(session, "radio_base_url")
    if not radio:
        log.warning("radio_base_url is unset — skipping tick.")
        return 0
    await _store_receiver_location_if_missing(client, session, radio)
    url = radio.rstrip("/") + "/data/aircraft.json"
    resp = await client.get(url, timeout=10.0)
    resp.raise_for_status()
    payload = resp.json()
    entries = payload.get("aircraft") or []

    store_raw = (await get_setting(session, "store_raw_sightings") or "false").lower() == "true"

    active_triggers = await trigger_engine.load_active_triggers(session)
    need_routes = any(
        t.origin_icaos.strip() or t.destination_icaos.strip() for t in active_triggers
    )

    new_firings: list[TriggerFiring] = []
    blocked_total = 0
    for entry in entries:
        hex_id = _strip(entry.get("hex"))
        if not hex_id:
            continue
        hex_id = hex_id.lower()

        aircraft = await _upsert_aircraft(session, entry)
        if aircraft is None:
            continue

        callsign = _strip(entry.get("flight"))
        origin: str | None = None
        destination: str | None = None
        if callsign and need_routes:
            route = await flight_routes.get_route(session, client, callsign)
            if route is not None:
                origin = route.origin_icao
                destination = route.destination_icao

        sighting = _build_sighting(hex_id, entry, origin, destination, store_raw)
        if sighting is not None:
            session.add(sighting)

        if active_triggers:
            facts = trigger_engine.AircraftFacts(
                icao_hex=hex_id,
                callsign=callsign,
                registration=aircraft.registration,
                type_code=aircraft.type_code,
                year=aircraft.year,
                lat=_coerce_float(entry.get("lat")),
                lon=_coerce_float(entry.get("lon")),
                altitude_baro=_coerce_int(entry.get("alt_baro")),
                origin_icao=origin,
                destination_icao=destination,
            )
            firings, blocked = await trigger_engine.evaluate_and_record(
                session, active_triggers, facts
            )
            new_firings.extend(firings)
            blocked_total += blocked

    # Commit sightings/aircraft first so they survive even if delivery crashes.
    await session.commit()

    log.info(
        "Tick: %d aircraft, %d active trigger(s), %d firing(s), %d cooldown-blocked.",
        len(entries),
        len(active_triggers),
        len(new_firings),
        blocked_total,
    )

    if new_firings:
        try:
            await notifications.deliver_for_firings(session, client, new_firings)
            await session.commit()
        except Exception:
            log.exception("Notification dispatch failed; firings are still recorded.")
            await session.rollback()
    return len(entries)


async def run_forever(stop_event: asyncio.Event) -> None:
    log.info("Aircraft ingester starting.")
    async with httpx.AsyncClient() as client:
        while not stop_event.is_set():
            interval = DEFAULT_INTERVAL
            try:
                async with SessionLocal() as session:
                    raw = await get_setting(session, "ingest_interval_seconds")
                    if raw:
                        try:
                            interval = max(1.0, float(raw))
                        except ValueError:
                            pass
                    await _tick(client, session)
            except Exception:
                log.exception("Ingest tick failed; will retry.")
            await _maybe_cleanup_sightings()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    log.info("Aircraft ingester stopped.")
