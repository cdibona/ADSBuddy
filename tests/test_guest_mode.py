"""Guest (no-account) read-only access + airspace stats."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock


def test_guest_user_flags():
    from app.deps import _guest_user
    g = _guest_user()
    assert g.is_guest is True and g.is_admin is False and g.is_active is True
    assert g.username == "guest"


def test_real_user_is_not_guest():
    from app.models import User
    u = User(username="alice", is_admin=False, is_active=True)
    assert u.is_guest is False  # class attribute default


def test_current_viewer_returns_guest_when_enabled(monkeypatch):
    from app import deps
    # No session cookie; guest access on -> a guest viewer.
    async def no_user(request, session): return None
    monkeypatch.setattr(deps, "current_user_optional", no_user)
    async def enabled(session): return True
    monkeypatch.setattr(deps, "guest_access_enabled", enabled)
    req = types.SimpleNamespace(cookies={}, state=types.SimpleNamespace())
    viewer = asyncio.run(deps.current_viewer(req, session=None))
    assert viewer is not None and viewer.is_guest is True


def test_current_viewer_none_when_disabled(monkeypatch):
    from app import deps
    async def no_user(request, session): return None
    monkeypatch.setattr(deps, "current_user_optional", no_user)
    async def disabled(session): return False
    monkeypatch.setattr(deps, "guest_access_enabled", disabled)
    req = types.SimpleNamespace(cookies={}, state=types.SimpleNamespace())
    assert asyncio.run(deps.current_viewer(req, session=None)) is None


def test_guest_setting_is_auth_category():
    from app.settings_store import setting_category, DEFAULT_SETTINGS
    assert "guest_access_enabled" in {s.key for s in DEFAULT_SETTINGS}
    assert setting_category("guest_access_enabled") == "auth"


def test_stats_route_registered():
    from app.routes_pages import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/stats" in paths


def test_nav_hides_triggers_for_guest():
    import app.routes_pages as rp
    from app.deps import _guest_user
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/stats"))
    stats = {"count": 5, "window_minutes": 15, "generated_at": __import__("datetime").datetime(2026,6,26,tzinfo=__import__("datetime").timezone.utc),
             "breakdown": {k: 0 for k in ["helicopter","seaplane","light","private_jet","cargo","airliner","other"]}}
    out = rp.templates.env.get_template("stats.html").render(request=req, user=_guest_user(), stats=stats, window="15m")
    assert "/triggers" not in out      # guest nav has no Triggers link
    assert ">Sign in<" in out          # guest gets a Sign in link
    assert "Viewing as guest" in out   # banner
    assert "/stats" in out             # Stats link present


def test_radio_url_env_is_read(monkeypatch):
    monkeypatch.setenv("ADSBUDDY_RADIO_URL", "http://adsb.local:8080")
    monkeypatch.setenv("POSTGRES_USER", "x"); monkeypatch.setenv("POSTGRES_PASSWORD", "x")
    monkeypatch.setenv("POSTGRES_DB", "x"); monkeypatch.setenv("ADSBUDDY_SECRET_KEY", "x")
    monkeypatch.setenv("ADSBUDDY_ADMIN_USERNAME", "x"); monkeypatch.setenv("ADSBUDDY_ADMIN_PASSWORD", "x")
    from app.config import Settings
    assert Settings().radio_url == "http://adsb.local:8080"
