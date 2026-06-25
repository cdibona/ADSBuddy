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
    def test_known_code_links_directly_to_article(self):
        # B738 (737-800) resolves to the 737 Next Generation article, not a search.
        url = type_url("B738")
        assert url == "https://en.wikipedia.org/wiki/Boeing_737_Next_Generation"
        assert "Special:Search" not in url

    def test_known_code_is_case_insensitive(self):
        assert type_url("b738") == type_url("B738")

    def test_variants_collapse_to_family_article(self):
        # All 737 MAX codes point at the same article.
        assert type_url("B38M") == type_url("B39M")
        assert "Boeing_737_MAX" in type_url("B38M")

    def test_none_returns_none(self):
        assert type_url(None) is None

    def test_empty_string_returns_none(self):
        assert type_url("") is None

    def test_whitespace_only_returns_none(self):
        assert type_url("  ") is None

    def test_unknown_code_falls_back_to_search(self):
        url = type_url("ZZZZ")
        assert "Special:Search" in url
        assert "ZZZZ" in url

    def test_unknown_code_prefers_description_in_search(self):
        url = type_url("ZZZZ", "EMBRAER EMB-505 Phenom 300")
        assert "Special:Search" in url
        assert "Phenom" in url
        # The opaque code should not be what we search for when we have a name.
        assert "ZZZZ" not in url

    def test_known_code_ignores_description(self):
        # A curated code wins even if a quirky per-airframe description exists.
        assert type_url("B737", "Boeing C-40B") == (
            "https://en.wikipedia.org/wiki/Boeing_737_Next_Generation"
        )


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


class TestRegistrationProviderAndDeepLink:
    def test_us_nnumber_deep_links_to_result_page(self):
        from app.aircraft_helpers import registration_url
        url = registration_url("N424LF")
        assert "registry.faa.gov" in url and "NNumberResult" in url and "N424LF" in url

    def test_provider_label(self):
        from app.aircraft_helpers import registration_provider
        assert registration_provider("N424LF") == "FAA"
        assert registration_provider("G-ABCD") == "airframes"
        assert registration_provider(None) is None
        assert registration_provider("") is None


class TestExternalLinkLabels:
    def test_aircraft_list_uses_labels_not_arrow(self):
        import types
        from datetime import datetime, timezone
        from app.routes_pages import templates
        from app.models import Aircraft
        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/aircraft"))
        ac = Aircraft(icao_hex="a50b7b", registration="N424LF", type_code="B407",
                      description="BELL 407", owner_op="x", year=2018,
                      last_seen=datetime(2026, 6, 24, 16, tzinfo=timezone.utc))
        out = templates.env.get_template("aircraft.html").render(
            request=req, user=types.SimpleNamespace(username="a", is_admin=True),
            aircraft=[ac], type_active=None, common_types=[])
        assert "↗" not in out          # the weird arrow is gone
        # Registration text itself links to the FAA registry (no separate chip).
        assert "registry.faa.gov" in out
        assert ">N424LF</a>" in out
        # Type code text itself links to Wikipedia (no separate chip).
        assert "wikipedia.org" in out
        assert ">B407</a>" in out
        # OpenSky moved to the detail page only — not on the recent list.
        assert "opensky" not in out.lower()
