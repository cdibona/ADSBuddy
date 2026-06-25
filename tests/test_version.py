"""Tests for the footer version/uptime helpers."""
from __future__ import annotations

from datetime import timedelta

import pytest


class TestUptimeStr:
    def test_minutes_only(self):
        from app import version

        now = version.STARTED_AT + timedelta(minutes=7)
        assert version.uptime_str(now) == "7m"

    def test_zero_shows_0m(self):
        from app import version

        assert version.uptime_str(version.STARTED_AT) == "0m"

    def test_negative_clamps_to_zero(self):
        from app import version

        assert version.uptime_str(version.STARTED_AT - timedelta(minutes=5)) == "0m"

    def test_hours_and_minutes(self):
        from app import version

        now = version.STARTED_AT + timedelta(hours=3, minutes=12)
        assert version.uptime_str(now) == "3h 12m"

    def test_days_hours_minutes(self):
        from app import version

        now = version.STARTED_AT + timedelta(days=2, hours=3, minutes=7)
        assert version.uptime_str(now) == "2d 3h 7m"

    def test_whole_hour_omits_minutes_when_present(self):
        from app import version

        # Exactly 2h0m: days omitted, hours shown, minutes 0 -> not appended
        now = version.STARTED_AT + timedelta(hours=2)
        assert version.uptime_str(now) == "2h"


class TestCommitUrl:
    def test_placeholder_sha_has_no_url(self, monkeypatch):
        from app import version

        monkeypatch.setattr(version, "GIT_SHA", "dev")
        assert version.github_commit_url() is None

    def test_real_sha_links_to_github(self, monkeypatch):
        from app import version

        monkeypatch.setattr(version, "GIT_SHA", "abc1234")
        assert version.github_commit_url() == (
            "https://github.com/cdibona/ADSBuddy/commit/abc1234"
        )


class TestFooterRendering:
    def test_base_extending_template_renders_footer(self):
        """A page extending base.html exposes the footer globals (no UndefinedError)."""
        import types

        from app.routes_pages import templates

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/aircraft"))
        out = templates.env.get_template("aircraft.html").render(
            request=req,
            user=types.SimpleNamespace(username="admin", is_admin=True),
            aircraft=[],
            type_active=None,
        common_types=["B738", "PC12"],
        )
        assert 'class="site-footer"' in out
        assert "uptime" in out
        assert "version" in out
