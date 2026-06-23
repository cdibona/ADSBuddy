"""Tests for Phase 5 table filter helpers and filter-bar template rendering.

The helpers are pure (no I/O) so they're unit-tested directly; the templates
are rendered against the real Jinja env to catch markup/variable errors.
"""
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Trigger status filter
# ---------------------------------------------------------------------------

class TestTriggerStatusFilter:
    def test_valid_values_pass_through(self):
        from app.routes_triggers import _normalize_trigger_status

        assert _normalize_trigger_status("all") == "all"
        assert _normalize_trigger_status("active") == "active"
        assert _normalize_trigger_status("paused") == "paused"

    def test_case_and_whitespace_insensitive(self):
        from app.routes_triggers import _normalize_trigger_status

        assert _normalize_trigger_status("  ACTIVE ") == "active"
        assert _normalize_trigger_status("Paused") == "paused"

    def test_invalid_or_missing_defaults_to_all(self):
        from app.routes_triggers import _normalize_trigger_status

        assert _normalize_trigger_status(None) == "all"
        assert _normalize_trigger_status("") == "all"
        assert _normalize_trigger_status("bogus") == "all"
        assert _normalize_trigger_status("active; drop table") == "all"


# ---------------------------------------------------------------------------
# Firings time-bucket filter
# ---------------------------------------------------------------------------

class TestFiringsBucket:
    def test_valid_values(self):
        from app.routes_triggers import _normalize_firings_bucket

        for v in ("all", "today", "24h", "7d"):
            assert _normalize_firings_bucket(v) == v

    def test_invalid_defaults_to_all(self):
        from app.routes_triggers import _normalize_firings_bucket

        assert _normalize_firings_bucket(None) == "all"
        assert _normalize_firings_bucket("week") == "all"
        assert _normalize_firings_bucket("  TODAY ") == "today"

    def test_cutoff_for_all_is_none(self):
        from app.routes_triggers import _firings_since_cutoff

        now = datetime(2026, 6, 23, 15, 30, tzinfo=timezone.utc)
        assert _firings_since_cutoff("all", now) is None

    def test_cutoff_today_is_utc_midnight(self):
        from app.routes_triggers import _firings_since_cutoff

        now = datetime(2026, 6, 23, 15, 30, 45, tzinfo=timezone.utc)
        assert _firings_since_cutoff("today", now) == datetime(
            2026, 6, 23, 0, 0, 0, tzinfo=timezone.utc
        )

    def test_cutoff_24h_and_7d(self):
        from app.routes_triggers import _firings_since_cutoff

        now = datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc)
        assert _firings_since_cutoff("24h", now) == datetime(
            2026, 6, 22, 15, 0, tzinfo=timezone.utc
        )
        assert _firings_since_cutoff("7d", now) == datetime(
            2026, 6, 16, 15, 0, tzinfo=timezone.utc
        )


# ---------------------------------------------------------------------------
# Aircraft A–Z registration filter
# ---------------------------------------------------------------------------

class TestRegLetterFilter:
    def test_single_letter_uppercased(self):
        from app.routes_pages import _normalize_reg_letter

        assert _normalize_reg_letter("n") == "N"
        assert _normalize_reg_letter("A") == "A"
        assert _normalize_reg_letter(" z ") == "Z"

    def test_non_letter_or_multichar_is_none(self):
        from app.routes_pages import _normalize_reg_letter

        assert _normalize_reg_letter(None) is None
        assert _normalize_reg_letter("") is None
        assert _normalize_reg_letter("5") is None
        assert _normalize_reg_letter("NA") is None
        assert _normalize_reg_letter("%") is None


# ---------------------------------------------------------------------------
# Filter-bar template rendering
# ---------------------------------------------------------------------------

class TestTriggerConditionItems:
    def _trigger(self, **kw):
        from app.models import Trigger

        defaults = dict(id=1, owner_id=1, name="t", tail_patterns="", flight_patterns="",
                        type_codes="", origin_icaos="", destination_icaos="",
                        min_year=None, max_year=None, min_age_years=None, max_age_years=None)
        defaults.update(kw)
        return Trigger(**defaults)

    def test_empty_trigger_has_no_items(self):
        from app.routes_triggers import trigger_condition_items

        assert trigger_condition_items(self._trigger()) == []

    def test_collects_active_conditions_in_order(self):
        from app.routes_triggers import trigger_condition_items

        t = self._trigger(tail_patterns="N1*", type_codes="B738", min_year=1990, max_year=2000)
        items = trigger_condition_items(t)
        labels = [lbl for lbl, _ in items]
        assert labels == ["tail", "type", "year"]
        assert dict(items)["year"] == "≥ 1990 and ≤ 2000"

    def test_age_range_one_sided(self):
        from app.routes_triggers import trigger_condition_items

        t = self._trigger(min_age_years=50)
        assert dict(trigger_condition_items(t))["age"] == "≥ 50y"


