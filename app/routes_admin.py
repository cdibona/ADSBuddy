"""Admin pages: user management and the settings editor."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import require_admin
from app.models import Setting, User
from app.security import hash_password
from app.settings_store import set_value

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


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


@router.post("/settings/{key}")
async def admin_settings_set(
    key: str,
    value: str = Form(""),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_session),
):
    await set_value(db, key, value)
    return RedirectResponse(url="/admin/settings", status_code=status.HTTP_303_SEE_OTHER)
