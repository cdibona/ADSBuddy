"""Open (appliance) mode: no login, every request acts as the admin."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock


def _settings(**env):
    from app.config import Settings
    base = dict(POSTGRES_USER="x", POSTGRES_PASSWORD="x", POSTGRES_DB="x",
                ADSBUDDY_SECRET_KEY="x", ADSBUDDY_ADMIN_USERNAME="x", ADSBUDDY_ADMIN_PASSWORD="x")
    base.update(env)
    return Settings(**base)


def test_mode_parsing():
    assert _settings().open_mode is False                      # default MultiUser
    assert _settings(ADSBUDDY_MODE="open").open_mode is True
    assert _settings(ADSBUDDY_MODE="OPEN").open_mode is True
    assert _settings(ADSBUDDY_MODE="MultiUser").open_mode is False


def test_alias_accepts_literal_name(monkeypatch):
    # The user's literal "ADSBuddyMode" env var works too (the real path).
    from app.config import Settings
    for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB",
              "ADSBUDDY_SECRET_KEY", "ADSBUDDY_ADMIN_USERNAME", "ADSBUDDY_ADMIN_PASSWORD"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("ADSBuddyMode", "open")
    assert Settings().open_mode is True


def test_current_user_optional_returns_admin_in_open_mode(monkeypatch):
    from app import deps
    from app.models import User
    admin = User(username="admin", is_admin=True, is_active=True, timezone="UTC")

    res = MagicMock(); res.scalar_one_or_none.return_value = admin
    session = AsyncMock(); session.execute = AsyncMock(return_value=res)

    import app.config as cfg
    monkeypatch.setattr(cfg, "get_settings", lambda: _settings(ADSBUDDY_MODE="open"))
    req = types.SimpleNamespace(cookies={}, state=types.SimpleNamespace())
    out = asyncio.run(deps.current_user_optional(req, session))
    assert out is admin and out.is_admin is True   # no cookie, still admin
