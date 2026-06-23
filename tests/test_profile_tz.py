"""Tests for per-user timezone formatting, profile settings, and nav dropdown."""
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest


class TestTimeFmt:
    def test_format_dt_converts_to_zone(self):
        from app import timefmt

        dt = datetime(2026, 6, 23, 19, 0, 0, tzinfo=timezone.utc)  # summer -> PDT (-7)
        out = timefmt.format_dt(dt, "America/Los_Angeles", "%Y-%m-%d %H:%M %Z")
        assert out == "2026-06-23 12:00 PDT"

    def test_format_dt_utc_default(self):
        from app import timefmt

        dt = datetime(2026, 1, 1, 5, 30, tzinfo=timezone.utc)
        assert timefmt.format_dt(dt, "UTC", "%H:%M %Z") == "05:30 UTC"

    def test_format_dt_naive_assumed_utc(self):
        from app import timefmt

        dt = datetime(2026, 6, 23, 19, 0, 0)  # naive
        assert timefmt.format_dt(dt, "America/Los_Angeles", "%H:%M") == "12:00"

    def test_format_dt_none(self):
        from app import timefmt

        assert timefmt.format_dt(None, "UTC") == ""

    def test_invalid_tz_falls_back_to_utc(self):
        from app import timefmt

        dt = datetime(2026, 6, 23, 19, 0, tzinfo=timezone.utc)
        assert timefmt.format_dt(dt, "Not/AZone", "%H:%M") == "19:00"

    def test_is_valid_tz(self):
        from app import timefmt

        assert timefmt.is_valid_tz("America/New_York")
        assert timefmt.is_valid_tz("UTC")
        assert not timefmt.is_valid_tz("Mars/Olympus")
        assert not timefmt.is_valid_tz("")
        assert not timefmt.is_valid_tz(None)


class TestLocaldtFilter:
    def test_filter_uses_request_state_tz(self):
        from app.routes_pages import templates

        # request.state.user_tz drives the conversion.
        state = types.SimpleNamespace(user_tz="America/Los_Angeles")
        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/"), state=state)
        tpl = templates.env.from_string("{{ dt | localdt('%H:%M %Z') }}")
        out = tpl.render(request=req, dt=datetime(2026, 6, 23, 19, 0, tzinfo=timezone.utc))
        assert out == "12:00 PDT"

    def test_filter_defaults_utc_without_state(self):
        from app.routes_pages import templates

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/"))
        tpl = templates.env.from_string("{{ dt | localdt('%H:%M %Z') }}")
        out = tpl.render(request=req, dt=datetime(2026, 6, 23, 19, 0, tzinfo=timezone.utc))
        assert out == "19:00 UTC"


class TestNavAndProfile:
    def _req(self, path="/profile"):
        return types.SimpleNamespace(url=types.SimpleNamespace(path=path))

    def test_nav_dropdown_admin(self):
        from app.routes_profile import templates

        user = types.SimpleNamespace(username="cdibona", is_admin=True,
                                     email="me@x.com", timezone="UTC")
        out = templates.env.get_template("profile.html").render(
            request=self._req(), user=user, channels=[], kinds=[], kind_label={},
            last_by_channel={},
        )
        # Dropdown: username, Profile, Admin (admin), Logout.
        assert "cdibona" in out
        assert 'href="/profile"' in out
        assert 'href="/admin"' in out
        assert "Logout" in out
        # Settings form present with tz options.
        assert 'action="/profile/settings"' in out
        assert "America/Los_Angeles" in out

    def test_nav_dropdown_non_admin_hides_admin(self):
        from app.routes_profile import templates

        user = types.SimpleNamespace(username="alice", is_admin=False,
                                     email=None, timezone="UTC")
        out = templates.env.get_template("profile.html").render(
            request=self._req(), user=user, channels=[], kinds=[], kind_label={},
            last_by_channel={},
        )
        assert "alice" in out
        assert 'href="/admin"' not in out
        assert "Logout" in out
