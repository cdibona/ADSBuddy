"""Unit tests for pure helper functions in app/routes_triggers.py.

Tests only the synchronous utility functions that have no HTTP/DB side-effects:
  - _delivery_label
  - _pop_flash
  - _strip_or_empty
  - _int_or_none

All functions are imported directly; no HTTP client or database required.
"""
from __future__ import annotations

import urllib.parse
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routes_triggers import (
    _delivery_label,
    _int_or_none,
    _pop_flash,
    _strip_or_empty,
)

FLASH_COOKIE = "adsbuddy_flash"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_request(cookies: dict | None = None) -> SimpleNamespace:
    """Minimal stand-in for fastapi.Request with a .cookies dict."""
    return SimpleNamespace(cookies=cookies or {})


# ---------------------------------------------------------------------------
# _delivery_label
# ---------------------------------------------------------------------------

class TestDeliveryLabel:
    def test_failed_takes_priority_over_sent(self):
        assert _delivery_label(has_sent=True, has_failed=True) == "failed"

    def test_failed_flag_alone(self):
        assert _delivery_label(has_sent=False, has_failed=True) == "failed"

    def test_sent_flag_no_failure(self):
        assert _delivery_label(has_sent=True, has_failed=False) == "sent"

    def test_neither_flag_is_pending(self):
        assert _delivery_label(has_sent=False, has_failed=False) == "pending"

    def test_none_flags_are_pending(self):
        assert _delivery_label(has_sent=None, has_failed=None) == "pending"

    def test_none_failed_sent_true(self):
        assert _delivery_label(has_sent=True, has_failed=None) == "sent"

    def test_none_sent_failed_true(self):
        assert _delivery_label(has_sent=None, has_failed=True) == "failed"


# ---------------------------------------------------------------------------
# _pop_flash
# ---------------------------------------------------------------------------

class TestPopFlash:
    def test_no_cookie_returns_none(self):
        req = _make_request()
        assert _pop_flash(req) is None

    def test_empty_cookie_returns_none(self):
        req = _make_request({FLASH_COOKIE: ""})
        assert _pop_flash(req) is None

    def test_success_message(self):
        encoded = urllib.parse.quote("Trigger saved.")
        req = _make_request({FLASH_COOKIE: f"success:{encoded}"})
        result = _pop_flash(req)
        assert result == ("success", "Trigger saved.")

    def test_error_message(self):
        encoded = urllib.parse.quote("Something went wrong")
        req = _make_request({FLASH_COOKIE: f"error:{encoded}"})
        level, msg = _pop_flash(req)
        assert level == "error"
        assert msg == "Something went wrong"

    def test_message_containing_colon(self):
        # partition splits on first colon only
        raw_msg = "Error: db failed"
        encoded = urllib.parse.quote(raw_msg)
        req = _make_request({FLASH_COOKIE: f"error:{encoded}"})
        level, msg = _pop_flash(req)
        assert level == "error"
        assert msg == raw_msg

    def test_special_characters_decoded(self):
        raw_msg = "Trigger \"Alpha\" deleted!"
        encoded = urllib.parse.quote(raw_msg)
        req = _make_request({FLASH_COOKIE: f"success:{encoded}"})
        _, msg = _pop_flash(req)
        assert msg == raw_msg


# ---------------------------------------------------------------------------
# _strip_or_empty
# ---------------------------------------------------------------------------

class TestStripOrEmpty:
    def test_none_returns_empty_string(self):
        assert _strip_or_empty(None) == ""

    def test_empty_string_returns_empty(self):
        assert _strip_or_empty("") == ""

    def test_whitespace_only_returns_empty(self):
        assert _strip_or_empty("   ") == ""

    def test_strips_surrounding_whitespace(self):
        assert _strip_or_empty("  hello  ") == "hello"

    def test_inner_spaces_preserved(self):
        assert _strip_or_empty("  hello world  ") == "hello world"

    def test_already_clean_string(self):
        assert _strip_or_empty("clean") == "clean"


# ---------------------------------------------------------------------------
# _int_or_none
# ---------------------------------------------------------------------------

class TestIntOrNone:
    def test_none_returns_none(self):
        assert _int_or_none(None) is None

    def test_empty_string_returns_none(self):
        assert _int_or_none("") is None

    def test_whitespace_only_returns_none(self):
        assert _int_or_none("   ") is None

    def test_valid_integer_string(self):
        assert _int_or_none("42") == 42

    def test_negative_integer_string(self):
        assert _int_or_none("-7") == -7

    def test_zero_string(self):
        assert _int_or_none("0") == 0

    def test_whitespace_padded_integer(self):
        assert _int_or_none("  100  ") == 100

    def test_float_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _int_or_none("3.14")
        assert exc_info.value.status_code == 400

    def test_alpha_string_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _int_or_none("abc")
        assert exc_info.value.status_code == 400

    def test_detail_contains_bad_value(self):
        with pytest.raises(HTTPException) as exc_info:
            _int_or_none("bad")
        assert "bad" in exc_info.value.detail
