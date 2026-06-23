"""Login, logout, and the gated /test/login route for E2E suites."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models import User, UserSession
from app.security import (
    SESSION_COOKIE_NAME,
    hash_password,
    new_session_id,
    session_expiry,
    verify_password,
)

log = logging.getLogger(__name__)
from app import version

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
version.register(templates)


async def _start_session(
    db: AsyncSession, user: User, response: Response
) -> None:
    sid = new_session_id()
    db.add(UserSession(id=sid, user_id=user.id, expires_at=session_expiry()))
    await db.commit()
    response.set_cookie(
        SESSION_COOKIE_NAME,
        sid,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
        secure=False,  # tailnet-only, no TLS termination expected
    )


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_session),
) -> Response:
    row = await db.execute(select(User).where(User.username == username))
    user = row.scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(user.password_hash, password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid username or password."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    await _start_session(db, user, response)
    return response


@router.post("/logout")
async def logout(request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        existing = await db.execute(select(UserSession).where(UserSession.id == sid))
        sess = existing.scalar_one_or_none()
        if sess is not None:
            await db.delete(sess)
            await db.commit()
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.post("/test/login")
async def test_login(
    username: str = Form(...),
    is_admin: bool = Form(False),
    db: AsyncSession = Depends(get_session),
) -> Response:
    """E2E hook: mint a session for an arbitrary user without a password.

    Only available when ADSBUDDY_TEST_MODE=1. The endpoint creates the user
    on demand if missing so test suites don't need separate fixture wiring.
    """
    if not get_settings().test_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    row = await db.execute(select(User).where(User.username == username))
    user = row.scalar_one_or_none()
    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(new_session_id()),  # unusable random
            is_admin=is_admin,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    elif is_admin and not user.is_admin:
        user.is_admin = True
        await db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    await _start_session(db, user, response)
    log.warning(
        "TEST MODE: minted session for %r (admin=%s) at %s",
        username,
        user.is_admin,
        datetime.now(timezone.utc).isoformat(),
    )
    return response
