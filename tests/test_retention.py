"""Unit tests for app/ingest.py utility functions.

Tests the pure (no-I/O) coercion helpers and the async cleanup throttle.
All async calls use asyncio.run() directly so pytest-asyncio is not required.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import app.ingest as ingest
from app.ingest import (
    _coerce_float,
    _coerce_int,
    _parse_retention_days,
    _strip,
)


# ---------------------------------------------------------------------------
# _coerce_int
# ---------------------------------------------------------------------------

class TestCoerceInt:
    def test_none_returns_none(self):
        assert _coerce_int(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_int("") is None

    def test_ground_returns_none(self):
        assert _coerce_int("ground") is None

    def test_integer_string(self):
        assert _coerce_int("42") == 42

    def test_negative_integer_string(self):
        assert _coerce_int("-5") == -5

    def test_float_value_truncates(self):
        # int(3.7) == 3
        assert _coerce_int(3.7) == 3

    def test_float_string_returns_none(self):
        # int("3.7") raises ValueError → None
        assert _coerce_int("3.7") is None

    def test_zero_string(self):
        assert _coerce_int("0") == 0

    def test_integer_passthrough(self):
        assert _coerce_int(100) == 100

    def test_dict_returns_none(self):
        assert _coerce_int({}) is None


# ---------------------------------------------------------------------------
# _coerce_float
# ---------------------------------------------------------------------------

class TestCoerceFloat:
    def test_none_returns_none(self):
        assert _coerce_float(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_float("") is None

    def test_float_string(self):
        assert _coerce_float("3.14") == 3.14

    def test_integer_string(self):
        assert _coerce_float("10") == 10.0

    def test_negative(self):
        assert _coerce_float("-1.5") == -1.5

    def test_invalid_string_returns_none(self):
        assert _coerce_float("abc") is None

    def test_float_passthrough(self):
        assert _coerce_float(2.718) == 2.718

    def test_integer_passthrough(self):
        assert _coerce_float(5) == 5.0


# ---------------------------------------------------------------------------
# _strip
# ---------------------------------------------------------------------------

class TestStrip:
    def test_none_returns_none(self):
        assert _strip(None) is None

    def test_empty_string_returns_none(self):
        assert _strip("") is None

    def test_whitespace_only_returns_none(self):
        assert _strip("   ") is None

    def test_strips_surrounding_whitespace(self):
        assert _strip("  hello  ") == "hello"

    def test_inner_spaces_preserved(self):
        assert _strip("  hello world  ") == "hello world"

    def test_non_string_converted_and_stripped(self):
        assert _strip(42) == "42"

    def test_float_converted(self):
        assert _strip(3.14) == "3.14"


# ---------------------------------------------------------------------------
# _parse_retention_days
# ---------------------------------------------------------------------------

class TestParseRetentionDays:
    def test_none_defaults_to_30(self):
        assert _parse_retention_days(None) == 30

    def test_empty_string_defaults_to_30(self):
        assert _parse_retention_days("") == 30

    def test_whitespace_defaults_to_30(self):
        assert _parse_retention_days("   ") == 30

    def test_non_numeric_defaults_to_30(self):
        assert _parse_retention_days("abc") == 30

    def test_zero_disables_cleanup(self):
        assert _parse_retention_days("0") is None

    def test_negative_disables_cleanup(self):
        assert _parse_retention_days("-1") is None

    def test_valid_positive(self):
        assert _parse_retention_days("30") == 30

    def test_valid_large(self):
        assert _parse_retention_days("365") == 365

    def test_strips_whitespace_before_parse(self):
        assert _parse_retention_days("  7  ") == 7


# ---------------------------------------------------------------------------
# _maybe_cleanup_sightings — throttle and exception-reset behaviour
# ---------------------------------------------------------------------------

class TestMaybeCleanupSightings:
    """Tests that manipulate the module-level _last_cleanup sentinel."""

    def _run(self):
        asyncio.run(ingest._maybe_cleanup_sightings())

    def test_throttle_skips_when_cleanup_is_recent(self):
        """If _last_cleanup was just set, SessionLocal must never be called."""
        original = ingest._last_cleanup
        try:
            ingest._last_cleanup = time.monotonic()  # "just ran"
            with patch("app.ingest.SessionLocal") as mock_sl:
                self._run()
            mock_sl.assert_not_called()
        finally:
            ingest._last_cleanup = original

    def test_exception_resets_last_cleanup_to_zero(self):
        """On DB error, _last_cleanup is reset to 0.0 so cleanup retries."""
        original = ingest._last_cleanup
        try:
            # Force the throttle check to pass (long time since last run).
            ingest._last_cleanup = 0.0

            # Build a context manager whose __aenter__ raises.
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
            cm.__aexit__ = AsyncMock(return_value=False)

            with patch("app.ingest.SessionLocal", return_value=cm):
                self._run()

            assert ingest._last_cleanup == 0.0
        finally:
            ingest._last_cleanup = original

    def test_disabled_retention_sets_timestamp(self):
        """When retention is disabled (days=None), _last_cleanup is still set."""
        original = ingest._last_cleanup
        try:
            ingest._last_cleanup = 0.0

            mock_session = AsyncMock()
            cm = AsyncMock()
            cm.__aenter__ = AsyncMock(return_value=mock_session)
            cm.__aexit__ = AsyncMock(return_value=False)

            # get_setting returns "0" → _parse_retention_days returns None (disabled)
            with patch("app.ingest.SessionLocal", return_value=cm), \
                 patch("app.ingest.get_setting", new=AsyncMock(return_value="0")):
                self._run()

            # _last_cleanup was updated before the try block
            assert ingest._last_cleanup > 0.0
        finally:
            ingest._last_cleanup = original
