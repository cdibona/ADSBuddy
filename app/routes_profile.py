"""User profile + notification channel management.

Each user manages their own channels. Admin settings (SMTP / Twilio creds)
are configured separately in /admin/settings.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import notifications, timefmt, version
from app.database import get_session
from app.deps import require_user
from app.models import (
    CHANNEL_KINDS,
    NotificationChannel,
    NotificationDelivery,
    User,
)

log = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
version.register(templates)
timefmt.register(templates)

CHANNEL_KIND_LABELS = {
    "discord": "Discord",
    "email": "Email",
    "webhook": "Webhook",
    "sms_twilio": "SMS (Twilio)",
}


def _strip(v: str | None) -> str:
    return (v or "").strip()


def _build_config(kind: str, form: dict[str, str]) -> dict[str, Any]:
    if kind == "discord":
        cfg = {"webhook_url": _strip(form.get("webhook_url"))}
        username = _strip(form.get("username"))
        if username:
            cfg["username"] = username
        return cfg
    if kind == "email":
        return {"to_address": _strip(form.get("to_address"))}
    if kind == "webhook":
        cfg = {"url": _strip(form.get("url"))}
        auth = _strip(form.get("auth_header"))
        if auth:
            cfg["auth_header"] = auth
        return cfg
    if kind == "sms_twilio":
        return {"to_phone": _strip(form.get("to_phone"))}
    raise HTTPException(status_code=400, detail=f"Unknown channel kind: {kind!r}")


async def _load_channel(
    session: AsyncSession, channel_id: int, actor: User
) -> NotificationChannel:
    row = await session.execute(
        select(NotificationChannel).where(NotificationChannel.id == channel_id)
    )
    channel = row.scalar_one_or_none()
    if channel is None or channel.user_id != actor.id:
        # Even admins go through their own profile for their own channels;
        # don't leak existence across users.
        raise HTTPException(status_code=404)
    return channel


@router.get("/profile", response_class=HTMLResponse)
async def profile(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    chans = (
        await db.execute(
            select(NotificationChannel)
            .where(NotificationChannel.user_id == user.id)
            .order_by(NotificationChannel.kind, NotificationChannel.created_at)
        )
    ).scalars().all()

    # Most-recent delivery per channel, for the "Last delivery" column.
    last_by_channel: dict[int, NotificationDelivery] = {}
    if chans:
        ids = [c.id for c in chans]
        rows = (
            await db.execute(
                select(NotificationDelivery)
                .where(NotificationDelivery.channel_id.in_(ids))
                .order_by(desc(NotificationDelivery.created_at))
                .limit(200)
            )
        ).scalars()
        for d in rows:
            last_by_channel.setdefault(d.channel_id, d)

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "channels": chans,
            "kinds": [(k, CHANNEL_KIND_LABELS[k]) for k in await notifications.available_channel_kinds(db)],
            "kind_label": CHANNEL_KIND_LABELS,
            "last_by_channel": last_by_channel,
        },
    )


@router.post("/profile/settings")
async def profile_settings_save(
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    form = dict(await request.form())
    tz = _strip(form.get("timezone")) or "UTC"
    user.timezone = tz if timefmt.is_valid_tz(tz) else "UTC"
    user.email = _strip(form.get("email")) or None
    await db.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/profile/channels/new", response_class=HTMLResponse)
async def channel_new_form(
    request: Request,
    kind: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    if kind not in CHANNEL_KINDS:
        raise HTTPException(status_code=404)
    if kind not in await notifications.available_channel_kinds(db):
        raise HTTPException(status_code=404, detail=f"{kind} is not available until an admin configures it.")
    return templates.TemplateResponse(
        request,
        "channel_form.html",
        {
            "user": user,
            "channel": None,
            "kind": kind,
            "kind_label": CHANNEL_KIND_LABELS[kind],
            "action": f"/profile/channels/new?kind={kind}",
            "title": f"New {CHANNEL_KIND_LABELS[kind]} channel",
        },
    )


@router.post("/profile/channels/new")
async def channel_new_submit(
    request: Request,
    kind: str,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    if kind not in CHANNEL_KINDS:
        raise HTTPException(status_code=404)
    if kind not in await notifications.available_channel_kinds(db):
        raise HTTPException(status_code=404, detail=f"{kind} is not available until an admin configures it.")
    form = dict(await request.form())
    name = _strip(form.get("name")) or CHANNEL_KIND_LABELS[kind]
    channel = NotificationChannel(
        user_id=user.id,
        kind=kind,
        name=name,
        is_active=form.get("is_active") == "true",
        config=_build_config(kind, form),
    )
    db.add(channel)
    await db.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/profile/channels/{channel_id}/edit", response_class=HTMLResponse)
async def channel_edit_form(
    channel_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    channel = await _load_channel(db, channel_id, user)
    return templates.TemplateResponse(
        request,
        "channel_form.html",
        {
            "user": user,
            "channel": channel,
            "kind": channel.kind,
            "kind_label": CHANNEL_KIND_LABELS[channel.kind],
            "action": f"/profile/channels/{channel.id}/edit",
            "title": f"Edit {CHANNEL_KIND_LABELS[channel.kind]} channel: {channel.name}",
        },
    )


@router.post("/profile/channels/{channel_id}/edit")
async def channel_edit_submit(
    channel_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    channel = await _load_channel(db, channel_id, user)
    form = dict(await request.form())
    channel.name = _strip(form.get("name")) or channel.name
    channel.is_active = form.get("is_active") == "true"
    channel.config = _build_config(channel.kind, form)
    await db.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/channels/{channel_id}/delete")
async def channel_delete(
    channel_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    channel = await _load_channel(db, channel_id, user)
    await db.delete(channel)
    await db.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/profile/channels/{channel_id}/test")
async def channel_send_test(
    channel_id: int,
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_session),
):
    channel = await _load_channel(db, channel_id, user)
    async with httpx.AsyncClient() as client:
        await notifications.send_test(db, client, channel)
    await db.commit()
    return RedirectResponse(url="/profile", status_code=status.HTTP_303_SEE_OTHER)
