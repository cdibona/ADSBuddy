"""Tailscale Serve identity sign-in route. Additive — local/OAuth auth unchanged."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import oauth, tailscale_auth
from app.database import get_session
from app.routes_auth import _start_session
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/auth/tailscale/login")
async def tailscale_login(request: Request, db: AsyncSession = Depends(get_session)):
    ident = await tailscale_auth.tailscale_identity(request, db)
    if ident is None:
        # Not enabled, peer not trusted, or no header — bounce to the form with
        # ?manual so the login page doesn't auto-redirect back into a loop.
        return RedirectResponse(url="/login?error=ts_unavailable&manual=1",
                                status_code=status.HTTP_303_SEE_OTHER)
    login, name = ident
    auto = ((await get_setting(db, "oauth_auto_provision")) or "false").lower() == "true"
    # Reuse the OAuth linking logic: match a stored identity, else a user whose
    # email equals the tailnet login, else auto-provision when enabled.
    user = await oauth.resolve_user(db, "tailscale", login, login, auto)
    if user is None:
        log.info("Tailscale login for %r matched no account.", login)
        return RedirectResponse(url="/login?error=ts_noaccount&manual=1",
                                status_code=status.HTTP_303_SEE_OTHER)
    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    await _start_session(db, user, resp)
    return resp
