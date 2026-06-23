"""Tests for aircraft helper functions and route registration.

Pure unit tests — no database or HTTP stack required.
"""

from __future__ import annotations

from app.aircraft_helpers import opensky_url, registration_url, type_url


class TestRegistrationUrl:
    def test_n_number_returns_faa_url(self):
        url = registration_url("N12345")
        assert url is not None
        assert "registry.faa.gov" in url
        assert "N12345" in url

    def test_n_number_lowercase_input(self):
        url = registration_url("n12345")
        assert url is not None
        assert "registry.faa.gov" in url

    def test_non_us_registration_returns_airframes(self):
        url = registration_url("G-ABCD")
        assert url is not None
        assert "airframes.org" in url
        assert "G-ABCD" in url

    def test_canadian_registration_returns_airframes(self):
        url = registration_url("C-GABC")
        assert url is not None
        assert "airframes.org" in url

    def test_none_returns_none(self):
        assert registration_url(None) is None

    def test_empty_string_returns_none(self):
        assert registration_url("") is None

    def test_whitespace_only_returns_none(self):
        assert registration_url("   ") is None

    def test_single_n_routes_to_airframes(self):
        # "N" alone is not a valid US registration; must have at least one more char.
        url = registration_url("N")
        assert url is not None
        assert "airframes.org" in url


class TestTypeUrl:
    def test_type_code_returns_wikipedia_url(self):
        url = type_url("B738")
        assert url is not None
        assert "wikipedia.org" in url
        assert "B738" in url

    def test_none_returns_none(self):
        assert type_url(None) is None

    def test_empty_string_returns_none(self):
        assert type_url("") is None

    def test_whitespace_only_returns_none(self):
        assert type_url("  ") is None

    def test_type_code_is_url_encoded(self):
        url = type_url("A320neo")
        assert url is not None
        assert "wikipedia.org" in url
        assert "A320neo" in url


class TestOpenskyUrl:
    def test_hex_returns_opensky_url(self):
        url = opensky_url("a1b2c3")
        assert url is not None
        assert "opensky-network.org" in url
        assert "a1b2c3" in url

    def test_hex_is_lowercased(self):
        url = opensky_url("A1B2C3")
        assert url is not None
        assert "a1b2c3" in url
        assert "A1B2C3" not in url

    def test_none_returns_none(self):
        assert opensky_url(None) is None

    def test_empty_string_returns_none(self):
        assert opensky_url("") is None

    def test_whitespace_returns_none(self):
        assert opensky_url("  ") is None


class TestAircraftRouteRegistration:
    """Verify the aircraft detail route is registered on routes_pages.router."""

    def test_aircraft_detail_route_exists(self):
        from app.routes_pages import router

        paths = [route.path for route in router.routes]
        assert "/aircraft/{icao_hex}" in paths

    def test_aircraft_list_route_exists(self):
        from app.routes_pages import router

        paths = [route.path for route in router.routes]
        assert "/aircraft" in paths
