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

from app.aircraft_helpers import opensky_url, registration_url, trigger_prefill_url, type_url
from app.database import get_session
from app.deps import current_user_optional, require_user
from app.models import Aircraft, Sighting, Trigger, TriggerFiring, User
from app.settings_store import get_required

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_HEX_RE = re.compile(r"^[0-9a-f]{1,8}$")
_VALID_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HISTORY_PER_PAGE = 50

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
# Register URL helpers as Jinja2 globals so all templates can call them directly.
templates.env.globals.update(
    registration_url=registration_url,
    type_url=type_url,
    opensky_url=opensky_url,
    trigger_prefill_url=trigger_prefill_url,
)


@router.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    user: User | None = Depends(current_user_optional),
    db: AsyncSession = Depends(get_session),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    radio_base_url = await get_required(db, "radio_base_url")
    site_title = await get_required(db, "site_title")
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user,
            "radio_base_url": radio_base_url.rstrip("/"),
            "site_title": site_title,
        },
    )


@router.get("/aircraft", response_class=HTMLResponse)
async def recent_aircraft(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    rows = await db.execute(
        select(Aircraft).order_by(Aircraft.last_seen.desc()).limit(200)
    )
    aircraft = rows.scalars().all()
    return templates.TemplateResponse(
        request,
        "aircraft.html",
        {"user": user, "aircraft": aircraft},
    )


@router.get("/aircraft/{icao_hex}", response_class=HTMLResponse)
async def aircraft_detail(
    icao_hex: str,
    request: Request,
    user: User = Depends(require_user),
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

    # Last 10 trigger firings, newest first. Non-admins only see their own.
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

    return templates.TemplateResponse(
        request,
        "aircraft_detail.html",
        {
            "user": user,
            "aircraft": aircraft,
            "sightings": sightings,
            "firings_rows": firings_rows,
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
    user: User = Depends(require_user),
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
    page: int = Query(1, ge=1),
):
    filters, errors = _parse_history_filters(
        tail, hex_raw, callsign, type_code, owner, year_raw, route,
        start_date, end_date,
    )

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
    }

    # Only search if filters were supplied and are valid.
    searched = bool(filters) and not errors
    aircraft_page: list[Aircraft] = []
    recent_sightings: dict[str, Sighting] = {}
    total = 0
    total_pages = 1

    if searched:
        conditions = _build_history_conditions(filters)

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
