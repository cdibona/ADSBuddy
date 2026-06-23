"""Tests for the admin diagnostics page and firings auto-refresh."""
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest


@pytest.fixture
def admin():
    return types.SimpleNamespace(username="cdibona", is_admin=True, id=3)


class TestDiagnosticsRendering:
    def test_renders_summary_failures_and_attempts(self, admin):
        from app.routes_admin import templates
        from app.models import (
            NotificationChannel, NotificationDelivery, TriggerFiring, Trigger, User,
        )

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/diagnostics"))
        ch = NotificationChannel(id=1, user_id=3, kind="discord", name="HaxorTest")
        owner = User(id=3, username="cdibona", is_admin=True, is_active=True, password_hash="x")
        firing = TriggerFiring(id=210132, trigger_id=11, icao_hex="a50b7b", registration="N424LF",
                               fired_at=datetime(2026, 6, 23, 17, 37, tzinfo=timezone.utc))
        trig = Trigger(id=11, owner_id=3, name="Lifeflight")
        ok = NotificationDelivery(id=419373, firing_id=210132, channel_id=1, status="sent",
                                  is_test=False, created_at=datetime(2026, 6, 23, 17, 37, tzinfo=timezone.utc))
        bad = NotificationDelivery(id=1, firing_id=210132, channel_id=1, status="failed",
                                   error="Name or service not known", is_test=False,
                                   created_at=datetime(2026, 6, 23, 17, 0, tzinfo=timezone.utc))

        out = templates.env.get_template("admin_diagnostics.html").render(
            request=req, user=admin, now=datetime(2026, 6, 23, 18, 0, tzinfo=timezone.utc),
            firings_24h=5, sent_24h=4, failed_24h=1, skipped_24h=3, tests_24h=2,
            fail_rows=[(bad, ch, owner, firing, trig)],
            skipped_rows=[],
            recent_rows=[(ok, ch, owner, firing, trig), (bad, ch, owner, firing, trig)],
        )
        assert "firings (24h)" in out and ">5<" in out
        assert "Name or service not known" in out      # failure error surfaced
        assert "Lifeflight" in out                       # trigger name
        assert "/aircraft/a50b7b" in out                 # aircraft link
        assert "N424LF" in out

    def test_handles_test_send_with_no_firing(self, admin):
        from app.routes_admin import templates
        from app.models import NotificationChannel, NotificationDelivery, User

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/diagnostics"))
        ch = NotificationChannel(id=1, user_id=3, kind="email", name="me")
        owner = User(id=3, username="cdibona", is_admin=True, is_active=True, password_hash="x")
        # firing/trigger are None for a channel test — must not crash the template.
        d = NotificationDelivery(id=2, firing_id=None, channel_id=1, status="skipped",
                                 error="SMTP not configured", is_test=True,
                                 created_at=datetime(2026, 6, 23, 17, 0, tzinfo=timezone.utc))
        out = templates.env.get_template("admin_diagnostics.html").render(
            request=req, user=admin, now=datetime(2026, 6, 23, 18, 0, tzinfo=timezone.utc),
            firings_24h=0, sent_24h=0, failed_24h=0, skipped_24h=1, tests_24h=1,
            fail_rows=[], skipped_rows=[(d, ch, owner, None, None)],
            recent_rows=[(d, ch, owner, None, None)],
        )
        assert "SMTP not configured" in out
        assert "test" in out


class TestFiringsAutoRefresh:
    def test_shows_updated_time_and_reload_script(self, admin):
        from app.routes_triggers import templates

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/firings"))
        out = templates.env.get_template("firings.html").render(
            request=req, user=admin, rows=[], delivery_status={}, total=0,
            page=1, per_page=100, total_pages=1, start=0, end=0, since="all",
            loaded_at=datetime(2026, 6, 23, 18, 5, 30, tzinfo=timezone.utc), flash=None,
        )
        assert "auto-refreshes every 30s" in out
        assert "18:05:30 UTC" in out
        assert "location.reload()" in out


class TestSkippedClassification:
    def test_unconfigured_email_records_skipped_not_failed(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from app import notifications

        # SMTP host empty -> _send_email raises ChannelNotConfigured -> "skipped".
        from app.models import NotificationChannel, Trigger
        ch = NotificationChannel(id=1, user_id=1, kind="email", name="me",
                                 is_active=True, config={"to_address": "x@y.com"})
        trig = Trigger(id=1, owner_id=1, name="t")

        recorded = {}

        async def fake_get(session, key):
            return ""  # smtp_host empty

        session = AsyncMock()
        session.add = MagicMock(side_effect=lambda d: recorded.update(
            status=d.status, error=d.error))

        async def go():
            # Patch settings get used inside _send_email
            orig = notifications.get_setting
            notifications.get_setting = fake_get
            try:
                ok = await notifications._dispatch_one(
                    session, AsyncMock(), ch, trig, None, is_test=True)
            finally:
                notifications.get_setting = orig
            return ok

        ok = asyncio.run(go())
        assert ok is False
        assert recorded["status"] == "skipped"
        assert "SMTP not configured" in recorded["error"]


class TestDeliveryLabelSkipped:
    def test_priority(self):
        from app.routes_triggers import _delivery_label
        assert _delivery_label(True, True, True) == "failed"
        assert _delivery_label(True, False, True) == "sent"
        assert _delivery_label(False, False, True) == "skipped"
        assert _delivery_label(False, False, False) == "pending"


class TestDeliveryDetailRender:
    def test_renders_full_trace(self):
        import types
        from datetime import datetime, timezone
        from app.routes_admin import templates
        from app.models import NotificationChannel, NotificationDelivery, TriggerFiring, Trigger, User

        req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/diagnostics/delivery/2"))
        ch = NotificationChannel(id=1, user_id=3, kind="email", name="me", is_active=True, config={})
        owner = User(id=3, username="cdibona", is_admin=True, is_active=True, password_hash="x")
        firing = TriggerFiring(id=9, trigger_id=11, icao_hex="a50b7b", registration="N424LF",
                               callsign="LIFE1",
                               fired_at=datetime(2026, 6, 23, 17, 37, tzinfo=timezone.utc))
        trig = Trigger(id=11, owner_id=3, name="Lifeflight")
        d = NotificationDelivery(id=2, firing_id=9, channel_id=1, status="skipped",
                                 error="SMTP not configured", is_test=False,
                                 created_at=datetime(2026, 6, 23, 17, 37, tzinfo=timezone.utc))
        out = templates.env.get_template("admin_delivery.html").render(
            request=req, user=owner, delivery=d, channel=ch, owner=owner,
            firing=firing, trigger=trig)
        assert "Lifeflight" in out
        assert "/aircraft/a50b7b" in out
        assert "SMTP not configured" in out
        assert "not an error" in out  # skipped explanation
