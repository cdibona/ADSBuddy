"""Triggers + firings UI.

A non-admin user only sees and can edit their own triggers and firings.
An admin can see everyone's (the listings include an owner column).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_session
from app.deps import require_user
from app.models import Trigger, TriggerFiring, User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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


async def _load_trigger(
    session: AsyncSession, trigger_id: int, actor: User
) -> Trigger:
    row = await session.execute(
        select(Trigger).where(Trigger.id == trigger_id).options(selectinload(Trigger.owner))
    )
    trigger = row.scalar_one_or_none()
    if trigger is None:
        raise HTTPException(status_code=404)
    if trigger.owner_id != actor.id and not actor.is_admin:
        # Don't leak existence to other users.
        raise HTTPException(status_code=404)
    return trigger


@router.get("/triggers", response_class=HTMLResponse)
async def triggers_list(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = select(Trigger).options(selectinload(Trigger.owner)).order_by(Trigger.created_at.desc())
    if not user.is_admin:
        stmt = stmt.where(Trigger.owner_id == user.id)
    triggers = (await db.execute(stmt)).scalars().all()
    return templates.TemplateResponse(
        request, "triggers.html", {"user": user, "triggers": triggers}
    )


@router.get("/triggers/new", response_class=HTMLResponse)
async def trigger_new_form(
    request: Request,
    user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "trigger_form.html",
        {"user": user, "trigger": None, "action": "/triggers/new", "title": "New trigger"},
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
    return RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/triggers/{trigger_id}/edit", response_class=HTMLResponse)
async def trigger_edit_form(
    trigger_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    return templates.TemplateResponse(
        request,
        "trigger_form.html",
        {
            "user": user,
            "trigger": trigger,
            "action": f"/triggers/{trigger.id}/edit",
            "title": f"Edit trigger: {trigger.name}",
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
    return RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/triggers/{trigger_id}/delete")
async def trigger_delete(
    trigger_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    trigger = await _load_trigger(db, trigger_id, user)
    await db.delete(trigger)
    await db.commit()
    return RedirectResponse(url="/triggers", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/firings", response_class=HTMLResponse)
async def firings_list(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    stmt = (
        select(TriggerFiring, Trigger)
        .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
        .order_by(TriggerFiring.fired_at.desc())
        .limit(200)
    )
    if not user.is_admin:
        stmt = stmt.where(Trigger.owner_id == user.id)
    rows = (await db.execute(stmt)).all()
    return templates.TemplateResponse(
        request, "firings.html", {"user": user, "rows": rows}
    )
