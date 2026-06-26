"""FastAPI app entry point. Wires routers, runs first-boot bootstrap, and
starts the background aircraft.json ingester."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app import (
    bootstrap,
    ingest,
    routes_admin,
    routes_auth,
    routes_ingest,
    routes_oauth,
    routes_pages,
    routes_profile,
    routes_tailscale,
    routes_triggers,
)
from app.config import get_settings
from app.database import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with SessionLocal() as session:
        await bootstrap.run(session)
    stop_event = asyncio.Event()
    ingest_task = asyncio.create_task(ingest.run_forever(stop_event), name="adsb-ingest")
    try:
        yield
    finally:
        stop_event.set()
        await ingest_task


app = FastAPI(title="ADSBuddy", lifespan=lifespan)
# Signed-cookie session used only for the transient OAuth handshake state
# (Authlib stores state/nonce/PKCE here). App login uses its own DB-backed
# cookie, not this.
app.add_middleware(
    SessionMiddleware,
    secret_key=get_settings().secret_key,
    same_site="lax",
    https_only=False,  # behind Tailscale Serve TLS; cookie is transient state only
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(routes_auth.router)
app.include_router(routes_pages.router)
app.include_router(routes_triggers.router)
app.include_router(routes_profile.router)
app.include_router(routes_admin.router)
app.include_router(routes_ingest.router)
app.include_router(routes_oauth.router)
app.include_router(routes_tailscale.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
