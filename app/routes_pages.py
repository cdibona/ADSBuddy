"""Top-level page routes: map (iframe) and recent aircraft."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aircraft_helpers import opensky_url, registration_url, trigger_prefill_url, type_url
from app.database import get_session
from app.deps import current_user_optional, require_user
from app.models import Aircraft, Sighting, Trigger, TriggerFiring, User
from app.settings_store import get_required

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
