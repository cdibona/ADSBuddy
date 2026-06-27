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
  `ADSBUDDY_BIND` (default `127.0.0.1` — localhost only).
- **`db`** — `postgres:16`, with data in the named volume `adsbuddy_pgdata`
  (survives restarts and image upgrades; `docker compose down -v` wipes it).

Four Compose files are provided — pick one:

| File | Postgres | Image | Use when |
|------|----------|-------|----------|
| `docker-compose.ghcr.yml` | bundled `db` container | pulled from GHCR | **Most deployments.** No build. |
| `docker-compose.yml` | bundled `db` container | built from source | Development / local changes. |
| `docker-compose.external-db.yml` | **external** (you run it) | pulled from GHCR | Low-write hosts (Raspberry Pi / SD card). |
| `docker-compose.pi.yml` | bundled, **in RAM (tmpfs)** | pulled from GHCR | Single Pi, no SD wear — **but volatile** (see below). |

All four read the same `.env`. To avoid typing `-f <file>` every time, set
`COMPOSE_FILE` in `.env` (see below) and just run `docker compose ...`.

---

## Run with Docker Compose

### Released image (recommended)

```bash
ADSBUDDY_IMAGE_TAG=1.1.1 docker compose -f docker-compose.ghcr.yml up -d
docker compose -f docker-compose.ghcr.yml logs -f app     # watch it come up
```

Pin a version with `ADSBUDDY_IMAGE_TAG` (omit to track `:latest`). Upgrade by
bumping the tag and re-running `up -d`.

### How to update your Docker container

When the app's menu shows an **"⬆ update available"** badge (or you just want the
newest release), pick whichever path matches how you installed:

