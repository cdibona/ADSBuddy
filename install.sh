#!/bin/sh
# ADSBuddy one-line installer:
#   curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh
#
# Installs the latest release in "open" mode (no login — for a trusted appliance
# like an adsb-im Pi). Installs Docker if missing (with your OK), generates the
# session secret, picks a free web port, asks which radio to poll, binds 0.0.0.0,
# and starts the stack. Re-running locates your existing install (from the running
# container) and updates it in place, reusing its .env — no duplicate directory.
set -eu

REPO_RAW="https://raw.githubusercontent.com/cdibona/ADSBuddy/main"
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

# Locate an existing ADSBuddy install by asking Docker where its compose project
# lives (the dir holding .env), so a re-run updates it in place instead of
# creating a fresh ./adsbuddy. Prints the dir, or nothing.
find_existing_dir() {
  _cid=$($DOCKER ps -a --format '{{.ID}} {{.Image}}' 2>/dev/null \
         | awk '/ghcr.io\/cdibona\/adsbuddy/{print $1; exit}')
  [ -z "$_cid" ] && return 1
  _wd=$($DOCKER inspect "$_cid" \
        --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null)
  [ -n "$_wd" ] && [ -d "$_wd" ] && printf '%s' "$_wd"
}

# Pick the install dir: explicit ADSBUDDY_DIR wins; else reuse a detected
# existing install; else default to ./adsbuddy.
DIR="${ADSBUDDY_DIR:-}"
if [ -z "$DIR" ]; then
  DIR="$(find_existing_dir 2>/dev/null || true)"
  if [ -n "$DIR" ]; then
    say "Found existing ADSBuddy install at ${DIR} — updating it in place."
  else
    DIR="adsbuddy"
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
say "Fetching compose files ..."
curl -fsSL "$REPO_RAW/docker-compose.ghcr.yml" -o docker-compose.ghcr.yml
# Auto-update sidecar (Watchtower) unless ADSBUDDY_NO_AUTOUPDATE=1.
CF="-f docker-compose.ghcr.yml"
if [ "${ADSBUDDY_NO_AUTOUPDATE:-0}" != "1" ]; then
  curl -fsSL "$REPO_RAW/docker-compose.autoupdate.yml" -o docker-compose.autoupdate.yml
  CF="$CF -f docker-compose.autoupdate.yml"
fi

UPDATING=0
if [ -f .env ]; then
  say "Existing install found — updating to the latest release (keeping your .env)."
  UPDATING=1
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

say "Pulling latest image + starting ADSBuddy ..."
$DOCKER compose $CF pull 2>/dev/null || true
if ! $DOCKER compose $CF up -d; then
  say ""
  say "Startup failed. If the error above says 'unauthorized' pulling the image,"
  say "the GHCR package is private — either ask the maintainer to make"
  say "  ghcr.io/cdibona/adsbuddy  public, or authenticate this machine:"
  say "  echo <YOUR_GH_TOKEN> | docker login ghcr.io -u <your-github-user> --password-stdin"
  say "then re-run this installer."
  exit 1
fi

if [ "$UPDATING" = "1" ]; then
  say ""
  say "ADSBuddy updated to the latest release. Open:  http://localhost:${PORT}"
  if [ "${ADSBUDDY_NO_AUTOUPDATE:-0}" != "1" ]; then
    say "Auto-updates are on (Watchtower checks hourly). Re-run this line anytime to update now."
  fi
  exit 0
fi

say ""
say "ADSBuddy is up in OPEN mode (no login). Open:  http://localhost:${PORT}"
say "It's already pointed at your radio; configure everything else in the app."
if [ "${ADSBUDDY_NO_AUTOUPDATE:-0}" != "1" ]; then
  say "Auto-updates are ON — Watchtower checks hourly and the menu shows a badge"
  say "when an update lands. Re-run this install line anytime to update immediately."
fi
say "Want logins? Set ADSBUDDY_MODE=MultiUser in ${DIR}/.env and re-run this installer;"
say "sign in as admin / AdminChangeMe."
say "Uninstall:  curl -fsSL ${REPO_RAW}/uninstall.sh | sh"
