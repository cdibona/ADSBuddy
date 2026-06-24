"""Resolve a geofence center from user input to (lat, lon).

Accepts these forms, resolved at trigger-save time (never on the hot path):
  - "lat,lon"        e.g. "47.63, -122.53"   (parsed locally)
  - US ZIP (5 digit) e.g. "98101"            (zippopotam.us)
  - airport code     e.g. "KSEA" or "SEA"    (aviationweather.gov; a 3-letter
                     IATA code is assumed to be US and mapped to ICAO "K"+code)

All network calls are best-effort: any failure returns None and the caller
treats the geofence as unresolved.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_ZIP_RE = re.compile(r"^\d{5}$")
_ICAO_RE = re.compile(r"^[A-Za-z]{3,4}$")

_ZIPPOPOTAM = "https://api.zippopotam.us/us/{zip}"
_AVWX_AIRPORT = "https://aviationweather.gov/api/data/airport"


@dataclass(frozen=True)
class Center:
    lat: float
    lon: float


def _valid(lat: float, lon: float) -> bool:
    return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def parse_latlon(text: str) -> Center | None:
    """Pure parse of a 'lat,lon' string. None if it isn't one / out of range."""
    m = _LATLON_RE.match(text or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    return Center(lat, lon) if _valid(lat, lon) else None


async def _resolve_zip(zip_code: str, client: httpx.AsyncClient) -> Center | None:
    try:
        resp = await client.get(_ZIPPOPOTAM.format(zip=zip_code), timeout=8.0)
        if resp.status_code != 200:
            return None
        place = (resp.json().get("places") or [None])[0]
        if not place:
            return None
        lat, lon = float(place["latitude"]), float(place["longitude"])
        return Center(lat, lon) if _valid(lat, lon) else None
    except (httpx.RequestError, KeyError, ValueError, TypeError):
        return None


def icao_candidates(code: str) -> list[str]:
    """ICAO codes to try for an airport input, in priority order.

    A 4-letter code is taken as ICAO as-is. A 3-letter code is assumed to be a
    US IATA code and mapped to ICAO by prefixing 'K' (SEA -> KSEA) — the common
    case — with the bare code and a 'P' prefix (Alaska/Hawaii/Pacific) as
    fallbacks, so the user needn't know the ICAO form.
    """
    code = code.upper()
    if len(code) == 4:
        return [code]
    return ["K" + code, code, "P" + code]


async def _resolve_icao(code: str, client: httpx.AsyncClient) -> Center | None:
    candidates = icao_candidates(code)
    try:
        resp = await client.get(
            _AVWX_AIRPORT,
            params={"ids": ",".join(candidates), "format": "json"},
            timeout=8.0,
            headers={"User-Agent": "ADSBuddy/0.1"},
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data:
            return None
        by_icao = {row.get("icaoId"): row for row in data if row.get("icaoId")}
        # Honor candidate priority (K-prefix first), not API ordering.
        for cand in candidates:
            row = by_icao.get(cand)
            if not row:
                continue
            lat, lon = float(row["lat"]), float(row["lon"])
            return Center(lat, lon) if _valid(lat, lon) else None
        return None
    except (httpx.RequestError, KeyError, ValueError, TypeError, IndexError):
        return None


async def resolve_center(text: str, client: httpx.AsyncClient) -> Center | None:
    """Resolve free-form center input to coordinates, or None if unresolvable."""
    t = (text or "").strip()
    if not t:
        return None
    latlon = parse_latlon(t)
    if latlon is not None:
        return latlon
    if _ZIP_RE.match(t):
        return await _resolve_zip(t, client)
    if _ICAO_RE.match(t):
        return await _resolve_icao(t, client)
    return None
