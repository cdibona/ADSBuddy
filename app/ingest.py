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
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import flight_routes, notifications, triggers as trigger_engine, version
from app.database import SessionLocal
from app.models import Aircraft, NotificationDelivery, RadioSource, Sighting, TriggerFiring
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)

DEFAULT_INTERVAL = 5.0
_CLEANUP_INTERVAL = 3600.0  # run at most once per hour
_last_cleanup: float = 0.0
_last_delivery_cleanup: float = 0.0


async def delete_deliveries_before(session: AsyncSession, cutoff: datetime) -> int:
    """Batch-delete notification_deliveries older than ``cutoff``. Caller commits per batch.

    Shared by the hourly auto-prune and the admin on-demand purge.
    """
    total = 0
    batch_size = 5_000
    while True:
        id_rows = (
            await session.execute(
                select(NotificationDelivery.id)
                .where(NotificationDelivery.created_at < cutoff)
                .limit(batch_size)
            )
        ).scalars().all()
        if not id_rows:
            break
        result = await session.execute(
            delete(NotificationDelivery).where(NotificationDelivery.id.in_(id_rows))
        )
        total += result.rowcount
        await session.commit()
    return total


async def _maybe_cleanup_deliveries() -> None:
    """Prune the notification-delivery log on the same hourly cadence as sightings."""
    global _last_delivery_cleanup
    now = time.monotonic()
    if now - _last_delivery_cleanup < _CLEANUP_INTERVAL:
        return
    _last_delivery_cleanup = now
    try:
        async with SessionLocal() as session:
            days = _parse_retention_days(await get_setting(session, "delivery_retention_days"))
            if days is None:
                return  # disabled
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            deleted = await delete_deliveries_before(session, cutoff)
            if deleted:
                log.info("Delivery-log cleanup: deleted %d rows older than %d days.", deleted, days)
    except Exception:
        log.warning("Delivery-log cleanup failed; will retry next cycle.", exc_info=True)
        _last_delivery_cleanup = 0.0


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


def _strip(value: Any, maxlen: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if maxlen is not None:
        s = s[:maxlen]
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


async def downsample_estimate(session: AsyncSession, interval: int) -> tuple[int, int]:
    """(total_sightings, rows_that_would_be_deleted) keeping ~1 per (hex, source,
    ``interval``-second bucket). Only rows older than one interval are eligible
    (so the estimate matches what ``downsample_run`` actually removes — the live
    bucket is protected). Read-only dry run."""
    if interval <= 0:
        raise ValueError("interval must be > 0")
    row = (
        await session.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE seen_at < now() - make_interval(secs => :iv)) "
                "- count(DISTINCT (icao_hex, source, floor(extract(epoch from seen_at) / :iv))) "
                "  FILTER (WHERE seen_at < now() - make_interval(secs => :iv)) AS would_del "
                "FROM sightings"
            ),
            {"iv": interval},
        )
    ).one()
    return int(row.total), int(row.would_del)


async def downsample_run(session: AsyncSession, interval: int) -> int:
    """Delete redundant sightings, keeping the earliest row in each
    (hex, source, ``interval``-second bucket). Batched per hex (uses the
    icao_hex index); commits per hex. Rows newer than one interval are left
    untouched so a concurrent ingest tick can't have its fresh position deleted.
    Irreversible. Returns rows deleted."""
    if interval <= 0:
        raise ValueError("interval must be > 0")
    hexes = (
        await session.execute(text("SELECT DISTINCT icao_hex FROM sightings"))
    ).scalars().all()
    total = 0
    for hx in hexes:
        res = await session.execute(
            text(
                "DELETE FROM sightings s USING ("
                " SELECT id, row_number() OVER ("
                "   PARTITION BY source, floor(extract(epoch from seen_at) / :iv)"
                "   ORDER BY seen_at) AS rn"
                " FROM sightings WHERE icao_hex = :hex) r"
                " WHERE s.id = r.id AND r.rn > 1"
                " AND s.seen_at < now() - make_interval(secs => :iv)"
            ),
            {"iv": interval, "hex": hx},
        )
        total += res.rowcount
        await session.commit()
    return total