class TestTriggersConditionsRendering:
    def _ctx(self, triggers):
        return dict(
            request=types.SimpleNamespace(url=types.SimpleNamespace(path="/triggers")),
            user=types.SimpleNamespace(username="admin", is_admin=False, id=1),
            triggers=triggers, status="all",
            counts={"all": len(triggers), "active": 0, "paused": 0}, flash=None,
        )

    def test_subset_and_more_link(self):
        from app.routes_triggers import templates
        from app.models import Trigger

        # 5 conditions -> show 3, summarize "+2 more".
        t = Trigger(id=7, owner_id=1, name="busy", is_active=True, notes="",
                    tail_patterns="N1*", flight_patterns="UAL*", type_codes="B738",
                    origin_icaos="KSFO", destination_icaos="KJFK",
                    min_year=None, max_year=None, min_age_years=None, max_age_years=None,
                    cooldown_seconds=3600)
        out = templates.env.get_template("triggers.html").render(**self._ctx([t]))
        assert "+2 more" in out
        assert 'class="col-conditions"' in out

    def test_no_conditions_shows_any_aircraft(self):
        from app.routes_triggers import templates
        from app.models import Trigger

        t = Trigger(id=8, owner_id=1, name="catch-all", is_active=True, notes="",
                    tail_patterns="", flight_patterns="", type_codes="",
                    origin_icaos="", destination_icaos="",
                    min_year=None, max_year=None, min_age_years=None, max_age_years=None,
                    cooldown_seconds=3600)
        out = templates.env.get_template("triggers.html").render(**self._ctx([t]))
        assert "any aircraft" in out


@pytest.fixture
def fake_request():
    return types.SimpleNamespace(url=types.SimpleNamespace(path="/"))


@pytest.fixture
def admin_user():
    return types.SimpleNamespace(username="admin", is_admin=True, id=1)


class TestFilterBarRendering:
    def test_triggers_filter_bar_renders_with_counts(self, fake_request, admin_user):
        from app.routes_triggers import templates

        tpl = templates.env.get_template("triggers.html")
        out = tpl.render(
            request=fake_request,
            user=admin_user,
            triggers=[],
            status="active",
            counts={"all": 9, "active": 7, "paused": 2},
            flash=None,
        )
        assert "Active (7)" in out
        assert "Paused (2)" in out
        assert "All (9)" in out
        # The active filter chip is marked.
        assert "chip-on" in out
        assert 'href="/triggers?status=active"' in out

    def test_firings_filter_bar_and_actions(self, fake_request, admin_user):
        from app.routes_triggers import templates
        from app.models import Trigger, TriggerFiring

        firing = TriggerFiring(
            id=1, trigger_id=1, icao_hex="a1b2c3", registration="N12345",
            type_code="B738", year=2005, lat=37.6, lon=-122.4,
            altitude_baro=10000, origin_icao="KSFO", destination_icao="KJFK",
            fired_at=datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc),
        )
        trig = Trigger(id=1, owner_id=1, name="My trigger")
        tpl = templates.env.get_template("firings.html")
        out = tpl.render(
            request=fake_request,
            user=admin_user,
            rows=[(firing, trig)],
            delivery_status={1: "sent"},
            total=1, page=1, per_page=100, total_pages=1,
            start=1, end=1, since="24h", flash=None,
        )
        # Time-bucket chips present, with the active one marked.
        assert 'href="/firings?since=today"' in out
        assert 'href="/firings?since=7d"' in out
        assert "chip-on" in out
        # Per-row create-trigger action prefilled from the firing.
        assert "/triggers/new?hex=a1b2c3" in out
        assert "Detail" in out

    def test_aircraft_az_jump_bar(self, fake_request, admin_user):
        from app.routes_pages import templates
        from app.models import Aircraft

        ac = Aircraft(
            icao_hex="a1b2c3", registration="N12345", type_code="B738",
            owner_op="United", year=2005,
            last_seen=datetime(2026, 6, 23, 15, 0, tzinfo=timezone.utc),
        )
        tpl = templates.env.get_template("aircraft.html")
        out = tpl.render(
            request=fake_request,
            user=admin_user,
            aircraft=[ac],
            reg_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            reg_active="N",
        )
        assert 'href="/aircraft?reg=A"' in out
        assert 'href="/aircraft?reg=Z"' in out
        # "All" reset link.
        assert 'href="/aircraft"' in out
        # Active letter chip marked.
        assert "chip-on" in out
