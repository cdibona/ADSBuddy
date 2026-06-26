"""FastAPI dependencies: pull the current user from the session cookie."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User, UserSession
from app.security import SESSION_COOKIE_NAME
from app.settings_store import get as get_setting


def _guest_user() -> User:
    """A transient, read-only viewer for guest mode (never persisted)."""
    g = User(username="guest", is_admin=False, is_active=True, timezone="UTC")
    g.is_guest = True
    return g


async def guest_access_enabled(session: AsyncSession) -> bool:
    return ((await get_setting(session, "guest_access_enabled")) or "false").lower() == "true"


async def current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    from app.config import get_settings

    if get_settings().open_mode:
        # Open (appliance) mode: no login — act as the first admin on every
        # request. The bootstrap admin always exists by the time we serve.
        admin = (
            await session.execute(
                select(User)
                .where(User.is_admin.is_(True), User.is_active.is_(True))
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if admin is not None:
            request.state.user_tz = admin.timezone or "UTC"
            return admin

    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if not sid:
        return None
    row = await session.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.id == sid)
    )
    pair = row.one_or_none()
    if pair is None:
        return None
    user_session, user = pair
    if user_session.expires_at < datetime.now(timezone.utc):
        await session.delete(user_session)
        await session.commit()
        return None
    if not user.is_active:
        return None
    # Stash the tz so the localdt template filter can localize timestamps.
    request.state.user_tz = user.timezone or "UTC"
    return user


async def require_user(
    user: User | None = Depends(current_user_optional),
) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required",
            headers={"Location": "/login"},
        )
    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


async def current_viewer(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """A logged-in user, or a read-only guest when guest access is enabled.

    Used by the public-safe read-only pages (aircraft, history, map, stats).
    Returns None only when there's no session AND guest access is off.
    """
    user = await current_user_optional(request, session)
    if user is not None:
        return user
    if await guest_access_enabled(session):
        request.state.user_tz = "UTC"
        return _guest_user()
    return None


async def require_viewer(
    viewer: User | None = Depends(current_viewer),
) -> User:
    if viewer is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login required",
            headers={"Location": "/login"},
        )
    return viewer
