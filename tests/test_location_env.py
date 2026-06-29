"""Station location oriented from env (adsb-im FEEDER_LAT/LONG style)."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def _cfg(lat="", lon="", alt=""):
    return types.SimpleNamespace(feeder_lat=lat, feeder_lon=lon, feeder_alt_m=alt)


def test_env_aliases_parse():
    from app.config import Settings
    base = dict(POSTGRES_USER="x", POSTGRES_PASSWORD="x", POSTGRES_DB="x",
                ADSBUDDY_SECRET_KEY="x", ADSBUDDY_ADMIN_USERNAME="x", ADSBUDDY_ADMIN_PASSWORD="x")
    assert Settings(**base, FEEDER_LAT="47.6", FEEDER_LONG="-122.3").feeder_lon == "-122.3"
    # ADSBUDDY_* aliases also work
    assert Settings(**base, ADSBUDDY_LAT="1.0", ADSBUDDY_LON="2.0").feeder_lat == "1.0"


def test_sync_applies_env_location(monkeypatch):
    from app import bootstrap
    store = {"receiver_lat": "0", "receiver_lon": "0"}
    monkeypatch.setattr(bootstrap, "get_settings", lambda: _cfg("47.62", "-122.35", "50"))
    async def fake_get(s, k): return store.get(k)
    async def fake_set(s, k, v): store[k] = v
    monkeypatch.setattr(bootstrap, "get_setting", fake_get)
    monkeypatch.setattr(bootstrap, "set_value", fake_set)
    sess = AsyncMock()
    asyncio.run(bootstrap.sync_location_from_env(sess))
    assert store["receiver_lat"] == "47.62" and store["receiver_lon"] == "-122.35"
    assert store["receiver_alt_m"] == "50"


def test_sync_noop_without_env(monkeypatch):
    from app import bootstrap
    store = {"receiver_lat": "10.0", "receiver_lon": "20.0"}
    monkeypatch.setattr(bootstrap, "get_settings", lambda: _cfg("", "", ""))
    async def fake_get(s, k): return store.get(k)
    async def fake_set(s, k, v): store[k] = v
    monkeypatch.setattr(bootstrap, "get_setting", fake_get)
    monkeypatch.setattr(bootstrap, "set_value", fake_set)
    asyncio.run(bootstrap.sync_location_from_env(AsyncMock()))
    assert store == {"receiver_lat": "10.0", "receiver_lon": "20.0"}  # untouched


def test_sources_test_route_registered():
    from app.routes_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/admin/sources/{source_id}/test" in paths
