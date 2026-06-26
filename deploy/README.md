# Deployment

How to run ADSBuddy as a long-lived service: Docker Compose for the stack, an
optional systemd unit so it survives reboots, notes on the database (bundled vs.
external), and a forward-looking section on co-locating with adsb-im on a
Raspberry Pi.

For the 2-minute first run, see **Quick install** in the top-level
[`README.md`](../README.md). This document is the operational reference.

---

## What runs

ADSBuddy is a Docker Compose stack of (normally) two containers:

- **`app`** — the ADSBuddy image. On start it runs `alembic upgrade head` then
  serves on container port `8000`. The Compose port map binds it to
  `127.0.0.1` and your tailnet IP only — never a public interface.
- **`db`** — `postgres:16`, with data in the named volume `adsbuddy_pgdata`
  (survives restarts and image upgrades; `docker compose down -v` wipes it).

Three Compose files are provided — pick one:

| File | Postgres | Image | Use when |
|------|----------|-------|----------|
| `docker-compose.ghcr.yml` | bundled `db` container | pulled from GHCR | **Most deployments.** No build. |
| `docker-compose.yml` | bundled `db` container | built from source | Development / local changes. |
| `docker-compose.external-db.yml` | **external** (you run it) | pulled from GHCR | Low-write hosts (Raspberry Pi / SD card). |

All three read the same `.env`. To avoid typing `-f <file>` every time, set
`COMPOSE_FILE` in `.env` (see below) and just run `docker compose ...`.

---

## Run with Docker Compose

### Released image (recommended)

```bash
ADSBUDDY_IMAGE_TAG=1.0.1 docker compose -f docker-compose.ghcr.yml up -d
docker compose -f docker-compose.ghcr.yml logs -f app     # watch it come up
```

Pin a version with `ADSBUDDY_IMAGE_TAG` (omit to track `:latest`). Upgrade by
bumping the tag and re-running `up -d`.

### Build from source

```bash
git pull
ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build
```

The `ADSBUDDY_GIT_SHA` prefix bakes the commit into the image so the site footer
shows the deployed version (linked to GitHub) alongside uptime. Omit it and the
footer just reads `dev`.

### Make the file choice sticky

Rather than passing `-f` each time, put the selection in `.env`:

```dotenv
# .env
COMPOSE_FILE=docker-compose.ghcr.yml
ADSBUDDY_IMAGE_TAG=1.0.1
```

Then `docker compose up -d`, `docker compose logs -f app`, etc. all use that
file — which is also what the systemd unit below invokes.

---

## Run under systemd (start on boot)

A unit is provided so the stack comes up on boot and restarts on failure (via
each container's `restart: unless-stopped`).

The shipped [`adsbuddy.service`](adsbuddy.service) runs `docker compose` from
`WorkingDirectory=/home/cdibona/ADSBuddy` — **edit that path** for your install,
and make sure `.env` lives in that directory (it's where Compose reads it).
If you set `COMPOSE_FILE` in `.env` (above), the unit needs no other changes.

```bash
sudo cp deploy/adsbuddy.service /etc/systemd/system/adsbuddy.service
# edit WorkingDirectory if your checkout isn't /home/cdibona/ADSBuddy
sudo systemctl daemon-reload
sudo systemctl enable --now adsbuddy.service     # enable = on boot; --now = start it
```

### Operate

```bash
systemctl status adsbuddy            # service state
sudo systemctl restart adsbuddy      # restart the whole stack
sudo systemctl stop adsbuddy         # docker compose down
docker compose ps                    # container-level view (from the work dir)
docker compose logs -f app           # tail app logs
```

The boot unit intentionally does **not** rebuild/pull on every boot (keeps boot
fast and reliable). To ship a new version, run the appropriate `up -d` from the
Docker section above, then optionally `systemctl restart adsbuddy`.

---

## Database: bundled vs. external

By default (`docker-compose.ghcr.yml` / `docker-compose.yml`) ADSBuddy runs its
**own** Postgres container — zero setup, data in the `adsbuddy_pgdata` volume.

To use an **external** Postgres instead (you run the database elsewhere), use
`docker-compose.external-db.yml`, which starts only the `app` container:

1. Create the database and a role on your Postgres server:

   ```sql
   CREATE ROLE adsbuddy LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE adsbuddy OWNER adsbuddy;
   ```

   The role needs DDL rights on that database — the app runs
   `alembic upgrade head` on every start.

2. Point `.env` at it:

   ```dotenv
   POSTGRES_HOST=192.168.1.50      # your Postgres host (not "db")
   POSTGRES_PORT=5432
   POSTGRES_USER=adsbuddy
   POSTGRES_PASSWORD=choose-a-password
   POSTGRES_DB=adsbuddy
   ```

3. Run app-only:

   ```bash
   docker compose -f docker-compose.external-db.yml up -d
   ```

Back it up like any Postgres (`pg_dump adsbuddy`). The bundled-Postgres volume
can be archived with:
`docker run --rm -v adsbuddy_pgdata:/v -v "$PWD":/b alpine tar czf /b/pgdata.tgz -C /v .`

---

## Raspberry Pi alongside adsb-im (planned)

The eventual target is running ADSBuddy on the same Pi that already runs
[adsb-feeder-image](https://github.com/dirkhh/adsb-feeder-image) (adsb.im). It's
the same Docker Compose stack; the Pi-specific considerations:

- **Keep the database off the SD card.** ADSBuddy writes a sighting row per
  aircraft per tick — steady writes that will wear a typical SD card. Prefer
  `docker-compose.external-db.yml` with Postgres on another host (a NAS, a small
  always-on box, or a managed instance). If the database must live on the Pi,
  put `adsbuddy_pgdata` on an SSD / USB-attached disk rather than the SD card,
  and raise `sighting_min_interval_seconds` (Admin → System) to cut write
  volume. The de-dup + retention controls already bound growth.
- **Point ADSBuddy at the local radio.** adsb-im serves tar1090 on the Pi; set
  `radio_base_url` (Admin → System) to the local feeder, e.g.
  `http://127.0.0.1:8080` (or whatever host/port adsb-im exposes).
- **Mind the ports.** adsb-im already uses common ports (often `8080`); pick a
  free `ADSBUDDY_PORT` in `.env` so the two don't collide.
- **Architecture.** The image uses the standard `python:3.12-slim` base; if a
  given tag isn't published for arm64, build on the Pi with `docker-compose.yml`.
  Check with
  `docker image inspect ghcr.io/cdibona/adsbuddy:<tag> --format '{{.Architecture}}'`.

This section is a sketch, not yet a tested runbook — it'll firm up once the Pi
co-install is exercised.

---

## TLS / remote access

ADSBuddy binds to localhost + the tailnet IP only and speaks plain HTTP. For
HTTPS across the tailnet, front it with **Tailscale Serve** (terminates TLS and
proxies to the app port), e.g. `tailscale serve --bg <ADSBUDDY_PORT>` mapping
your `<host>.ts.net` name to the local app. Set `site_base_url` (Admin → System)
to that HTTPS URL so notification links and OAuth redirect URIs are absolute.

## Notes

- Configuration the app needs to boot lives in `.env` (gitignored); everything
  else (radio URL, ingest cadence, API keys, alert rules) lives in the Postgres
  `settings` table and is edited from the admin UI.
- `ADSBUDDY_TEST_MODE=1` exposes `/test/login` for E2E suites — leave it `0` in
  any real deployment.
