"""First-run side effects: seed default settings, ensure an admin exists."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User
from app.security import hash_password
from app.settings_store import seed_defaults

log = logging.getLogger(__name__)


async def ensure_admin(session: AsyncSession) -> None:
    """Create the bootstrap admin user if no admin exists yet."""
    cfg = get_settings()
    has_admin = (
        await session.execute(select(User.id).where(User.is_admin.is_(True)).limit(1))
    ).first()
    if has_admin:
        return
    existing = (
        await session.execute(select(User).where(User.username == cfg.admin_username))
    ).scalar_one_or_none()
    if existing is not None:
        existing.is_admin = True
        existing.is_active = True
        log.info("Promoted existing user %r to admin (bootstrap).", cfg.admin_username)
    else:
        session.add(
            User(
                username=cfg.admin_username,
                password_hash=hash_password(cfg.admin_password),
                is_admin=True,
                is_active=True,
            )
        )
        log.info("Created bootstrap admin user %r.", cfg.admin_username)
    await session.commit()


async def run(session: AsyncSession) -> None:
    await seed_defaults(session)
    await ensure_admin(session)
