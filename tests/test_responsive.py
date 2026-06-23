"""Tests: every data-list template has data-label attributes on its <td> elements.

These are fast render tests — no DB, no HTTP server.
"""
from __future__ import annotations

import types
from datetime import datetime, timezone


def _req(path="/"):
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))


def _admin():
    return types.SimpleNamespace(username="admin", is_admin=True, id=1)


# ---------------------------------------------------------------------------
# firings.html
# ---------------------------------------------------------------------------

def test_firings_cells_have_data_labels():
    from app.routes_triggers import templates
    from app.models import Trigger, TriggerFiring

    f = TriggerFiring(
        id=1, trigger_id=1, icao_hex="a1b2c3", registration="N1",
        fired_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc),
    )
    t = Trigger(id=1, owner_id=1, name="T")
    out = templates.env.get_template("firings.html").render(
        request=_req("/firings"), user=_admin(),
        rows=[(f, t)], delivery_status={1: "sent"}, total=1, page=1, per_page=100,
        total_pages=1, start=1, end=1, since="all",
        loaded_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc), flash=None,
    )
    assert 'data-label="Aircraft"' in out
    assert 'data-label="When"' in out
    assert 'data-label="Trigger"' in out
    assert 'data-label="Callsign"' in out
    assert 'data-label="Type"' in out
    assert 'data-label="Year"' in out
    assert 'data-label="Route"' in out
    assert 'data-label="Altitude"' in out
    assert 'data-label="Notified"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# aircraft.html
# ---------------------------------------------------------------------------

def test_aircraft_cells_have_data_labels():
    from app.routes_pages import templates
    from app.models import Aircraft

    ac = Aircraft(
        icao_hex="a1b2c3", registration="N12345", type_code="B738",
        description="Boeing 737", owner_op="United", year=2005,
        last_seen=datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc),
    )
    out = templates.env.get_template("aircraft.html").render(
        request=_req("/aircraft"), user=_admin(),
        aircraft=[ac],
        reg_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        reg_active=None,
    )
    assert 'data-label="Hex"' in out
    assert 'data-label="Reg"' in out
    assert 'data-label="Type"' in out
    assert 'data-label="Description"' in out
    assert 'data-label="Owner / Operator"' in out
    assert 'data-label="Year"' in out
    assert 'data-label="Last seen"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# history_search.html
# ---------------------------------------------------------------------------

def test_history_search_cells_have_data_labels():
    from app.routes_pages import templates
    from app.models import Aircraft

    ac = Aircraft(
        icao_hex="a1b2c3", registration="N12345", type_code="B738",
        description="Boeing 737", owner_op="United", year=2005,
        last_seen=datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc),
    )
    out = templates.env.get_template("history_search.html").render(
        request=_req("/history"), user=_admin(),
        form={k: "" for k in ["tail", "hex", "callsign", "type", "owner",
                               "year", "route", "start_date", "end_date", "trigger"]},
        errors=[], searched=True, trigger_options=[],
        aircraft=[ac], recent_sightings={},
        total=1, page=1, per_page=50, total_pages=1, start=1, end=1, filter_qs="",
    )
    assert 'data-label="Hex"' in out
    assert 'data-label="Reg / Tail"' in out
    assert 'data-label="Type"' in out
    assert 'data-label="Owner / Operator"' in out
    assert 'data-label="Year"' in out
    assert 'data-label="Last seen"' in out
    assert 'data-label="Recent callsign"' in out
    assert 'data-label="Recent route"' in out
    assert 'data-label="Last position"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# triggers.html
# ---------------------------------------------------------------------------

def test_triggers_cells_have_data_labels():
    from app.routes_triggers import templates
    from app.models import Trigger

    t = Trigger(
        id=1, owner_id=1, name="Lifeflight", is_active=True, notes="",
        tail_patterns="N424LF", flight_patterns="", type_codes="",
        origin_icaos="", destination_icaos="",
        min_year=None, max_year=None, min_age_years=None, max_age_years=None,
        cooldown_seconds=3600,
    )
    out = templates.env.get_template("triggers.html").render(
        request=_req("/triggers"), user=_admin(),
        triggers=[t], status="all",
        counts={"all": 1, "active": 1, "paused": 0}, flash=None,
    )
    assert 'data-label="Name"' in out
    assert 'data-label="Owner"' in out  # admin sees Owner column
    assert 'data-label="Active"' in out
    assert 'data-label="Conditions"' in out
    assert 'data-label="Cooldown"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# admin_users.html
# ---------------------------------------------------------------------------

