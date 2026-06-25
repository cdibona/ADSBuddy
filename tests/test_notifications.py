"""Tests for app/notifications.py — message formatting and dispatch.

Run:  .venv/bin/python -m pytest tests/test_notifications.py -v
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.notifications import _format_message, deliver_for_firings


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_TS = datetime(2026, 6, 23, 15, 0, 0, tzinfo=timezone.utc)


def _trigger(id: int, name: str, owner_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(id=id, name=name, owner_id=owner_id,
                           center_lat=None, center_lon=None, radius_miles=None)


_FIRING_COUNTER = 0


def _firing(trigger_id: int, icao_hex: str = "a1b2c3", **kw) -> SimpleNamespace:
    global _FIRING_COUNTER
    _FIRING_COUNTER += 1
    defaults = dict(
        id=_FIRING_COUNTER,  # simulates the DB-assigned BigInteger PK after commit
        trigger_id=trigger_id,
        icao_hex=icao_hex,
        registration="N12345",
        callsign="UAL123",
        type_code="B738",
        category=None,
        year=2010,
        lat=None,
        lon=None,
        altitude_baro=None,
        origin_icao=None,
        destination_icao=None,
        squawk=None,
        emergency=None,
        fired_at=_TS,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _channel(id: int = 1, user_id: int = 1, kind: str = "discord", name: str = "TestChan") -> SimpleNamespace:
    cfg: dict = {}
    if kind == "discord":
        cfg["webhook_url"] = "https://discord.example.com/webhook/test"
    return SimpleNamespace(id=id, user_id=user_id, kind=kind, name=name, config=cfg)


# ---------------------------------------------------------------------------
# _format_message
# ---------------------------------------------------------------------------


class TestFormatMessage:
    def test_trigger_name_appears_in_text(self):
        t = _trigger(1, "Bezos")
        f = _firing(1)
        c = _channel()
        msg = _format_message(t, f, c)
        assert msg["text"].startswith("Trigger: Bezos\n")

    def test_different_trigger_name_appears(self):
        t = _trigger(2, "Police Helo")
        f = _firing(2)
        c = _channel()
        msg = _format_message(t, f, c)
        assert msg["text"].startswith("Trigger: Police Helo\n")
        assert "Bezos" not in msg["text"]

    def test_subject_contains_trigger_name(self):
        t = _trigger(1, "Coast Guard")
        f = _firing(1, registration="N999CG", callsign=None)
        c = _channel()
        msg = _format_message(t, f, c)
        assert "Coast Guard" in msg["subject"]

    def test_aircraft_ident_uses_callsign_plus_registration(self):
        t = _trigger(1, "T")
        f = _firing(1, registration="N42PB", callsign="UAL999")
        c = _channel()
        msg = _format_message(t, f, c)
        assert "UAL999 (N42PB)" in msg["text"]

    def test_test_message_when_firing_none(self):
        t = _trigger(1, "T")
        c = _channel(name="MyChannel")
        msg = _format_message(t, None, c)
        assert "test" in msg["text"].lower()


# ---------------------------------------------------------------------------
# deliver_for_firings — multi-trigger dispatch
# ---------------------------------------------------------------------------


def _make_async_session(triggers_by_id: dict, channels: list) -> AsyncMock:
    """Build a mock AsyncSession for deliver_for_firings tests."""
    call_count = 0

    async def _execute(stmt):
        nonlocal call_count
        call_count += 1
        result = MagicMock()
        # First call: notifications_enabled setting
        # deliver_for_firings calls get_setting first, which calls session.execute
        # We'll handle the setting mock via patch instead.
        # Calls from deliver_for_firings itself:
        # 1. select(Trigger).where(Trigger.id.in_(...))
        # 2. select(NotificationChannel).where(...)
        # 3+ : _record calls session.add, not execute
        if call_count == 1:
            # Trigger query — return all triggers that match the requested IDs
            result.scalars.return_value = iter(triggers_by_id.values())
        else:
            # Channel query
            result.scalars.return_value.__iter__ = lambda _: iter(channels)
            result.scalars.return_value.all = lambda: channels
        return result

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.add = MagicMock()
    return session


class TestDeliverForFirings:
    """Verify that each firing uses the trigger name it was created for."""

    def _run(self, session, client, firings):
        return asyncio.run(deliver_for_firings(session, client, firings))

    def test_single_trigger_single_firing_sends_correct_name(self):
        trigger_a = _trigger(1, "Bezos")
        firing_a = _firing(trigger_id=1, icao_hex="aabbcc")
        channel = _channel(user_id=1, kind="discord")

        sent_bodies: list[dict] = []

        async def mock_post(url, json, **kw):
            sent_bodies.append(json)
            resp = MagicMock()
            resp.status_code = 204
            return resp

        client = MagicMock()
        client.post = AsyncMock(side_effect=mock_post)

        # Build session mock manually so we control the query returns
        session = AsyncMock()
        session.add = MagicMock()

        trigger_rows = MagicMock()
        trigger_rows.scalars.return_value = [trigger_a]
        channel_rows = MagicMock()
        channel_rows.scalars.return_value = MagicMock()
        channel_rows.scalars.return_value.all.return_value = [channel]

        sel_rows = MagicMock(); sel_rows.all.return_value = []  # no per-trigger channel allow-list
        session.execute = AsyncMock(side_effect=[trigger_rows, channel_rows, sel_rows])

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="true")):
            self._run(session, client, [firing_a])

        assert len(sent_bodies) == 1
        # Firing messages now use Discord embeds; trigger name is in the description.
        embed = sent_bodies[0]["embeds"][0]
        assert "Bezos" in embed["description"]

    def test_two_triggers_each_firing_gets_its_own_name(self):
        """THE KEY TEST: two different triggers fire; each notification must name its own trigger."""
        trigger_bezos = _trigger(1, "Bezos", owner_id=1)
        trigger_helo = _trigger(2, "Police Helo", owner_id=1)
        firing_bezos = _firing(trigger_id=1, icao_hex="aa1111")
        firing_helo = _firing(trigger_id=2, icao_hex="bb2222")
        channel = _channel(user_id=1, kind="discord")

        sent_bodies: list[dict] = []

        async def mock_post(url, json, **kw):
            sent_bodies.append(json)
            resp = MagicMock()
            resp.status_code = 204
            return resp

        client = MagicMock()
        client.post = AsyncMock(side_effect=mock_post)
        session = AsyncMock()
        session.add = MagicMock()

        trigger_rows = MagicMock()
        trigger_rows.scalars.return_value = [trigger_bezos, trigger_helo]
        channel_rows = MagicMock()
        channel_rows.scalars.return_value = MagicMock()
        channel_rows.scalars.return_value.all.return_value = [channel]

        sel_rows = MagicMock(); sel_rows.all.return_value = []  # no per-trigger channel allow-list
        session.execute = AsyncMock(side_effect=[trigger_rows, channel_rows, sel_rows])

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="true")):
            self._run(session, client, [firing_bezos, firing_helo])

        assert len(sent_bodies) == 2, f"Expected 2 messages, got {len(sent_bodies)}"

        # Firing messages now use Discord embeds; trigger name is in the description.
        descriptions = [b["embeds"][0]["description"] for b in sent_bodies]
        bezos_msgs = [d for d in descriptions if "Bezos" in d]
        helo_msgs = [d for d in descriptions if "Police Helo" in d]

        assert len(bezos_msgs) == 1, (
            f"Expected 1 Bezos notification, got {len(bezos_msgs)}. "
            f"Descriptions: {descriptions}"
        )
        assert len(helo_msgs) == 1, (
            f"Expected 1 'Police Helo' notification, got {len(helo_msgs)}. "
            f"Descriptions: {descriptions}"
        )

    def test_firing_for_unknown_trigger_id_is_skipped(self):
        """A firing whose trigger_id no longer exists in the DB must be silently dropped."""
        trigger_bezos = _trigger(1, "Bezos", owner_id=1)
        firing_known = _firing(trigger_id=1, icao_hex="aa1111")
        firing_orphan = _firing(trigger_id=999, icao_hex="cc3333")
        channel = _channel(user_id=1, kind="discord")

        sent_bodies: list[dict] = []

        async def mock_post(url, json, **kw):
            sent_bodies.append(json)
            resp = MagicMock()
            resp.status_code = 204
            return resp

        client = MagicMock()
        client.post = AsyncMock(side_effect=mock_post)
        session = AsyncMock()
        session.add = MagicMock()

        trigger_rows = MagicMock()
        # Only trigger 1 is returned — trigger 999 doesn't exist
        trigger_rows.scalars.return_value = [trigger_bezos]
        channel_rows = MagicMock()
        channel_rows.scalars.return_value = MagicMock()
        channel_rows.scalars.return_value.all.return_value = [channel]

        sel_rows = MagicMock(); sel_rows.all.return_value = []  # no per-trigger channel allow-list
        session.execute = AsyncMock(side_effect=[trigger_rows, channel_rows, sel_rows])

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="true")):
            self._run(session, client, [firing_known, firing_orphan])

        # Only 1 notification: the orphan firing is silently dropped
        assert len(sent_bodies) == 1
        # Firing messages now use Discord embeds; trigger name is in the description.
        embed = sent_bodies[0]["embeds"][0]
        assert "Bezos" in embed["description"]

    def test_no_channels_means_no_discord_calls(self):
        """If the trigger owner has no channels, nothing is dispatched."""
        trigger_a = _trigger(1, "Bezos", owner_id=1)
        firing_a = _firing(trigger_id=1)

        client = MagicMock()
        client.post = AsyncMock()
        session = AsyncMock()
        session.add = MagicMock()

        trigger_rows = MagicMock()
        trigger_rows.scalars.return_value = [trigger_a]
        channel_rows = MagicMock()
        channel_rows.scalars.return_value = MagicMock()
        channel_rows.scalars.return_value.all.return_value = []  # no channels

        sel_rows = MagicMock(); sel_rows.all.return_value = []  # no per-trigger channel allow-list
        session.execute = AsyncMock(side_effect=[trigger_rows, channel_rows, sel_rows])

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="true")):
            self._run(session, client, [firing_a])

        client.post.assert_not_called()

    def test_notifications_disabled_sends_nothing(self):
        """When notifications_enabled=false, deliver_for_firings exits immediately."""
        client = MagicMock()
        client.post = AsyncMock()
        session = AsyncMock()

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="false")):
            asyncio.run(deliver_for_firings(session, client, [_firing(1)]))

        client.post.assert_not_called()
        # Session queries should also not run
        session.execute.assert_not_called()


class TestPerTriggerChannelSelection:
    def test_selection_excludes_unlisted_channel(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        import asyncio
        from app.notifications import deliver_for_firings

        trigger_a = _trigger(1, "Bezos")
        firing_a = _firing(trigger_id=1)
        channel = _channel(id=1, user_id=1, kind="discord")

        posts = []
        client = MagicMock()
        client.post = AsyncMock(side_effect=lambda *a, **k: posts.append(k) or MagicMock(status_code=204))

        session = AsyncMock(); session.add = MagicMock()
        trigger_rows = MagicMock(); trigger_rows.scalars.return_value = [trigger_a]
        channel_rows = MagicMock()
        channel_rows.scalars.return_value = MagicMock()
        channel_rows.scalars.return_value.all.return_value = [channel]
        sel_rows = MagicMock(); sel_rows.all.return_value = [(1, 99)]  # trigger 1 -> only channel 99
        session.execute = AsyncMock(side_effect=[trigger_rows, channel_rows, sel_rows])

        with patch("app.notifications.get_setting", new=AsyncMock(return_value="true")):
            asyncio.run(deliver_for_firings(session, client, [firing_a]))
        assert posts == []  # channel 1 not in the allow-list -> no delivery
