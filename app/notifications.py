"""Notification dispatch for trigger firings.

Architecture:
- One channel row per (user, destination). Kinds: discord, email, webhook, sms_twilio.
- When a Trigger fires, fan out to every active channel of the trigger's owner.
- Each delivery attempt records a NotificationDelivery row (sent or failed),
  so the user can see what got through and the admin can debug.
- Per-channel timeouts keep one slow endpoint from stalling the ingester.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

import aiosmtplib
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.aircraft_helpers import (
    aircraft_kind,
    kind_icon,
    kind_icon_url,
    kind_label,
    opensky_url,
    registration_provider,
    registration_url,
    type_url,
)
from app.models import (
    CHANNEL_KINDS,
    NotificationChannel,
    NotificationDelivery,
    Trigger,
    TriggerChannel,
    TriggerFiring,
)
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)

# Bounded so a stuck remote can't wedge the ingester tick.
_HTTP_TIMEOUT = 8.0
_SMTP_TIMEOUT = 10.0


class ChannelNotConfigured(Exception):
    """Raised when a channel can't deliver because required config is missing.

    Distinct from a real delivery failure: an unconfigured transport (e.g. SMTP
    not set up, a channel missing its destination) is recorded as 'skipped', not
    'failed', so it isn't counted as an error.
    """


async def smtp_configured(session: AsyncSession) -> bool:
    return bool((await get_setting(session, "smtp_host") or "").strip())


async def twilio_configured(session: AsyncSession) -> bool:
    sid = (await get_setting(session, "twilio_account_sid") or "").strip()
    token = (await get_setting(session, "twilio_auth_token") or "").strip()
    from_num = (await get_setting(session, "twilio_from_number") or "").strip()
    return bool(sid and token and from_num)


async def vestaboard_configured(session: AsyncSession) -> bool:
    return bool((await get_setting(session, "vestaboard_api_key") or "").strip())


async def trmnl_configured(session: AsyncSession) -> bool:
    return bool((await get_setting(session, "trmnl_webhook_url") or "").strip())


async def available_channel_kinds(session: AsyncSession) -> list[str]:
    """Channel kinds a user can actually use right now.

    Discord and generic webhooks need no admin setup, so they're always offered.
    Email, Twilio SMS, Vestaboard, and TRMNL depend on admin transport config,
    so they appear only once their transport is set up.
    """
    avail: list[str] = []
    for kind in CHANNEL_KINDS:
        if kind in ("discord", "webhook"):
            avail.append(kind)
        elif kind == "email" and await smtp_configured(session):
            avail.append(kind)
        elif kind == "sms_twilio" and await twilio_configured(session):
            avail.append(kind)
        elif kind == "vestaboard" and await vestaboard_configured(session):
            avail.append(kind)
        elif kind == "trmnl" and await trmnl_configured(session):
            avail.append(kind)
    return avail


# ---------- Discord embed --------------------------------------------------

_EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}


def _firing_color(trigger: Trigger, firing: TriggerFiring) -> int:
    if (firing.squawk in _EMERGENCY_SQUAWKS) or firing.emergency:
        return 0xED4245  # red
    if trigger.center_lat is not None and trigger.radius_miles is not None:
        return 0xFAA61A  # amber: geofence/watch
    return 0x3BA55D      # green: normal


def _firing_links(firing: TriggerFiring, base_url: str) -> list[str]:
    """Markdown links for the embed/email: detail, registry, type, OpenSky, map."""
    links: list[str] = []
    if base_url:
        links.append(f"[Detail]({base_url.rstrip('/')}/aircraft/{firing.icao_hex})")
    reg_url = registration_url(firing.registration)
    if reg_url:
        links.append(f"[{registration_provider(firing.registration)}]({reg_url})")
    t_url = type_url(firing.type_code)
    if t_url:
        links.append(f"[Type]({t_url})")
    os_url = opensky_url(firing.icao_hex)
    if os_url:
        links.append(f"[OpenSky]({os_url})")
    if firing.lat is not None and firing.lon is not None:
        links.append(f"[Map](https://www.google.com/maps?q={firing.lat:.5f},{firing.lon:.5f})")
    return links


def build_discord_embed(trigger: Trigger, firing: TriggerFiring, base_url: str) -> dict:
    ident = firing.registration or firing.icao_hex
    icon = kind_icon(firing.type_code, firing.category)
    title = f"{icon} {ident}" + (f" — {firing.type_code}" if firing.type_code else "")
    fields: list[dict] = []
    if firing.callsign:
        fields.append({"name": "Callsign", "value": firing.callsign, "inline": True})
    if firing.altitude_baro is not None:
        fields.append({"name": "Altitude", "value": f"{firing.altitude_baro} ft", "inline": True})
    if firing.lat is not None and firing.lon is not None:
        fields.append({"name": "Position", "value": f"{firing.lat:.4f}, {firing.lon:.4f}", "inline": True})
    if firing.origin_icao or firing.destination_icao:
        fields.append({
            "name": "Route",
            "value": f"{firing.origin_icao or '?'} → {firing.destination_icao or '?'}",
            "inline": True,
        })
    links = _firing_links(firing, base_url)
    if links:
        fields.append({"name": "Links", "value": " · ".join(links), "inline": False})
    desc_bits = []
    if firing.squawk in _EMERGENCY_SQUAWKS:
        desc_bits.append(f"**EMERGENCY** squawk {firing.squawk}")
    desc_bits.append(f"trigger: {trigger.name}")
    embed: dict = {
        "title": title,
        "description": " · ".join(desc_bits),
        "color": _firing_color(trigger, firing),
        "fields": fields,
        "footer": {"text": f"ADSBuddy · {kind_label(firing.type_code, firing.category)}"},
    }
    if base_url:
        base = base_url.rstrip("/")
        embed["url"] = f"{base}/aircraft/{firing.icao_hex}"
    if firing.fired_at:
        embed["timestamp"] = firing.fired_at.isoformat()
    return embed


def build_email_html(trigger: Trigger, firing: TriggerFiring, base_url: str) -> str:
    """Return a small HTML table summarising the firing, for use as email alternative.

    All dynamic values are HTML-escaped — trigger names (and ADS-B fields) are
    user/remote-controlled and must not be able to inject markup into the
    text/html MIME part.
    """
    esc = html.escape
    ident = esc(firing.registration or firing.icao_hex)
    if firing.callsign:
        ident = f"{esc(firing.callsign)} ({ident})"

    rows: list[str] = []
    rows.append(f"<tr><td><b>Trigger</b></td><td>{esc(trigger.name)}</td></tr>")
    rows.append(f"<tr><td><b>Aircraft</b></td><td>{ident}</td></tr>")
    rows.append(f"<tr><td><b>Kind</b></td><td>{esc(kind_label(firing.type_code, firing.category))}</td></tr>")
    if firing.type_code:
        type_val = esc(firing.type_code)
        if firing.year:
            type_val += f" ({firing.year})"
        rows.append(f"<tr><td><b>Type</b></td><td>{type_val}</td></tr>")
    if firing.altitude_baro is not None:
        rows.append(f"<tr><td><b>Altitude</b></td><td>{firing.altitude_baro} ft</td></tr>")
    if firing.lat is not None and firing.lon is not None:
        rows.append(f"<tr><td><b>Position</b></td><td>{firing.lat:.4f}, {firing.lon:.4f}</td></tr>")
    if firing.origin_icao or firing.destination_icao:
        route = f"{esc(firing.origin_icao or '?')} → {esc(firing.destination_icao or '?')}"
        rows.append(f"<tr><td><b>Route</b></td><td>{route}</td></tr>")
    if firing.fired_at:
        rows.append(
            f"<tr><td><b>At</b></td><td>{firing.fired_at.strftime('%Y-%m-%d %H:%M:%S UTC')}</td></tr>"
        )
    link_bits: list[str] = []

    def _a(url: str | None, label: str) -> None:
        if url:
            link_bits.append(f'<a href="{esc(url, quote=True)}">{esc(label)}</a>')

    if base_url:
        _a(f"{base_url.rstrip('/')}/aircraft/{firing.icao_hex}", "Detail")
    _a(registration_url(firing.registration), registration_provider(firing.registration) or "Registry")
    _a(type_url(firing.type_code), "Type")
    _a(opensky_url(firing.icao_hex), "OpenSky")
    if firing.lat is not None and firing.lon is not None:
        _a(f"https://www.google.com/maps?q={firing.lat:.5f},{firing.lon:.5f}", "Map")
    if link_bits:
        rows.append(f"<tr><td><b>Links</b></td><td>{' · '.join(link_bits)}</td></tr>")

    table = "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">{}</table>".format(
        "".join(rows)
    )
    subject = f"ADSBuddy alert: {esc(trigger.name)}: {ident}"
    return (
        "<!DOCTYPE html><html><body>"
        f"<h2>{subject}</h2>"
        f"{table}"
        "</body></html>"
    )


# ---------- message formatting ---------------------------------------------


def _format_message(
    trigger: Trigger, firing: TriggerFiring | None, channel: NotificationChannel
) -> dict[str, str]:
    if firing is None:
        return {
            "subject": f"[ADSBuddy] Test for channel: {channel.name}",
            "text": (
                f"This is a test from ADSBuddy.\n"
                f"Channel: {channel.name} ({channel.kind})\n"
                "If you got this, the channel is wired up correctly."
            ),
        }
    ident = firing.registration or firing.icao_hex
    if firing.callsign:
        ident = f"{firing.callsign} ({ident})"
    lines = [f"Trigger: {trigger.name}", f"Aircraft: {ident}"]
    if firing.type_code:
        type_line = f"Type: {firing.type_code}"
        if firing.year:
            type_line += f" ({firing.year})"
        lines.append(type_line)
    if firing.origin_icao or firing.destination_icao:
        lines.append(
            f"Route: {firing.origin_icao or '?'} → {firing.destination_icao or '?'}"
        )
    if firing.altitude_baro is not None:
        lines.append(f"Altitude: {firing.altitude_baro} ft")
    if firing.lat is not None and firing.lon is not None:
        lines.append(f"Position: {firing.lat:.4f}, {firing.lon:.4f}")
    lines.append(f"At: {firing.fired_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    return {
        "subject": f"[ADSBuddy] {trigger.name}: {ident}",
        "text": "\n".join(lines),
    }


def _webhook_payload(
    trigger: Trigger, firing: TriggerFiring | None, channel: NotificationChannel,
    base_url: str = "",
) -> dict[str, Any]:
    if firing is None:
        return {
            "test": True,
            "channel": {"id": channel.id, "name": channel.name, "kind": channel.kind},
        }
    return {
        "trigger": {"id": trigger.id, "name": trigger.name},
        "firing": {
            "id": firing.id,
            "icao_hex": firing.icao_hex,
            "callsign": firing.callsign,
            "registration": firing.registration,
            "type_code": firing.type_code,
            "category": firing.category,
            "kind": aircraft_kind(firing.type_code, firing.category),
            "year": firing.year,
            "lat": firing.lat,
            "lon": firing.lon,
            "altitude_baro": firing.altitude_baro,
            "origin_icao": firing.origin_icao,
            "destination_icao": firing.destination_icao,
            "fired_at": firing.fired_at.isoformat() if firing.fired_at else None,
        },
        "links": {
            "detail": f"{base_url.rstrip('/')}/aircraft/{firing.icao_hex}" if base_url else None,
            "registry": registration_url(firing.registration),
            "type": type_url(firing.type_code),
            "opensky": opensky_url(firing.icao_hex),
            "map": (f"https://www.google.com/maps?q={firing.lat:.5f},{firing.lon:.5f}"
                    if firing.lat is not None and firing.lon is not None else None),
        },
    }


# ---------- per-kind senders -----------------------------------------------


async def _send_discord(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    trigger: Trigger,
    firing: TriggerFiring | None,
) -> None:
    url = (channel.config or {}).get("webhook_url")
    if not url:
        raise ChannelNotConfigured("Discord channel is missing 'webhook_url' in config.")
    body: dict[str, Any] = {"username": (channel.config or {}).get("username") or "ADSBuddy"}
    if firing is not None:
        base = await get_setting(session, "site_base_url") or ""
        body["embeds"] = [build_discord_embed(trigger, firing, base)]
    else:
        body["content"] = "ADSBuddy test — channel wired up correctly."
    resp = await client.post(url, json=body, timeout=_HTTP_TIMEOUT)
    if resp.status_code >= 300:
        raise RuntimeError(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")


async def _send_generic_webhook(
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    payload: dict[str, Any],
) -> None:
    cfg = channel.config or {}
    url = cfg.get("url")
    if not url:
        raise ChannelNotConfigured("Webhook channel is missing 'url' in config.")
    headers = {"Content-Type": "application/json"}
    auth = cfg.get("auth_header")
    if auth:
        headers["Authorization"] = auth
    resp = await client.post(url, json=payload, headers=headers, timeout=_HTTP_TIMEOUT)
    if resp.status_code >= 300:
        raise RuntimeError(f"Webhook returned {resp.status_code}: {resp.text[:200]}")


async def _send_email(
    session: AsyncSession,
    channel: NotificationChannel,
    message: dict[str, str],
    trigger: Trigger | None = None,
    firing: TriggerFiring | None = None,
) -> None:
    host = await get_setting(session, "smtp_host")
    if not host:
        raise ChannelNotConfigured("SMTP not configured (smtp_host is empty).")
    port_raw = await get_setting(session, "smtp_port") or "587"
    try:
        port = int(port_raw)
    except ValueError as e:
        raise ValueError(f"smtp_port is not an integer: {port_raw!r}") from e
    username = await get_setting(session, "smtp_username") or None
    password = await get_setting(session, "smtp_password") or None
    sender = await get_setting(session, "smtp_from") or username or "adsbuddy@localhost"
    use_tls = ((await get_setting(session, "smtp_use_tls")) or "true").lower() == "true"

    to_addr = (channel.config or {}).get("to_address")
    if not to_addr:
        raise ChannelNotConfigured("Email channel is missing 'to_address' in config.")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to_addr
    msg["Subject"] = message["subject"]
    msg.set_content(message["text"])

    # Attach HTML alternative when we have a real firing to render.
    if trigger is not None and firing is not None:
        base = await get_setting(session, "site_base_url") or ""
        html = build_email_html(trigger, firing, base)
        msg.add_alternative(html, subtype="html")

    await aiosmtplib.send(
        msg,
        hostname=host,
        port=port,
        username=username,
        password=password,
        start_tls=use_tls,
        timeout=_SMTP_TIMEOUT,
    )


async def _send_sms_twilio(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    message: dict[str, str],
) -> None:
    sid = await get_setting(session, "twilio_account_sid")
    token = await get_setting(session, "twilio_auth_token")
    from_num = await get_setting(session, "twilio_from_number")
    if not (sid and token and from_num):
        raise ChannelNotConfigured(
            "Twilio not configured (account SID / auth token / from number)."
        )

    to_num = (channel.config or {}).get("to_phone")
    if not to_num:
        raise ChannelNotConfigured("SMS channel is missing 'to_phone' in config.")

    # Twilio caps a single segment at 160 chars; we let it segment up to ~10.
    body = message["text"][:1500]
    resp = await client.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data={"From": from_num, "To": to_num, "Body": body},
        auth=(sid, token),
        timeout=_HTTP_TIMEOUT,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Twilio returned {resp.status_code}: {resp.text[:200]}")


# ---------- orchestration --------------------------------------------------


async def _record(
    session: AsyncSession,
    channel: NotificationChannel,
    firing: TriggerFiring | None,
    status: str,
    error: str | None,
    is_test: bool,
) -> None:
    session.add(
        NotificationDelivery(
            firing_id=firing.id if firing is not None else None,
            channel_id=channel.id,
            status=status,
            error=(error[:1000] if error else None),
            is_test=is_test,
        )
    )


def _compact_text(trigger: Trigger, firing: TriggerFiring | None) -> str:
    """Short one-glance message for small displays (Vestaboard ~132 chars)."""
    if firing is None:
        return f"ADSBuddy test: {trigger.name}"[:132]
    ident = firing.registration or firing.icao_hex
    parts = [trigger.name, ident or "?"]
    if firing.callsign:
        parts.append(firing.callsign)
    if firing.type_code:
        parts.append(firing.type_code)
    if firing.altitude_baro is not None:
        parts.append(f"{firing.altitude_baro}ft")
    return " ".join(parts)[:132]


# ---- Vestaboard 6x22 layout -----------------------------------------------

_VB_ROWS, _VB_COLS = 6, 22
_VB_RED, _VB_GREEN, _VB_BLUE = 63, 66, 67
_VB_CODES = {" ": 0}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
    _VB_CODES[_c] = _i
for _i, _c in enumerate("123456789", start=27):
    _VB_CODES[_c] = _i
_VB_CODES["0"] = 36
_VB_CODES.update({"!": 37, "@": 38, "#": 39, "$": 40, "(": 41, ")": 42, "-": 44,
                  "+": 46, "&": 47, "=": 48, ";": 49, ":": 50, "'": 52, '"': 53,
                  "%": 54, ",": 55, ".": 56, "/": 59, "?": 60, "°": 62})


def _vb_center(text: str) -> list[int]:
    """A 22-cell row with the text (uppercased, mapped to codes) centered."""
    text = (text or "").upper().replace("→", "-").replace("·", " ")
    codes = [_VB_CODES.get(ch, 0) for ch in text][:_VB_COLS]
    pad = _VB_COLS - len(codes)
    left = pad // 2
    return [0] * left + codes + [0] * (pad - left)


def _vestaboard_matrix(trigger: Trigger, firing: TriggerFiring | None) -> list[list[int]]:
    """A framed 6x22 board: a status-color bar top & bottom, 3-4 centered lines."""
    emergency = bool(firing and (firing.squawk in _EMERGENCY_SQUAWKS or firing.emergency))
    bar = [_VB_RED if emergency else _VB_BLUE] * _VB_COLS
    if firing is None:
        lines = [trigger.name, "(TEST)", "", ""]
    else:
        type_alt = firing.type_code or ""
        if firing.altitude_baro is not None:
            type_alt = f"{type_alt} {firing.altitude_baro}FT".strip()
        route = ""
        if firing.origin_icao or firing.destination_icao:
            route = f"{firing.origin_icao or '?'}-{firing.destination_icao or '?'}"
        lines = [trigger.name, firing.registration or firing.icao_hex or "", type_alt, route]
    return [bar, *(_vb_center(line) for line in lines), bar]


async def _send_vestaboard(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    trigger: Trigger,
    firing: TriggerFiring | None,
) -> None:
    key = (await get_setting(session, "vestaboard_api_key") or "").strip()
    if not key:
        raise ChannelNotConfigured("Vestaboard not configured (vestaboard_api_key is empty).")
    headers = {"X-Vestaboard-Read-Write-Key": key, "Content-Type": "application/json"}
    # Preferred: a laid-out character matrix; fall back to plain text if the
    # board/API rejects the matrix form.
    try:
        resp = await client.post(
            "https://rw.vestaboard.com/", headers=headers,
            json={"characters": _vestaboard_matrix(trigger, firing)}, timeout=15.0,
        )
        resp.raise_for_status()
        return resp.status_code
    except Exception:
        resp = await client.post(
            "https://rw.vestaboard.com/", headers=headers,
            json={"text": _compact_text(trigger, firing)}, timeout=15.0,
        )
        resp.raise_for_status()
        return resp.status_code


async def _send_trmnl(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    trigger: Trigger,
    firing: TriggerFiring | None,
) -> None:
    url = (await get_setting(session, "trmnl_webhook_url") or "").strip()
    if not url:
        raise ChannelNotConfigured("TRMNL not configured (trmnl_webhook_url is empty).")
    if "/api/custom_plugins/" in url and url.rstrip("/").endswith("custom_plugins"):
        raise ChannelNotConfigured(
            "TRMNL webhook URL is missing its plugin UUID — copy the full Webhook URL "
            "from the plugin's settings (e.g. https://trmnl.com/api/custom_plugins/<uuid>)."
        )
    # Stable, all-string key set so the plugin's Liquid markup can rely on it
    # (no nulls/missing keys). Includes kind/route for the richer layout.
    if firing is None:
        mv = {
            "trigger": trigger.name, "aircraft": "(test)", "callsign": "", "type": "",
            "altitude": "", "route": "", "year": "", "time": "",
            "kind": "plane", "kind_label": "Aircraft",
            "icon_url": kind_icon_url(None, None), "text": _compact_text(trigger, None),
        }
    else:
        route = ""
        if firing.origin_icao or firing.destination_icao:
            route = f"{firing.origin_icao or '?'} → {firing.destination_icao or '?'}"
        mv = {
            "trigger": trigger.name,
            "aircraft": firing.registration or firing.icao_hex or "",
            "callsign": firing.callsign or "",
            "type": firing.type_code or "",
            "altitude": str(firing.altitude_baro) if firing.altitude_baro is not None else "",
            "route": route,
            "year": str(firing.year) if firing.year else "",
            "time": firing.fired_at.strftime("%Y-%m-%d %H:%M UTC") if firing.fired_at else "",
            "kind": aircraft_kind(firing.type_code, firing.category),
            "kind_label": kind_label(firing.type_code, firing.category),
            "icon_url": kind_icon_url(firing.type_code, firing.category),
            "text": _compact_text(trigger, firing),
        }
    resp = await client.post(url, json={"merge_variables": mv}, timeout=15.0)
    resp.raise_for_status()
    return resp.status_code


def _sample_trigger() -> Trigger:
    return Trigger(id=0, owner_id=0, name="ADSBuddy test", is_active=True, cooldown_seconds=0)


def _sample_firing() -> TriggerFiring:
    """A fully-populated, realistic firing so test sends render like the real thing.

    No id/trigger_id — it's transient (never persisted), so a test delivery row
    records firing_id=None rather than referencing a non-existent firing.
    """
    return TriggerFiring(
        icao_hex="a835af",
        registration="N628TS",
        callsign="N628TS",
        type_code="GLF6",
        category="A2",  # small jet -> ✈️ / "Jet"
        year=2015,
        altitude_baro=38000,
        lat=47.4502,
        lon=-122.3088,
        origin_icao="KSJC",
        destination_icao="KPDX",
        fired_at=datetime.now(timezone.utc),
    )


async def latest_firing_and_trigger(session: AsyncSession):
    """The most recent real firing + its trigger, or the synthetic sample if none."""
    row = (
        await session.execute(
            select(TriggerFiring, Trigger)
            .join(Trigger, Trigger.id == TriggerFiring.trigger_id)
            .order_by(TriggerFiring.fired_at.desc())
            .limit(1)
        )
    ).first()
    if row is not None:
        firing, trigger = row
        return trigger, firing
    return _sample_trigger(), _sample_firing()


async def send_transport_test(
    session: AsyncSession, client: httpx.AsyncClient, kind: str
) -> tuple[bool, str]:
    """Send the most recent real firing to an admin transport (vestaboard/trmnl);
    falls back to a synthetic sample if nothing has fired yet.

    Returns (ok, message) for the admin UI — does not record a delivery row.
    """
    trigger, firing = await latest_firing_and_trigger(session)
    try:
        if kind == "vestaboard":
            code = await _send_vestaboard(session, client, None, trigger, firing)
            return True, f"Test sent (HTTP {code}) — check the board."
        elif kind == "trmnl":
            code = await _send_trmnl(session, client, None, trigger, firing)
            return True, f"Test sent (HTTP {code}). Reload the TRMNL Edit-Markup page — its preview renders from this push."
        else:
            return False, f"Unknown transport: {kind}"
    except ChannelNotConfigured as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001
        return False, f"Failed: {e}"


async def _dispatch_one(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
    trigger: Trigger,
    firing: TriggerFiring | None,
    is_test: bool,
) -> bool:
    """Try one channel; record the outcome. Returns True on success."""
    if channel.kind not in CHANNEL_KINDS:
        await _record(session, channel, firing, "failed",
                      f"Unknown channel kind: {channel.kind!r}", is_test)
        return False
    try:
        if channel.kind == "discord":
            await _send_discord(session, client, channel, trigger, firing)
        elif channel.kind == "email":
            await _send_email(session, channel, _format_message(trigger, firing, channel),
                              trigger=trigger, firing=firing)
        elif channel.kind == "webhook":
            base = await get_setting(session, "site_base_url") or ""
            await _send_generic_webhook(
                client, channel, _webhook_payload(trigger, firing, channel, base)
            )
        elif channel.kind == "sms_twilio":
            await _send_sms_twilio(
                session, client, channel, _format_message(trigger, firing, channel)
            )
        elif channel.kind == "vestaboard":
            await _send_vestaboard(session, client, channel, trigger, firing)
        elif channel.kind == "trmnl":
            await _send_trmnl(session, client, channel, trigger, firing)
        await _record(session, channel, firing, "sent", None, is_test)
        return True
    except ChannelNotConfigured as e:
        # Not a real failure — the transport/channel just isn't set up.
        log.info(
            "Channel %s (%s) skipped for trigger %s: %s",
            channel.id, channel.kind, trigger.id, e,
        )
        await _record(session, channel, firing, "skipped", str(e), is_test)
        return False
    except Exception as e:  # noqa: BLE001  -- one bad channel mustn't kill the others
        log.warning(
            "Channel %s (%s) failed for trigger %s: %s",
            channel.id, channel.kind, trigger.id, e,
        )
        await _record(session, channel, firing, "failed", str(e), is_test)
        return False


async def deliver_for_firings(
    session: AsyncSession,
    client: httpx.AsyncClient,
    firings: list[TriggerFiring],
) -> None:
    """Fan out each firing to its owner's active channels.

    Caller is responsible for committing afterwards — we add Delivery rows
    but don't commit, so the ingester can batch in one transaction.
    """
    enabled = ((await get_setting(session, "notifications_enabled")) or "true").lower() == "true"
    if not enabled or not firings:
        return

    # Batch-load triggers + channels to avoid N+1.
    trigger_ids = {f.trigger_id for f in firings}
    triggers = {
        t.id: t
        for t in (
            await session.execute(select(Trigger).where(Trigger.id.in_(trigger_ids)))
        ).scalars()
    }
    owner_ids = {t.owner_id for t in triggers.values()}
    chans = (
        await session.execute(
            select(NotificationChannel).where(
                NotificationChannel.user_id.in_(owner_ids),
                NotificationChannel.is_active.is_(True),
            )
        )
    ).scalars().all()
    by_owner: dict[int, list[NotificationChannel]] = {}
    for c in chans:
        by_owner.setdefault(c.user_id, []).append(c)

    # Per-trigger channel allow-lists. A trigger with no rows uses ALL channels.
    selections: dict[int, set[int]] = {}
    for tid, cid in (
        await session.execute(
            select(TriggerChannel.trigger_id, TriggerChannel.channel_id).where(
                TriggerChannel.trigger_id.in_(trigger_ids)
            )
        )
    ).all():
        selections.setdefault(tid, set()).add(cid)

    for firing in firings:
        trigger = triggers.get(firing.trigger_id)
        if trigger is None:
            continue
        allowed = selections.get(trigger.id)
        for channel in by_owner.get(trigger.owner_id, ()):
            if allowed is not None and channel.id not in allowed:
                continue
            await _dispatch_one(session, client, channel, trigger, firing, is_test=False)


async def send_test(
    session: AsyncSession,
    client: httpx.AsyncClient,
    channel: NotificationChannel,
) -> bool:
    """Send the most recent real firing through one channel (or a synthetic
    sample if nothing has fired). Used by the profile UI."""
    trigger, firing = await latest_firing_and_trigger(session)
    return await _dispatch_one(session, client, channel, trigger, firing, is_test=True)
