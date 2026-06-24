"""OAuth login/callback routes. Additive — local/tailnet auth is unchanged."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app import oauth as oauth_mod
from app.database import get_session
from app.routes_auth import _start_session
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)
router = APIRouter()


def _redirect_uri(request: Request, base: str, provider: str) -> str:
    base = (base or str(request.base_url)).rstrip("/")
    return f"{base}/auth/oauth/{provider}/callback"


@router.get("/auth/oauth/{provider}/login")
async def oauth_login(provider: str, request: Request, db: AsyncSession = Depends(get_session)):
    if provider not in oauth_mod.PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    creds = await oauth_mod.provider_credentials(db, provider)
    if creds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not configured")
    client = oauth_mod.build_client(provider, *creds)
    base = await get_setting(db, "site_base_url") or ""
    return await client.authorize_redirect(request, _redirect_uri(request, base, provider))


@router.get("/auth/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request, db: AsyncSession = Depends(get_session)):
    if provider not in oauth_mod.PROVIDERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    creds = await oauth_mod.provider_credentials(db, provider)
    if creds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    client = oauth_mod.build_client(provider, *creds)
    try:
        subject, email = await oauth_mod.fetch_identity(provider, client, request)
    except Exception:
        log.exception("OAuth callback failed for provider %s", provider)
        return RedirectResponse(url="/login?error=oauth", status_code=status.HTTP_303_SEE_OTHER)

    auto = ((await get_setting(db, "oauth_auto_provision")) or "false").lower() == "true"
    user = await oauth_mod.resolve_user(db, provider, subject, email, auto)
    if user is None:
        return RedirectResponse(url="/login?error=noaccount", status_code=status.HTTP_303_SEE_OTHER)

    resp = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    await _start_session(db, user, resp)
    return resp
