"""Unit tests for Phase 4: historical aircraft search.

Pure unit tests - no database or HTTP stack required.
All helpers tested here are pure functions (no I/O).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# _parse_history_filters
# ---------------------------------------------------------------------------


class TestParseHistoryFilters:
    def _parse(self, **kwargs):
        from app.routes_pages import _parse_history_filters

        defaults = dict(
            tail=None,
            hex_raw=None,
            callsign=None,
            type_code=None,
            owner=None,
            year_raw=None,
            route=None,
            start_date=None,
            end_date=None,
        )
        defaults.update(kwargs)
        return _parse_history_filters(**defaults)

    # --- tail ---
    def test_tail_populates_filter(self):
        filters, errors = self._parse(tail="N12345")
        assert errors == []
        assert filters["tail"] == "N12345"

    def test_tail_whitespace_stripped(self):
        filters, errors = self._parse(tail="  N12345  ")
        assert filters["tail"] == "N12345"

    def test_tail_empty_string_omitted(self):
        filters, errors = self._parse(tail="")
        assert "tail" not in filters
        assert errors == []

    def test_tail_whitespace_only_omitted(self):
        filters, errors = self._parse(tail="   ")
        assert "tail" not in filters
        assert errors == []

    # --- hex ---
    def test_hex_valid_normalized_to_lowercase(self):
        filters, errors = self._parse(hex_raw="A1B2C3")
        assert errors == []
        assert filters["hex"] == "a1b2c3"

    def test_hex_already_lowercase(self):
        filters, errors = self._parse(hex_raw="a1b2c3")
        assert errors == []
        assert filters["hex"] == "a1b2c3"

    def test_hex_invalid_chars_produces_error(self):
        filters, errors = self._parse(hex_raw="ZZZZZZ")
        assert errors
        assert "ZZZZZZ" in errors[0]
        assert "hex" not in filters

    def test_hex_too_long_produces_error(self):
        filters, errors = self._parse(hex_raw="a1b2c3d4e5")  # 10 chars > 8
        assert errors
        assert "hex" not in filters

    def test_hex_empty_omitted(self):
        filters, errors = self._parse(hex_raw="")
        assert "hex" not in filters
        assert errors == []

    def test_hex_max_length_valid(self):
        filters, errors = self._parse(hex_raw="a1b2c3d4")  # 8 chars
        assert errors == []
        assert filters["hex"] == "a1b2c3d4"

    def test_hex_whitespace_stripped(self):
        filters, errors = self._parse(hex_raw="  a1b2c3  ")
        assert errors == []
        assert filters["hex"] == "a1b2c3"

    # --- callsign ---
    def test_callsign_populates_filter(self):
        filters, errors = self._parse(callsign="UAL123")
        assert errors == []
        assert filters["callsign"] == "UAL123"

    def test_callsign_empty_omitted(self):
        filters, errors = self._parse(callsign="")
        assert "callsign" not in filters

    def test_callsign_whitespace_stripped(self):
        filters, errors = self._parse(callsign="  UAL123  ")
        assert filters["callsign"] == "UAL123"

    # --- type_code ---
    def test_type_code_populates_filter(self):
        filters, errors = self._parse(type_code="B738")
        assert errors == []
        assert filters["type_code"] == "B738"

    def test_type_code_empty_omitted(self):
        filters, errors = self._parse(type_code="")
        assert "type_code" not in filters

    # --- owner ---
    def test_owner_populates_filter(self):
        filters, errors = self._parse(owner="United")
        assert errors == []
        assert filters["owner"] == "United"

    def test_owner_empty_omitted(self):
        filters, errors = self._parse(owner="")
        assert "owner" not in filters

    # --- year ---
    def test_year_valid_integer(self):
        filters, errors = self._parse(year_raw="2010")
        assert errors == []
        assert filters["year"] == 2010

    def test_year_lower_boundary_valid(self):
        filters, errors = self._parse(year_raw="1900")
        assert errors == []
        assert filters["year"] == 1900

    def test_year_upper_boundary_valid(self):
        filters, errors = self._parse(year_raw="2100")
        assert errors == []
        assert filters["year"] == 2100

    def test_year_below_range_produces_error(self):
        filters, errors = self._parse(year_raw="1800")
        assert errors
        assert "year" not in filters

    def test_year_above_range_produces_error(self):
        filters, errors = self._parse(year_raw="2200")
        assert errors
        assert "year" not in filters

    def test_year_non_numeric_produces_error(self):
        filters, errors = self._parse(year_raw="notayear")
        assert errors
        assert "year" not in filters

    def test_year_empty_omitted(self):
        filters, errors = self._parse(year_raw="")
        assert "year" not in filters
        assert errors == []

    def test_year_1899_out_of_range(self):
        filters, errors = self._parse(year_raw="1899")
        assert errors
        assert "year" not in filters

    def test_year_2101_out_of_range(self):
        filters, errors = self._parse(year_raw="2101")
        assert errors
        assert "year" not in filters

    # --- route ---
    def test_route_populates_filter(self):
        filters, errors = self._parse(route="KSFO")
        assert errors == []
        assert filters["route"] == "KSFO"

    def test_route_empty_omitted(self):
        filters, errors = self._parse(route="")
        assert "route" not in filters

    def test_route_whitespace_stripped(self):
        filters, errors = self._parse(route="  KSFO  ")
        assert filters["route"] == "KSFO"

    # --- start_date ---
    def test_start_date_valid_produces_datetime(self):
        filters, errors = self._parse(start_date="2024-01-15")
        assert errors == []
        assert "start_dt" in filters
        dt = filters["start_dt"]
        assert isinstance(dt, datetime)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo is not None

    def test_start_date_is_utc(self):
        filters, errors = self._parse(start_date="2024-06-01")
        assert errors == []
        dt = filters["start_dt"]
        assert dt.tzinfo == timezone.utc

    def test_start_date_invalid_format_produces_error(self):
        filters, errors = self._parse(start_date="15-01-2024")
        assert errors
        assert "start_dt" not in filters

    def test_start_date_invalid_value_produces_error(self):
        filters, errors = self._parse(start_date="2024-13-99")
        assert errors
        assert "start_dt" not in filters

    def test_start_date_empty_omitted(self):
        filters, errors = self._parse(start_date="")
        assert "start_dt" not in filters
        assert errors == []

    def test_start_date_non_date_string_produces_error(self):
        filters, errors = self._parse(start_date="yesterday")
        assert errors
        assert "start_dt" not in filters

    # --- end_date ---
    def test_end_date_advances_to_next_day(self):
        """End date is inclusive so upper bound = start of next day."""
        filters, errors = self._parse(end_date="2024-01-15")
        assert errors == []
        assert "end_dt" in filters
        dt = filters["end_dt"]
        assert dt.day == 16  # exclusive: next day midnight

    def test_end_date_invalid_format_produces_error(self):
        filters, errors = self._parse(end_date="Jan 15 2024")
        assert errors
        assert "end_dt" not in filters

    def test_end_date_empty_omitted(self):
        filters, errors = self._parse(end_date="")
        assert "end_dt" not in filters
        assert errors == []

    def test_end_date_invalid_value_produces_error(self):
        filters, errors = self._parse(end_date="2024-02-30")
        assert errors
        assert "end_dt" not in filters

    # --- multiple filters / edge cases ---
    def test_multiple_valid_filters(self):
        filters, errors = self._parse(
            tail="N12345", type_code="B738", year_raw="2010"
        )
        assert errors == []
        assert filters["tail"] == "N12345"
        assert filters["type_code"] == "B738"
        assert filters["year"] == 2010

    def test_one_invalid_does_not_suppress_others(self):
        filters, errors = self._parse(tail="N12345", hex_raw="ZZZZZZ")
        assert errors  # hex error present
        assert filters["tail"] == "N12345"  # tail still parsed
        assert "hex" not in filters

    def test_all_empty_returns_empty_filters_no_errors(self):
        filters, errors = self._parse()
        assert filters == {}
        assert errors == []

    def test_none_inputs_all_empty(self):
        filters, errors = self._parse(
            tail=None, hex_raw=None, callsign=None, type_code=None,
            owner=None, year_raw=None, route=None, start_date=None, end_date=None,
        )
        assert filters == {}
        assert errors == []


# ---------------------------------------------------------------------------
# _build_history_conditions
# ---------------------------------------------------------------------------


class TestBuildHistoryConditions:
    def _build(self, **kwargs):
        from app.routes_pages import _build_history_conditions

        return _build_history_conditions(kwargs)

    def test_empty_filters_returns_no_conditions(self):
        assert self._build() == []

    def test_tail_produces_one_condition(self):
        conds = self._build(tail="N12345")
        assert len(conds) == 1

    def test_hex_produces_one_condition(self):
        conds = self._build(hex="a1b2c3")
        assert len(conds) == 1

    def test_type_code_produces_one_condition(self):
        conds = self._build(type_code="B738")
        assert len(conds) == 1

    def test_owner_produces_one_condition(self):
        conds = self._build(owner="United")
        assert len(conds) == 1

    def test_year_produces_one_condition(self):
        conds = self._build(year=2010)
        assert len(conds) == 1

    def test_callsign_produces_one_condition(self):
        conds = self._build(callsign="UAL123")
        assert len(conds) == 1

    def test_route_produces_one_condition(self):
        conds = self._build(route="KSFO")
        assert len(conds) == 1

    def test_start_dt_alone_produces_one_condition(self):
        dt = datetime(2024, 1, 1, tzinfo=timezone.utc)
        conds = self._build(start_dt=dt)
        assert len(conds) == 1

    def test_end_dt_alone_produces_one_condition(self):
        dt = datetime(2024, 1, 2, tzinfo=timezone.utc)
        conds = self._build(end_dt=dt)
        assert len(conds) == 1

    def test_start_and_end_dt_produce_one_combined_condition(self):
        """Both date bounds are merged into a single EXISTS subquery."""
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        conds = self._build(start_dt=dt1, end_dt=dt2)
        assert len(conds) == 1

    def test_all_filters_produce_expected_count(self):
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 1, 2, tzinfo=timezone.utc)
        conds = self._build(
            tail="N12345",
            hex="a1b2c3",
            type_code="B738",
            owner="United",
            year=2010,
            callsign="UAL123",
            route="KSFO",
            start_dt=dt1,
            end_dt=dt2,
        )
        # tail, hex, type_code, owner, year, callsign, route = 7 direct
        # start_dt + end_dt merged into 1 date condition
        # Total = 8
        assert len(conds) == 8

    def test_conditions_are_independent_across_calls(self):
        """Calling twice with same input produces independent list objects."""
        from app.routes_pages import _build_history_conditions

        conds1 = _build_history_conditions({"tail": "N12345"})
        conds2 = _build_history_conditions({"tail": "N12345"})
        assert conds1 is not conds2

    def test_only_date_filters_produce_one_condition(self):
        """Pair of date filters yields exactly one combined EXISTS condition."""
        dt1 = datetime(2024, 1, 1, tzinfo=timezone.utc)
        dt2 = datetime(2024, 2, 1, tzinfo=timezone.utc)
        conds = self._build(start_dt=dt1, end_dt=dt2)
        assert len(conds) == 1


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class TestHistoryRouteRegistration:
    def test_history_route_exists(self):
        from app.routes_pages import router

        paths = [route.path for route in router.routes]
        assert "/history" in paths

    def test_history_route_accepts_get(self):
        from app.routes_pages import router

        history_routes = [
            r for r in router.routes
            if hasattr(r, "path") and r.path == "/history"
        ]
        assert history_routes, "No /history route found on router"
        assert "GET" in history_routes[0].methods

    def test_history_route_is_distinct_from_aircraft_routes(self):
        """Sanity check: /history doesn't shadow /aircraft."""
        from app.routes_pages import router

        paths = [route.path for route in router.routes]
        assert "/history" in paths
        assert "/aircraft" in paths
        assert "/aircraft/{icao_hex}" in paths
