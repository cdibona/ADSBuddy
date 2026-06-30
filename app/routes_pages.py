"""Top-level page routes: map (iframe), recent aircraft, and history search."""

from __future__ import annotations

import math
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timefmt, version
from app.aircraft_helpers import (
    opensky_url,
    registration_provider,
    registration_url,
    trigger_prefill_url,
    type_url,
)
from app.database import get_session
from app.deps import current_user_optional, current_viewer, require_user, require_viewer
from app.models import Aircraft, RadioSource, Sighting, Trigger, TriggerFiring, User
from app.type_links import type_link_map
from app.settings_store import get_required

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_HEX_RE = re.compile(r"^[0-9a-f]{1,8}$")
_VALID_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HISTORY_PER_PAGE = 50
# How many recent position-bearing sightings to plot as the detail-page path.
_MAP_POSITION_LIMIT = 250

# Marker colors assigned per sighting source on the detail map.
_SOURCE_PALETTE = ("#4ea4ff", "#3fb950", "#ff6b6b", "#d2a8ff", "#f0883e")


def _to_float(raw: str | None) -> float | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_trigger_choice(raw: str | None) -> str | int | None:
    """Parse the history 'trigger' filter: None (off), 'any', or a trigger id."""
    if not raw:
        return None
    v = raw.strip().lower()
    if v == "any":
        return "any"
    try:
        return int(v)
    except ValueError:
        return None


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
# Register URL helpers as Jinja2 globals so all templates can call them directly.
templates.env.globals.update(
    registration_url=registration_url,
    registration_provider=registration_provider,
    type_url=type_url,
    opensky_url=opensky_url,
    trigger_prefill_url=trigger_prefill_url,
)
version.register(templates)
timefmt.register(templates)


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: User | None = Depends(current_viewer),
    db: AsyncSession = Depends(get_session),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    site_title = await get_required(db, "site_title")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "radio_base_url": await _map_radio_url(db),
            "site_title": site_title,
        },
    )


