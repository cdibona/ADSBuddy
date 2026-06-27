"""Update-available badge: semver compare of running vs latest release."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def _set(monkeypatch, current, latest):
    from app import version
    monkeypatch.setattr(version, "VERSION", current)
    version.set_latest_release(latest)


def test_update_available_basic(monkeypatch):
    from app import version
    _set(monkeypatch, "1.2.0", "v1.3.0")
    assert version.update_available() == "v1.3.0"
    _set(monkeypatch, "1.2.0", "v1.2.0")
    assert version.update_available() is None          # same
    _set(monkeypatch, "1.2.5", "v1.2.4")
    assert version.update_available() is None          # running ahead
    _set(monkeypatch, "1.2.0", "v1.2.1")
    assert version.update_available() == "v1.2.1"


def test_dev_build_never_shows_badge(monkeypatch):
    from app import version
    _set(monkeypatch, "dev", "v9.9.9")
    assert version.update_available() is None          # source build, no version
    _set(monkeypatch, "1.2.0", "")
    assert version.update_available() is None          # latest unknown


def test_semver_parsing():
    from app.version import _semver
    assert _semver("v1.2.3") == (1, 2, 3)
    assert _semver("1.2") == (1, 2)
    assert _semver("dev") is None
    assert _semver("1.2.x") is None


def test_refresh_handles_errors_silently(monkeypatch):
    from app import version
    monkeypatch.setattr(version, "VERSION", "1.0.0")
    version.set_latest_release(None)
    # 200 with a tag -> cached
    client = AsyncMock()
    client.get = AsyncMock(return_value=types.SimpleNamespace(status_code=200, json=lambda: {"tag_name": "v1.5.0"}))
    asyncio.run(version.refresh_latest_release(client))
    assert version.update_available() == "v1.5.0"
    # network error -> no crash, keeps previous
    client.get = AsyncMock(side_effect=RuntimeError("offline"))
    asyncio.run(version.refresh_latest_release(client))
    assert version.update_available() == "v1.5.0"


def test_register_exposes_update_globals():
    from app.routes_pages import templates
    g = templates.env.globals
    assert "app_update_available" in g and "app_version" in g and "app_releases_url" in g
