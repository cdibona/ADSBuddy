"""Part 3: admin-editable type-link registry."""
from __future__ import annotations

import asyncio
import types
from datetime import datetime, timezone


def test_normalize_code():
    from app.type_links import normalize_code
    assert normalize_code(" b738 ") == "B738"
    assert normalize_code(None) is None
    assert normalize_code("") is None


def test_admin_types_routes_registered():
    from app.routes_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/admin/types" in paths
    assert "/admin/types/sync" in paths
    assert "/admin/types/{code}/delete" in paths


def test_admin_types_page_renders():
    from app.routes_admin import templates
    from app.models import TypeLink
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/types"), query_params={})
    link = TypeLink(code="B738", description="BOEING 737-800",
                    url="https://en.wikipedia.org/wiki/Boeing_737_Next_Generation",
                    updated_at=datetime(2026, 6, 24, tzinfo=timezone.utc))
    out = templates.env.get_template("admin_types.html").render(
        request=req, user=types.SimpleNamespace(username="a", is_admin=True),
        links=[link], unsynced=3)
    assert "B738" in out
    assert "Sync from seen aircraft (3 new)" in out
    assert 'action="/admin/types"' in out


def test_aircraft_list_uses_type_link_override():
    from app.routes_pages import templates
    from app.models import Aircraft
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/aircraft"))
    ac = Aircraft(icao_hex="a1b2c3", registration="N1", type_code="B738",
                  description="BOEING 737-800", owner_op="x", year=2010,
                  last_seen=datetime(2026, 6, 24, tzinfo=timezone.utc))
    out = templates.env.get_template("aircraft.html").render(
        request=req, user=types.SimpleNamespace(username="a", is_admin=True),
        aircraft=[ac], type_active=None, common_types=[],
        type_links={"B738": "https://example.com/custom-737"})
    assert "https://example.com/custom-737" in out   # admin override wins
