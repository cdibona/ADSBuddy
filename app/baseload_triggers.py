"""Default 'baseload' triggers seeded on a fresh install.

A curated set of celebrity/notable aircraft plus two universal rules
(Emergency squawk, Vintage). Seeded by app.bootstrap into the admin account,
inserted only when a trigger of the same name doesn't already exist (so user
edits and deletions are never clobbered). All are seeded PAUSED except the two
flagged ``is_active`` below, which are useful to everyone out of the box.

Local/personal triggers (Lifeflight, SeaTac, Bainbridge helicopters, etc.) are
deliberately NOT part of the baseload.

Each entry carries only the fields it needs; everything else uses the Trigger
column defaults.
"""
from __future__ import annotations

BASELOAD_TRIGGERS: list[dict] = [
    {'name': 'Vintage (75+ years)', 'is_active': True, 'cooldown_seconds': 60, 'exclude_type_codes': 'DHC2, DHC3, BE35, T206', 'min_age_years': 75},
    {'name': 'Emergency squawk', 'is_active': True, 'cooldown_seconds': 900, 'squawk_patterns': '7500,7600,7700'},
    {'name': 'Air Force One', 'is_active': False, 'cooldown_seconds': 3600, 'type_codes': 'VC25'},
    {'name': 'Alex Rodriguez', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N313AR'},
    {'name': 'Bill Gates', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N887WM,N194WM'},
    {'name': 'Blake Shelton', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N958TB'},
    {'name': 'Caesars Palace Casino', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N898CE'},
    {'name': 'Dan Bilzerian', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N701DB'},
    {'name': 'David Geffen', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N221DG'},
    {'name': 'Donald Trump', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N757AF'},
    {'name': 'Dr. Phil', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N4DP'},
    {'name': 'Drake', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N767CJ'},
    {'name': 'Elon Musk', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N628TS,N272BG'},
    {'name': 'Elton John', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'M-EDZE'},
    {'name': 'Eric Schmidt', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N652WE'},
    {'name': 'Floyd Mayweather', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N151SD'},
    {'name': 'George Lucas', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N138GL'},
    {'name': 'Google', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N10XG'},
    {'name': 'Harrison Ford', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N6GU'},
    {'name': 'Jay Z', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N444SC'},
    {'name': 'Jeff Bezos', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N758PB,N751GZ,N616SR'},
    {'name': 'Jerry Jones', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N1DC'},
    {'name': 'Jim Carrey', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N162JC'},
    {'name': 'Judge Judy', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N555QB'},
    {'name': 'Kenny Chesney', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N7KC'},
    {'name': 'Kid Rock', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N71KR'},
    {'name': 'Kim Kardashian', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N1980K'},
    {'name': 'Kylie Jenner', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N810KJ'},
    {'name': 'Lady Gaga', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N474D'},
    {'name': 'Larry Ellison', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N817GS'},
    {'name': 'Luke Bryan', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N506AB'},
    {'name': 'Magic Johnson', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N32MJ'},
    {'name': 'Mark Cuban', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N921MT'},
    {'name': 'Marc Benioff', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N650HA'},
    {'name': 'Mark Wahlberg', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N143MW'},
    {'name': 'Mark Zuckerberg', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N68885,N49AH,N3880'},
    {'name': 'Matt Damon', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N444WT'},
    {'name': 'Max Verstappen', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'PH-DFT'},
    {'name': 'Michael Bloomberg', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N5MV,N47EG,N8AG'},
    {'name': 'Michael Jordan', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N236MJ'},
    {'name': 'Phil Knight (Nike)', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N1KE'},
    {'name': 'Nike Corporation', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N6453'},
    {'name': 'Oprah Winfrey', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N540W'},
    {'name': 'P. Diddy', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N1969C'},
    {'name': 'Peter Thiel', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N878DB'},
    {'name': 'Phil Mickelson', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N800PM'},
    {'name': 'Playboy Corporation', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N950PB'},
    {'name': 'Ron DeSantis', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N943FL'},
    {'name': 'Ronald Perelman', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N838MF'},
    {'name': 'Rupert Murdoch', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N898NC'},
    {'name': 'Sergey Brin', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N232G'},
    {'name': 'Steve Ballmer', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N709DS'},
    {'name': 'Steve Wynn', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N88WR'},
    {'name': 'Steven Spielberg', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N900KS'},
    {'name': 'Taylor Swift', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N898TS,N621MM'},
    {'name': 'Tommy Hilfiger', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N818TH'},
    {'name': 'Tiger Woods', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N517TW'},
    {'name': 'Tom Cruise', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N350XX'},
    {'name': 'Travis Scott', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N713TS'},
    {'name': 'Tyler Perry', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N378TP'},
]
"""Active out of the box: 'Vintage (75+ years)', 'Emergency squawk'. Rest paused."""


# Fields a trigger spec may carry (everything else uses Trigger column defaults).
# Mirrors the keys above and is used to serialize a user's trigger for sharing.
SPEC_STR_FIELDS = (
    "tail_patterns", "flight_patterns", "type_codes", "owner_patterns",
    "squawk_patterns", "categories", "exclude_tail_patterns",
    "exclude_flight_patterns", "exclude_type_codes", "exclude_owner_patterns",
    "origin_icaos", "destination_icaos", "geofence_center", "notes",
)
SPEC_NUM_FIELDS = (
    "min_year", "max_year", "min_age_years", "max_age_years",
    "min_altitude_ft", "max_altitude_ft", "center_lat", "center_lon", "radius_miles",
)


def trigger_to_spec(trigger) -> dict:
    """Serialize a Trigger into the baseload-dict format (only its set fields),
    so a user can submit it to the project. Ownership/timestamps are dropped."""
    spec: dict = {
        "name": trigger.name,
        "is_active": bool(trigger.is_active),
        "cooldown_seconds": trigger.cooldown_seconds,
    }
    for f in SPEC_STR_FIELDS:
        v = getattr(trigger, f, "") or ""
        if isinstance(v, str) and v.strip():
            spec[f] = v
    for f in SPEC_NUM_FIELDS:
        v = getattr(trigger, f, None)
        if v is not None:
            spec[f] = v
    return spec
