"""Pure helper functions for aircraft-related external URL lookups.

All functions accept optional string inputs and return None for falsy inputs.
No I/O — safe to use in templates and route handlers.
"""

from __future__ import annotations

import urllib.parse


def registration_url(reg: str | None) -> str | None:
    """Return an external registry lookup URL for an aircraft registration.

    N-numbers (US, starting with 'N' and at least 2 chars) → FAA Aircraft Registry.
    All others → airframes.org (international database).
    Returns None for empty / None inputs.
    """
    if not reg:
        return None
    reg = reg.strip()
    if not reg:
        return None
    if reg.upper().startswith("N") and len(reg) > 1:
        return (
            "https://registry.faa.gov/aircraftinquiry/Search/NNumberInquiry"
            f"?nNumberTxt={urllib.parse.quote(reg)}"
        )
    return f"https://www.airframes.org/reg/{urllib.parse.quote(reg)}"


def type_url(type_code: str | None) -> str | None:
    """Return a Wikipedia search URL for an aircraft type code.

    Returns None for empty / None inputs.
    """
    if not type_code:
        return None
    type_code = type_code.strip()
    if not type_code:
        return None
    query = urllib.parse.quote_plus(f"{type_code} aircraft")
    return f"https://en.wikipedia.org/wiki/Special:Search?search={query}"


def opensky_url(icao_hex: str | None) -> str | None:
    """Return an OpenSky Network aircraft profile URL for an ICAO hex code.

    Returns None for empty / None inputs.
    """
    if not icao_hex:
        return None
    icao_hex = icao_hex.strip().lower()
    if not icao_hex:
        return None
    return f"https://opensky-network.org/aircraft-profile?icao24={icao_hex}"


def trigger_prefill_url(
    icao_hex: str | None,
    tail: str | None = None,
    type_code: str | None = None,
    year: int | str | None = None,
    owner: str | None = None,
) -> str | None:
    """Return a /triggers/new URL with aircraft data pre-populated as query params.

    Returns None for falsy icao_hex.
    """
    if not icao_hex:
        return None
    icao_hex = icao_hex.strip().lower()
    if not icao_hex:
        return None
    params: dict[str, str] = {"hex": icao_hex}
    if tail:
        tail = tail.strip()
        if tail:
            params["tail"] = tail
    if type_code:
        type_code = type_code.strip()
        if type_code:
            params["type"] = type_code
    if year is not None:
        year_str = str(year).strip()
        if year_str:
            params["year"] = year_str
    if owner:
        owner = owner.strip()
        if owner:
            params["owner"] = owner
    return "/triggers/new?" + urllib.parse.urlencode(params)
