"""First-run side effects: seed default settings, ensure an admin exists."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import RadioSource, User
from app.security import hash_password
from app.settings_store import get as get_setting
from app.settings_store import seed_defaults, set_value

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
    """Seed the first "Local radio" source on initial setup.

    Runs only when no sources exist yet (one-time). The URL comes from the
    ADSBUDDY_RADIO_URL env var (set in docker-compose) if provided, otherwise
    the radio_base_url setting. Admins manage sources from Admin → Sources after
    this; changing the env later has no effect (it's pre-configuration only).
    """
    existing = (await session.execute(select(RadioSource.id).limit(1))).first()
    if existing:
        return
    env_url = get_settings().radio_url.strip()
    url = env_url or (await get_setting(session, "radio_base_url")) or ""
    if not url.strip():
        # Fresh install with no configured radio — nothing to seed. Leave the
        # sources table empty so admins add their own; don't seed a dead stub.
        return
    if env_url:
        # Keep the deprecated alias setting consistent with what we seeded.
        await set_value(session, "radio_base_url", env_url)
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
    log.info("Seeded default radio source 'Local radio' from %s: %r.",
             "ADSBUDDY_RADIO_URL" if env_url else "radio_base_url", url)


async def seed_baseload_triggers(session: AsyncSession) -> None:
    """Seed the default 'baseload' triggers into the first admin account, and
    pick up new ones when an image update ships more.

    Each baseload trigger is offered exactly once: we track the names we've ever
    applied in the ``baseload_applied`` setting. A new release that adds triggers
    introduces names we haven't applied → they get inserted on the next boot.
    A trigger the user later deleted stays deleted (its name is already in the
    applied set, so we never re-add it). Existing triggers (same name) are left
    untouched.
    """
    import json

    from app.baseload_triggers import all_baseload_triggers
    from app.models import Trigger

    baseload = all_baseload_triggers()

    owner = (
        await session.execute(
            select(User).where(User.is_admin.is_(True)).order_by(User.id).limit(1)
        )
    ).scalar_one_or_none()
    if owner is None:
        return

    try:
        applied = set(json.loads((await get_setting(session, "baseload_applied")) or "[]"))
    except (ValueError, TypeError):
        applied = set()
    existing = {n for (n,) in (await session.execute(select(Trigger.name))).all()}

    added = 0
    for spec in baseload:
        name = spec["name"]
        if name in applied:
            continue  # already offered once — respect the user's keep/delete choice
        if name not in existing:
            session.add(Trigger(owner_id=owner.id, **spec))
            added += 1
        applied.add(name)

    await set_value(session, "baseload_applied", json.dumps(sorted(applied)))
    await session.commit()
    if added:
        log.info("Seeded %d new baseload trigger(s).", added)


async def run(session: AsyncSession) -> None:
    await seed_defaults(session)
    await seed_default_source(session)
    await ensure_admin(session)
    await seed_baseload_triggers(session)
    from app.type_links import sync_type_links

    await sync_type_links(session)
