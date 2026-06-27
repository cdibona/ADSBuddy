"""App version + uptime, surfaced in the page footer.

The git SHA is baked into the image at build time via the ADSBUDDY_GIT_SHA
build arg (see Dockerfile / docker-compose.yml); it falls back to "dev" for
local runs that don't pass it. Uptime is measured from process start.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from fastapi.templating import Jinja2Templates

GITHUB_REPO = "https://github.com/cdibona/ADSBuddy"
GITHUB_API_LATEST = "https://api.github.com/repos/cdibona/ADSBuddy/releases/latest"
# "How to update your Docker container" section in the deployment notes.
UPDATE_DOCS_URL = f"{GITHUB_REPO}/blob/main/deploy/README.md#how-to-update-your-docker-container"

GIT_SHA = (os.environ.get("ADSBUDDY_GIT_SHA") or "dev").strip() or "dev"
# Release version (e.g. "1.2.3"), baked from the git tag at build time. "dev"
# for local/source builds — we only show the update badge for real versions.
VERSION = (os.environ.get("ADSBUDDY_VERSION") or "dev").strip() or "dev"

# Captured at import (≈ process start), used to compute uptime.
STARTED_AT = datetime.now(timezone.utc)

_PLACEHOLDER_SHAS = {"dev", "unknown", ""}

# Latest release tag seen from GitHub (refreshed periodically by the ingester).
_latest_release: str | None = None


def _semver(tag: str) -> tuple[int, ...] | None:
    """Parse 'v1.2.3' / '1.2.3' → (1, 2, 3); None if it isn't plain semver."""
    s = (tag or "").strip().lstrip("vV")
    parts = s.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def set_latest_release(tag: str | None) -> None:
    global _latest_release
    _latest_release = (tag or "").strip() or None


def update_available() -> str | None:
    """The latest release tag if it's newer than what's running, else None."""
    cur, latest = _semver(VERSION), _semver(_latest_release or "")
    if cur is None or latest is None:
        return None
    return _latest_release if latest > cur else None


async def refresh_latest_release(client) -> None:
    """Fetch the latest GitHub release tag into the cache. Best-effort/silent —
    network errors, rate limits, and offline appliances just leave it unset."""
    if _semver(VERSION) is None:
        return  # source/dev build — nothing to compare against
    try:
        resp = await client.get(
            GITHUB_API_LATEST, headers={"Accept": "application/vnd.github+json"}, timeout=8.0
        )
        if resp.status_code == 200:
            set_latest_release(resp.json().get("tag_name"))
    except Exception:  # noqa: BLE001
        pass


def github_commit_url() -> str | None:
    """Link to the deployed commit on GitHub, or None for placeholder SHAs."""
    if GIT_SHA in _PLACEHOLDER_SHAS:
        return None
    return f"{GITHUB_REPO}/commit/{GIT_SHA}"


def uptime_str(now: datetime | None = None) -> str:
    """Human-readable uptime since process start (e.g. '2d 3h 7m')."""
    now = now or datetime.now(timezone.utc)
    secs = max(0, int((now - STARTED_AT).total_seconds()))
    days, rem = divmod(secs, 86_400)
    hours, rem = divmod(rem, 3_600)
    mins = rem // 60
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    # Always show minutes so very fresh processes don't render an empty string.
    if mins or not parts:
        parts.append(f"{mins}m")
    return " ".join(parts)


def register(templates: Jinja2Templates) -> None:
    """Expose version/uptime helpers as Jinja globals for the footer.

    Must be called for every Jinja2Templates instance that renders a page
    extending base.html (i.e. all of them), or base.html's footer would raise
    an undefined-global error.
    """
    from app.config import get_settings

    templates.env.globals.update(
        app_git_sha=GIT_SHA,
        app_version=VERSION,
        app_commit_url=github_commit_url(),
        app_uptime=uptime_str,
        app_started_at=STARTED_AT,
        app_update_available=update_available,
        app_releases_url=f"{GITHUB_REPO}/releases/latest",
        app_update_docs_url=UPDATE_DOCS_URL,
        ephemeral_db=get_settings().ephemeral_db,
        open_mode=get_settings().open_mode,
    )
