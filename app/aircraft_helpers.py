"""Pure helper functions for aircraft-related external URL lookups.

All functions accept optional string inputs and return None for falsy inputs.
No I/O — safe to use in templates and route handlers.
"""

from __future__ import annotations

import urllib.parse

# Coarse aircraft kinds for iconography. ADS-B emitter category is the primary
# signal (A7 = rotorcraft, A1 = light); a small type-code set is the fallback
# when no category was received. Unknown falls back to a generic plane.
_KIND_ICON = {"helicopter": "🚁", "light": "🛩️", "jet": "✈️", "plane": "✈️"}
_KIND_LABEL = {"helicopter": "Helicopter", "light": "Light plane", "jet": "Jet", "plane": "Aircraft"}

_HELI_TYPES = frozenset({
    "R22", "R44", "R66", "B06", "B407", "B412", "B429", "EC20", "EC25", "EC30",
    "EC35", "EC45", "AS50", "AS55", "A109", "A119", "A139", "A169", "AW09",
    "AW139", "AW169", "S76", "S92", "H500", "H60", "UH60", "EXPL", "GAZL", "B505",
})
_LIGHT_TYPES = frozenset({
    "C150", "C152", "C162", "C170", "C172", "C175", "C177", "C182", "C185",
    "C206", "C210", "P28A", "P28B", "P28R", "P32R", "PA18", "PA24", "PA28",
    "PA32", "PA46", "SR20", "SR22", "DA40", "DA42", "DA20", "BE33", "BE35",
    "BE36", "M20P", "M20T", "RV6", "RV7", "RV8", "RV10", "GLID",
})


def aircraft_kind(type_code: str | None, category: str | None = None) -> str:
    """Coarse kind for iconography: 'helicopter' | 'light' | 'jet' | 'plane'."""
    cat = (category or "").strip().upper()
    if cat == "A7":
        return "helicopter"
    if cat == "A1":
        return "light"
    if cat in ("A2", "A3", "A4", "A5", "A6"):
        return "jet"
    tc = (type_code or "").strip().upper()
    if tc in _HELI_TYPES:
        return "helicopter"
    if tc in _LIGHT_TYPES:
        return "light"
    return "plane"


def kind_icon(type_code: str | None, category: str | None = None) -> str:
    """Emoji for the aircraft's coarse kind (✈️ / 🚁 / 🛩️)."""
    return _KIND_ICON[aircraft_kind(type_code, category)]


def kind_label(type_code: str | None, category: str | None = None) -> str:
    """Human label for the aircraft's coarse kind (Helicopter / Light plane / Jet)."""
    return _KIND_LABEL[aircraft_kind(type_code, category)]


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
        # Deep-link straight to the FAA registry *result* page for this N-number
        # (lands on the aircraft record, not the search form).
        return (
            "https://registry.faa.gov/AircraftInquiry/Search/NNumberResult"
            f"?nNumberTxt={urllib.parse.quote(reg)}"
        )
    return f"https://www.airframes.org/reg/{urllib.parse.quote(reg)}"


def registration_provider(reg: str | None) -> str | None:
    """Short label for where registration_url points: 'FAA' (US) or 'airframes'."""
    if not reg or not reg.strip():
        return None
    return "FAA" if reg.strip().upper().startswith("N") and len(reg.strip()) > 1 else "airframes"


