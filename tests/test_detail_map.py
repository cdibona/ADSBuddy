"""Tests for the aircraft-detail location map and history lat/long column."""
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest


class TestToFloat:
    def test_parses_numbers(self):
        from app.routes_pages import _to_float

        assert _to_float("47.6323") == pytest.approx(47.6323)
        assert _to_float("-122.5") == pytest.approx(-122.5)

    def test_blank_or_invalid_is_none(self):
        from app.routes_pages import _to_float

        assert _to_float(None) is None
        assert _to_float("") is None
        assert _to_float("   ") is None
        assert _to_float("not-a-number") is None


@pytest.fixture
def req():
    return types.SimpleNamespace(url=types.SimpleNamespace(path="/aircraft/a1b2c3"))


@pytest.fixture
def admin():
    return types.SimpleNamespace(username="admin", is_admin=True, id=1)


def _aircraft():
    from app.models import Aircraft

    return Aircraft(
        icao_hex="a1b2c3", registration="N12345", type_code="B738",
        description="BOEING 737-800", owner_op="United", year=2005,
        first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_seen=datetime(2026, 6, 23, 16, 0, tzinfo=timezone.utc),
    )


class TestDetailMapRendering:
    def test_map_renders_with_points_and_receiver(self, req, admin):
        from app.routes_pages import templates

        tpl = templates.env.get_template("aircraft_detail.html")
        out = tpl.render(
            request=req, user=admin, aircraft=_aircraft(), sightings=[], firings_rows=[],
            map_points=[
                {"lat": 47.4, "lon": -122.2, "t": "2026-06-23 15:59:00 UTC",
                 "source": "local_radio", "color": "#4ea4ff", "alt": 9000, "flight": "UAL1", "track": 270.0},
                {"lat": 47.5, "lon": -122.3, "t": "2026-06-23 16:00:00 UTC",
                 "source": "local_radio", "color": "#4ea4ff", "alt": 10000, "flight": "UAL1", "track": 280.0},
            ],
            map_sources=[{"source": "local_radio", "color": "#4ea4ff"}],
            receiver={"lat": 47.6323, "lon": -122.5269, "label": "Local radio"},
        )
        assert 'id="sight-map"' in out
        assert "leaflet@1.9.4/dist/leaflet.js" in out
        assert "leaflet@1.9.4/dist/leaflet.css" in out
        # Legend shows the source and the station.
        assert "local_radio" in out
        assert "(station)" in out
        # Receiver coords reach the JS payload.
        assert "47.6323" in out
        # Path direction indicators present.
        assert "Latest report" in out
        assert "Track start" in out
        assert "direction of travel" in out

    def test_no_points_shows_placeholder_and_no_leaflet(self, req, admin):
        from app.routes_pages import templates

        tpl = templates.env.get_template("aircraft_detail.html")
        out = tpl.render(
            request=req, user=admin, aircraft=_aircraft(), sightings=[], firings_rows=[],
            map_points=[], map_sources=[], receiver=None,
        )
        assert "No positioned sightings to map yet." in out
        # Don't pull in Leaflet when there's nothing to plot.
        assert "leaflet@1.9.4" not in out


class TestHistoryPositionColumn:
    def test_history_shows_last_position(self, admin):
        from app.routes_pages import templates
        from app.models import Aircraft, Sighting

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/history"))
        ac = _aircraft()
        s = Sighting(
            icao_hex="a1b2c3", flight="UAL1", lat=47.1234, lon=-122.5678,
            source="local_radio",
            seen_at=datetime(2026, 6, 23, 16, 0, tzinfo=timezone.utc),
        )
        tpl = templates.env.get_template("history_search.html")
        out = tpl.render(
            request=req, user=admin,
            form={k: "" for k in ["tail", "hex", "callsign", "type", "owner",
                                  "year", "route", "start_date", "end_date"]},
            errors=[], searched=True, aircraft=[ac], recent_sightings={"a1b2c3": s},
            total=1, page=1, per_page=50, total_pages=1, start=1, end=1, filter_qs="",
        )
        assert "Last position" in out          # column header
        assert "47.1234, -122.5678" in out      # formatted coordinates
