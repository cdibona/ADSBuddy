"""Baseload trigger seed data + policy."""
from __future__ import annotations


def test_baseload_active_policy():
    from app.baseload_triggers import BASELOAD_TRIGGERS
    active = {t["name"] for t in BASELOAD_TRIGGERS if t.get("is_active")}
    assert active == {"Vintage (75+ years)", "Emergency squawk"}
    # Everything else is paused.
    assert all(not t.get("is_active") for t in BASELOAD_TRIGGERS
               if t["name"] not in active)


def test_baseload_excludes_local_triggers():
    from app.baseload_triggers import BASELOAD_TRIGGERS
    names = {t["name"] for t in BASELOAD_TRIGGERS}
    for excluded in ("Lifeflight", "Likely Lifeflight", "SeaTac departures", "LSE", "LMG"):
        assert excluded not in names


def test_baseload_includes_celebs_and_specials():
    from app.baseload_triggers import BASELOAD_TRIGGERS
    names = {t["name"] for t in BASELOAD_TRIGGERS}
    assert {"Taylor Swift", "Elon Musk", "Air Force One", "Emergency squawk"} <= names
    assert len(BASELOAD_TRIGGERS) == 60


def test_baseload_names_unique():
    from app.baseload_triggers import BASELOAD_TRIGGERS
    names = [t["name"] for t in BASELOAD_TRIGGERS]
    assert len(names) == len(set(names))


def test_seed_function_exists():
    from app.bootstrap import seed_baseload_triggers
    assert callable(seed_baseload_triggers)


def test_trigger_to_spec_serializes_set_fields_only():
    from app.baseload_triggers import trigger_to_spec
    from app.models import Trigger
    t = Trigger(name="Jane Doe", is_active=False, cooldown_seconds=3600,
                tail_patterns="N12345,N9ZZ", squawk_patterns="", min_age_years=None,
                max_altitude_ft=1000, owner_id=1)
    spec = trigger_to_spec(t)
    assert spec == {"name": "Jane Doe", "is_active": False, "cooldown_seconds": 3600,
                    "tail_patterns": "N12345,N9ZZ", "max_altitude_ft": 1000}
    # No owner_id / empty fields / None numerics leak in.
    assert "owner_id" not in spec and "squawk_patterns" not in spec and "min_age_years" not in spec


def test_export_and_contribute_routes_registered():
    from app.routes_triggers import router
    paths = {r.path for r in router.routes if hasattr(r, "path")}
    assert "/triggers/{trigger_id}/export" in paths


def test_contribute_url_prefills_github_issue():
    import types, urllib.parse
    from app.routes_triggers import _contribute_url
    t = types.SimpleNamespace(name="Jane Doe", is_active=False, cooldown_seconds=3600,
                              tail_patterns="N12345")
    # fill the rest of the spec fields as empty/None
    for f in ("flight_patterns","type_codes","owner_patterns","squawk_patterns","categories",
              "exclude_tail_patterns","exclude_flight_patterns","exclude_type_codes",
              "exclude_owner_patterns","origin_icaos","destination_icaos","geofence_center","notes"):
        setattr(t, f, "")
    for f in ("min_year","max_year","min_age_years","max_age_years","min_altitude_ft",
              "max_altitude_ft","center_lat","center_lon","radius_miles"):
        setattr(t, f, None)
    url = _contribute_url(t)
    assert url.startswith("https://github.com/cdibona/ADSBuddy/issues/new?")
    assert "trigger-submission" in url
    assert "N12345" in urllib.parse.unquote(url)


def test_baseload_internal_key_hidden():
    from app.settings_store import setting_category
    assert setting_category("baseload_applied") == "internal"  # not on any admin tab
