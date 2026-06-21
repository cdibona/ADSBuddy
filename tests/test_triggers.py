"""Unit tests for app/triggers.py.

Tests the pure helper functions (no I/O) and the async evaluate_and_record
function using a mocked AsyncSession.  No database connection required.
All async calls use asyncio.run() so pytest-asyncio is not needed.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.triggers import (
    AircraftFacts,
    _any_exact,
    _any_pattern,
    _csv,
    _pattern_match,
    evaluate_and_record,
    matches,
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

NOW_YEAR = 2026


def _make_trigger(**kw) -> SimpleNamespace:
    """Return a minimal Trigger-like namespace with all fields matches() needs."""
    defaults = dict(
        id=1,
        name="test-trigger",
        cooldown_seconds=300,
        tail_patterns="",
        flight_patterns="",
        type_codes="",
        origin_icaos="",
        destination_icaos="",
        min_year=None,
        max_year=None,
        min_age_years=None,
        max_age_years=None,
        is_active=True,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _make_facts(**kw) -> AircraftFacts:
    defaults = dict(
        icao_hex="a1b2c3",
        callsign="UAL123",
        registration="N12345",
        type_code="B738",
        year=2010,
        lat=37.6,
        lon=-122.4,
        altitude_baro=35000,
        origin_icao="KSFO",
        destination_icao="KLAX",
    )
    defaults.update(kw)
    return AircraftFacts(**defaults)


def _make_session(first_result=None) -> AsyncMock:
    """Return a mock AsyncSession where execute().first() returns first_result."""
    execute_result = MagicMock()
    execute_result.first.return_value = first_result
    session = AsyncMock()
    session.execute = AsyncMock(return_value=execute_result)
    session.add = MagicMock()
    return session


# ---------------------------------------------------------------------------
# _csv
# ---------------------------------------------------------------------------

class TestCsv:
    def test_empty_string_returns_empty_list(self):
        assert _csv("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert _csv("   ") == []

    def test_single_value(self):
        assert _csv("B738") == ["b738"]

    def test_multiple_values(self):
        assert _csv("B738,A320,B77W") == ["b738", "a320", "b77w"]

    def test_strips_whitespace(self):
        assert _csv(" B738 , A320 ") == ["b738", "a320"]

    def test_lowercases(self):
        assert _csv("KSFO") == ["ksfo"]

    def test_filters_blank_entries(self):
        assert _csv("B738,,A320") == ["b738", "a320"]


# ---------------------------------------------------------------------------
# _pattern_match
# ---------------------------------------------------------------------------

class TestPatternMatch:
    def test_exact_match(self):
        assert _pattern_match("n12345", "n12345") is True

    def test_exact_no_match(self):
        assert _pattern_match("n12345", "n99999") is False

    def test_wildcard_star_match(self):
        assert _pattern_match("ual*", "ual123") is True

    def test_wildcard_star_no_match(self):
        assert _pattern_match("ual*", "dal123") is False

    def test_wildcard_question_mark(self):
        assert _pattern_match("ual12?", "ual123") is True

    def test_wildcard_question_mark_no_match(self):
        assert _pattern_match("ual12?", "ual1234") is False

    def test_case_sensitive_exact(self):
        # _pattern_match is case-sensitive; callers lowercase first
        assert _pattern_match("n12345", "N12345") is False


# ---------------------------------------------------------------------------
# _any_pattern
# ---------------------------------------------------------------------------

class TestAnyPattern:
    def test_empty_patterns_always_true(self):
        assert _any_pattern([], "anything") is True

    def test_none_value_returns_false(self):
        assert _any_pattern(["ual*"], None) is False

    def test_matching_pattern(self):
        assert _any_pattern(["ual*"], "UAL123") is True

    def test_non_matching_pattern(self):
        assert _any_pattern(["dal*"], "UAL123") is False

    def test_multiple_patterns_first_matches(self):
        assert _any_pattern(["dal*", "ual*"], "UAL123") is True

    def test_multiple_patterns_none_match(self):
        assert _any_pattern(["dal*", "aal*"], "UAL123") is False


# ---------------------------------------------------------------------------
# _any_exact
# ---------------------------------------------------------------------------

class TestAnyExact:
    def test_empty_values_always_true(self):
        assert _any_exact([], "anything") is True

    def test_none_value_returns_false(self):
        assert _any_exact(["ksfo"], None) is False

    def test_exact_match_case_insensitive(self):
        assert _any_exact(["ksfo"], "KSFO") is True

    def test_no_match(self):
        assert _any_exact(["klax"], "KSFO") is False

    def test_multiple_values_one_matches(self):
        assert _any_exact(["klax", "ksfo"], "KSFO") is True


# ---------------------------------------------------------------------------
# matches
# ---------------------------------------------------------------------------

class TestMatches:
    def test_empty_trigger_matches_everything(self):
        trigger = _make_trigger()
        assert matches(trigger, _make_facts(), NOW_YEAR) is True

    def test_tail_pattern_exact_match(self):
        trigger = _make_trigger(tail_patterns="N12345")
        assert matches(trigger, _make_facts(registration="N12345"), NOW_YEAR) is True

    def test_tail_pattern_no_match(self):
        trigger = _make_trigger(tail_patterns="N99999")
        assert matches(trigger, _make_facts(registration="N12345"), NOW_YEAR) is False

    def test_flight_pattern_wildcard(self):
        trigger = _make_trigger(flight_patterns="UAL*")
        assert matches(trigger, _make_facts(callsign="UAL456"), NOW_YEAR) is True

    def test_flight_pattern_no_match(self):
        trigger = _make_trigger(flight_patterns="DAL*")
        assert matches(trigger, _make_facts(callsign="UAL123"), NOW_YEAR) is False

    def test_type_code_match(self):
        trigger = _make_trigger(type_codes="B738")
        assert matches(trigger, _make_facts(type_code="B738"), NOW_YEAR) is True

    def test_type_code_no_match(self):
        trigger = _make_trigger(type_codes="A320")
        assert matches(trigger, _make_facts(type_code="B738"), NOW_YEAR) is False

    def test_origin_icao_match(self):
        trigger = _make_trigger(origin_icaos="KSFO")
        assert matches(trigger, _make_facts(origin_icao="KSFO"), NOW_YEAR) is True

    def test_destination_icao_no_match(self):
        trigger = _make_trigger(destination_icaos="KORD")
        assert matches(trigger, _make_facts(destination_icao="KLAX"), NOW_YEAR) is False

    def test_min_year_pass(self):
        trigger = _make_trigger(min_year=2000)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is True

    def test_min_year_fail(self):
        trigger = _make_trigger(min_year=2020)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is False

    def test_max_year_pass(self):
        trigger = _make_trigger(max_year=2020)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is True

    def test_max_year_fail(self):
        trigger = _make_trigger(max_year=2005)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is False

    def test_min_age_years_pass(self):
        # Aircraft from 2010 is 16 years old; min_age=10 → pass
        trigger = _make_trigger(min_age_years=10)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is True

    def test_min_age_years_fail(self):
        # Aircraft from 2024 is 2 years old; min_age=10 → fail
        trigger = _make_trigger(min_age_years=10)
        assert matches(trigger, _make_facts(year=2024), NOW_YEAR) is False

    def test_max_age_years_pass(self):
        # Aircraft from 2024 is 2 years old; max_age=5 → pass
        trigger = _make_trigger(max_age_years=5)
        assert matches(trigger, _make_facts(year=2024), NOW_YEAR) is True

    def test_max_age_years_fail(self):
        # Aircraft from 2010 is 16 years old; max_age=5 → fail
        trigger = _make_trigger(max_age_years=5)
        assert matches(trigger, _make_facts(year=2010), NOW_YEAR) is False

    def test_none_year_with_min_year_constraint_fails(self):
        trigger = _make_trigger(min_year=2000)
        assert matches(trigger, _make_facts(year=None), NOW_YEAR) is False

    def test_multiple_conditions_all_pass(self):
        trigger = _make_trigger(
            flight_patterns="UAL*",
            type_codes="B738",
            origin_icaos="KSFO",
        )
        facts = _make_facts(callsign="UAL123", type_code="B738", origin_icao="KSFO")
        assert matches(trigger, facts, NOW_YEAR) is True

    def test_multiple_conditions_one_fails(self):
        trigger = _make_trigger(
            flight_patterns="UAL*",
            type_codes="A320",  # mismatch
        )
        facts = _make_facts(callsign="UAL123", type_code="B738")
        assert matches(trigger, facts, NOW_YEAR) is False


# ---------------------------------------------------------------------------
# evaluate_and_record
# ---------------------------------------------------------------------------

class TestEvaluateAndRecord:
    def _run(self, session, triggers, facts):
        return asyncio.run(evaluate_and_record(session, triggers, facts))

    def test_empty_triggers_returns_empty(self):
        session = _make_session()
        firings, blocked = self._run(session, [], _make_facts())
        assert firings == []
        assert blocked == 0
        session.execute.assert_not_called()

    def test_non_matching_trigger_returns_empty(self):
        session = _make_session()
        trigger = _make_trigger(type_codes="A320")
        facts = _make_facts(type_code="B738")
        firings, blocked = self._run(session, [trigger], facts)
        assert firings == []
        assert blocked == 0
        # No cooldown check needed for non-matching
        session.execute.assert_not_called()

    def test_matching_trigger_no_cooldown_creates_firing(self):
        session = _make_session(first_result=None)  # no cooldown row
        trigger = _make_trigger(id=42, type_codes="B738")
        facts = _make_facts(type_code="B738", icao_hex="aabbcc")
        firings, blocked = self._run(session, [trigger], facts)
        assert len(firings) == 1
        assert blocked == 0
        assert firings[0].trigger_id == 42
        assert firings[0].icao_hex == "aabbcc"
        session.add.assert_called_once()

    def test_matching_trigger_with_cooldown_is_blocked(self):
        cooldown_row = MagicMock()  # truthy → cooldown active
        session = _make_session(first_result=cooldown_row)
        trigger = _make_trigger(id=7, type_codes="B738")
        facts = _make_facts(type_code="B738")
        firings, blocked = self._run(session, [trigger], facts)
        assert firings == []
        assert blocked == 1
        session.add.assert_not_called()

    def test_mixed_triggers(self):
        """One fires, one is cooldown-blocked, one doesn't match."""
        results = [None, MagicMock()]  # first call: no cooldown; second: blocked
        execute_result_iter = iter(results)

        def _side_effect(_stmt):
            val = next(execute_result_iter, None)
            mock_er = MagicMock()
            mock_er.first.return_value = val
            return mock_er

        session = AsyncMock()
        session.execute = AsyncMock(side_effect=_side_effect)
        session.add = MagicMock()

        t_fire = _make_trigger(id=1, type_codes="B738")
        t_block = _make_trigger(id=2, type_codes="B738", cooldown_seconds=3600)
        t_miss = _make_trigger(id=3, type_codes="A320")  # won't match

        facts = _make_facts(type_code="B738")
        firings, blocked = self._run(session, [t_fire, t_block, t_miss], facts)
        assert len(firings) == 1
        assert firings[0].trigger_id == 1
        assert blocked == 1
