"""Auto-disable a notification channel after consecutive failures."""
from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock


def _chan(**kw):
    d = dict(id=1, kind="webhook", name="Sink", is_active=True, config={"url": "http://dead/"},
             mode="everything", consecutive_failures=0, disabled_reason=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


def _run(monkeypatch, channel, threshold="3", fail=True):
    from app import notifications
    async def fake_get(s, k):
        return {"channel_disable_after_failures": threshold}.get(k, "")
    monkeypatch.setattr(notifications, "get_setting", fake_get)
    async def fake_record(*a, **k): pass
    monkeypatch.setattr(notifications, "_record", fake_record)
    async def boom(*a, **k):
        raise RuntimeError("name resolution failed")
    async def ok(*a, **k): pass
    monkeypatch.setattr(notifications, "_send_generic_webhook", boom if fail else ok)
    monkeypatch.setattr(notifications, "_webhook_payload", lambda *a, **k: {})
    trig = types.SimpleNamespace(id=9, name="t")
    return asyncio.run(notifications._dispatch_one(AsyncMock(), AsyncMock(), channel, trig, None, is_test=False))


def test_disables_after_threshold(monkeypatch):
    ch = _chan(consecutive_failures=2)   # one more failure hits threshold 3
    ok = _run(monkeypatch, ch, threshold="3", fail=True)
    assert ok is False
    assert ch.consecutive_failures == 3
    assert ch.is_active is False
    assert "Auto-disabled" in ch.disabled_reason and "name resolution" in ch.disabled_reason


def test_not_yet_at_threshold(monkeypatch):
    ch = _chan(consecutive_failures=0)
    _run(monkeypatch, ch, threshold="10", fail=True)
    assert ch.consecutive_failures == 1 and ch.is_active is True and ch.disabled_reason is None


def test_threshold_zero_never_disables(monkeypatch):
    ch = _chan(consecutive_failures=99)
    _run(monkeypatch, ch, threshold="0", fail=True)
    assert ch.is_active is True  # 0 = feature off


def test_success_resets_streak(monkeypatch):
    ch = _chan(consecutive_failures=5, disabled_reason=None)
    ok = _run(monkeypatch, ch, threshold="3", fail=False)
    assert ok is True and ch.consecutive_failures == 0


def test_test_delivery_does_not_count(monkeypatch):
    from app import notifications
    ch = _chan(consecutive_failures=2)
    async def fake_get(s, k): return "3"
    monkeypatch.setattr(notifications, "get_setting", fake_get)
    async def fake_record(*a, **k): pass
    monkeypatch.setattr(notifications, "_record", fake_record)
    async def boom(*a, **k): raise RuntimeError("x")
    monkeypatch.setattr(notifications, "_send_generic_webhook", boom)
    monkeypatch.setattr(notifications, "_webhook_payload", lambda *a, **k: {})
    asyncio.run(notifications._dispatch_one(AsyncMock(), AsyncMock(), ch,
                types.SimpleNamespace(id=1, name="t"), None, is_test=True))
    assert ch.consecutive_failures == 2 and ch.is_active is True  # test didn't increment
