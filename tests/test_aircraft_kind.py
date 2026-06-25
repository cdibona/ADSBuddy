"""Aircraft kind classification + icons for notifications."""
from __future__ import annotations


def test_kind_by_category():
    from app.aircraft_helpers import aircraft_kind
    assert aircraft_kind("GLF6", "A7") == "helicopter"   # category wins
    assert aircraft_kind("C172", "A1") == "light"
    assert aircraft_kind("B738", "A3") == "jet"
    assert aircraft_kind("B738", "A5") == "jet"


def test_kind_by_type_fallback_when_no_category():
    from app.aircraft_helpers import aircraft_kind
    assert aircraft_kind("R44", None) == "helicopter"
    assert aircraft_kind("C172", "") == "light"
    assert aircraft_kind("ZZZZ", None) == "plane"   # unknown -> generic
    assert aircraft_kind(None, None) == "plane"


def test_icons_and_labels():
    from app.aircraft_helpers import kind_icon, kind_label
    assert kind_icon("R44", None) == "🚁"
    assert kind_icon("C172", None) == "🛩️"
    assert kind_icon("B738", "A3") == "✈️"
    assert kind_label("R44", None) == "Helicopter"
    assert kind_label("C172", None) == "Light plane"


def test_discord_embed_has_icon_and_links():
    import types
    from datetime import datetime, timezone
    from app.notifications import build_discord_embed
    f = types.SimpleNamespace(
        icao_hex="a835af", registration="N628TS", callsign="N628TS", type_code="GLF6",
        category="A2", year=2015, altitude_baro=38000, lat=47.45, lon=-122.31,
        origin_icao="KSJC", destination_icao="KPDX", squawk=None, emergency=None,
        fired_at=datetime(2026, 6, 25, tzinfo=timezone.utc))
    t = types.SimpleNamespace(name="Elon Musk", center_lat=None, radius_miles=None)
    embed = build_discord_embed(t, f, "https://h:8443")
    assert embed["title"].startswith("✈️ N628TS")
    link_field = next(fld for fld in embed["fields"] if fld["name"] == "Links")
    assert "registry.faa.gov" in link_field["value"]      # FAA deep link
    assert "/aircraft/a835af" in link_field["value"]       # detail link
    assert "opensky-network.org" in link_field["value"]
    assert "Jet" in embed["footer"]["text"]


def test_helicopter_gets_heli_icon():
    import types
    from app.notifications import build_discord_embed
    f = types.SimpleNamespace(
        icao_hex="abc", registration="N911", callsign=None, type_code="EC35",
        category="A7", year=None, altitude_baro=600, lat=None, lon=None,
        origin_icao=None, destination_icao=None, squawk=None, emergency=None, fired_at=None)
    t = types.SimpleNamespace(name="Helo", center_lat=None, radius_miles=None)
    embed = build_discord_embed(t, f, "")
    assert embed["title"].startswith("🚁")


def test_kind_icon_urls_are_public_svgs():
    from app.aircraft_helpers import kind_icon_url
    assert kind_icon_url("EC35", "A7").endswith("emoji_u1f681.svg")   # helicopter
    assert kind_icon_url("C172", None).endswith("emoji_u1f6e9.svg")   # light plane
    assert kind_icon_url("B738", "A3").endswith("emoji_u2708.svg")    # jet
    assert kind_icon_url("B738", "A3").startswith("https://")          # public, fetchable by TRMNL


def test_vestaboard_matrix_is_centered_6x22():
    import types
    from app import notifications as n
    f = types.SimpleNamespace(registration="N628TS", icao_hex="a", type_code="GLF6",
                              altitude_baro=38000, origin_icao="KSJC", destination_icao="KPDX",
                              squawk=None, emergency=None)
    t = types.SimpleNamespace(name="ELON MUSK")
    m = n._vestaboard_matrix(t, f)
    assert len(m) == 6 and all(len(row) == 22 for row in m)        # full board
    assert m[0] == [n._VB_BLUE] * 22 and m[5] == [n._VB_BLUE] * 22  # color bars top/bottom
    # N628TS row: N=14, 6=32, 2=28, 8=34, T=20, S=19 — present and centered (blank-padded)
    row = m[2]
    assert 14 in row and row[0] == 0 and row[-1] == 0


def test_vestaboard_matrix_emergency_is_red():
    import types
    from app import notifications as n
    f = types.SimpleNamespace(registration="N1", icao_hex="a", type_code="B738",
                              altitude_baro=1000, origin_icao=None, destination_icao=None,
                              squawk="7700", emergency=None)
    m = n._vestaboard_matrix(types.SimpleNamespace(name="EMERG"), f)
    assert m[0] == [n._VB_RED] * 22
