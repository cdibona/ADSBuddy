# ADSBuddy

**Know what's flying over your house — and get pinged when something interesting does.**

ADSBuddy turns your local ADS-B radio (an
[adsb-feeder-image](https://github.com/dirkhh/adsb-feeder-image) / adsb.im box)
into a searchable aircraft database with a real alerting engine. It polls the
radio's `aircraft.json` (or accepts a push feed), records every sighting in
Postgres, and watches the sky against rules you define — then tells you on
whatever screen you like, from Discord to a Vestaboard to an e-ink TRMNL.

Out of the box it ships a curated watchlist of **celebrity jets**, **Air Force
One**, an **emergency-squawk** rule (7500/7600/7700), and a **75+-year-old
vintage aircraft** alert — so it's doing something interesting the minute it
boots. One command installs it.

```bash
curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
```

## What it does

- **🛩️ Aircraft database & history.** Every aircraft and sighting lands in
  Postgres. Search history by tail, hex, callsign, type, operator, year, or
  route, with paging and quick type filters. Each aircraft gets a detail page
  with its recent flight path on a map and deep links to the FAA registry, the
  type's Wikipedia page, and other trackers.
- **🔔 A real trigger engine.** Alert on tail numbers, callsigns, ICAO type
  codes, operators, **emergency squawks**, **altitude bands** (e.g. helicopters
  under 1000 ft), aircraft **age** ("anything older than 50 years"), ADS-B
  emitter category, and **geofences** (within N miles of a point). Add exclusions,
  per-trigger cooldowns, and pause/resume — all from the web UI.
- **📣 Notifications, your way.** Route firings to **Discord**, **email**,
  **webhooks**, **SMS** (Twilio), a **Vestaboard** split-flap, or a **TRMNL**
  e-ink display. Each trigger picks its own channels; each channel has a mode —
  *everything*, *emergencies only*, or *periodic summary*.
- **📺 The airspace "summary" device.** Point a TRMNL (or any summary-mode
  channel) at your sky and it shows a live digest: aircraft count plus a fun
  breakdown — helicopters, light planes, private jets, cargo, seaplanes,
  airliners — and the last notable alert.
- **📊 Stats & a public guest view.** A `/stats` dashboard shows the live
  airspace breakdown. Flip on **guest mode** to share read-only aircraft,
  history, the map, and stats with the household — no account needed.
- **🌍 Community watchlists.** Built a great trigger? Submit it as a one-click
  **pull request**; merged triggers ship to everyone on the next release, and
  deployments pick them up automatically.
- **🔄 Self-updating.** The installer wires up auto-updates and the menu shows
  an "update available" badge when a new release lands.

Built to run on the local tailnet, backed by Postgres, embedding the radio's
tar1090 map. **Roadmap:** AIS for boats, and mobile / smart-glasses clients that
label the planes physically overhead.

## Quick install

```bash
curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
```

That installs the **latest release** and starts it in **open mode** (no login —
for a trusted appliance like an adsb-im Pi). If Docker isn't installed it offers
to install it (via the official `get.docker.com` script, needs sudo). It
generates the session secret,
binds to all interfaces, asks which radio to poll (default
`http://127.0.0.1:8080`), and picks a free web port (starting at 8000, walking
up if it's taken) — the installer prints the URL. It's already ingesting;
configure everything in the app. To force a port, pipe into an env-prefixed
shell — `curl -fsSL …/install.sh | ADSBUDDY_PORT=8090 sh` — or edit
`ADSBUDDY_PORT` in `adsbuddy/.env` and re-run
`docker compose -f docker-compose.ghcr.yml up -d`.

Want logins (guest / user / admin)? Set `ADSBUDDY_MODE=MultiUser` in
`adsbuddy/.env`, re-run `docker compose -f docker-compose.ghcr.yml up -d`, and
sign in as `admin` / `AdminChangeMe`. For external Postgres, systemd, Raspberry
Pi notes, and other options, see **[`deploy/README.md`](deploy/README.md)**.

## Build from source (development)

To build the image locally from a checkout instead of pulling a release:

```bash
cp .env.template .env
$EDITOR .env                          # set secret, passwords, bind address
ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up --build
```

(The `ADSBUDDY_GIT_SHA` prefix bakes the commit into the image so the footer
shows the deployed version; plain `docker compose up --build` works too and
just shows `dev`.)

## Deployment

For running ADSBuddy as a long-lived service — systemd unit, choosing a Compose
file, using an **external Postgres** (recommended on a Raspberry Pi to spare the
SD card), and co-locating with adsb-im — see **[`deploy/README.md`](deploy/README.md)**.

## Configuration

- `.env` (gitignored) holds **only** the handful of values the app needs to
  boot: the web port, the bind address, Postgres credentials, a
  session-signing secret, the first-run admin username/password, and optionally
  `ADSBUDDY_RADIO_URL` to pre-seed your adsb-im radio on first boot. See
  `.env.template` for the full list with comments.
- **Everything else** — the radio source(s), the aircraft.json polling interval,
  alert rules — lives in the Postgres `settings`/`radio_sources` tables and is
  editable from the admin UI (Sources, System, …).

### Access mode

`ADSBUDDY_MODE` in `.env` selects the access model:

- **`MultiUser`** (default) — guest / user / admin with logins (local password,
  OAuth, and/or Tailscale sign-in; optional read-only guest access).
- **`open`** — **no login at all; every visitor has full admin.** Intended for a
  trusted single appliance (e.g. an adsb-im Pi) reachable only on your
  tailnet/LAN. The UI shows a permanent "open mode" banner. Do **not** use it on
  a shared or public network.

## Users

- A single admin user is created on first boot from
  `ADSBUDDY_ADMIN_USERNAME` / `ADSBUDDY_ADMIN_PASSWORD`. **Change the password
  immediately** after the first login.
- Admins can create additional users (admin or non-admin) from the admin page.

## Testing

`ADSBUDDY_TEST_MODE=1` enables `/test/login`, an endpoint that mints a session
cookie for a named user without driving the login form. Intended for
Playwright / E2E suites only. Leave it off (`0`) in any deployment you care
about; the production Docker image defaults it off.

## Releases

Tagged releases publish a container image to GHCR automatically. Pushing a
`vX.Y.Z` tag runs the `Release image` workflow, which builds and pushes
`ghcr.io/cdibona/adsbuddy:<version>`, `:<major>.<minor>`, and `:latest`.

```bash
git tag -a v1.0.2 -m "ADSBuddy v1.0.2"
git push origin v1.0.2
gh release create v1.0.2 --generate-notes
```

Deploy a release with `docker-compose.ghcr.yml` (see **Quick install** above).

## Architecture (v1)

- **Backend:** FastAPI + SQLAlchemy (async) + Alembic.
- **Frontend:** Jinja2 templates with a thin layer of vanilla JS.
- **Map page:** iframes the radio's tar1090 UI so the look matches your
  existing adsb.im. We separately ingest the radio's `/data/aircraft.json`
  into Postgres so the database and alerting layers have data to work on.
- **Database:** Postgres 16, container-managed via Docker Compose.

## License

See `LICENSE`.
