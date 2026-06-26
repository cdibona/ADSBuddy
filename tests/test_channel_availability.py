"""Part 1: only offer channel kinds whose transport is configured."""
from __future__ import annotations

import asyncio
import types


def _patch_settings(monkeypatch, values):
    from app import notifications
    async def fake_get(session, key):
        return values.get(key, "")
    monkeypatch.setattr(notifications, "get_setting", fake_get)


def test_self_configured_kinds_always_available(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {})
    # Discord, webhook, Vestaboard, TRMNL carry their own per-channel config.
    assert asyncio.run(notifications.available_channel_kinds(None)) == [
        "discord", "webhook", "vestaboard", "trmnl"]


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


def test_vestaboard_and_trmnl_always_available(monkeypatch):
    from app import notifications
    _patch_settings(monkeypatch, {})  # per-user config, no admin gating
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


def test_trmnl_vestaboard_config_built_per_channel():
    from app.routes_profile import _build_config
    assert _build_config("trmnl", {"webhook_url": " https://trmnl.com/api/custom_plugins/x "}) == \
        {"webhook_url": "https://trmnl.com/api/custom_plugins/x"}
    assert _build_config("vestaboard", {"api_key": " key123 "}) == {"api_key": "key123"}


def test_trmnl_missing_uuid_is_caught():
    import types
    from unittest.mock import AsyncMock
    from app import notifications

    # Per-channel webhook URL missing the UUID -> ChannelNotConfigured, no POST.
    channel = types.SimpleNamespace(config={"webhook_url": "https://trmnl.com/api/custom_plugins/"})
    client = AsyncMock()
    trig = types.SimpleNamespace(name="t")
    import pytest
    with pytest.raises(notifications.ChannelNotConfigured):
        asyncio.run(notifications._send_trmnl(None, client, channel, trig, None))
    client.post.assert_not_called()


def test_trmnl_missing_webhook_is_caught():
    import types
    from unittest.mock import AsyncMock
    from app import notifications
    channel = types.SimpleNamespace(config={})  # no webhook_url
    import pytest
    with pytest.raises(notifications.ChannelNotConfigured):
        asyncio.run(notifications._send_trmnl(None, AsyncMock(), channel, types.SimpleNamespace(name="t"), None))


def test_sample_firing_is_realistic():
    from app import notifications
    f = notifications._sample_firing()
    assert f.registration == "N628TS" and f.type_code == "GLF6" and f.altitude_baro == 38000
    text = notifications._compact_text(notifications._sample_trigger(), f)
    assert "N628TS" in text and "GLF6" in text  # test renders like a real firing


def test_latest_firing_falls_back_to_sample():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock
    from app import notifications
    # No firings -> .first() is None -> synthetic sample.
    res = MagicMock(); res.first.return_value = None
    session = AsyncMock(); session.execute = AsyncMock(return_value=res)
    trigger, firing = asyncio.run(notifications.latest_firing_and_trigger(session))
    assert trigger.name == "ADSBuddy test" and firing.registration == "N628TS"