async def _upsert_aircraft(session: AsyncSession, entry: dict[str, Any]) -> Aircraft | None:
    hex_id = _strip(entry.get("hex"), 8)
    if not hex_id:
        return None
    hex_id = hex_id.lower()

    reg = _strip(entry.get("r"), 16)
    type_code = _strip(entry.get("t"), 8)
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
        flight=_strip(entry.get("flight"), 16),
        lat=lat,
        lon=lon,
        altitude_baro=_coerce_int(entry.get("alt_baro")),
        altitude_geom=_coerce_int(entry.get("alt_geom")),
        ground_speed=_coerce_float(entry.get("gs")),
        track=_coerce_float(entry.get("track")),
        baro_rate=_coerce_int(entry.get("baro_rate")),
        geom_rate=_coerce_int(entry.get("geom_rate")),
        squawk=_strip(entry.get("squawk"), 8),
        category=_strip(entry.get("category"), 4),
        emergency=_strip(entry.get("emergency"), 16),
        nav_heading=_coerce_float(entry.get("nav_heading")),
        origin_icao=origin,
        destination_icao=destination,
        rssi=_coerce_float(entry.get("rssi")),
        seen_age=_coerce_float(entry.get("seen")),
        raw=entry if store_raw else None,
    )


async def _learn_receiver_location(
    client: httpx.AsyncClient, source: RadioSource
) -> None:
    """Fill a poll source's receiver lat/lon from its radio's receiver.json (once).

    Mutates ``source`` in place (caller commits). Non-fatal on failure.
    """
    if source.receiver_lat is not None and source.receiver_lon is not None:
        return
    if not source.url:
        return
    try:
        resp = await client.get(source.url.rstrip("/") + "/data/receiver.json", timeout=8.0)
        resp.raise_for_status()
        data = resp.json()
        lat, lon = data.get("lat"), data.get("lon")
        if lat is None or lon is None:
            return
        source.receiver_lat = float(lat)
        source.receiver_lon = float(lon)
        log.info("Learned receiver location for source %r: %s, %s", source.name, lat, lon)
    except Exception:
        log.debug("Could not fetch receiver.json for source %r; will retry.", source.name, exc_info=True)


def _parse_min_interval(raw: str | None) -> int:
    """Seconds between stored sightings per (aircraft, source). 0 = store all."""
    if raw is None or not raw.strip():
        return 0
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return 0


async def _trigger_context(session: AsyncSession) -> tuple[list, bool, bool, int]:
    """Shared per-batch context: (active_triggers, need_routes, store_raw, min_interval)."""
    active_triggers = await trigger_engine.load_active_triggers(session)
    need_routes = any(
        t.origin_icaos.strip() or t.destination_icaos.strip() for t in active_triggers
    )
    store_raw = (await get_setting(session, "store_raw_sightings") or "false").lower() == "true"
    min_interval = _parse_min_interval(await get_setting(session, "sighting_min_interval_seconds"))
    return active_triggers, need_routes, store_raw, min_interval


async def _recent_sighting_times(
    session: AsyncSession, source_name: str, hexes: list[str]
) -> dict[str, datetime]:
    """Most-recent stored sighting time per hex for this source (for de-dup)."""
    if not hexes:
        return {}
    rows = await session.execute(
        select(Sighting.icao_hex, func.max(Sighting.seen_at))
        .where(Sighting.icao_hex.in_(hexes), Sighting.source == source_name)
        .group_by(Sighting.icao_hex)
    )
    return {hx: ts for hx, ts in rows.all()}


