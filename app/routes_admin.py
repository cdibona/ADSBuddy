"""Admin pages: user management and the settings editor."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import notifications, timefmt, version
from app.database import get_session
from app.deps import require_admin
from app.models import (
    Aircraft,
    FlightRoute,
    NotificationChannel,
    NotificationDelivery,
    RadioSource,
    Setting,
    Sighting,
    Trigger,
    TriggerFiring,
    TypeLink,
    User,
)
from app.type_links import normalize_code, sync_type_links
from app.security import hash_password
from app.settings_store import get as get_setting
from app.settings_store import set_value, setting_category

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
    all_settings = (
        (await db.execute(select(Setting).order_by(Setting.key))).scalars().all()
    )
    auth_settings = [s for s in all_settings if setting_category(s.key) == "auth"]
    return templates.TemplateResponse(
        request, "admin_users.html",
        {
            "user": user,
            "users": users,
            "auth_settings": auth_settings,
            "client_host": request.client.host if request.client else "?",
        },
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


@router.get("/settings")
async def admin_settings_redirect(user: User = Depends(require_admin)):
    """The old flat Settings page is now split across System + Notifications."""
    return RedirectResponse(url="/admin/system", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


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


@router.post("/diagnostics/purge")
async def admin_diagnostics_purge(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """On-demand prune of the notification-delivery log by the retention window."""
    from app.ingest import _parse_retention_days, delete_deliveries_before

    days = _parse_retention_days(await get_setting(db, "delivery_retention_days"))
    if days is None:
        days = 30  # auto-prune disabled — on-demand still uses a sane floor
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = await delete_deliveries_before(db, cutoff)
    return RedirectResponse(
        url=f"/admin/diagnostics?purged={deleted}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/system", response_class=HTMLResponse)
async def admin_system(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Read-only system information: version, uptime, DB stats, key settings."""
    async def _count(model) -> int:
        return (await db.execute(select(func.count()).select_from(model))).scalar_one()

    counts = {
        "aircraft": await _count(Aircraft),
        "sightings": await _count(Sighting),
        "firings": await _count(TriggerFiring),
        "triggers": await _count(Trigger),
        "users": await _count(User),
        "channels": await _count(NotificationChannel),
        "deliveries": await _count(NotificationDelivery),
        "routes": await _count(FlightRoute),
    }
    last_sighting = (await db.execute(select(func.max(Sighting.seen_at)))).scalar_one()
    last_firing = (await db.execute(select(func.max(TriggerFiring.fired_at)))).scalar_one()
    paused_firings = (
        await db.execute(
            select(func.count(TriggerFiring.id))
            .select_from(TriggerFiring)
            .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .where(Trigger.is_active.is_(False))
        )
    ).scalar_one()
    failed_firings = (
        await db.execute(
            select(func.count(func.distinct(TriggerFiring.id)))
            .select_from(TriggerFiring)
            .join(NotificationDelivery, NotificationDelivery.firing_id == TriggerFiring.id)
            .where(NotificationDelivery.status == "failed")
        )
    ).scalar_one()
    # Per-trigger firing counts (noisiest first) for the targeted-purge dropdown.
    fc = {
        tid: n
        for tid, n in (
            await db.execute(
                select(TriggerFiring.trigger_id, func.count()).group_by(TriggerFiring.trigger_id)
            )
        ).all()
    }
    trigger_firing_counts = sorted(
        (
            {"id": tid, "name": name, "count": fc.get(tid, 0)}
            for tid, name in (
                await db.execute(select(Trigger.id, Trigger.name))
            ).all()
        ),
        key=lambda r: (-r["count"], r["name"].lower()),
    )
    db_revision = (
        await db.execute(text("SELECT version_num FROM alembic_version"))
    ).scalar_one_or_none()

    all_settings = (
        (await db.execute(select(Setting).order_by(Setting.key))).scalars().all()
    )
    system_settings = [s for s in all_settings if setting_category(s.key) == "system"]

    return templates.TemplateResponse(
        request,
        "admin_system.html",
        {
            "user": user,
            "now": datetime.now(timezone.utc),
            "git_sha": version.GIT_SHA,
            "commit_url": version.github_commit_url(),
            "started_at": version.STARTED_AT,
            "uptime": version.uptime_str(),
            "db_revision": db_revision,
            "counts": counts,
            "last_sighting": last_sighting,
            "last_firing": last_firing,
            "paused_firings": paused_firings,
            "failed_firings": failed_firings,
            "trigger_firing_counts": trigger_firing_counts,
            "settings": system_settings,
        },
    )


