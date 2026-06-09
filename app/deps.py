"""FastAPI dependencies: pull the current user from the session cookie."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User, UserSession
from app.security import SESSION_COOKIE_NAME


async def current_user_optional(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User | None:
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
