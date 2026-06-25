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
