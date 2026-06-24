"""Tests for multi-source ingest (admin Sources page + push route)."""
from __future__ import annotations

import types
from datetime import datetime, timezone


def test_admin_sources_renders_poll_and_push():
    from app.routes_admin import templates
    from app.models import RadioSource
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/sources"))
    poll = RadioSource(id=1, name="Local radio", kind="poll", url="http://r:8080",
                       is_active=True, receiver_lat=47.6, receiver_lon=-122.5,
                       created_at=datetime(2026, 6, 24, tzinfo=timezone.utc))
    push = RadioSource(id=2, name="Feeder", kind="push", token="secrettok",
                       is_active=True, created_at=datetime(2026, 6, 24, tzinfo=timezone.utc))
    out = templates.env.get_template("admin_sources.html").render(
        request=req, user=types.SimpleNamespace(username="admin", is_admin=True),
        sources=[poll, push], base_url="https://h:8443")
    assert "Local radio" in out and "http://r:8080" in out
    assert "https://h:8443/ingest/secrettok" in out   # push URL built from base_url
    assert "Sources" in out                            # subnav tab


def test_push_route_registered():
    from app.routes_ingest import router
    paths = [r.path for r in router.routes if hasattr(r, "path")]
    assert "/ingest/{token}" in paths


def test_admin_subnav_has_sources_tab():
    from app.routes_admin import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/sources"))
    out = templates.env.get_template("_admin_nav.html").render(request=req)
    assert 'href="/admin/sources"' in out


def test_strip_truncates_to_maxlen():
    from app.ingest import _strip
    assert _strip("ABCDEFGHIJ", 8) == "ABCDEFGH"
    assert _strip("  spaced  ", 4) == "spac"
    assert _strip(None, 8) is None
    assert _strip("", 8) is None
    assert _strip("ok") == "ok"  # no cap


def test_bearer_token_parsing():
    import types
    from app.routes_ingest import _bearer_token
    def req(h): return types.SimpleNamespace(headers={"authorization": h})
    assert _bearer_token(req("Bearer abc123")) == "abc123"
    assert _bearer_token(req("bearer xyz")) == "xyz"
    assert _bearer_token(req("Basic abc")) is None
    assert _bearer_token(types.SimpleNamespace(headers={})) is None
