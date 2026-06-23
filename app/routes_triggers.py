"""Triggers + firings UI.

A non-admin user only sees and can edit their own triggers and firings.
An admin can see everyone's (the listings include an owner column).
"""

from __future__ import annotations

import math
import re
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import settings_store
from app.database import get_session
from app.deps import require_user
from app.models import NotificationDelivery, Trigger, TriggerFiring, User

from app.aircraft_helpers import opensky_url, registration_url, type_url

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
# Register URL helpers so firings.html can use registration_url / type_url.
templates.env.globals.update(
    registration_url=registration_url,
    type_url=type_url,
    opensky_url=opensky_url,
)

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


def _delivery_label(has_sent: bool | None, has_failed: bool | None) -> str:
    """Map delivery aggregate flags to a display label. Failed takes priority."""
    if has_failed:
        return "failed"
    if has_sent:
        return "sent"
    return "pending"


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
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Trigger)
        .options(selectinload(Trigger.owner))
        .order_by(Trigger.created_at.desc())
    )
    if not user.is_admin:
        stmt = stmt.where(Trigger.owner_id == user.id)
    triggers = (await db.execute(stmt)).scalars().all()
    flash = _pop_flash(request)
    response = templates.TemplateResponse(
        request, "triggers.html", {"user": user, "triggers": triggers, "flash": flash}
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
    db.add(trigger)
    await db.commit()
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
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
    await db.commit()
    resp = RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)
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
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    # --- count total (1 query) ---
    count_stmt = (
        select(func.count())
        .select_from(TriggerFiring)
        .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
    )
    if not user.is_admin:
        count_stmt = count_stmt.where(Trigger.owner_id == user.id)
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
            "flash": flash,
        },
    )
    if flash:
        response.delete_cookie(FLASH_COOKIE)
    return response