async def _map_radio_url(db: AsyncSession) -> str:
    """tar1090 URL embedded on the Map page: the pinned source (Admin → Sources
    'Show on map') wins; else the legacy radio_base_url; else the first active
    poll source with a URL."""
    from app.settings_store import get as get_setting

    pinned = (await get_setting(db, "map_source_id") or "").strip()
    if pinned.isdigit():
        src = await db.get(RadioSource, int(pinned))
        if src is not None and src.url:
            return src.url.rstrip("/")
    base = (await get_setting(db, "radio_base_url") or "").strip()
    if base:
        return base.rstrip("/")
    row = (
        await db.execute(
            select(RadioSource)
            .where(RadioSource.kind == "poll", RadioSource.is_active.is_(True), RadioSource.url.isnot(None))
            .order_by(RadioSource.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    return row.url.rstrip("/") if (row and row.url) else ""


@router.get("/aircraft", response_class=HTMLResponse)
async def recent_aircraft(
    request: Request,
    type: str | None = Query(None),
    user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_session),
):
    type_q = (type or "").strip()
    stmt = select(Aircraft).order_by(Aircraft.last_seen.desc())
    if type_q:
        stmt = stmt.where(Aircraft.type_code.ilike(f"%{type_q}%"))
    rows = await db.execute(stmt.limit(200))
    aircraft = rows.scalars().all()

    # Most common type codes seen, as quick-filter chips.
    common = (
        await db.execute(
            select(Aircraft.type_code, func.count())
            .where(Aircraft.type_code.isnot(None), Aircraft.type_code != "")
            .group_by(Aircraft.type_code)
            .order_by(func.count().desc())
            .limit(14)
        )
    ).all()
    common_types = [t for t, _n in common]
    type_links = await type_link_map(db, [a.type_code for a in aircraft])

    return templates.TemplateResponse(
        request,
        "aircraft.html",
        {
            "user": user,
            "aircraft": aircraft,
            "type_active": type_q or None,
            "common_types": common_types,
            "type_links": type_links,
        },
    )


_STATS_WINDOWS = {"15m": 15, "1h": 60, "today": None}


@router.get("/stats", response_class=HTMLResponse)
async def airspace_stats(
    request: Request,
    window: str = Query("15m"),
    user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_session),
):
    from datetime import datetime, timezone

    from app.stats import airspace_breakdown

    window = window if window in _STATS_WINDOWS else "15m"
    if window == "today":
        now = datetime.now(timezone.utc)
        minutes = max(1, int((now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() // 60))
    else:
        minutes = _STATS_WINDOWS[window]
    stats = await airspace_breakdown(db, minutes)
    return templates.TemplateResponse(
        request,
        "stats.html",
        {"user": user, "stats": stats, "window": window},
    )


@router.get("/aircraft/{icao_hex}", response_class=HTMLResponse)
async def aircraft_detail(
    icao_hex: str,
    request: Request,
    user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_session),
):
    hex_lower = icao_hex.strip().lower()

    # Fetch the aircraft record.
    result = await db.execute(select(Aircraft).where(Aircraft.icao_hex == hex_lower))
    aircraft = result.scalar_one_or_none()
    if aircraft is None:
        raise HTTPException(status_code=404, detail="Aircraft not found")

    # Last 10 sightings, newest first.
    sightings_result = await db.execute(
        select(Sighting)
        .where(Sighting.icao_hex == hex_lower)
        .order_by(Sighting.seen_at.desc())
        .limit(10)
    )
    sightings = sightings_result.scalars().all()

    # Last 10 trigger firings, newest first. Non-admins only see their own;
    # guests see none (firings reveal personal trigger config).
    if getattr(user, "is_guest", False):
        firings_rows = []
    else:
        firings_stmt = (
            select(TriggerFiring, Trigger)
            .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .where(TriggerFiring.icao_hex == hex_lower)
            .order_by(TriggerFiring.fired_at.desc())
            .limit(10)
        )
        if not user.is_admin:
            firings_stmt = firings_stmt.where(Trigger.owner_id == user.id)
        firings_rows = (await db.execute(firings_stmt)).all()

    # ---- Map data: pull a deeper, position-bearing slice (independent of the
    # 10-row table above) so the map can draw an actual flight path, not just
    # the last handful of points. Newest-first from the DB, mapped oldest→newest.
    map_rows = (
        await db.execute(
            select(Sighting)
            .where(
                Sighting.icao_hex == hex_lower,
                Sighting.lat.is_not(None),
                Sighting.lon.is_not(None),
            )
            .order_by(Sighting.seen_at.desc())
            .limit(_MAP_POSITION_LIMIT)
        )
    ).scalars().all()

    color_by_source: dict[str, str] = {}
    map_points: list[dict] = []
    for s in reversed(map_rows):  # oldest → newest, so the path runs forward in time
        if s.source not in color_by_source:
            color_by_source[s.source] = _SOURCE_PALETTE[
                len(color_by_source) % len(_SOURCE_PALETTE)
            ]
        map_points.append(
            {
                "lat": s.lat,
                "lon": s.lon,
                "t": timefmt.format_dt(s.seen_at, user.timezone, "%Y-%m-%d %H:%M:%S %Z"),
                "source": s.source,
                "color": color_by_source[s.source],
                "alt": s.altitude_baro,
                "flight": s.flight,
                "track": s.track,  # heading in degrees, for direction arrows
            }
        )
    map_sources = [{"source": src, "color": clr} for src, clr in color_by_source.items()]

    # Station markers: every source that knows its receiver location.
    recv_rows = (
        await db.execute(
            select(RadioSource).where(
                RadioSource.receiver_lat.is_not(None),
                RadioSource.receiver_lon.is_not(None),
            )
        )
    ).scalars().all()
    receivers = [
        {"lat": r.receiver_lat, "lon": r.receiver_lon, "label": r.name} for r in recv_rows
    ]

    # Guests shouldn't see the operator's casual source names — relabel them
    # generically ("Source" / "Source 1", "Source 2", … when there's more than one),
    # consistently across the legend, point popups, and receiver markers.
    if getattr(user, "is_guest", False):
        names = list(dict.fromkeys(
            [*color_by_source.keys(), *(r["label"] for r in receivers)]
        ))
        multi = len(names) > 1
        alias = {n: (f"Source {i}" if multi else "Source") for i, n in enumerate(names, 1)}
        for p in map_points:
            p["source"] = alias.get(p["source"], "Source")
        map_sources = [{"source": alias.get(s["source"], "Source"), "color": s["color"]} for s in map_sources]
        receivers = [{**r, "label": alias.get(r["label"], "Source")} for r in receivers]

    return templates.TemplateResponse(
        request,
        "aircraft_detail.html",
        {
            "user": user,
            "aircraft": aircraft,
            "sightings": sightings,
            "firings_rows": firings_rows,
            "map_points": map_points,
            "map_sources": map_sources,
            "receivers": receivers,
            "type_links": await type_link_map(db, [aircraft.type_code]),
        },
    )


# ---------------------------------------------------------------------------
# History search helpers
# ---------------------------------------------------------------------------

def _parse_history_filters(
    tail: str | None,
    hex_raw: str | None,
    callsign: str | None,
    type_code: str | None,
    owner: str | None,
    year_raw: str | None,
    route: str | None,
    start_date: str | None,
    end_date: str | None,
) -> tuple[dict, list[str]]:
    """Parse and validate history search inputs.

    Returns (filters_dict, errors_list).  filters_dict contains only valid,
    normalised values; errors_list is empty on success.
    """
    filters: dict = {}
    errors: list[str] = []

    if tail:
        val = tail.strip()
        if val:
            filters["tail"] = val

    if hex_raw:
        val = hex_raw.strip().lower()
        if val:
            if not _VALID_HEX_RE.match(val):
                errors.append(
                    f"Invalid ICAO hex '{hex_raw}' — must be 1–8 hex digits."
                )
            else:
                filters["hex"] = val

    if callsign:
        val = callsign.strip()
        if val:
            filters["callsign"] = val

    if type_code:
        val = type_code.strip()
        if val:
            filters["type_code"] = val

    if owner:
        val = owner.strip()
        if val:
            filters["owner"] = val

    if year_raw:
        val = year_raw.strip()
        if val:
            try:
                yr = int(val)
                if 1900 <= yr <= 2100:
                    filters["year"] = yr
                else:
                    errors.append(
                        f"Year {yr} is out of range — must be between 1900 and 2100."
                    )
            except ValueError:
                errors.append(f"Year '{year_raw}' is not a valid number.")

    if route:
        val = route.strip()
        if val:
            filters["route"] = val

    if start_date:
        val = start_date.strip()
        if val:
            if not _VALID_DATE_RE.match(val):
                errors.append(
                    f"Start date '{start_date}' must be in YYYY-MM-DD format."
                )
            else:
                try:
                    filters["start_dt"] = datetime(
                        *[int(x) for x in val.split("-")], tzinfo=timezone.utc
                    )
                except ValueError:
                    errors.append(f"Start date '{start_date}' is not a valid date.")

    if end_date:
        val = end_date.strip()
        if val:
            if not _VALID_DATE_RE.match(val):
                errors.append(
                    f"End date '{end_date}' must be in YYYY-MM-DD format."
                )
            else:
                try:
                    # End of the specified day (exclusive upper bound = next day midnight)
                    parsed = datetime(*[int(x) for x in val.split("-")], tzinfo=timezone.utc)
                    filters["end_dt"] = parsed + timedelta(days=1)
                except ValueError:
                    errors.append(f"End date '{end_date}' is not a valid date.")

    return filters, errors


def _build_history_conditions(filters: dict) -> list:
    """Build a list of SQLAlchemy WHERE conditions from parsed history filters.

    All conditions are AND-combined by callers via .where(*conditions).
    """
    conditions = []

    if "tail" in filters:
        conditions.append(Aircraft.registration.ilike(f"%{filters['tail']}%"))

    if "hex" in filters:
        conditions.append(Aircraft.icao_hex == filters["hex"])

    if "type_code" in filters:
        conditions.append(Aircraft.type_code.ilike(f"%{filters['type_code']}%"))

    if "owner" in filters:
        conditions.append(Aircraft.owner_op.ilike(f"%{filters['owner']}%"))

    if "year" in filters:
        conditions.append(Aircraft.year == filters["year"])

    if "callsign" in filters:
        pattern = f"%{filters['callsign']}%"
        sub = (
            select(Sighting.id)
            .where(
                Sighting.icao_hex == Aircraft.icao_hex,
                Sighting.flight.ilike(pattern),
            )
            .correlate(Aircraft)
            .exists()
        )
        conditions.append(sub)

    if "route" in filters:
        pattern = f"%{filters['route']}%"
        sub = (
            select(Sighting.id)
            .where(
                Sighting.icao_hex == Aircraft.icao_hex,
                or_(
                    Sighting.origin_icao.ilike(pattern),
                    Sighting.destination_icao.ilike(pattern),
                ),
            )
            .correlate(Aircraft)
            .exists()
        )
        conditions.append(sub)

    # Date range — filter aircraft that had at least one sighting in the window.
    date_conditions: list = []
    if "start_dt" in filters:
        date_conditions.append(Sighting.seen_at >= filters["start_dt"])
    if "end_dt" in filters:
        date_conditions.append(Sighting.seen_at < filters["end_dt"])
    if date_conditions:
        sub = (
            select(Sighting.id)
            .where(Sighting.icao_hex == Aircraft.icao_hex, *date_conditions)
            .correlate(Aircraft)
            .exists()
        )
        conditions.append(sub)

    return conditions


# ---------------------------------------------------------------------------
# History search route
# ---------------------------------------------------------------------------

@router.get("/history", response_class=HTMLResponse)
async def history_search(
    request: Request,
    user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_session),
    tail: str | None = Query(None),
    hex_raw: str | None = Query(None, alias="hex"),
    callsign: str | None = Query(None),
    type_code: str | None = Query(None, alias="type"),
    owner: str | None = Query(None),
    year_raw: str | None = Query(None, alias="year"),
    route: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    trigger: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    filters, errors = _parse_history_filters(
        tail, hex_raw, callsign, type_code, owner, year_raw, route,
        start_date, end_date,
    )
    # Guests can't use the trigger filter (it's personal config) — ignore it.
    is_guest = getattr(user, "is_guest", False)
    trigger_choice = None if is_guest else _parse_trigger_choice(trigger)

    # Repopulate the form with raw user inputs.
    form = {
        "tail": tail or "",
        "hex": hex_raw or "",
        "callsign": callsign or "",
        "type": type_code or "",
        "owner": owner or "",
        "year": year_raw or "",
        "route": route or "",
        "start_date": start_date or "",
        "end_date": end_date or "",
        "trigger": trigger or "",
    }

    # Triggers available for the dropdown (own triggers; admins see all; guests none).
    if is_guest:
        trigger_options = []
    else:
        trig_stmt = select(Trigger.id, Trigger.name).order_by(Trigger.name)
        if not user.is_admin:
            trig_stmt = trig_stmt.where(Trigger.owner_id == user.id)
        trigger_options = (await db.execute(trig_stmt)).all()

    # Only search if filters were supplied and are valid.
    searched = (bool(filters) or trigger_choice is not None) and not errors
    aircraft_page: list[Aircraft] = []
    recent_sightings: dict[str, Sighting] = {}
    total = 0
    total_pages = 1

    if searched:
        conditions = _build_history_conditions(filters)

        # Trigger filter: aircraft that have fired the chosen trigger (or any).
        # Owner-scoped for non-admins so a crafted id can't probe others' triggers.
        if trigger_choice is not None:
            fsub = select(TriggerFiring.id).where(
                TriggerFiring.icao_hex == Aircraft.icao_hex
            )
            if trigger_choice != "any":
                fsub = fsub.where(TriggerFiring.trigger_id == trigger_choice)
            if not user.is_admin:
                fsub = fsub.join(
                    Trigger, Trigger.id == TriggerFiring.trigger_id
                ).where(Trigger.owner_id == user.id)
            conditions.append(fsub.correlate(Aircraft).exists())

        # Count total matching aircraft (1 query).
        count_stmt = select(func.count()).select_from(Aircraft)
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total = (await db.execute(count_stmt)).scalar_one()

        total_pages = max(1, math.ceil(total / _HISTORY_PER_PAGE))
        page = min(page, total_pages)
        offset = (page - 1) * _HISTORY_PER_PAGE

        # Fetch the aircraft page (1 query).
        data_stmt = (
            select(Aircraft).order_by(Aircraft.last_seen.desc())
            .limit(_HISTORY_PER_PAGE)
            .offset(offset)
        )
        if conditions:
            data_stmt = data_stmt.where(*conditions)
        aircraft_page = (await db.execute(data_stmt)).scalars().all()

        # Batch-load most recent sighting per aircraft on this page (1 query).
        hex_list = [a.icao_hex for a in aircraft_page]
        if hex_list:
            # Subquery: max seen_at per hex in the page.
            latest_subq = (
                select(
                    Sighting.icao_hex,
                    func.max(Sighting.seen_at).label("max_seen"),
                )
                .where(Sighting.icao_hex.in_(hex_list))
                .group_by(Sighting.icao_hex)
                .subquery()
            )
            latest_stmt = select(Sighting).join(
                latest_subq,
                and_(
                    Sighting.icao_hex == latest_subq.c.icao_hex,
                    Sighting.seen_at == latest_subq.c.max_seen,
                ),
            )
            for s in (await db.execute(latest_stmt)).scalars().all():
                # Keep only the first in case of timestamp ties.
                if s.icao_hex not in recent_sightings:
                    recent_sightings[s.icao_hex] = s

    # Build the base query string for pagination links (filters only, no page).
    qs_parts = []
    for key, raw in [
        ("tail", tail), ("hex", hex_raw), ("callsign", callsign),
        ("type", type_code), ("owner", owner), ("year", year_raw),
        ("route", route), ("start_date", start_date), ("end_date", end_date),
        ("trigger", trigger),
    ]:
        if raw and raw.strip():
            qs_parts.append(f"{key}={urllib.parse.quote_plus(raw.strip())}")
    filter_qs = "&".join(qs_parts)

    start = (page - 1) * _HISTORY_PER_PAGE + 1 if total else 0
    end = min((page - 1) * _HISTORY_PER_PAGE + _HISTORY_PER_PAGE, total)

    return templates.TemplateResponse(
        request,
        "history_search.html",
        {
            "user": user,
            "form": form,
            "errors": errors,
            "searched": searched,
            "trigger_options": trigger_options,
            "aircraft": aircraft_page,
            "recent_sightings": recent_sightings,
            "total": total,
            "page": page,
            "per_page": _HISTORY_PER_PAGE,
            "total_pages": total_pages,
            "start": start,
            "end": end,
            "filter_qs": filter_qs,
        },
    )
