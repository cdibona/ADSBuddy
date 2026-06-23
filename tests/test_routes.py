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


class TestTriggerPrefillUrl:
    def test_none_hex_returns_none(self):
        from app.aircraft_helpers import trigger_prefill_url

        assert trigger_prefill_url(None) is None

    def test_empty_hex_returns_none(self):
        from app.aircraft_helpers import trigger_prefill_url

        assert trigger_prefill_url("") is None

    def test_whitespace_hex_returns_none(self):
        from app.aircraft_helpers import trigger_prefill_url

        assert trigger_prefill_url("  ") is None

    def test_valid_hex_returns_url(self):
        from app.aircraft_helpers import trigger_prefill_url

        url = trigger_prefill_url("a1b2c3")
        assert url is not None
        assert url.startswith("/triggers/new?")
        assert "hex=a1b2c3" in url

    def test_hex_is_lowercased(self):
        from app.aircraft_helpers import trigger_prefill_url

        url = trigger_prefill_url("A1B2C3")
        assert url is not None
        assert "hex=a1b2c3" in url

    def test_optional_fields_in_url(self):
        from app.aircraft_helpers import trigger_prefill_url

        url = trigger_prefill_url("a1b2c3", tail="N12345", type_code="B738", year=1985, owner="United")
        assert url is not None
        assert "tail=N12345" in url
        assert "type=B738" in url
        assert "year=1985" in url
        assert "owner=United" in url

    def test_none_optional_fields_omitted(self):
        from app.aircraft_helpers import trigger_prefill_url

        url = trigger_prefill_url("a1b2c3")
        assert url is not None
        assert "tail" not in url
        assert "type" not in url
        assert "year" not in url
        assert "owner" not in url


class TestParsePrefillParams:
    def test_no_hex_returns_empty(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params(None, None, None, None, None)
        assert prefill == {}
        assert error is None

    def test_empty_hex_returns_empty(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("", None, None, None, None)
        assert prefill == {}
        assert error is None

    def test_invalid_hex_returns_error(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("ZZZZZZ", None, None, None, None)
        assert prefill == {}
        assert error is not None
        assert "ZZZZZZ" in error

    def test_valid_hex_populates_prefill(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("a1b2c3", None, None, None, None)
        assert error is None
        assert prefill["hex"] == "a1b2c3"

    def test_hex_normalized_to_lowercase(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("A1B2C3", None, None, None, None)
        assert error is None
        assert prefill["hex"] == "a1b2c3"

    def test_optional_fields_populate_prefill(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("a1b2c3", "N12345", "B738", "1985", "United")
        assert error is None
        assert prefill["tail"] == "N12345"
        assert prefill["type"] == "B738"
        assert prefill.get("year") == "1985"
        assert prefill["owner"] == "United"

    def test_invalid_year_silently_omitted(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("a1b2c3", None, None, "notayear", None)
        assert error is None
        assert "year" not in prefill

    def test_out_of_range_year_silently_omitted(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, error = _parse_prefill_params("a1b2c3", None, None, "1800", None)
        assert error is None
        assert "year" not in prefill

    def test_name_defaults_to_tail(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, _ = _parse_prefill_params("a1b2c3", "N12345", None, None, None)
        assert prefill.get("name") == "N12345"

    def test_name_falls_back_to_hex(self):
        from app.routes_triggers import _parse_prefill_params

        prefill, _ = _parse_prefill_params("a1b2c3", None, None, None, None)
        assert prefill.get("name") == "a1b2c3"
