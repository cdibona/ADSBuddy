"""FastAPI app entry point. Wires routers, runs first-boot bootstrap, and
starts the background aircraft.json ingester."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app import (
    bootstrap,
    ingest,
    routes_admin,
    routes_auth,
    routes_pages,
    routes_triggers,
)
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
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(routes_auth.router)
app.include_router(routes_pages.router)
app.include_router(routes_triggers.router)
app.include_router(routes_admin.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
