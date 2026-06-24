"""Push-ingest endpoint: a feeder POSTs aircraft.json-shaped data to us.

Authenticated by a per-source token, supplied either as an ``Authorization:
Bearer <token>`` header (preferred — keeps the secret out of access logs) or in
the path (``/ingest/<token>``, convenient for simple clients). No session
cookie — this is machine-to-machine. Reuses the poll pipeline (process_entries).
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
_MAX_BODY_BYTES = 8 * 1024 * 1024  # 8 MB


async def _lookup_source(db: AsyncSession, token: str | None) -> RadioSource:
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing push token")
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
    return source


async def _handle_push(source: RadioSource, request: Request, db: AsyncSession) -> dict:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > _MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Body must be JSON")
    entries = body.get("aircraft") if isinstance(body, dict) else None
    if not isinstance(entries, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Expected {"aircraft": [ ... ]}')
    if len(entries) > _MAX_PUSH_ENTRIES:
        log.warning("Push source %r sent %d entries; capping at %d.", source.name, len(entries), _MAX_PUSH_ENTRIES)
        entries = entries[:_MAX_PUSH_ENTRIES]

    active_triggers, need_routes, store_raw, min_interval = await ingest._trigger_context(db)
    async with httpx.AsyncClient() as client:
        new_firings, _blocked = await ingest.process_entries(
            db, client, source.name, entries, active_triggers, need_routes, store_raw, min_interval
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


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return None


@router.post("/ingest")
async def push_ingest_header(request: Request, db: AsyncSession = Depends(get_session)):
    """Preferred form: token in the Authorization: Bearer header."""
    source = await _lookup_source(db, _bearer_token(request))
    return await _handle_push(source, request, db)


@router.post("/ingest/{token}")
async def push_ingest_path(token: str, request: Request, db: AsyncSession = Depends(get_session)):
    """Convenience form: token in the path (avoid where access logs are retained)."""
    source = await _lookup_source(db, token)
    return await _handle_push(source, request, db)
