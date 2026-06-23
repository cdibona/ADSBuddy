"""Triggers + firings UI.

A non-admin user only sees and can edit their own triggers and firings.
An admin can see everyone's (the listings include an owner column).
"""

from __future__ import annotations

import math
import re
import urllib.parse
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

import httpx

from app import geocode, settings_store, timefmt, version
from app.database import get_session
from app.deps import require_user
from app.models import NotificationDelivery, Trigger, TriggerFiring, User

from app.aircraft_helpers import (
    opensky_url,
    registration_url,
    trigger_prefill_url,
    type_url,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
# Register URL helpers so firings.html can use registration_url / type_url /
# trigger_prefill_url (for the per-row "Create trigger" action).
templates.env.globals.update(
    registration_url=registration_url,
    type_url=type_url,
    opensky_url=opensky_url,
    trigger_prefill_url=trigger_prefill_url,
)
version.register(templates)
timefmt.register(templates)
# Defined below; registered here so triggers.html can summarize conditions.
templates.env.globals.update(trigger_condition_items=lambda t: trigger_condition_items(t))

FLASH_COOKIE = "adsbuddy_flash"
_DEFAULT_PER_PAGE = 100
_MAX_PER_PAGE = 200

# Validates ICAO hex codes: 1–8 hex digits (e.g. a1b2c3, aabbcc).
_VALID_HEX_RE = re.compile(r"^[0-9a-f]{1,8}$")


def _set_flash(response: RedirectResponse, level: str, message: str) -> None:
    encoded = urllib.parse.quote(message)
    response.set_cookie(
        FLASH_COOKIE, f"{level}:{encoded}", max_age=120, httponly=True, samesite="lax"
    )


def _pop_flash(request: Request) -> tuple[str, str] | None:
    raw = request.cookies.get(FLASH_COOKIE)
    if not raw:
        return None
    level, _, encoded = raw.partition(":")
    return level, urllib.parse.unquote(encoded)


def _strip_or_empty(value: str | None) -> str:
    return (value or "").strip()


def _int_or_none(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Expected integer, got {raw!r}")


def _float_or_none(raw: str | None) -> float | None:
    if raw is None:
        return None
    raw = raw.strip()
    if raw == "":
        return None
    try:
        return float(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Expected a number, got {raw!r}")


async def _apply_geofence(trigger: Trigger, form: dict[str, str]) -> str | None:
    """Set the trigger's geofence from the form, resolving the center.

    Returns a warning message if the center couldn't be resolved (the trigger
    is still saved, just with an inactive geofence), else None.
    """
    raw = _strip_or_empty(form.get("geofence_center"))
    trigger.geofence_center = raw
    if not raw:
        trigger.center_lat = trigger.center_lon = trigger.radius_miles = None
        return None
    radius = _float_or_none(form.get("geofence_radius_miles"))
    trigger.radius_miles = radius if (radius and radius > 0) else 25.0
    async with httpx.AsyncClient() as client:
        center = await geocode.resolve_center(raw, client)
    if center is None:
        trigger.center_lat = trigger.center_lon = None
        return (
            f"Couldn't resolve geofence center {raw!r} (use 'lat,lon', a US ZIP, "
            "or an ICAO code like KSEA). The trigger is saved but the geofence "
            "is inactive until the center resolves."
        )
    trigger.center_lat, trigger.center_lon = center.lat, center.lon
    return None


def _delivery_label(has_sent: bool | None, has_failed: bool | None) -> str:
    """Map delivery aggregate flags to a display label. Failed takes priority."""
    if has_failed:
        return "failed"
    if has_sent:
        return "sent"
    return "pending"


_TRIGGER_STATUSES = ("all", "active", "paused")
_FIRINGS_BUCKETS = ("all", "today", "24h", "7d")


def _normalize_trigger_status(raw: str | None) -> str:
    """Clamp the triggers list status filter to a known value (default 'all')."""
    val = (raw or "all").strip().lower()
    return val if val in _TRIGGER_STATUSES else "all"


def _normalize_firings_bucket(raw: str | None) -> str:
    """Clamp the firings time-bucket filter to a known value (default 'all')."""
    val = (raw or "all").strip().lower()
    return val if val in _FIRINGS_BUCKETS else "all"


def _range_str(lo: int | None, hi: int | None, suffix: str = "") -> str:
    """Render a min/max range like '≥ 1990 and ≤ 2000', '≥ 1990', or '≤ 2000'."""
    if lo is not None and hi is not None:
        return f"≥ {lo}{suffix} and ≤ {hi}{suffix}"
    if lo is not None:
        return f"≥ {lo}{suffix}"
    return f"≤ {hi}{suffix}"


def trigger_condition_items(t: Trigger) -> list[tuple[str, str]]:
    """(label, value) pairs for a trigger's active conditions, in display order.

    Registered as a Jinja global so the triggers table can show a subset and
    summarize the rest as '+N more'.
    """
    items: list[tuple[str, str]] = []
    if t.tail_patterns:
        items.append(("tail", t.tail_patterns))
    if t.flight_patterns:
        items.append(("flight", t.flight_patterns))
    if t.type_codes:
        items.append(("type", t.type_codes))
    if t.owner_patterns:
        items.append(("owner", t.owner_patterns))
    if t.min_year is not None or t.max_year is not None:
        items.append(("year", _range_str(t.min_year, t.max_year)))
    if t.min_age_years is not None or t.max_age_years is not None:
        items.append(("age", _range_str(t.min_age_years, t.max_age_years, suffix="y")))
    if t.origin_icaos:
        items.append(("origin", t.origin_icaos))
    if t.destination_icaos:
        items.append(("destination", t.destination_icaos))
    if t.geofence_center:
        if t.center_lat is not None and t.center_lon is not None and t.radius_miles is not None:
            items.append(("within", f"{t.radius_miles:g} mi of {t.geofence_center}"))
        else:
            items.append(("within", f"{t.geofence_center} (unresolved)"))
    return items


def _firings_since_cutoff(bucket: str, now: datetime) -> datetime | None:
    """Translate a time bucket into a lower-bound cutoff. None means no bound."""
    if bucket == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if bucket == "24h":
        return now - timedelta(hours=24)
    if bucket == "7d":
        return now - timedelta(days=7)
    return None


def _parse_prefill_params(
    hex_raw: str | None,
    tail: str | None,
    type_code: str | None,
    year_raw: str | None,
    owner: str | None,
) -> tuple[dict[str, object], str | None]:
    """Parse and validate query-param prefill inputs.

    Returns (prefill_dict, error_message).  prefill_dict is empty when
    hex_raw is absent.  error_message is set only when hex_raw is present
    but invalid.
    """
    if not hex_raw:
        return {}, None
    hex_lower = hex_raw.strip().lower()
    if not _VALID_HEX_RE.match(hex_lower):
        return {}, f"Invalid ICAO hex '{hex_raw}' — must be 1–8 hex digits."
    prefill: dict[str, object] = {"hex": hex_lower}
    if tail:
        tail = tail.strip()
        if tail:
            prefill["tail"] = tail
    if type_code:
        type_code = type_code.strip()
        if type_code:
            prefill["type"] = type_code
    if owner:
        owner = owner.strip()
        if owner:
            prefill["owner"] = owner
    if year_raw:
        try:
            yr = int(year_raw.strip())
            if 1900 <= yr <= 2100:
                prefill["year"] = str(yr)
        except ValueError:
            pass  # silently omit invalid years
    prefill["name"] = prefill.get("tail") or hex_lower
    return prefill, None


async def _load_trigger(session: AsyncSession, trigger_id: int, actor: User) -> Trigger:
    row = await session.execute(
        select(Trigger)
        .where(Trigger.id == trigger_id)
        .options(selectinload(Trigger.owner))
    )
    trigger = row.scalar_one_or_none()
    if trigger is None:
        raise HTTPException(status_code=404)
    if trigger.owner_id != actor.id and not actor.is_admin:
        # Don't leak existence to other users.
        raise HTTPException(status_code=404)
    return trigger


async def _get_route_lookup_enabled(db: AsyncSession) -> bool:
    value = await settings_store.get(db, "route_lookup_enabled")
    return (value or "true").lower() == "true"


@router.get("/triggers", response_class=HTMLResponse)
async def triggers_list(
    request: Request,
    status_filter: str | None = Query(None, alias="status"),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    status = _normalize_trigger_status(status_filter)
    stmt = (
        select(Trigger)
        .options(selectinload(Trigger.owner))
        .order_by(Trigger.created_at.desc())
    )
    if not user.is_admin:
        stmt = stmt.where(Trigger.owner_id == user.id)
    all_triggers = (await db.execute(stmt)).scalars().all()

    # Counts for the filter bar are computed over the (owner-scoped) full set;
    # trigger lists are small enough that an in-memory split beats extra queries.
    counts = {
        "all": len(all_triggers),
        "active": sum(1 for t in all_triggers if t.is_active),
        "paused": sum(1 for t in all_triggers if not t.is_active),
    }
    if status == "active":
        triggers = [t for t in all_triggers if t.is_active]
    elif status == "paused":
        triggers = [t for t in all_triggers if not t.is_active]
    else:
        triggers = list(all_triggers)

    flash = _pop_flash(request)
    response = templates.TemplateResponse(
        request,
        "triggers.html",
        {
            "user": user,
            "triggers": triggers,
            "status": status,
            "counts": counts,
            "flash": flash,
        },
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE)
    return response


@router.get("/triggers/new", response_class=HTMLResponse)
async def trigger_new_form(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
    hex_raw: str | None = Query(None, alias="hex"),
    tail: str | None = Query(None),
    type_code: str | None = Query(None, alias="type"),
    year_raw: str | None = Query(None, alias="year"),
    owner: str | None = Query(None),
):
    route_lookup_enabled = await _get_route_lookup_enabled(db)
    prefill, prefill_error = _parse_prefill_params(hex_raw, tail, type_code, year_raw, owner)
    return templates.TemplateResponse(
        request,
        "trigger_form.html",
        {
            "user": user,
            "trigger": None,
            "action": "/triggers/new",
            "title": "New trigger",
            "route_lookup_enabled": route_lookup_enabled,
            "prefill": prefill,
            "prefill_error": prefill_error,
        },
    )


def _apply_form_to_trigger(trigger: Trigger, form: dict[str, str]) -> None:
    trigger.name = _strip_or_empty(form.get("name")) or "Untitled"
    trigger.notes = _strip_or_empty(form.get("notes"))
    trigger.is_active = form.get("is_active") == "true"
    trigger.tail_patterns = _strip_or_empty(form.get("tail_patterns"))
    trigger.flight_patterns = _strip_or_empty(form.get("flight_patterns"))
    trigger.type_codes = _strip_or_empty(form.get("type_codes"))
    trigger.owner_patterns = _strip_or_empty(form.get("owner_patterns"))
    trigger.origin_icaos = _strip_or_empty(form.get("origin_icaos"))
    trigger.destination_icaos = _strip_or_empty(form.get("destination_icaos"))
    trigger.min_year = _int_or_none(form.get("min_year"))
    trigger.max_year = _int_or_none(form.get("max_year"))
    trigger.min_age_years = _int_or_none(form.get("min_age_years"))
    trigger.max_age_years = _int_or_none(form.get("max_age_years"))
    cooldown = _int_or_none(form.get("cooldown_seconds"))
    trigger.cooldown_seconds = cooldown if cooldown is not None else 3600


@router.post("/triggers/new")
async def trigger_new_submit(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    form = dict(await request.form())
    trigger = Trigger(owner_id=user.id, name="")
    _apply_form_to_trigger(trigger, form)
    warning = await _apply_geofence(trigger, form)
    db.add(trigger)
    await db.commit()
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
    if warning:
        _set_flash(resp, "error", warning)
    else:
        _set_flash(resp, "success", f"Trigger '{trigger.name}' created.")
    return resp


@router.get("/triggers/{trigger_id}/edit", response_class=HTMLResponse)
async def trigger_edit_form(
    trigger_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    route_lookup_enabled = await _get_route_lookup_enabled(db)
    return templates.TemplateResponse(
        request,
        "trigger_form.html",
        {
            "user": user,
            "trigger": trigger,
            "action": f"/triggers/{trigger.id}/edit",
            "title": f"Edit trigger: {trigger.name}",
            "route_lookup_enabled": route_lookup_enabled,
            "prefill": {},
            "prefill_error": None,
        },
    )


@router.post("/triggers/{trigger_id}/edit")
async def trigger_edit_submit(
    trigger_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    form = dict(await request.form())
    _apply_form_to_trigger(trigger, form)
    warning = await _apply_geofence(trigger, form)
    await db.commit()
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
    if warning:
        _set_flash(resp, "error", warning)
    else:
        _set_flash(resp, "success", f"Trigger '{trigger.name}' saved.")
    return resp


@router.post("/triggers/{trigger_id}/toggle")
async def trigger_toggle(
    trigger_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    trigger.is_active = not trigger.is_active
    await db.commit()
    label = "activated" if trigger.is_active else "paused"
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
    _set_flash(resp, "success", f"Trigger '{trigger.name}' {label}.")
    return resp


@router.post("/triggers/{trigger_id}/delete")
async def trigger_delete(
    trigger_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    name = trigger.name
    await db.delete(trigger)
    await db.commit()
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
    _set_flash(resp, "success", f"Trigger '{name}' deleted.")
    return resp


@router.get("/firings", response_class=HTMLResponse)
async def firings_list(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(_DEFAULT_PER_PAGE, ge=1, le=_MAX_PER_PAGE),
    since: str | None = Query(None),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    now = datetime.now(timezone.utc)
    bucket = _normalize_firings_bucket(since)
    cutoff = _firings_since_cutoff(bucket, now)

    # --- count total (1 query) ---
    count_stmt = (
        select(func.count())
        .select_from(TriggerFiring)
        .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
    )
    if not user.is_admin:
        count_stmt = count_stmt.where(Trigger.owner_id == user.id)
    if cutoff is not None:
        count_stmt = count_stmt.where(TriggerFiring.fired_at >= cutoff)
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Clamp page to valid range.
    total_pages = max(1, math.ceil(total / per_page))
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    start = offset + 1 if total else 0
    end = min(offset + per_page, total)

    # --- fetch page ---
    rows_stmt = (
        select(TriggerFiring, Trigger)
        .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
        .order_by(TriggerFiring.fired_at.desc())
        .limit(per_page)
        .offset(offset)
    )
    if not user.is_admin:
        rows_stmt = rows_stmt.where(Trigger.owner_id == user.id)
    if cutoff is not None:
        rows_stmt = rows_stmt.where(TriggerFiring.fired_at >= cutoff)
    rows = (await db.execute(rows_stmt)).all()

    # --- batch-load delivery status (1 query for the whole page) ---
    firing_ids = [f.id for f, _t in rows]
    delivery_status: dict[int, str] = {}
    if firing_ids:
        ds_rows = (
            await db.execute(
                select(
                    NotificationDelivery.firing_id,
                    func.bool_or(NotificationDelivery.status == "sent").label(
                        "has_sent"
                    ),
                    func.bool_or(NotificationDelivery.status == "failed").label(
                        "has_failed"
                    ),
                )
                .where(
                    NotificationDelivery.firing_id.in_(firing_ids),
                    NotificationDelivery.is_test.is_(False),
                )
                .group_by(NotificationDelivery.firing_id)
            )
        ).all()
        for ds in ds_rows:
            delivery_status[ds.firing_id] = _delivery_label(ds.has_sent, ds.has_failed)

    flash = _pop_flash(request)
    response = templates.TemplateResponse(
        request,
        "firings.html",
        {
            "user": user,
            "rows": rows,
            "delivery_status": delivery_status,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "start": start,
            "end": end,
            "since": bucket,
            "loaded_at": now,
            "flash": flash,
        },
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE)
    return response
