"""Top-level page routes: map (iframe) and recent aircraft."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import current_user_optional, require_user
from app.models import Aircraft, User
from app.settings_store import get_required

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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