async def process_entries(
    session: AsyncSession,
    client: httpx.AsyncClient,
    source_name: str,
    entries: list[dict[str, Any]],
    active_triggers: list,
    need_routes: bool,
    store_raw: bool,
    min_interval: int = 0,
) -> tuple[list[TriggerFiring], int]:
    """Upsert aircraft, store sightings (tagged ``source_name``), enrich routes,
    and evaluate triggers for one batch of aircraft.json entries. Caller commits.

    De-dup: when ``min_interval`` > 0, store at most one sighting per
    (aircraft, source) per ``min_interval`` seconds (the first after a gap is
    always stored). Trigger evaluation still runs for every entry. Shared by the
    poll tick and the push endpoint. Returns (new_firings, blocked).
    """
    new_firings: list[TriggerFiring] = []
    blocked_total = 0
    now = datetime.now(timezone.utc)

    last_seen: dict[str, datetime] = {}
    if min_interval > 0:
        hexes = [h for h in (_strip(e.get("hex"), 8) for e in entries) if h]
        last_seen = await _recent_sighting_times(session, source_name, [h.lower() for h in hexes])

    for entry in entries:
        hex_id = _strip(entry.get("hex"), 8)
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

        # Storage de-dup (does NOT affect trigger evaluation below).
        store_it = True
        if min_interval > 0:
            prev = last_seen.get(hex_id)
            if prev is not None:
                elapsed = (now - prev).total_seconds()
                # Suppress only within the window; a negative elapsed (clock skew)
                # falls through to storing rather than wedging the aircraft.
                if 0 <= elapsed < min_interval:
                    store_it = False
        if store_it:
            sighting = _build_sighting(hex_id, entry, origin, destination, store_raw)
            if sighting is not None:
                sighting.source = source_name
                session.add(sighting)
                last_seen[hex_id] = now  # so a repeated hex in this batch isn't re-stored

        if active_triggers:
            facts = trigger_engine.AircraftFacts(
                icao_hex=hex_id,
                callsign=callsign,
                registration=aircraft.registration,
                type_code=aircraft.type_code,
                owner_op=aircraft.owner_op,
                squawk=_strip(entry.get("squawk"), 8),
                emergency=_strip(entry.get("emergency"), 16),
                year=aircraft.year,
                lat=_coerce_float(entry.get("lat")),
                lon=_coerce_float(entry.get("lon")),
                altitude_baro=_coerce_int(entry.get("alt_baro")),
                origin_icao=origin,
                destination_icao=destination,
                category=_strip(entry.get("category"), 4),
            )
            firings, blocked = await trigger_engine.evaluate_and_record(
                session, active_triggers, facts
            )
            new_firings.extend(firings)
            blocked_total += blocked
    return new_firings, blocked_total


async def _tick(client: httpx.AsyncClient) -> int:
    """Poll every active source. Each source runs in its OWN session so a
    failure (fetch or notify) can't corrupt the others; committing each
    source's firings before the next runs lets the cooldown de-dupe an aircraft
    seen by multiple sources in the same tick.
    """
    async with SessionLocal() as session:
        source_ids = (
            await session.execute(
                select(RadioSource.id).where(
                    RadioSource.kind == "poll", RadioSource.is_active.is_(True)
                )
            )
        ).scalars().all()
    if not source_ids:
        log.warning("No active poll sources — skipping tick.")
        return 0

    total_entries = 0
    for source_id in source_ids:
        async with SessionLocal() as session:
            source = await session.get(RadioSource, source_id)
            if source is None or not source.is_active or not source.url:
                continue

            # Learn + persist the receiver location regardless of the fetch below.
            await _learn_receiver_location(client, source)
            await session.commit()

            try:
                resp = await client.get(source.url.rstrip("/") + "/data/aircraft.json", timeout=10.0)
                resp.raise_for_status()
                entries = resp.json().get("aircraft") or []
            except Exception:
                log.warning("Source %r fetch failed; skipping this tick.", source.name, exc_info=True)
                continue

            active_triggers, need_routes, store_raw, min_interval = await _trigger_context(session)
            new_firings, blocked = await process_entries(
                session, client, source.name, entries, active_triggers, need_routes, store_raw, min_interval
            )
            source.last_seen_at = datetime.now(timezone.utc)
            await session.commit()
            total_entries += len(entries)
            log.info(
                "Tick[%s]: %d aircraft, %d firing(s), %d cooldown-blocked.",
                source.name, len(entries), len(new_firings), blocked,
            )
            if new_firings:
                try:
                    await notifications.deliver_for_firings(session, client, new_firings)
                    await session.commit()
                except Exception:
                    log.exception("Notification dispatch failed; firings are still recorded.")
                    await session.rollback()
    return total_entries


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
                await _tick(client)
            except Exception:
                log.exception("Ingest tick failed; will retry.")
            await _maybe_cleanup_sightings()
            await _maybe_cleanup_deliveries()
            await _maybe_send_summary(client)
            await _maybe_check_release(client)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    log.info("Aircraft ingester stopped.")


async def _maybe_send_summary(client: httpx.AsyncClient) -> None:
    """Push the airspace summary to each summary-mode channel that's due."""
    try:
        async with SessionLocal() as session:
            await notifications.deliver_summaries(session, client)
    except Exception:
        log.warning("Airspace summary push failed; will retry next cycle.", exc_info=True)


_RELEASE_CHECK_INTERVAL = 6 * 3600  # seconds
_last_release_check = 0.0


async def _maybe_check_release(client: httpx.AsyncClient) -> None:
    """Refresh the latest-release cache at most every ~6h (drives the UI badge)."""
    global _last_release_check
    now = asyncio.get_event_loop().time()
    if _last_release_check and now - _last_release_check < _RELEASE_CHECK_INTERVAL:
        return
    _last_release_check = now
    await version.refresh_latest_release(client)
