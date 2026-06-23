"""Trigger evaluation: match aircraft entries against user-defined rules
and record firings (with per-(trigger, aircraft) cooldown).

The match function is pure (no I/O) so it's trivially unit-testable; the
recording side does the DB work.
"""
from __future__ import annotations

import fnmatch
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Trigger, TriggerFiring

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AircraftFacts:
    """Normalized snapshot of an aircraft.json entry used by the matcher."""

    icao_hex: str
    callsign: str | None
    registration: str | None
    type_code: str | None
    owner_op: str | None
    year: int | None
    lat: float | None
    lon: float | None
    altitude_baro: int | None
    origin_icao: str | None
    destination_icao: str | None


def _csv(field: str | None) -> list[str]:
    return [v.strip().lower() for v in (field or "").split(",") if v.strip()]


def _pattern_match(pattern: str, value: str) -> bool:
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatchcase(value, pattern)
    return pattern == value


def _any_pattern(patterns: list[str], value: str | None) -> bool:
    if not patterns:
        return True
    if value is None:
        return False
    v = value.lower()
    return any(_pattern_match(p, v) for p in patterns)


def _any_exact(values: list[str], value: str | None) -> bool:
    if not values:
        return True
    if value is None:
        return False
    return value.lower() in values


def _any_contains(patterns: list[str], value: str | None) -> bool:
    """Match if any pattern is a substring of value (case-insensitive).

    Wildcards (`*`/`?`) switch a pattern to a full fnmatch instead. Used for
    owner/operator, which is free-form text ("United Air Lines Inc").
    """
    if not patterns:
        return True
    if value is None:
        return False
    v = value.lower()
    for p in patterns:
        if "*" in p or "?" in p:
            if fnmatch.fnmatchcase(v, p):
                return True
        elif p in v:
            return True
    return False


def matches(trigger: Trigger, facts: AircraftFacts, now_year: int) -> bool:
    """Pure predicate. All non-empty fields must match (AND)."""
    if not _any_pattern(_csv(trigger.tail_patterns), facts.registration):
        return False
    if not _any_pattern(_csv(trigger.flight_patterns), facts.callsign):
        return False
    if not _any_exact(_csv(trigger.type_codes), facts.type_code):
        return False
    if not _any_contains(_csv(trigger.owner_patterns), facts.owner_op):
        return False
    if not _any_exact(_csv(trigger.origin_icaos), facts.origin_icao):
        return False
    if not _any_exact(_csv(trigger.destination_icaos), facts.destination_icao):
        return False

    year = facts.year
    if trigger.min_year is not None and (year is None or year < trigger.min_year):
        return False
    if trigger.max_year is not None and (year is None or year > trigger.max_year):
        return False
    if trigger.min_age_years is not None and (
        year is None or (now_year - year) < trigger.min_age_years
    ):
        return False
    if trigger.max_age_years is not None and (
        year is None or (now_year - year) > trigger.max_age_years
    ):
        return False
    return True


async def load_active_triggers(session: AsyncSession) -> list[Trigger]:
    rows = await session.execute(select(Trigger).where(Trigger.is_active.is_(True)))
    return list(rows.scalars().all())


async def evaluate_and_record(
    session: AsyncSession,
    triggers: Iterable[Trigger],
    facts: AircraftFacts,
) -> tuple[list[TriggerFiring], int]:
    """Evaluate every trigger against one aircraft and record firings.

    Returns ``(new_firings, blocked_count)`` where ``blocked_count`` is the
    number of triggers that matched but were suppressed by cooldown.
    Caller commits.
    """
    trigger_list = list(triggers)
    if not trigger_list:
        return [], 0
    now = datetime.now(timezone.utc)
    now_year = now.year
    created: list[TriggerFiring] = []
    blocked = 0
    for trigger in trigger_list:
        if not matches(trigger, facts, now_year):
            log.debug(
                "trigger %d (%s): no match for %s",
                trigger.id,
                trigger.name,
                facts.icao_hex,
            )
            continue
        threshold = now - timedelta(seconds=max(0, trigger.cooldown_seconds))
        already = (
            await session.execute(
                select(TriggerFiring.id)
                .where(
                    TriggerFiring.trigger_id == trigger.id,
                    TriggerFiring.icao_hex == facts.icao_hex,
                    TriggerFiring.fired_at > threshold,
                )
                .limit(1)
            )
        ).first()
        if already:
            log.debug(
                "trigger %d (%s): cooldown active for %s",
                trigger.id,
                trigger.name,
                facts.icao_hex,
            )
            blocked += 1
            continue
        log.debug(
            "trigger %d (%s): FIRED for %s",
            trigger.id,
            trigger.name,
            facts.icao_hex,
        )
        firing = TriggerFiring(
            trigger_id=trigger.id,
            icao_hex=facts.icao_hex,
            callsign=facts.callsign,
            registration=facts.registration,
            type_code=facts.type_code,
            year=facts.year,
            lat=facts.lat,
            lon=facts.lon,
            altitude_baro=facts.altitude_baro,
            origin_icao=facts.origin_icao,
            destination_icao=facts.destination_icao,
        )
        session.add(firing)
        created.append(firing)
    return created, blocked
