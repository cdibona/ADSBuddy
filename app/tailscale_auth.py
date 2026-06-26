"""Tailscale Serve identity-header sign-in.

When the app sits behind `tailscale serve`, Tailscale injects identity headers
on each proxied request — `Tailscale-User-Login` (the tailnet login, usually an
email) and `Tailscale-User-Name` (display name). We can trust those to sign a
user in *only* when the request actually came through Serve.

Because any client that can reach the app directly could forge those headers,
this is FAIL-CLOSED: the header is honored only when the request's immediate
peer is in the admin-set `tailscale_trusted_proxies` allowlist (and the feature
is enabled). The real guarantee still comes from the deployment binding the app
to localhost-only and fronting it with Serve — see deploy/README.md.
"""
from __future__ import annotations

import ipaddress
import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.settings_store import get as get_setting

log = logging.getLogger(__name__)

LOGIN_HEADER = "tailscale-user-login"
NAME_HEADER = "tailscale-user-name"


async def tailscale_enabled(db: AsyncSession) -> bool:
    return ((await get_setting(db, "tailscale_auth_enabled")) or "false").lower() == "true"


def peer_trusted(client_host: str | None, trusted_csv: str | None) -> bool:
    """True if client_host falls in one of the trusted IPs/CIDRs. Fail-closed:
    blank allowlist or unparseable address → not trusted."""
    cidrs = [c.strip() for c in (trusted_csv or "").split(",") if c.strip()]
    if not cidrs or not client_host:
        return False
    try:
        ip = ipaddress.ip_address(client_host)
    except ValueError:
        return False
    for c in cidrs:
        try:
            if ip in ipaddress.ip_network(c, strict=False):
                return True
        except ValueError:
            continue
    return False


async def tailscale_identity(request: Request, db: AsyncSession) -> tuple[str, str | None] | None:
    """(login, display_name) from trusted Serve headers, or None if the feature
    is off, the peer isn't trusted, or no header is present."""
    if not await tailscale_enabled(db):
        return None
    trusted = await get_setting(db, "tailscale_trusted_proxies")
    client_host = request.client.host if request.client else None
    if not peer_trusted(client_host, trusted):
        return None
    login = (request.headers.get(LOGIN_HEADER) or "").strip()
    if not login:
        return None
    name = (request.headers.get(NAME_HEADER) or "").strip() or None
    return login, name
