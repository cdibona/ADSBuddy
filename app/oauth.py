"""OAuth / SSO: provider wiring (Authlib) + account linking.

Dormant until an admin sets a provider's client id/secret. Local/tailnet login
is untouched. Linking: an external identity maps to a local user by a stored
(provider, subject); failing that, by matching the user's email; failing that,
a new user is created only when oauth_auto_provision is on.
"""
from __future__ import annotations

import logging

from authlib.integrations.starlette_client import OAuth
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserIdentity
from app.security import new_session_id
from app.settings_store import get as get_setting

log = logging.getLogger(__name__)

PROVIDERS = ("google", "github")
_GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"


async def provider_credentials(db: AsyncSession, provider: str) -> tuple[str, str] | None:
    """(client_id, client_secret) for a provider, or None if not configured."""
    cid = (await get_setting(db, f"oauth_{provider}_client_id")) or ""
    secret = (await get_setting(db, f"oauth_{provider}_client_secret")) or ""
    if cid.strip() and secret.strip():
        return cid.strip(), secret.strip()
    return None


async def configured_providers(db: AsyncSession) -> list[str]:
    """Providers that have credentials set (for showing login buttons)."""
    out = []
    for p in PROVIDERS:
        if await provider_credentials(db, p):
            out.append(p)
    return out


def build_client(provider: str, client_id: str, client_secret: str):
    """A fresh Authlib client for one provider (config lives in the DB, so we
    build per-request rather than registering at startup)."""
    oauth = OAuth()
    if provider == "google":
        oauth.register(
            name="google",
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=_GOOGLE_DISCOVERY,
            client_kwargs={"scope": "openid email profile"},
        )
    elif provider == "github":
        oauth.register(
            name="github",
            client_id=client_id,
            client_secret=client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={"scope": "read:user user:email"},
        )
    else:
        raise ValueError(f"Unknown provider {provider!r}")
    return getattr(oauth, provider)


async def fetch_identity(provider: str, client, request) -> tuple[str, str | None]:
    """Complete the callback and return (subject, email)."""
    token = await client.authorize_access_token(request)
    if provider == "google":
        info = token.get("userinfo") or await client.userinfo(token=token)
        return str(info["sub"]), (info.get("email") or None)
    # github
    resp = await client.get("user", token=token)
    u = resp.json()
    email = u.get("email")
    if not email:
        er = await client.get("user/emails", token=token)
        emails = er.json() if er.status_code == 200 else []
        primary = next((e for e in emails if e.get("primary")), None)
        primary = primary or (emails[0] if emails else None)
        email = primary.get("email") if primary else None
    return str(u["id"]), (email or None)


async def _unique_username(db: AsyncSession, base: str) -> str:
    base = (base or "user").strip().lower() or "user"
    candidate = base
    n = 1
    while (await db.execute(select(User.id).where(User.username == candidate))).first():
        n += 1
        candidate = f"{base}{n}"
    return candidate


async def resolve_user(
    db: AsyncSession, provider: str, subject: str, email: str | None, auto_provision: bool
) -> User | None:
    """Map an external identity to a local user (linking/provisioning). Caller commits."""
    ident = (
        await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider, UserIdentity.subject == subject
            )
        )
    ).scalar_one_or_none()
    if ident is not None:
        user = (await db.execute(select(User).where(User.id == ident.user_id))).scalar_one_or_none()
        if user and user.is_active:
            return user
        return None

    if email:
        user = (
            await db.execute(select(User).where(func.lower(User.email) == email.lower()))
        ).scalar_one_or_none()
        if user is not None:
            if not user.is_active:
                return None
            db.add(UserIdentity(user_id=user.id, provider=provider, subject=subject, email=email))
            await db.commit()
            return user

    if auto_provision and email:
        user = User(
            username=await _unique_username(db, email.split("@", 1)[0]),
            password_hash=new_session_id(),  # unusable random; OAuth-only account
            is_admin=False,
            is_active=True,
            email=email,
        )
        db.add(user)
        await db.flush()
        db.add(UserIdentity(user_id=user.id, provider=provider, subject=subject, email=email))
        await db.commit()
        return user

    return None
