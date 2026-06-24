"""Push-ingest endpoint: a feeder POSTs aircraft.json-shaped data to us.

Authenticated by a per-source token in the path. No session cookie — this is
machine-to-machine. Reuses the same processing pipeline as the poll tick.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import ingest, notifications
from app.database import get_session
from app.models import RadioSource

log = logging.getLogger(__name__)
router = APIRouter()

_MAX_PUSH_ENTRIES = 10_000


@router.post("/ingest/{token}")
async def push_ingest(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
):
    source = (
        await db.execute(
            select(RadioSource).where(
                RadioSource.token == token,
                RadioSource.kind == "push",
                RadioSource.is_active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown or inactive source token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be JSON")
    entries = body.get("aircraft") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Expected {"aircraft": [ ... ]}',
        )
    if len(entries) > _MAX_PUSH_ENTRIES:
        log.warning("Push source %r sent %d entries; capping at %d.", source.name, len(entries), _MAX_PUSH_ENTRIES)
        entries = entries[:_MAX_PUSH_ENTRIES]

    active_triggers, need_routes, store_raw = await ingest._trigger_context(db)
    async with httpx.AsyncClient() as client:
        new_firings, _blocked = await ingest.process_entries(
            db, client, source.name, entries, active_triggers, need_routes, store_raw
        )
        source.last_seen_at = datetime.now(timezone.utc)
        await db.commit()
        if new_firings:
            try:
                await notifications.deliver_for_firings(db, client, new_firings)
                await db.commit()
            except Exception:
                log.exception("Push notify dispatch failed; firings recorded.")
                await db.rollback()
    return {"accepted": len(entries), "firings": len(new_firings)}
