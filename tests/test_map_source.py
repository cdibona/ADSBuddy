"""Pinning which source's tar1090 map the Map page embeds."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def _src(url):
    return types.SimpleNamespace(url=url, kind="poll")


def test_pinned_source_wins(monkeypatch):
    from app import routes_pages, settings_store
    async def fake_get(s, k):
        return {"map_source_id": "5", "radio_base_url": "http://legacy:8080"}.get(k, "")
    monkeypatch.setattr(settings_store, "get", fake_get)
    db = AsyncMock()
    db.get = AsyncMock(return_value=_src("http://pinned:8080/"))
    assert asyncio.run(routes_pages._map_radio_url(db)) == "http://pinned:8080"


def test_falls_back_to_radio_base_url(monkeypatch):
    from app import routes_pages, settings_store
    async def fake_get(s, k):
        return {"map_source_id": "", "radio_base_url": "http://legacy:8080/"}.get(k, "")
    monkeypatch.setattr(settings_store, "get", fake_get)
    db = AsyncMock()
    assert asyncio.run(routes_pages._map_radio_url(db)) == "http://legacy:8080"


def test_pin_toggle_route_registered():
    from app.routes_admin import router
    assert "/admin/sources/{source_id}/pin-map" in {r.path for r in router.routes if hasattr(r, "path")}


def test_map_source_id_hidden_from_tabs():
    from app.settings_store import setting_category
    assert setting_category("map_source_id") == "internal"
