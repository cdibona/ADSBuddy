#!/bin/sh
# ADSBuddy one-line installer:
#   curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
#
# Installs the latest release in "open" mode (no login — for a trusted appliance
# like an adsb-im Pi). Installs Docker if missing (with your OK), generates the
# session secret, picks a free web port, asks which radio to poll, binds 0.0.0.0,
# and starts the stack. Re-running keeps your .env.
set -eu

REPO_RAW="https://raw.githubusercontent.com/cdibona/ADSBuddy/main"
DIR="${ADSBUDDY_DIR:-adsbuddy}"
say() { printf '%s\n' "$*"; }

# Docker: install via the official convenience script if it's missing.
if ! command -v docker >/dev/null 2>&1; then
  if [ -r /dev/tty ]; then
    printf 'Docker is not installed. Install it now (https://get.docker.com, needs sudo)? [Y/n]: ' > /dev/tty
    read -r _ans < /dev/tty || _ans=""
    case "$_ans" in
      [Nn]*) say "Install Docker, then re-run this script."; exit 1 ;;
    esac
    say "Installing Docker ..."
    if [ "$(id -u)" -eq 0 ]; then curl -fsSL https://get.docker.com | sh
    else curl -fsSL https://get.docker.com | sudo sh; fi
    # Enable + start the service on systemd hosts (no-op elsewhere).
    if command -v systemctl >/dev/null 2>&1; then sudo systemctl enable --now docker >/dev/null 2>&1 || true; fi
  else
    say "Docker is required. Install it with:  curl -fsSL https://get.docker.com | sh"
    exit 1
  fi
fi

# How to call docker. If you can't reach the daemon directly (no 'docker' group
# / fresh install), fall back to sudo — which will prompt for your password.
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    DOCKER="sudo docker"
    if ! sudo -n true 2>/dev/null; then
      say "You don't have permission to use Docker directly — using sudo (you'll be prompted for your password)."
    fi
  else
    say "Can't access the Docker daemon and 'sudo' isn't available."
    say "Add yourself to the 'docker' group (and re-login), or run this as root."
    exit 1
  fi
fi

# True if a TCP port already has a listener (best-effort across ss/lsof/nc).
port_in_use() {
  _p="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${_p}\$"
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"${_p}" -sTCP:LISTEN >/dev/null 2>&1
  elif command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "${_p}" >/dev/null 2>&1
  else
    return 1   # can't check — assume free
  fi
}

mkdir -p "$DIR"; cd "$DIR"
say "Fetching docker-compose.ghcr.yml ..."
curl -fsSL "$REPO_RAW/docker-compose.ghcr.yml" -o docker-compose.ghcr.yml

if [ -f .env ]; then
  say "Existing .env found — keeping your settings."
  PORT="$(awk -F= '/^ADSBUDDY_PORT=/{print $2}' .env 2>/dev/null | tr -d '[:space:]')"
  PORT="${PORT:-8000}"
else
  # Radio: env var, else prompt (via /dev/tty so it works under curl|sh), else default.
  RADIO="${ADSBUDDY_RADIO_URL:-}"
  if [ -z "$RADIO" ] && [ -r /dev/tty ]; then
    printf 'adsb-im radio URL [http://127.0.0.1:8080]: ' > /dev/tty
    read -r RADIO < /dev/tty || RADIO=""
  fi
  RADIO="${RADIO:-http://127.0.0.1:8080}"

  # Web port: env override or 8000; if taken, walk up to the next free one.
  PORT="${ADSBUDDY_PORT:-8000}"
  _want="$PORT"; _n=0
  while port_in_use "$PORT" && [ "$_n" -lt 50 ]; do PORT=$((PORT + 1)); _n=$((_n + 1)); done
  if [ "$PORT" != "$_want" ]; then
    say "Port ${_want} is in use — using ${PORT} instead (set ADSBUDDY_PORT in .env to change)."
  fi

  gen() { openssl rand -base64 "$1" 2>/dev/null | tr -d '\n=+/' || head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

  say "Writing .env (open mode, generated secret, port ${PORT}) ..."
  cat > .env <<EOF
ADSBUDDY_PORT=${PORT}
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
if ! $DOCKER compose -f docker-compose.ghcr.yml up -d; then
  say ""
  say "Startup failed. If the error above says 'unauthorized' pulling the image,"
  say "the GHCR package is private — either ask the maintainer to make"
  say "  ghcr.io/cdibona/adsbuddy  public, or authenticate this machine:"
  say "  echo <YOUR_GH_TOKEN> | docker login ghcr.io -u <your-github-user> --password-stdin"
  say "then re-run:  $DOCKER compose -f docker-compose.ghcr.yml up -d"
  exit 1
fi

say ""
say "ADSBuddy is up in OPEN mode (no login). Open:  http://localhost:${PORT}"
say "It's already pointed at your radio; configure everything else in the app."
say "Want logins? Set ADSBUDDY_MODE=MultiUser in ${DIR}/.env, re-run 'docker compose"
say "-f docker-compose.ghcr.yml up -d', and sign in as admin / AdminChangeMe."
