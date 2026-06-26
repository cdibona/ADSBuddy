"""Admin toggle to disable username/password login once OAuth is configured."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def _patch(monkeypatch, values):
    from app import oauth, tailscale_auth
    async def fake_get(db, key):
        return values.get(key, "")
    monkeypatch.setattr(oauth, "get_setting", fake_get)
    monkeypatch.setattr(tailscale_auth, "get_setting", fake_get)


def test_local_login_on_by_default(monkeypatch):
    from app import oauth
    _patch(monkeypatch, {})  # nothing set -> default true
    assert asyncio.run(oauth.local_login_allowed(None)) is True


def test_disable_takes_effect_only_when_oauth_configured(monkeypatch):
    from app import oauth
    # Disabled but NO provider configured -> fail-safe keeps local login ON.
    _patch(monkeypatch, {"local_login_enabled": "false"})
    assert asyncio.run(oauth.local_login_allowed(None)) is True

    # Disabled AND a provider configured (site_base_url + google creds) -> OFF.
    _patch(monkeypatch, {
        "local_login_enabled": "false",
        "site_base_url": "https://h:8443",
        "oauth_google_client_id": "gid", "oauth_google_client_secret": "gsec",
    })
    assert asyncio.run(oauth.local_login_allowed(None)) is False


def test_login_post_rejected_when_disabled(monkeypatch):
    from app import routes_auth
    monkeypatch.setattr(routes_auth, "_OAUTH_ERRORS", routes_auth._OAUTH_ERRORS)
    import app.oauth as oauth
    monkeypatch.setattr(oauth, "local_login_allowed", AsyncMock(return_value=False))
    monkeypatch.setattr(oauth, "configured_providers", AsyncMock(return_value=["google"]))
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/login"), query_params={})
    resp = asyncio.run(routes_auth.login_submit(req, "admin", "pw", db=None))
    assert resp.status_code == 403


def test_login_page_hides_form_when_disabled():
    from app.routes_auth import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/login"))
    out = templates.env.get_template("login.html").render(
        request=req, error=None, oauth_providers=["google"], local_login=False)
    assert 'name="password"' not in out      # form hidden
    assert "/auth/oauth/google/login" in out  # SSO offered
    assert ">or<" not in out                  # no separator when only SSO


def test_login_page_shows_form_when_enabled():
    from app.routes_auth import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/login"))
    out = templates.env.get_template("login.html").render(
        request=req, error=None, oauth_providers=["google"], local_login=True)
    assert 'name="password"' in out
    assert "or" in out  # separator present when both


def test_local_login_setting_is_auth_category():
    from app.settings_store import setting_category, DEFAULT_SETTINGS
    assert "local_login_enabled" in {s.key for s in DEFAULT_SETTINGS}
    assert setting_category("local_login_enabled") == "auth"