# ICAO type designator -> exact Wikipedia article title. Covers the types we
# see often enough to warrant a direct link instead of a search. The long tail
# falls back to a description- or code-based search (see type_url below).
# Variant codes intentionally collapse onto the family/series article that
# actually documents them (e.g. all 737NG codes -> "Boeing 737 Next Generation").
_TYPE_WIKI: dict[str, str] = {
    # —— Boeing 737 ——
    "B732": "Boeing 737",
    "B733": "Boeing 737 Classic",
    "B734": "Boeing 737 Classic",
    "B735": "Boeing 737 Classic",
    "B736": "Boeing 737 Next Generation",
    "B737": "Boeing 737 Next Generation",
    "B738": "Boeing 737 Next Generation",
    "B739": "Boeing 737 Next Generation",
    "B37M": "Boeing 737 MAX",
    "B38M": "Boeing 737 MAX",
    "B39M": "Boeing 737 MAX",
    "B3XM": "Boeing 737 MAX",
    # —— Boeing 747 / 757 / 767 / 777 / 787 ——
    "B741": "Boeing 747",
    "B742": "Boeing 747",
    "B743": "Boeing 747",
    "B744": "Boeing 747-400",
    "B748": "Boeing 747-8",
    "B74S": "Boeing 747SP",
    "B752": "Boeing 757",
    "B753": "Boeing 757",
    "B762": "Boeing 767",
    "B763": "Boeing 767",
    "B764": "Boeing 767",
    "B772": "Boeing 777",
    "B773": "Boeing 777",
    "B77L": "Boeing 777",
    "B77W": "Boeing 777",
    "B778": "Boeing 777X",
    "B779": "Boeing 777X",
    "B788": "Boeing 787 Dreamliner",
    "B789": "Boeing 787 Dreamliner",
    "B78X": "Boeing 787 Dreamliner",
    "B712": "Boeing 717",
    "B722": "Boeing 727",
    # —— Airbus ——
    "A318": "Airbus A320 family",
    "A319": "Airbus A320 family",
    "A320": "Airbus A320 family",
    "A321": "Airbus A320 family",
    "A19N": "Airbus A320neo family",
    "A20N": "Airbus A320neo family",
    "A21N": "Airbus A320neo family",
    "A332": "Airbus A330",
    "A333": "Airbus A330",
    "A338": "Airbus A330neo",
    "A339": "Airbus A330neo",
    "A342": "Airbus A340",
    "A343": "Airbus A340",
    "A346": "Airbus A340",
    "A359": "Airbus A350",
    "A35K": "Airbus A350",
    "A388": "Airbus A380",
    "BCS1": "Airbus A220",
    "BCS3": "Airbus A220",
    # —— Embraer ——
    "E135": "Embraer ERJ family",
    "E145": "Embraer ERJ family",
    "E170": "Embraer E-Jet family",
    "E75S": "Embraer E-Jet family",
    "E75L": "Embraer E-Jet family",
    "E190": "Embraer E-Jet family",
    "E195": "Embraer E-Jet family",
    "E290": "Embraer E-Jet E2 family",
    "E295": "Embraer E-Jet E2 family",
    "E50P": "Embraer Phenom 100",
    "E55P": "Embraer Phenom 300",
    # —— Bombardier / regional ——
    "CRJ1": "Bombardier CRJ100/200",
    "CRJ2": "Bombardier CRJ100/200",
    "CRJ7": "Bombardier CRJ700 series",
    "CRJ9": "Bombardier CRJ700 series",
    "CRJX": "Bombardier CRJ700 series",
    "DH8A": "De Havilland Canada Dash 8",
    "DH8B": "De Havilland Canada Dash 8",
    "DH8C": "De Havilland Canada Dash 8",
    "DH8D": "De Havilland Canada Dash 8",
    "CL30": "Bombardier Challenger 300",
    "CL35": "Bombardier Challenger 300",
    "CL60": "Bombardier Challenger 600 series",
    "GLEX": "Bombardier Global Express",
    "GL5T": "Bombardier Global 7500",
    "GL7T": "Bombardier Global 7500",
    # —— Business jets ——
    "GLF4": "Gulfstream IV",
    "GLF5": "Gulfstream V",
    "GLF6": "Gulfstream G650",
    "GA5C": "Gulfstream G500",
    "C525": "Cessna CitationJet/M2",
    "C25C": "Cessna Citation CJ4",
    "C560": "Cessna Citation V",
    "C56X": "Cessna Citation Excel",
    "C68A": "Cessna Citation Latitude",
    "C700": "Cessna Citation Longitude",
    "C750": "Cessna Citation X",
    "F2TH": "Dassault Falcon 2000",
    # —— Cessna / general aviation ——
    "C150": "Cessna 150",
    "C152": "Cessna 152",
    "C172": "Cessna 172",
    "C162": "Cessna 162 Skycatcher",
    "C177": "Cessna 177 Cardinal",
    "C180": "Cessna 180",
    "C182": "Cessna 182 Skylane",
    "C82S": "Cessna 182 Skylane",
    "C82T": "Cessna 182 Skylane",
    "C185": "Cessna 185",
    "C206": "Cessna 206",
    "T206": "Cessna 206",
    "C208": "Cessna 208 Caravan",
    "C210": "Cessna 210",
    "C414": "Cessna 414",
    "C421": "Cessna 421",
    # —— Piper / Cirrus / Mooney / Beech / Pilatus / DHC ——
    "P28A": "Piper PA-28 Cherokee",
    "PA28": "Piper PA-28 Cherokee",
    "PA46": "Piper PA-46",
    "SR20": "Cirrus SR20",
    "SR22": "Cirrus SR22",
    "S22T": "Cirrus SR22",
    "M20P": "Mooney M20",
    "M20T": "Mooney M20",
    "BE33": "Beechcraft Bonanza",
    "BE35": "Beechcraft Bonanza",
    "BE36": "Beechcraft Bonanza",
    "BE58": "Beechcraft Baron",
    "BE20": "Beechcraft Super King Air",
    "B350": "Beechcraft Super King Air",
    "C90": "Beechcraft King Air",
    "PC12": "Pilatus PC-12",
    "PC24": "Pilatus PC-24",
    "PA18": "Piper PA-18 Super Cub",
    "DHC2": "De Havilland Canada DHC-2 Beaver",
    "DHC6": "De Havilland Canada DHC-6 Twin Otter",
    # —— Experimental / kit ——
    "RV6": "Van's Aircraft RV-6",
    "RV7": "Van's Aircraft RV-7",
    # —— Rotorcraft / Diamond ——
    "R44": "Robinson R44",
    "DA40": "Diamond DA40",
    "DA42": "Diamond DA42",
    # —— Military / other common overhead ——
    "C17": "Boeing C-17 Globemaster III",
    "C130": "Lockheed C-130 Hercules",
    "C30J": "Lockheed Martin C-130J Super Hercules",
    "K35R": "Boeing KC-135 Stratotanker",
    "H60": "Sikorsky UH-60 Black Hawk",
}


def _wiki_article_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def type_url(type_code: str | None, description: str | None = None) -> str | None:
    """Return a Wikipedia URL for an aircraft type.

    Known ICAO type designators link straight to the right article. Anything
    else falls back to a Wikipedia search, preferring the human-readable
    ``description`` (e.g. "BOEING 737-800") over the bare code when available.

    Returns None for empty / None ``type_code``.
    """
    if not type_code:
        return None
    code = type_code.strip().upper()
    if not code:
        return None

    article = _TYPE_WIKI.get(code)
    if article:
        return _wiki_article_url(article)

    term = (description or "").strip()
    if not term:
        term = f"{code} aircraft"
    query = urllib.parse.quote_plus(term)
    return f"https://en.wikipedia.org/wiki/Special:Search?search={query}"


def opensky_url(icao_hex: str | None) -> str | None:
    """Return an OpenSky Network aircraft profile URL for an ICAO hex code.

    Returns None for empty / None inputs.
    """
    if not icao_hex:
        return None
    # TIS-B / ADS-R targets carry a synthetic '~'-prefixed address with no real
    # ICAO 24-bit registration, so OpenSky has no profile for them.
    icao_hex = icao_hex.strip().lower().lstrip("~")
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
