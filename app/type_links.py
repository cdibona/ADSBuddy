"""Maintain and resolve admin-editable type-code → destination links.

Type codes seen on aircraft are auto-registered with a default Wikipedia URL;
admins can override the URL/description on the admin Types tab. The aircraft
pages prefer the stored URL when present, else fall back to the curated helper.
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aircraft_helpers import type_url
from app.models import Aircraft, TypeLink

log = logging.getLogger(__name__)


def normalize_code(code: str | None) -> str | None:
    c = (code or "").strip().upper()
    return c or None


async def sync_type_links(session: AsyncSession) -> int:
    """Register any type codes seen on aircraft that aren't in type_links yet.

    Idempotent — only inserts missing codes (never overwrites admin edits).
    Returns the number added.
    """
    existing = set((await session.execute(select(TypeLink.code))).scalars())
    rows = (
        await session.execute(
            select(Aircraft.type_code, func.min(Aircraft.description))
            .where(Aircraft.type_code.isnot(None), Aircraft.type_code != "")
            .group_by(Aircraft.type_code)
        )
    ).all()
    added = 0
    for code, desc in rows:
        norm = normalize_code(code)
        if norm is None or norm in existing:
            continue
        session.add(TypeLink(code=norm, description=desc, url=type_url(norm, desc)))
        existing.add(norm)
        added += 1
    if added:
        await session.commit()
        log.info("Registered %d new type link(s).", added)
    return added


async def type_link_map(session: AsyncSession, codes) -> dict[str, str]:
    """{normalized type code: stored url} for the given codes (only where a URL is set)."""
    norm = {normalize_code(c) for c in codes if c}
    norm.discard(None)
    if not norm:
        return {}
    rows = (
        await session.execute(
            select(TypeLink.code, TypeLink.url).where(TypeLink.code.in_(norm))
        )
    ).all()
    return {code: url for code, url in rows if url}
