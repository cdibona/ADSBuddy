"""Airspace statistics: distinct-aircraft count + kind breakdown over a window.

Shared by the guest-facing /stats page and the notification summary so both
count and classify the same way.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.aircraft_helpers import summary_kind

KIND_BUCKETS = ("helicopter", "seaplane", "light", "private_jet", "cargo", "airliner", "other")


async def airspace_breakdown(session: AsyncSession, window_minutes: int) -> dict:
    """{count, window_minutes, breakdown{kind: n}, generated_at} for the last
    `window_minutes`, one row per distinct aircraft (latest sighting)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=window_minutes)
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT ON (s.icao_hex) a.type_code, a.owner_op, s.category "
                "FROM sightings s JOIN aircraft a ON a.icao_hex = s.icao_hex "
                "WHERE s.seen_at >= :cut ORDER BY s.icao_hex, s.seen_at DESC"
            ),
            {"cut": cutoff},
        )
    ).all()
    buckets = {k: 0 for k in KIND_BUCKETS}
    for type_code, owner_op, category in rows:
        buckets[summary_kind(type_code, category, owner_op)] += 1
    return {
        "count": len(rows),
        "window_minutes": window_minutes,
        "breakdown": buckets,
        "generated_at": now,
    }
