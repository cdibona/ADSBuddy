"""Part 1: only offer channel kinds whose transport is configured."""
from __future__ import annotations

import asyncio
import types


def _patch_settings(monkeypatch, values):
    from app import notifications
    async def fake_get(session, key):
        return values.get(key, "")
    monkeypatch.setattr(notifications, "get_setting", fake_get)


def test_only_webhooks_when_nothing_configured(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {})
    assert asyncio.run(notifications.available_channel_kinds(None)) == ["discord", "webhook"]


def test_email_appears_with_smtp(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {"smtp_host": "smtp.example.com"})
    kinds = asyncio.run(notifications.available_channel_kinds(None))
    assert "email" in kinds and "sms_twilio" not in kinds


def test_sms_needs_all_three_twilio_values(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {"twilio_account_sid": "AC", "twilio_auth_token": "tok"})
    assert "sms_twilio" not in asyncio.run(notifications.available_channel_kinds(None))
    _patch_settings(monkeypatch, {"twilio_account_sid": "AC", "twilio_auth_token": "tok",
                                  "twilio_from_number": "+15551234567"})
    assert "sms_twilio" in asyncio.run(notifications.available_channel_kinds(None))


def test_admin_notifications_groups_render():
    from app.routes_admin import templates
    from app.models import Setting
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/notifications"))
    def s(k): return Setting(key=k, value="", description="d", secret=False)
    out = templates.env.get_template("admin_notifications.html").render(
        request=req, user=types.SimpleNamespace(username="a", is_admin=True),
        master_settings=[s("notifications_enabled")],
        smtp_settings=[s("smtp_host")], twilio_settings=[s("twilio_account_sid")],
        smtp_ok=True, twilio_ok=False)
    assert "SMTP (email)" in out and "Twilio (SMS)" in out
    assert "configured" in out and "not set up" in out


def test_vestaboard_and_trmnl_gated(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {})
    kinds = asyncio.run(notifications.available_channel_kinds(None))
    assert "vestaboard" not in kinds and "trmnl" not in kinds
    _patch_settings(monkeypatch, {"vestaboard_api_key": "key", "trmnl_webhook_url": "https://x"})
    kinds = asyncio.run(notifications.available_channel_kinds(None))
    assert "vestaboard" in kinds and "trmnl" in kinds


def test_compact_text_truncates():
    import types
    from app import notifications
    trig = types.SimpleNamespace(name="X" * 200)
    firing = types.SimpleNamespace(registration="N1", icao_hex="a", callsign="UAL1",
                                   type_code="B738", altitude_baro=35000)
    out = notifications._compact_text(trig, firing)
    assert len(out) <= 132


def test_transport_test_route_registered():
    from app.routes_admin import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/admin/notifications/test/{kind}" in paths


def test_send_transport_test_ok_and_unconfigured(monkeypatch):
    from app import notifications
    from unittest.mock import AsyncMock

    # configured -> _send_vestaboard succeeds -> (True, ...)
    monkeypatch.setattr(notifications, "_send_vestaboard", AsyncMock(return_value=None))
    ok, msg = asyncio.run(notifications.send_transport_test(None, None, "vestaboard"))
    assert ok and "sent" in msg.lower()

    # not configured -> ChannelNotConfigured -> (False, reason)
    async def raiser(*a, **k):
        raise notifications.ChannelNotConfigured("TRMNL not configured (trmnl_webhook_url is empty).")
    monkeypatch.setattr(notifications, "_send_trmnl", raiser)
    ok, msg = asyncio.run(notifications.send_transport_test(None, None, "trmnl"))
    assert not ok and "not configured" in msg


def test_admin_notifications_has_test_buttons():
    import types
    from app.routes_admin import templates
    from app.models import Setting
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/notifications"))
    def s(k): return Setting(key=k, value="", description="d", secret=False)
    out = templates.env.get_template("admin_notifications.html").render(
        request=req, user=types.SimpleNamespace(username="a", is_admin=True),
        master_settings=[s("notifications_enabled")], smtp_settings=[], twilio_settings=[],
        vestaboard_settings=[s("vestaboard_api_key")], trmnl_settings=[s("trmnl_webhook_url")],
        smtp_ok=False, twilio_ok=False, vestaboard_ok=True, trmnl_ok=False)
    assert 'action="/admin/notifications/test/vestaboard"' in out
    assert 'action="/admin/notifications/test/trmnl"' in out


def test_trmnl_missing_uuid_is_caught(monkeypatch):
    import types
    from unittest.mock import AsyncMock
    from app import notifications

    async def fake_get(session, key):
        return "https://trmnl.com/api/custom_plugins/" if key == "trmnl_webhook_url" else ""
    monkeypatch.setattr(notifications, "get_setting", fake_get)
    client = AsyncMock()
    trig = types.SimpleNamespace(name="t")
    import pytest
    with pytest.raises(notifications.ChannelNotConfigured):
        asyncio.run(notifications._send_trmnl(None, client, None, trig, None))
    client.post.assert_not_called()  # never even attempted the bad URL
