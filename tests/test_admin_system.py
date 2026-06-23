"""Tests for the admin System tab and settings categorization."""
from __future__ import annotations

import types
from datetime import datetime, timezone


def test_setting_category():
    from app.settings_store import setting_category
    assert setting_category("smtp_host") == "notifications"
    assert setting_category("twilio_auth_token") == "notifications"
    assert setting_category("notifications_enabled") == "notifications"
    assert setting_category("radio_base_url") == "system"
    assert setting_category("sightings_retention_days") == "system"
    assert setting_category("some_custom_key") == "system"


def test_admin_system_renders():
    from app.routes_admin import templates
    from app.models import Setting
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/system"))
    out = templates.env.get_template("admin_system.html").render(
        request=req, user=types.SimpleNamespace(username="admin", is_admin=True),
        now=datetime(2026, 6, 23, 18, tzinfo=timezone.utc),
        git_sha="abc1234", commit_url="https://h/commit/abc1234",
        started_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc), uptime="2h",
        db_revision="20260623_0010",
        counts={"aircraft": 6976, "sightings": 8458577, "firings": 133100,
                "triggers": 10, "users": 3, "channels": 4, "deliveries": 419373, "routes": 500},
        last_sighting=datetime(2026, 6, 23, 17, 59, tzinfo=timezone.utc),
        last_firing=datetime(2026, 6, 23, 17, 37, tzinfo=timezone.utc),
        settings=[Setting(key="radio_base_url", value="http://x", description="radio", secret=False)],
    )
    assert "Admin — System" in out
    assert "20260623_0010" in out
    assert "8,458,577" in out          # sightings formatted with commas
    assert "radio_base_url" in out      # system settings editable list
    # System tab must NOT contain notification settings
    assert "smtp_host" not in out


def test_admin_subnav_has_four_tabs():
    from app.routes_admin import templates
    req = types.SimpleNamespace(url=types.SimpleNamespace(path="/admin/system"))
    out = templates.env.get_template("_admin_nav.html").render(request=req)
    for tab in ("/admin", "/admin/system", "/admin/notifications", "/admin/diagnostics"):
        assert f'href="{tab}"' in out
    assert "/admin/settings" not in out  # old flat Settings tab gone
