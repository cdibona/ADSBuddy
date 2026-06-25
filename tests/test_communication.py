"""Tests: every page has a consistent .page-head and a muted description line.

Fast render tests — no DB, no HTTP server.
"""
from __future__ import annotations

import types
from datetime import datetime, timezone


def _req(path="/"):
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _admin():
    return types.SimpleNamespace(username="admin", is_admin=True, id=1)


# ---------------------------------------------------------------------------
# triggers.html — empty list
# ---------------------------------------------------------------------------

def test_triggers_empty_has_page_head_and_description():
    from app.routes_triggers import templates

    out = templates.env.get_template("triggers.html").render(
        request=_req("/triggers"), user=_admin(),
        triggers=[], status="all",
        counts={"all": 0, "active": 0, "paused": 0}, flash=None,
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# firings.html — empty list
# ---------------------------------------------------------------------------

def test_firings_empty_has_page_head_and_description():
    from app.routes_triggers import templates

    out = templates.env.get_template("firings.html").render(
        request=_req("/firings"), user=_admin(),
        rows=[], delivery_status={}, total=0, page=1, per_page=100,
        total_pages=1, start=0, end=0, since="all",
        loaded_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc), flash=None,
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# aircraft.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_aircraft_has_page_head_and_description():
    from app.routes_pages import templates

    out = templates.env.get_template("aircraft.html").render(
        request=_req("/aircraft"), user=_admin(),
        aircraft=[],
        type_active=None,
        common_types=["B738", "PC12"],
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# admin_users.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_admin_users_has_page_head_and_description():
    from app.routes_admin import templates

    out = templates.env.get_template("admin_users.html").render(
        request=_req("/admin/users"),
        user=types.SimpleNamespace(username="admin", is_admin=True, id=1),
        users=[],
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# profile.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_profile_has_page_head_and_description():
    from app.routes_profile import templates, CHANNEL_KIND_LABELS

    out = templates.env.get_template("profile.html").render(
        request=_req("/profile"),
        user=types.SimpleNamespace(
            username="admin", is_admin=True, id=1,
            email="admin@example.com", timezone="UTC",
        ),
        channels=[],
        last_by_channel={},
        kind_label=CHANNEL_KIND_LABELS,
        kinds=[("discord", "Discord"), ("email", "Email"),
               ("webhook", "Webhook"), ("sms_twilio", "SMS (Twilio)")],
        common_timezones=["UTC", "US/Pacific"],
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# admin_notifications.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_admin_notifications_has_page_head_and_description():
    from app.routes_admin import templates

    out = templates.env.get_template("admin_notifications.html").render(
        request=_req("/admin/notifications"),
        user=types.SimpleNamespace(username="admin", is_admin=True, id=1),
        settings=[],
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# admin_diagnostics.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_admin_diagnostics_has_page_head_and_description():
    from app.routes_admin import templates

    out = templates.env.get_template("admin_diagnostics.html").render(
        request=_req("/admin/diagnostics"),
        user=types.SimpleNamespace(username="admin", is_admin=True, id=1),
        now=datetime(2026, 6, 23, 18, tzinfo=timezone.utc),
        firings_24h=0, sent_24h=0, failed_24h=0, skipped_24h=0, tests_24h=0,
        fail_rows=[], skipped_rows=[], recent_rows=[],
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out


# ---------------------------------------------------------------------------
# history_search.html — has page-head and muted description
# ---------------------------------------------------------------------------

def test_history_search_has_page_head_and_description():
    from app.routes_pages import templates

    out = templates.env.get_template("history_search.html").render(
        request=_req("/history"), user=_admin(),
        form={k: "" for k in ["tail", "hex", "callsign", "type", "owner",
                               "year", "route", "start_date", "end_date", "trigger"]},
        errors=[], searched=False, trigger_options=[],
        aircraft=[], recent_sightings={},
        total=0, page=1, per_page=50, total_pages=1, start=0, end=0, filter_qs="",
    )
    assert 'class="page-head"' in out
    assert 'class="muted"' in out
