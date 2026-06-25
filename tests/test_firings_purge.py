"""Tests for purging firings from paused triggers."""
from __future__ import annotations

import types


def test_purge_route_registered():
    from app.routes_triggers import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/firings/purge-paused" in paths


def _render(**ctx):
    from app.routes_triggers import templates
    base = dict(
        request=types.SimpleNamespace(url=types.SimpleNamespace(path="/firings"),
                                      query_params={}),
        user=types.SimpleNamespace(username="a", is_admin=True),
        rows=[], delivery_status={}, total=0, page=1, per_page=50, total_pages=1,
        start=0, end=0, since="all", loaded_at=None, flash=None,
        paused_firings_count=0,
    )
    base.update(ctx)
    return templates.env.get_template("firings.html").render(**base)


def test_purge_button_shown_when_paused_firings_exist():
    out = _render(paused_firings_count=60410)
    assert "Purge 60,410 firings from paused triggers" in out
    assert 'action="/firings/purge-paused"' in out


def test_purge_button_hidden_when_none():
    out = _render(paused_firings_count=0)
    assert "/firings/purge-paused" not in out