def test_admin_users_cells_have_data_labels():
    from app.routes_admin import templates
    from app.models import User

    u = User(
        id=2, username="testuser", is_admin=False, is_active=True,
        password_hash="x",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    out = templates.env.get_template("admin_users.html").render(
        request=_req("/admin/users"),
        user=types.SimpleNamespace(username="admin", is_admin=True, id=1),
        users=[u],
    )
    assert 'data-label="Username"' in out
    assert 'data-label="Role"' in out
    assert 'data-label="Active"' in out
    assert 'data-label="Created"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# admin_diagnostics.html  (three tables)
# ---------------------------------------------------------------------------

def test_admin_diagnostics_cells_have_data_labels():
    from app.routes_admin import templates
    from app.models import (
        NotificationChannel, NotificationDelivery, TriggerFiring, Trigger, User,
    )

    ch = NotificationChannel(id=1, user_id=3, kind="discord", name="HaxorTest")
    owner = User(id=3, username="cdibona", is_admin=True, is_active=True, password_hash="x")
    firing = TriggerFiring(
        id=1, trigger_id=1, icao_hex="a1b2c3", registration="N1",
        fired_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc),
    )
    trig = Trigger(id=1, owner_id=3, name="MyTrigger")
    d_fail = NotificationDelivery(
        id=1, firing_id=1, channel_id=1, status="failed",
        error="Oops", is_test=False,
        created_at=datetime(2026, 6, 23, 17, tzinfo=timezone.utc),
    )
    d_skip = NotificationDelivery(
        id=2, firing_id=1, channel_id=1, status="skipped",
        error="not set up", is_test=False,
        created_at=datetime(2026, 6, 23, 17, tzinfo=timezone.utc),
    )
    d_ok = NotificationDelivery(
        id=3, firing_id=1, channel_id=1, status="sent",
        is_test=False,
        created_at=datetime(2026, 6, 23, 17, tzinfo=timezone.utc),
    )

    out = templates.env.get_template("admin_diagnostics.html").render(
        request=_req("/admin/diagnostics"),
        user=types.SimpleNamespace(username="cdibona", is_admin=True, id=3),
        now=datetime(2026, 6, 23, 18, tzinfo=timezone.utc),
        firings_24h=1, sent_24h=1, failed_24h=1, skipped_24h=1, tests_24h=0,
        fail_rows=[(d_fail, ch, owner, firing, trig)],
        skipped_rows=[(d_skip, ch, owner, firing, trig)],
        recent_rows=[(d_ok, ch, owner, firing, trig)],
    )
    # Failures table headers
    assert 'data-label="When"' in out
    assert 'data-label="Channel"' in out
    assert 'data-label="Owner"' in out
    assert 'data-label="Trigger"' in out
    assert 'data-label="Aircraft"' in out
    assert 'data-label="Error"' in out
    # Skipped table
    assert 'data-label="Reason"' in out
    # Recent attempts table
    assert 'data-label="Status"' in out


# ---------------------------------------------------------------------------
# profile.html  (channels table)
# ---------------------------------------------------------------------------

def test_profile_channels_cells_have_data_labels():
    from app.routes_profile import templates, CHANNEL_KIND_LABELS
    from app.models import NotificationChannel, NotificationDelivery

    ch = NotificationChannel(
        id=1, user_id=1, kind="discord", name="MyDiscord",
        is_active=True, config={"webhook_url": "https://discord.com/api/webhooks/123/abc"},
    )
    last_d = NotificationDelivery(
        id=1, firing_id=None, channel_id=1, status="sent",
        is_test=False,
        created_at=datetime(2026, 6, 23, 17, tzinfo=timezone.utc),
    )
    out = templates.env.get_template("profile.html").render(
        request=_req("/profile"),
        user=types.SimpleNamespace(
            username="admin", is_admin=True, id=1,
            email="admin@example.com", timezone="UTC",
        ),
        channels=[ch],
        last_by_channel={1: last_d},
        kind_label=CHANNEL_KIND_LABELS,
        kinds=[("discord", "Discord"), ("email", "Email"), ("webhook", "Webhook"), ("sms_twilio", "SMS (Twilio)")],
        common_timezones=["UTC", "US/Pacific"],
    )
    assert 'data-label="Kind"' in out
    assert 'data-label="Name"' in out
    assert 'data-label="Destination"' in out
    assert 'data-label="Active"' in out
    assert 'data-label="Last delivery"' in out
    assert 'data-label=""' in out  # actions cell


# ---------------------------------------------------------------------------
# aircraft_detail.html  (sightings table + firings table)
# ---------------------------------------------------------------------------

def test_aircraft_detail_cells_have_data_labels():
    from app.routes_pages import templates
    from app.models import Aircraft, Sighting, Trigger, TriggerFiring

    ac = Aircraft(
        icao_hex="a1b2c3", registration="N12345", type_code="B738",
        description="Boeing 737", owner_op="United", year=2005,
        first_seen=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_seen=datetime(2026, 6, 23, 16, tzinfo=timezone.utc),
    )
    s = Sighting(
        icao_hex="a1b2c3", flight="UAL1",
        seen_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc),
    )
    f = TriggerFiring(
        id=1, trigger_id=1, icao_hex="a1b2c3",
        fired_at=datetime(2026, 6, 23, 16, tzinfo=timezone.utc),
    )
    t = Trigger(id=1, owner_id=1, name="TestTrigger")
    out = templates.env.get_template("aircraft_detail.html").render(
        request=_req("/aircraft/a1b2c3"), user=_admin(),
        aircraft=ac, sightings=[s], firings_rows=[(f, t)],
        map_points=[], map_sources=[], receiver=None,
    )
    # Sightings table
    assert 'data-label="Time"' in out
    assert 'data-label="Callsign"' in out
    assert 'data-label="Altitude"' in out
    assert 'data-label="Route"' in out
    # Firings table (also has Time, Trigger, Callsign, Type, Year, Route, Altitude)
    assert 'data-label="Trigger"' in out
    assert 'data-label="Type"' in out
    assert 'data-label="Year"' in out
