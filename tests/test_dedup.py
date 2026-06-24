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


class TestProcessEntriesDedup:
    def _run(self, monkeypatch, recent_map):
        """Drive process_entries with one positioned entry; return # sightings added."""
        import asyncio
        import types as _t
        from datetime import datetime, timezone
        from app import ingest

        added = []

        class FakeSession:
            def add(self, obj):
                added.append(obj)

        async def fake_upsert(session, entry):
            return _t.SimpleNamespace(registration=None, type_code=None, owner_op=None, year=None)

        async def fake_recent(session, source_name, hexes):
            return dict(recent_map)

        monkeypatch.setattr(ingest, "_upsert_aircraft", fake_upsert)
        monkeypatch.setattr(ingest, "_recent_sighting_times", fake_recent)
        entry = {"hex": "abc123", "lat": 1.0, "lon": 2.0}
        asyncio.run(ingest.process_entries(
            FakeSession(), None, "S", [entry], [], False, False, 180))
        return len(added)

    def test_first_sighting_stored(self, monkeypatch):
        assert self._run(monkeypatch, {}) == 1

    def test_recent_sighting_skipped(self, monkeypatch):
        from datetime import datetime, timezone, timedelta
        recent = {"abc123": datetime.now(timezone.utc) - timedelta(seconds=10)}
        assert self._run(monkeypatch, recent) == 0

    def test_old_sighting_stored_again(self, monkeypatch):
        from datetime import datetime, timezone, timedelta
        old = {"abc123": datetime.now(timezone.utc) - timedelta(seconds=300)}
        assert self._run(monkeypatch, old) == 1

    def test_min_interval_zero_stores_all(self, monkeypatch):
        import asyncio
        import types as _t
        from app import ingest
        added = []
        class FakeSession:
            def add(self, obj): added.append(obj)
        async def fake_upsert(session, entry):
            return _t.SimpleNamespace(registration=None, type_code=None, owner_op=None, year=None)
        monkeypatch.setattr(ingest, "_upsert_aircraft", fake_upsert)
        entry = {"hex": "abc123", "lat": 1.0, "lon": 2.0}
        asyncio.run(ingest.process_entries(FakeSession(), None, "S", [entry, entry], [], False, False, 0))
        assert len(added) == 2  # no dedup when interval=0