**1. Re-run the one-line installer (easiest).** It finds your existing install
(by asking Docker where the running container's compose project lives), reuses
that directory and its `.env`, pulls the latest image, and recreates in place —
no duplicate directory, your database untouched:

```bash
curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
```

**2. By hand with Docker Compose.** From your install directory (the one with
`.env`):

```bash
docker compose -f docker-compose.ghcr.yml pull      # fetch the new image
docker compose -f docker-compose.ghcr.yml up -d     # recreate the app
docker image prune -f                               # (optional) drop the old image
```

Pinning a specific version? Set `ADSBUDDY_IMAGE_TAG=1.2.4` in `.env` (or omit to
track `:latest`) before the `up -d`. Your Postgres data lives in the
`adsbuddy_pgdata` volume and is untouched by updates; the app runs
`alembic upgrade head` on start, so schema migrations apply automatically.

**3. Automatic.** The installer also runs a **Watchtower** sidecar
(`docker-compose.autoupdate.yml`) that polls GHCR hourly and updates the app in
place when a new release ships — only the app (it's label-enabled), never
Postgres. Opt out with `ADSBUDDY_NO_AUTOUPDATE=1`, or change the cadence with
`WATCHTOWER_POLL_INTERVAL` (seconds) in `.env`.

See the [release notes](https://github.com/cdibona/ADSBuddy/releases) for what
changed in each version.

### Uninstalling

```bash
curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/uninstall.sh | sh
```

Stops and removes the containers, network, and the auto-updater, but **keeps
your database volume and `.env`** so you can reinstall without data loss. To
delete the database too (irreversible), run `… | PURGE=1 sh`. By hand:
`docker compose -f docker-compose.ghcr.yml -f docker-compose.autoupdate.yml down`
(add `-v` to drop the data volume).

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
ADSBUDDY_IMAGE_TAG=1.1.1
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
- **Point ADSBuddy at the local radio.** adsb-im serves tar1090 on the Pi. Set
  `ADSBUDDY_RADIO_URL` in `.env` (e.g. `http://127.0.0.1:8080`, or whatever
  host/port adsb-im exposes) to seed it on first boot, or add it later under
  **Admin → Sources**.
- **Mind the ports.** adsb-im already uses common ports (often `8080`); pick a
  free `ADSBUDDY_PORT` in `.env` so the two don't collide.
- **Architecture.** The image uses the standard `python:3.12-slim` base; if a
  given tag isn't published for arm64, build on the Pi with `docker-compose.yml`.
  Check with
  `docker image inspect ghcr.io/cdibona/adsbuddy:<tag> --format '{{.Architecture}}'`.

This section is a sketch, not yet a tested runbook — it'll firm up once the Pi
co-install is exercised.

### In-memory (tmpfs) mode — `docker-compose.pi.yml`

If you want everything on the Pi with **zero database writes to the SD card**,
`docker-compose.pi.yml` runs Postgres entirely in RAM (`tmpfs`):

```bash
ADSBUDDY_IMAGE_TAG=1.1.1 docker compose -f docker-compose.pi.yml up -d
```

> ⚠ **The database is volatile.** Every reboot (or `docker compose down`) wipes
> *everything* — triggers, settings, channels, users, and history all reset to
> defaults. The app shows a permanent in-memory warning banner in this mode.
>
> **If you want to keep any of that, don't use this file — use
> `docker-compose.external-db.yml` with Postgres on another host.** tmpfs mode
> is for a demo / "just show me the live airspace" box, or a Pi where you're
> happy to re-bootstrap config on each boot.

---

## TLS / remote access

ADSBuddy binds to `ADSBUDDY_BIND` (default `127.0.0.1`) and speaks plain HTTP. For
HTTPS across the tailnet, front it with **Tailscale Serve** (terminates TLS and
proxies to the app port), e.g. `tailscale serve --bg <ADSBUDDY_PORT>` mapping
your `<host>.ts.net` name to the local app. Set `site_base_url` (Admin → System)
to that HTTPS URL so notification links and OAuth redirect URIs are absolute.

## Access mode: open vs. MultiUser (`ADSBUDDY_MODE`)

`ADSBUDDY_MODE` in `.env` chooses the access model:

- **`MultiUser`** (default) — the full guest / user / admin model with logins
  (local password, OAuth, Tailscale identity; optional read-only guest access).
- **`open`** — **no login; every request is treated as the admin.** No session,
  no password, admin settings fully exposed. The UI shows a permanent "open
  mode" banner.

Open mode is for a **trusted single appliance** — e.g. ADSBuddy running in a
container on the same adsb-im Pi, reachable only on your tailnet/LAN. Because
anyone who can reach the app gets full admin, only use it where the network is
trusted (and keep the tailnet-only / localhost binding). Switching modes needs
no data changes — just set `ADSBUDDY_MODE` and restart:

```dotenv
# .env  (on a dedicated radio appliance)
ADSBUDDY_MODE=open
```

The bootstrap admin (from `ADSBUDDY_ADMIN_USERNAME`) is still created and is the
identity open-mode requests act as, so triggers/channels are owned normally.

## Tailscale identity sign-in (Admin → Users)

ADSBuddy can sign users in from **Tailscale Serve identity headers**
(`Tailscale-User-Login`) — set `tailscale_auth_enabled=true`. Serve injects the
requester's tailnet identity (usually their email) on each proxied request, and
ADSBuddy matches it to a user the same way OAuth does.

**This is only safe if the app is reachable *exclusively* through Serve.** Any
client that can hit the app directly can forge those headers. So:

1. **Bind localhost-only.** In your `.env`-driven compose, the app publishes on
   whatever `ADSBUDDY_BIND` is set to. For header auth keep it at the default
   `127.0.0.1` so the only way in is `tailscale serve → 127.0.0.1:<port>` (do not
   set `ADSBUDDY_BIND=0.0.0.0`).

2. **Set the trusted proxy.** ADSBuddy refuses the header unless the request's
   peer is in `tailscale_trusted_proxies` (fail-closed). Behind Serve→Docker the
   peer is the Docker bridge gateway; the Admin → Users page shows the exact IP
   it currently sees — add it (e.g. `172.17.0.1/32`).

3. **Verify, then optionally disable passwords.** Confirm you can sign in via
   the "Continue as …" button, then set `local_login_enabled=false`. Recovery if
   you lock yourself out:
   `docker compose exec db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c
   "UPDATE settings SET value='true' WHERE key='local_login_enabled';"`

Note: for a **GitHub-backed** tailnet the login is `user@github`, not a real
email — set that as the user's email in ADSBuddy for the match to work.

## Notes

- Configuration the app needs to boot lives in `.env` (gitignored) — including
  the optional `ADSBUDDY_RADIO_URL` that pre-seeds the radio on first boot.
  Everything else (radio source(s), ingest cadence, alert rules) lives in the
  Postgres `settings`/`radio_sources` tables and is edited from the admin UI.
- `ADSBUDDY_TEST_MODE=1` exposes `/test/login` for E2E suites — leave it `0` in
  any real deployment.
