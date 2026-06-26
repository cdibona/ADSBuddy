#!/bin/sh
# ADSBuddy one-line installer:
#   curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
#
# Installs the latest release in "open" mode (no login — for a trusted appliance
# like an adsb-im Pi). Generates the session secret, auto-detects the tailnet IP,
# asks which radio to poll, and starts the stack. Re-running keeps your .env.
set -eu

REPO_RAW="https://raw.githubusercontent.com/cdibona/ADSBuddy/main"
DIR="${ADSBUDDY_DIR:-adsbuddy}"
say() { printf '%s\n' "$*"; }

command -v docker >/dev/null 2>&1 || { say "Docker is required — install Docker first."; exit 1; }

mkdir -p "$DIR"; cd "$DIR"
say "Fetching docker-compose.ghcr.yml ..."
curl -fsSL "$REPO_RAW/docker-compose.ghcr.yml" -o docker-compose.ghcr.yml

if [ -f .env ]; then
  say "Existing .env found — keeping your settings."
else
  # Radio: env var, else prompt (via /dev/tty so it works under curl|sh), else default.
  RADIO="${ADSBUDDY_RADIO_URL:-}"
  if [ -z "$RADIO" ] && [ -r /dev/tty ]; then
    printf 'adsb-im radio URL [http://127.0.0.1:8080]: ' > /dev/tty
    read -r RADIO < /dev/tty || RADIO=""
  fi
  RADIO="${RADIO:-http://127.0.0.1:8080}"

  gen() { openssl rand -base64 "$1" 2>/dev/null | tr -d '\n=+/' || head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

  say "Writing .env (open mode, generated secret) ..."
  cat > .env <<EOF
ADSBUDDY_PORT=8000
ADSBUDDY_BIND=0.0.0.0
ADSBUDDY_SECRET_KEY=$(gen 48)
ADSBUDDY_ADMIN_USERNAME=admin
ADSBUDDY_ADMIN_PASSWORD=AdminChangeMe
ADSBUDDY_MODE=open
ADSBUDDY_RADIO_URL=${RADIO}
ADSBUDDY_TEST_MODE=0
POSTGRES_USER=adsbuddy
POSTGRES_PASSWORD=$(gen 24)
POSTGRES_DB=adsbuddy
POSTGRES_HOST=db
POSTGRES_PORT=5432
EOF
  say "  radio: ${RADIO}  (bind: 0.0.0.0 — reachable on localhost, LAN, tailnet)"
fi

say "Pulling + starting ADSBuddy ..."
docker compose -f docker-compose.ghcr.yml up -d

say ""
say "ADSBuddy is up in OPEN mode (no login). Open:  http://localhost:8000"
say "It's already pointed at your radio; configure everything else in the app."
say "Want logins? Set ADSBUDDY_MODE=MultiUser in ${DIR}/.env, re-run 'docker compose"
say "-f docker-compose.ghcr.yml up -d', and sign in as admin / AdminChangeMe."
