"""First-run side effects: seed default settings, ensure an admin exists."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import RadioSource, User
from app.security import hash_password
from app.settings_store import get as get_setting
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


def _coerce_float(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


async def seed_default_source(session: AsyncSession) -> None:
    """Migrate the legacy single radio (radio_base_url) into a RadioSource.

    Runs only when no sources exist yet, so it's a one-time migration. The old
    settings keys (radio_base_url, receiver_lat/lon) are left in place as a
    deprecated alias; the ingester reads from radio_sources going forward.
    """
    existing = (await session.execute(select(RadioSource.id).limit(1))).first()
    if existing:
        return
    url = (await get_setting(session, "radio_base_url")) or ""
    if not url.strip():
        # Fresh install with no configured radio — nothing to migrate. Leave the
        # sources table empty so admins add their own; don't seed a dead stub.
        return
    source = RadioSource(
        name="Local radio",
        kind="poll",
        url=url.strip(),
        is_active=True,
        receiver_lat=_coerce_float(await get_setting(session, "receiver_lat")),
        receiver_lon=_coerce_float(await get_setting(session, "receiver_lon")),
    )
    session.add(source)
    await session.commit()
    log.info("Seeded default radio source 'Local radio' from radio_base_url=%r.", url)


async def run(session: AsyncSession) -> None:
    await seed_defaults(session)
    await seed_default_source(session)
    await ensure_admin(session)
