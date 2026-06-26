"""Tailscale Serve identity-header sign-in."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def test_peer_trusted_fail_closed():
    from app.tailscale_auth import peer_trusted
    # Blank allowlist -> never trusted (fail closed).
    assert peer_trusted("172.17.0.1", "") is False
    assert peer_trusted(None, "172.17.0.1/32") is False
    # In range / out of range.
    assert peer_trusted("172.17.0.1", "172.17.0.0/16") is True
    assert peer_trusted("172.17.0.1", "172.17.0.1/32") is True
    assert peer_trusted("10.0.0.5", "172.17.0.0/16,127.0.0.1/32") is False
    assert peer_trusted("127.0.0.1", "172.17.0.0/16,127.0.0.1/32") is True
    # Garbage host / cidr.
    assert peer_trusted("not-an-ip", "172.17.0.0/16") is False


def _req(headers=None, client_host="172.17.0.1"):
    return types.SimpleNamespace(
        headers=headers or {},
        client=types.SimpleNamespace(host=client_host),
        query_params={},
        url=types.SimpleNamespace(path="/login"),
    )


def _patch(monkeypatch, values):
    from app import tailscale_auth
    async def fake_get(db, key):
        return values.get(key, "")
    monkeypatch.setattr(tailscale_auth, "get_setting", fake_get)


def test_identity_requires_enabled_trusted_and_header(monkeypatch):
    from app import tailscale_auth as ts
    base = {"tailscale_auth_enabled": "true", "tailscale_trusted_proxies": "172.17.0.0/16"}
    hdr = {"tailscale-user-login": "chris@example.com", "tailscale-user-name": "Chris D"}

    # Happy path.
    _patch(monkeypatch, base)
    out = asyncio.run(ts.tailscale_identity(_req(hdr), None))
    assert out == ("chris@example.com", "Chris D")

    # Disabled -> None.
    _patch(monkeypatch, {**base, "tailscale_auth_enabled": "false"})
    assert asyncio.run(ts.tailscale_identity(_req(hdr), None)) is None

    # Untrusted peer -> None (header present but spoofable source).
    _patch(monkeypatch, base)
    assert asyncio.run(ts.tailscale_identity(_req(hdr, client_host="10.9.9.9"), None)) is None

    # No header -> None.
    assert asyncio.run(ts.tailscale_identity(_req({}), None)) is None


def test_route_registered():
    from app.routes_tailscale import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/auth/tailscale/login" in paths


def test_login_page_shows_tailscale_button():
    from app.routes_auth import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/login"))
    out = templates.env.get_template("login.html").render(
        request=req, error=None, oauth_providers=[], local_login=True,
        ts_login="chris@example.com")
    assert "/auth/tailscale/login" in out
    assert "Continue as chris@example.com (Tailscale)" in out


def test_tailscale_settings_are_auth_category():
    from app.settings_store import setting_category, DEFAULT_SETTINGS
    keys = {s.key for s in DEFAULT_SETTINGS}
    assert {"tailscale_auth_enabled", "tailscale_trusted_proxies"} <= keys
    assert setting_category("tailscale_auth_enabled") == "auth"
    assert setting_category("tailscale_trusted_proxies") == "auth"
