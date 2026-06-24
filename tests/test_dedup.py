"""Tests for sighting de-dup (Phase C)."""
from __future__ import annotations

import types


class TestParseMinInterval:
    def test_values(self):
        from app.ingest import _parse_min_interval
        assert _parse_min_interval("180") == 180
        assert _parse_min_interval("0") == 0
        assert _parse_min_interval("") == 0       # blank = store all
        assert _parse_min_interval(None) == 0
        assert _parse_min_interval("-5") == 0     # clamp
        assert _parse_min_interval("junk") == 0


def test_min_interval_setting_is_system():
    from app.settings_store import setting_category, DEFAULT_SETTINGS
    keys = {s.key for s in DEFAULT_SETTINGS}
    assert "sighting_min_interval_seconds" in keys
    assert setting_category("sighting_min_interval_seconds") == "system"


class TestSystemStorageCard:
    def _render(self, query):
        from datetime import datetime, timezone
        from app.routes_admin import templates
        from app.models import Setting
        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/system"), query_params=query)
        return templates.env.get_template("admin_system.html").render(
            request=req, user=types.SimpleNamespace(username="a", is_admin=True),
            now=datetime(2026, 6, 24, tzinfo=timezone.utc), git_sha="x", commit_url=None,
            started_at=datetime(2026, 6, 24, tzinfo=timezone.utc), uptime="1h", db_revision="0013",
            counts={k: 0 for k in ["aircraft", "sightings", "firings", "triggers", "users", "channels", "deliveries", "routes"]},
            last_sighting=None, last_firing=None,
            settings=[Setting(key="sighting_min_interval_seconds", value="180", description="d", secret=False)])

    def test_estimate_button_present(self):
        out = self._render({})
        assert "Estimate downsample" in out
        assert 'action="/admin/system/downsample"' in out

    def test_estimate_result_and_run_button(self):
        out = self._render({"est_total": "1000000", "est_del": "900000", "iv": "180"})
        assert "Would delete" in out and "900,000" in out
        assert "Run downsample now" in out

    def test_downsampled_confirmation(self):
        out = self._render({"downsampled": "12345"})
        assert "deleted 12,345 rows" in out
