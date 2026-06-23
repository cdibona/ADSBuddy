"""Tests for build_discord_embed and _firing_color in app/notifications.py."""
from app.notifications import build_discord_embed
from app.models import Trigger, TriggerFiring

EMERG = {"7500", "7600", "7700"}


def _firing(**kw):
    d = dict(id=1, trigger_id=1, icao_hex="a50b7b", registration="N424LF",
             type_code="B407", callsign="LIFE1", altitude_baro=1200,
             lat=47.61, lon=-122.33, squawk=None, emergency=None)
    d.update(kw); return TriggerFiring(**d)


def test_color_emergency_red():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(squawk="7700"), "")
    assert e["color"] == 0xED4245


def test_color_geofence_amber():
    t = Trigger(id=1, owner_id=1, name="X", center_lat=47.4, center_lon=-122.3, radius_miles=40)
    assert build_discord_embed(t, _firing(), "")["color"] == 0xFAA61A


def test_color_normal_green():
    assert build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "")["color"] == 0x3BA55D


def test_title_links_when_base_url_set():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "https://h:8443")
    assert e["url"] == "https://h:8443/aircraft/a50b7b"
    assert "N424LF" in e["title"]


def test_no_url_when_base_blank():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "")
    assert "url" not in e