@router.post("/system/downsample")
async def admin_system_downsample(
    action: str = Form("estimate"),
    confirm: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Estimate or run the historical sighting downsample (keep ~1 per interval)."""
    from app.ingest import _parse_min_interval, downsample_estimate, downsample_run

    interval = _parse_min_interval(await get_setting(db, "sighting_min_interval_seconds")) or 180
    if action == "run" and confirm == "yes":
        deleted = await downsample_run(db, interval)
        return RedirectResponse(
            url=f"/admin/system?downsampled={deleted}", status_code=status.HTTP_303_SEE_OTHER
        )
    total, would = await downsample_estimate(db, interval)
    return RedirectResponse(
        url=f"/admin/system?est_total={total}&est_del={would}&iv={interval}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/system/purge-paused-firings")
async def admin_purge_paused_firings(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Delete leftover firings whose trigger is currently paused (admin-only,
    all owners). Batched. Deliveries detach via ON DELETE SET NULL."""
    id_stmt = (
        select(TriggerFiring.id)
        .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
        .where(Trigger.is_active.is_(False))
        .limit(5000)
    )
    total = 0
    while True:
        ids = (await db.execute(id_stmt)).scalars().all()
        if not ids:
            break
        res = await db.execute(delete(TriggerFiring).where(TriggerFiring.id.in_(ids)))
        total += res.rowcount
        await db.commit()
    return RedirectResponse(
        url=f"/admin/system?firings_purged={total}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/system/purge-firings")
async def admin_purge_firings(
    trigger_id: str = Form("all"),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Purge firings for one trigger, or all of them. Batched. Deliveries detach
    via ON DELETE SET NULL, so the delivery log is preserved."""
    base = select(TriggerFiring.id)
    if trigger_id != "all":
        try:
            tid = int(trigger_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid trigger id")
        base = base.where(TriggerFiring.trigger_id == tid)
    total = 0
    while True:
        ids = (await db.execute(base.limit(5000))).scalars().all()
        if not ids:
            break
        res = await db.execute(delete(TriggerFiring).where(TriggerFiring.id.in_(ids)))
        total += res.rowcount
        await db.commit()
    return RedirectResponse(
        url=f"/admin/system?firings_cleared={total}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.post("/system/purge-failed-firings")
async def admin_purge_failed_firings(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Delete firings whose notification delivery failed (admin-only). Batched.
    Deliveries detach via ON DELETE SET NULL; the delivery log itself is kept."""
    id_stmt = (
        select(TriggerFiring.id)
        .join(NotificationDelivery, NotificationDelivery.firing_id == TriggerFiring.id)
        .where(NotificationDelivery.status == "failed")
        .distinct()
        .limit(5000)
    )
    total = 0
    while True:
        ids = (await db.execute(id_stmt)).scalars().all()
        if not ids:
            break
        res = await db.execute(delete(TriggerFiring).where(TriggerFiring.id.in_(ids)))
        total += res.rowcount
        await db.commit()
    return RedirectResponse(
        url=f"/admin/system?failed_purged={total}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/types", response_class=HTMLResponse)
async def admin_types(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    links = (await db.execute(select(TypeLink).order_by(TypeLink.code))).scalars().all()
    # How many seen-on-aircraft type codes aren't registered yet.
    seen = set(
        (
            await db.execute(
                select(Aircraft.type_code)
                .where(Aircraft.type_code.isnot(None), Aircraft.type_code != "")
                .distinct()
            )
        ).scalars()
    )
    known = {l.code for l in links}
    unsynced = len({normalize_code(c) for c in seen} - known)
    return templates.TemplateResponse(
        request,
        "admin_types.html",
        {"user": user, "links": links, "unsynced": unsynced},
    )


@router.post("/types/sync")
async def admin_types_sync(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    added = await sync_type_links(db)
    return RedirectResponse(url=f"/admin/types?synced={added}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/types")
async def admin_types_save(
    code: str = Form(...),
    description: str = Form(""),
    url: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    norm = normalize_code(code)
    if norm is None:
        raise HTTPException(status_code=400, detail="Type code required")
    link = await db.get(TypeLink, norm)
    if link is None:
        link = TypeLink(code=norm)
        db.add(link)
    link.description = description.strip() or None
    link.url = url.strip() or None
    link.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return RedirectResponse(url="/admin/types", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/types/{code}/delete")
async def admin_types_delete(
    code: str,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    link = await db.get(TypeLink, normalize_code(code) or "")
    if link is not None:
        await db.delete(link)
        await db.commit()
    return RedirectResponse(url="/admin/types", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/notifications", response_class=HTMLResponse)
async def admin_notifications(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Notification transport config, grouped into master / SMTP / Twilio."""
    by_key = {
        s.key: s
        for s in (await db.execute(select(Setting).order_by(Setting.key))).scalars().all()
    }

    def pick(keys: list[str]) -> list:
        return [by_key[k] for k in keys if k in by_key]

    return templates.TemplateResponse(
        request,
        "admin_notifications.html",
        {
            "user": user,
            "master_settings": pick(["notifications_enabled"]),
            "smtp_settings": pick(
                ["smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_from", "smtp_use_tls"]
            ),
            "twilio_settings": pick(
                ["twilio_account_sid", "twilio_auth_token", "twilio_from_number"]
            ),
            "summary_settings": pick(["summary_window_minutes", "summary_news_lookback_hours"]),
            "smtp_ok": await notifications.smtp_configured(db),
            "twilio_ok": await notifications.twilio_configured(db),
        },
    )


@router.post("/notifications/summary-now")
async def admin_summary_now(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Build + push the airspace summary immediately (to enabled transports)."""
    import httpx
    from urllib.parse import quote

    try:
        async with httpx.AsyncClient() as client:
            summary, sent = await notifications.run_summary(db, client)
        msg = (f"Summary sent to {', '.join(sent)} — {summary['count']} aircraft."
               if sent else "Nothing sent — enable a transport (TRMNL/Vestaboard) and configure it.")
    except Exception as e:  # noqa: BLE001
        msg = f"Summary failed: {e}"
    return RedirectResponse(
        url=f"/admin/notifications?summary_msg={quote(msg)}", status_code=status.HTTP_303_SEE_OTHER
    )


@router.get("/sources", response_class=HTMLResponse)
async def admin_sources(
    request: Request,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    sources = (
        await db.execute(select(RadioSource).order_by(RadioSource.created_at))
    ).scalars().all()
    return templates.TemplateResponse(
        request,
        "admin_sources.html",
        {
            "user": user,
            "sources": sources,
            "base_url": (await get_setting(db, "site_base_url")) or "",
        },
    )


@router.post("/sources")
async def admin_sources_create(
    name: str = Form(...),
    kind: str = Form("poll"),
    url: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    if kind not in ("poll", "push"):
        raise HTTPException(status_code=400, detail="kind must be poll or push")
    src = RadioSource(
        name=name[:64],
        kind=kind,
        url=(url.strip() or None) if kind == "poll" else None,
        token=secrets.token_urlsafe(24) if kind == "push" else None,
        is_active=True,
    )
    db.add(src)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"A source named {name!r} already exists.")
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


async def _load_source(db: AsyncSession, source_id: int) -> RadioSource:
    src = (
        await db.execute(select(RadioSource).where(RadioSource.id == source_id))
    ).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404)
    return src


@router.get("/sources/{source_id}/test")
async def admin_sources_test(
    source_id: int,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    """Probe a poll source's aircraft.json and report what came back (JSON, for
    the inline 'Test' button on the Sources tab)."""
    import httpx

    src = await _load_source(db, source_id)
    if src.kind != "poll":
        return JSONResponse({"ok": False, "message": "Push source — it POSTs to /ingest/<token>; nothing to poll."})
    if not src.url:
        return JSONResponse({"ok": False, "message": "No URL configured for this source."})
    url = src.url.rstrip("/") + "/data/aircraft.json"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=8.0)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"ok": False, "message": f"Can't reach it — {type(e).__name__}: {e}"[:200]})
    if resp.status_code != 200:
        return JSONResponse({"ok": False, "status": resp.status_code, "message": f"HTTP {resp.status_code} from {url}"})
    try:
        count = len(resp.json().get("aircraft") or [])
    except Exception:  # noqa: BLE001
        return JSONResponse({"ok": False, "status": 200, "message": "Reached it, but the response isn't aircraft.json."})
    return JSONResponse({"ok": True, "status": 200, "count": count,
                         "message": f"OK — {count} aircraft right now"})


@router.post("/sources/{source_id}/edit")
async def admin_sources_edit(
    source_id: int,
    name: str = Form(...),
    url: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    src = await _load_source(db, source_id)
    src.name = (name.strip() or src.name)[:64]
    if src.kind == "poll":
        src.url = url.strip() or None
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"A source named {name!r} already exists.")
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/toggle")
async def admin_sources_toggle(
    source_id: int,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    src = await _load_source(db, source_id)
    src.is_active = not src.is_active
    await db.commit()
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/sources/{source_id}/delete")
async def admin_sources_delete(
    source_id: int,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    src = await _load_source(db, source_id)
    await db.delete(src)
    await db.commit()
    return RedirectResponse(url="/admin/sources", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/{key}")
async def admin_settings_set(
    key: str,
    value: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    await set_value(db, key, value)
    # Return to the tab the setting lives on.
    dest = {
        "notifications": "/admin/notifications",
        "summary": "/admin/notifications",
        "auth": "/admin",
        "system": "/admin/system",
    }[setting_category(key)]
    return RedirectResponse(url=dest, status_code=status.HTTP_303_SEE_OTHER)
