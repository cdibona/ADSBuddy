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

GIT_SHA = (os.environ.get("ADSBUDDY_GIT_SHA") or "dev").strip() or "dev"

# Captured at import (≈ process start), used to compute uptime.
STARTED_AT = datetime.now(timezone.utc)

_PLACEHOLDER_SHAS = {"dev", "unknown", ""}


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
    templates.env.globals.update(
        app_git_sha=GIT_SHA,
        app_commit_url=github_commit_url(),
        app_uptime=uptime_str,
        app_started_at=STARTED_AT,
    )
