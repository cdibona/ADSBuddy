"""Admin pages: user management and the settings editor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import timefmt, version
from app.database import get_session
from app.deps import require_admin
from app.models import (
    NotificationChannel,
    NotificationDelivery,
    Setting,
    Trigger,
    TriggerFiring,
    User,
)
from app.security import hash_password
from app.settings_store import set_value

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")
version.register(templates)
timefmt.register(templates)


@router.get("", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    users = (await db.execute(select(User).order_by(User.username))).scalars().all()
    return templates.TemplateResponse(
        request, "admin_users.html", {"user": user, "users": users}
    )


@router.post("/users")
async def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin_flag: bool = Form(False, alias="is_admin"),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    existing = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already exists.")
    db.add(
        User(
            username=username,
            password_hash=hash_password(password),
            is_admin=is_admin_flag,
            is_active=True,
        )
    )
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/deactivate")
async def admin_deactivate_user(
    user_id: int,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404)
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="Refusing to deactivate yourself.")
    target.is_active = False
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/users/{user_id}/password")
async def admin_reset_password(
    user_id: int,
    password: str = Form(...),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    target = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404)
    target.password_hash = hash_password(password)
    await db.commit()
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/settings", response_class=HTMLResponse)
async def admin_settings_get(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    settings = (
        (await db.execute(select(Setting).order_by(Setting.key))).scalars().all()
    )
    return templates.TemplateResponse(
        request, "admin_settings.html", {"user": user, "settings": settings}
    )


@router.get("/diagnostics", response_class=HTMLResponse)
async def admin_diagnostics(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Read-only debugging surface over the firing/delivery audit trails.

    Surfaces what we already record (trigger_firings, notification_deliveries)
    so issues like 'fired but I can't see why a notify failed' don't require a
    DB shell. Admin-only.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    firings_24h = (
        await db.execute(
            select(func.count()).select_from(TriggerFiring).where(
                TriggerFiring.fired_at >= since
            )
        )
    ).scalar_one()

    deliv_counts = (
        await db.execute(
            select(NotificationDelivery.status, func.count())
            .where(
                NotificationDelivery.created_at >= since,
                NotificationDelivery.is_test.is_(False),
            )
            .group_by(NotificationDelivery.status)
        )
    ).all()
    sent_24h = sum(c for s, c in deliv_counts if s == "sent")
    failed_24h = sum(c for s, c in deliv_counts if s == "failed")
    skipped_24h = sum(c for s, c in deliv_counts if s == "skipped")
    tests_24h = (
        await db.execute(
            select(func.count()).select_from(NotificationDelivery).where(
                NotificationDelivery.created_at >= since,
                NotificationDelivery.is_test.is_(True),
            )
        )
    ).scalar_one()

    # Recent delivery failures (any time) — the first thing to check when a
    # notification doesn't arrive. firing/trigger are outer-joined (tests have none).
    fail_rows = (
        await db.execute(
            select(NotificationDelivery, NotificationChannel, User, TriggerFiring, Trigger)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .join(User, User.id == NotificationChannel.user_id)
            .outerjoin(TriggerFiring, TriggerFiring.id == NotificationDelivery.firing_id)
            .outerjoin(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .where(NotificationDelivery.status == "failed")
            .order_by(NotificationDelivery.created_at.desc())
            .limit(50)
        )
    ).all()

    # Recent "skipped" — channels that weren't configured (not real errors).
    skipped_rows = (
        await db.execute(
            select(NotificationDelivery, NotificationChannel, User, TriggerFiring, Trigger)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .join(User, User.id == NotificationChannel.user_id)
            .outerjoin(TriggerFiring, TriggerFiring.id == NotificationDelivery.firing_id)
            .outerjoin(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .where(NotificationDelivery.status == "skipped")
            .order_by(NotificationDelivery.created_at.desc())
            .limit(50)
        )
    ).all()

    # Recent delivery attempts of any status (the full trace for a firing).
    recent_rows = (
        await db.execute(
            select(NotificationDelivery, NotificationChannel, User, TriggerFiring, Trigger)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .join(User, User.id == NotificationChannel.user_id)
            .outerjoin(TriggerFiring, TriggerFiring.id == NotificationDelivery.firing_id)
            .outerjoin(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .order_by(NotificationDelivery.created_at.desc())
            .limit(100)
        )
    ).all()

    return templates.TemplateResponse(
        request,
        "admin_diagnostics.html",
        {
            "user": user,
            "now": now,
            "firings_24h": firings_24h,
            "sent_24h": sent_24h,
            "failed_24h": failed_24h,
            "skipped_24h": skipped_24h,
            "tests_24h": tests_24h,
            "fail_rows": fail_rows,
            "skipped_rows": skipped_rows,
            "recent_rows": recent_rows,
        },
    )


@router.get("/diagnostics/delivery/{delivery_id}", response_class=HTMLResponse)
async def admin_delivery_detail(
    delivery_id: int,
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Full trace for one delivery attempt: which trigger/channel/firing + error."""
    row = (
        await db.execute(
            select(NotificationDelivery, NotificationChannel, User, TriggerFiring, Trigger)
            .join(NotificationChannel, NotificationChannel.id == NotificationDelivery.channel_id)
            .join(User, User.id == NotificationChannel.user_id)
            .outerjoin(TriggerFiring, TriggerFiring.id == NotificationDelivery.firing_id)
            .outerjoin(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .where(NotificationDelivery.id == delivery_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404)
    delivery, channel, owner, firing, trigger = row
    return templates.TemplateResponse(
        request,
        "admin_delivery.html",
        {
            "user": user,
            "delivery": delivery,
            "channel": channel,
            "owner": owner,
            "firing": firing,
            "trigger": trigger,
        },
    )


@router.post("/settings/{key}")
async def admin_settings_set(
    key: str,
    value: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    await set_value(db, key, value)
    return RedirectResponse(url="/admin/settings", status_code=status.HTTP_303_SEE_OTHER)
