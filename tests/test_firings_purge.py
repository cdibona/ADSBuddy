"""Tests for purging firings from paused triggers (admin-only)."""
from __future__ import annotations

import types
from datetime import datetime, timezone


def test_purge_route_is_admin_only_and_registered():
    from app.routes_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/admin/system/purge-paused-firings" in paths


def test_firings_page_has_no_purge_button():
    """The purge moved to admin; the user-facing firings list must not offer it."""
    from app.routes_triggers import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/firings"), query_params={})
    out = templates.env.get_template("firings.html").render(
        request=req, user=types.SimpleNamespace(username="a", is_admin=False),
        rows=[], delivery_status={}, total=0, page=1, per_page=50, total_pages=1,
        start=0, end=0, since="all", loaded_at=datetime(2026, 6, 24, tzinfo=timezone.utc),
        flash=None)
    assert "purge-paused" not in out


def _render_system(**ctx):
    from app.routes_admin import templates
    from app.models import Setting
    base = dict(
        request=types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/system"),
                                      query_params={}),
        user=types.SimpleNamespace(username="admin", is_admin=True),
        now=datetime(2026, 6, 24, tzinfo=timezone.utc), git_sha="x", commit_url=None,
        started_at=datetime(2026, 6, 24, tzinfo=timezone.utc), uptime="1h", db_revision="0015",
        counts={k: 0 for k in ["aircraft", "sightings", "firings", "triggers", "users",
                               "channels", "deliveries", "routes"]},
        last_sighting=None, last_firing=None, paused_firings=0,
        settings=[Setting(key="sighting_min_interval_seconds", value="180", description="d", secret=False)],
    )
    base.update(ctx)
    return templates.env.get_template("admin_system.html").render(**base)


def test_admin_system_shows_purge_when_paused_firings_exist():
    out = _render_system(paused_firings=60410)
    assert "Purge 60,410 firings from paused triggers" in out
    assert 'action="/admin/system/purge-paused-firings"' in out


def test_admin_system_hides_purge_when_none():
    out = _render_system(paused_firings=0)
    assert "nothing to purge" in out.lower()


def test_admin_system_purge_confirmation_flash():
    out = _render_system(request=types.SimpleNamespace(
        url=types.SimpleNamespace(path="/admin/system"),
        query_params={"firings_purged": "60410"}))
    assert "Purged 60,410 firing(s)" in out
