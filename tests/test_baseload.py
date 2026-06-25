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
