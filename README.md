# ADSBuddy

A personal aggregation and alerting layer over the user's local ADS-B radio
(running [adsb-feeder-image](https://github.com/dirkhh/adsb-feeder-image)) plus
cloud sources like adsb.lol and FlightAware. Eventually: AIS for boats, saved
queries ("notify me when a plane older than 50 years flies overhead"), and
mobile / smart-glasses clients that label the planes physically overhead.

This is **v1**: a web frontend on the local tailnet, backed by Postgres,
embedding the radio's tar1090 map for now while we build the database and
alerting parts underneath.

## Quick start

```bash
cp .env.template .env
$EDITOR .env                          # set secret, passwords, tailnet IP
docker compose up --build
```

Then visit:

- `http://localhost:${ADSBUDDY_PORT}`  (from this host)
- `http://${ADSBUDDY_TAILNET_IP}:${ADSBUDDY_PORT}`  (from any tailnet device)

The app binds **only** to `127.0.0.1` and your tailnet IP — never to a public
interface.

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

## Architecture (v1)

- **Backend:** FastAPI + SQLAlchemy (async) + Alembic.
- **Frontend:** Jinja2 templates with a thin layer of vanilla JS.
- **Map page:** iframes the radio's tar1090 UI so the look matches your
  existing adsb.im. We separately ingest the radio's `/data/aircraft.json`
  into Postgres so the database and alerting layers have data to work on.
- **Database:** Postgres 16, container-managed via Docker Compose.

## License

See `LICENSE`.
