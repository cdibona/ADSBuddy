"""Tests for OAuth account-linking + provider config (Phase E)."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, MagicMock


def _result(value):
    r = MagicMock()
    r.scalar_one_or_none.return_value = value
    return r


def _session(execute_returns):
    s = AsyncMock()
    s.execute = AsyncMock(side_effect=execute_returns)
    s.add = MagicMock()
    s.commit = AsyncMock()
    s.flush = AsyncMock()
    return s


class TestResolveUser:
    def test_existing_identity_logs_in(self):
        from app import oauth
        from app.models import User, UserIdentity
        ident = UserIdentity(id=1, user_id=5, provider="google", subject="abc")
        user = User(id=5, username="cdibona", is_admin=True, is_active=True, password_hash="x")
        s = _session([_result(ident), _result(user)])
        out = asyncio.run(oauth.resolve_user(s, "google", "abc", "x@y.com", False))
        assert out is user

    def test_links_by_email(self):
        from app import oauth
        from app.models import User
        user = User(id=5, username="cdibona", is_admin=True, is_active=True,
                    password_hash="x", email="me@x.com")
        s = _session([_result(None), _result(user)])  # no identity, email matches
        out = asyncio.run(oauth.resolve_user(s, "github", "99", "ME@x.com", False))
        assert out is user
        s.add.assert_called_once()   # a UserIdentity link row was added
        s.commit.assert_awaited()

    def test_unknown_without_auto_provision_returns_none(self):
        from app import oauth
        s = _session([_result(None), _result(None)])  # no identity, no matching email
        out = asyncio.run(oauth.resolve_user(s, "google", "zzz", "new@x.com", False))
        assert out is None
        s.add.assert_not_called()

    def test_inactive_user_blocked(self):
        from app import oauth
        from app.models import User, UserIdentity
        ident = UserIdentity(id=1, user_id=5, provider="google", subject="abc")
        user = User(id=5, username="x", is_admin=False, is_active=False, password_hash="x")
        s = _session([_result(ident), _result(user)])
        assert asyncio.run(oauth.resolve_user(s, "google", "abc", None, False)) is None


class TestProviderConfig:
    def test_configured_providers(self, monkeypatch):
        from app import oauth
        async def fake_get(db, key):
            vals = {"oauth_google_client_id": "gid", "oauth_google_client_secret": "gsec",
                    "oauth_github_client_id": "", "oauth_github_client_secret": ""}
            return vals.get(key, "")
        monkeypatch.setattr(oauth, "get_setting", fake_get)
        out = asyncio.run(oauth.configured_providers(None))
        assert out == ["google"]   # github not configured


def test_login_renders_oauth_buttons():
    from app.routes_auth import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/login"))
    out = templates.env.get_template("login.html").render(
        request=req, error=None, oauth_providers=["google", "github"])
    assert "/auth/oauth/google/login" in out
    assert "Sign in with Github" in out


def test_oauth_routes_registered():
    from app.routes_oauth import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/auth/oauth/{provider}/login" in paths
    assert "/auth/oauth/{provider}/callback" in paths


def test_auth_settings_categorized():
    from app.settings_store import setting_category
    assert setting_category("oauth_google_client_id") == "auth"
    assert setting_category("oauth_auto_provision") == "auth"
