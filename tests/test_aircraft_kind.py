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


class TestSummary:
    def _firing(self, name, ago_sec, priority=True):
        # build a (name, fired_at) row-ish via SimpleNamespace not needed; tested via build_summary mock
        pass

    def test_human_ago(self):
        from datetime import datetime, timezone, timedelta
        from app.notifications import _human_ago
        now = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
        assert _human_ago(now, now - timedelta(minutes=4)) == "4m"
        assert _human_ago(now, now - timedelta(hours=2)) == "2h"
        assert _human_ago(now, now - timedelta(days=3)) == "3d"
        assert _human_ago(now, None) == "?"

    def test_summary_trmnl_mv_and_vb_matrix(self):
        from datetime import datetime, timezone
        from app import notifications as n
        s = {"count": 47, "window_minutes": 15, "news": "Lifeflight 4m ago",
             "generated_at": datetime(2026, 6, 25, 16, 49, tzinfo=timezone.utc)}
        mv = n._summary_trmnl_mv(s)
        assert mv["count"] == "47" and mv["window"] == "15 MIN" and mv["news"] == "Lifeflight 4m ago"
        assert mv["icon_url"].endswith("emoji_u1f4e1.svg")
        m = n._summary_vb_matrix(s)
        assert len(m) == 6 and all(len(r) == 22 for r in m)
        assert m[0] == [n._VB_BLUE] * 22   # bar


def test_summary_route_registered():
    from app.routes_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/admin/notifications/summary-now" in paths


def test_summary_settings_categorized():
    from app.settings_store import setting_category
    assert setting_category("summary_enabled") == "summary"
    assert setting_category("summary_interval_minutes") == "summary"


def test_summary_kind_buckets():
    from app.aircraft_helpers import summary_kind
    assert summary_kind("EC35", "A7") == "helicopter"
    assert summary_kind("DHC2", None) == "seaplane"        # Beaver
    assert summary_kind("C172", "A1") == "light"
    assert summary_kind("GLF6", "A2") == "private_jet"     # Gulfstream
    assert summary_kind("B748", "A5", "ATLAS AIR INC") == "cargo"   # operator-based
    assert summary_kind("B738", "A3", "UNITED") == "airliner"
    assert summary_kind("ZZZZ", None, None) == "other"


def test_is_emergency():
    import types
    from app.notifications import _is_emergency
    assert _is_emergency(types.SimpleNamespace(squawk="7700", emergency=None))
    assert _is_emergency(types.SimpleNamespace(squawk=None, emergency="general"))
    assert not _is_emergency(types.SimpleNamespace(squawk="1200", emergency=None))


def test_channel_mode_and_interval_parsing():
    from app.routes_profile import _channel_mode, _summary_interval
    assert _channel_mode("summary") == "summary"
    assert _channel_mode("bogus") == "everything"
    assert _channel_mode(None) == "everything"
    assert _summary_interval("7") == 7
    assert _summary_interval("0") == 1      # clamp
    assert _summary_interval("x") == 15
