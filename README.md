# ADSBuddy

A personal aggregation and alerting layer over the user's local ADS-B radio
(running [adsb-feeder-image](https://github.com/dirkhh/adsb-feeder-image)) plus
cloud sources like adsb.lol and FlightAware. Eventually: AIS for boats, saved
queries ("notify me when a plane older than 50 years flies overhead"), and
mobile / smart-glasses clients that label the planes physically overhead.

This is **v1**: a web frontend on the local tailnet, backed by Postgres,
embedding the radio's tar1090 map for now while we build the database and
alerting parts underneath.

## Quick install (released image)

Run the published release straight from GitHub Container Registry — **no clone,
no build, no login.** The image is public; you only need Docker and ~2 minutes.

```bash
# 1. Make a directory and grab the two files you need
mkdir adsbuddy && cd adsbuddy
curl -fsSLO https://raw.githubusercontent.com/cdibona/ADSBuddy/main/docker-compose.ghcr.yml
curl -fsSL  https://raw.githubusercontent.com/cdibona/ADSBuddy/main/.env.template -o .env

# 2. Fill in the handful of required values
#    - ADSBUDDY_SECRET_KEY : python3 -c "import secrets; print(secrets.token_urlsafe(48))"
#    - ADSBUDDY_TAILNET_IP : tailscale ip -4
#    - ADSBUDDY_ADMIN_PASSWORD / POSTGRES_PASSWORD : pick your own
$EDITOR .env

# 3. Pull + run a pinned release (omit the var to track :latest)
ADSBUDDY_IMAGE_TAG=1.0.1 docker compose -f docker-compose.ghcr.yml up -d
```

That pulls `ghcr.io/cdibona/adsbuddy:1.0.1`, starts Postgres, runs
`alembic upgrade head`, and serves the app. Watch it come up with
`docker compose -f docker-compose.ghcr.yml logs -f app`, then visit:

- `http://localhost:${ADSBUDDY_PORT}`  (from this host)
- `http://${ADSBUDDY_TAILNET_IP}:${ADSBUDDY_PORT}`  (from any tailnet device)

Log in with the `ADSBUDDY_ADMIN_USERNAME` / `ADSBUDDY_ADMIN_PASSWORD` you set,
then point ADSBuddy at your radio under **Admin → System** (`radio_base_url`).

The app binds **only** to `127.0.0.1` and your tailnet IP — never to a public
interface. To upgrade later, bump `ADSBUDDY_IMAGE_TAG` and re-run step 3.

## Build from source (development)

To build the image locally from a checkout instead of pulling a release:

```bash
cp .env.template .env
$EDITOR .env                          # set secret, passwords, tailnet IP
ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up --build
```

(The `ADSBUDDY_GIT_SHA` prefix bakes the commit into the image so the footer
shows the deployed version; plain `docker compose up --build` works too and
just shows `dev`.)

## Configuration

- `.env` (gitignored) holds **only** the handful of values the app needs to
  boot: the web port, the tailnet IP to bind to, Postgres credentials, a
  session-signing secret, and the first-run admin username/password. See
  `.env.template` for the full list with comments.
- **Everything else** — the radio URL, the aircraft.json polling interval,
  adsb.lol / FlightAware API keys, alert rules — lives in the Postgres
  `settings` table and is editable from the admin UI.

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
