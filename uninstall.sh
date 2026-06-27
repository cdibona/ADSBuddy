#!/bin/sh
# ADSBuddy uninstaller:
#   curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/uninstall.sh | sh
#
# Stops and removes the ADSBuddy containers, network, and the Watchtower
# auto-updater. By default it KEEPS your database volume and .env so you can
# reinstall without losing data. To also delete the database (irreversible),
# run with PURGE=1:
#   curl -fsSL .../uninstall.sh | PURGE=1 sh
set -eu

DIR="${ADSBUDDY_DIR:-adsbuddy}"
say() { printf '%s\n' "$*"; }

if [ ! -d "$DIR" ]; then say "No '$DIR' directory here — nothing to uninstall."; exit 0; fi
cd "$DIR"

# Run docker with sudo if the daemon isn't reachable directly.
DOCKER="docker"
if ! docker info >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
  DOCKER="sudo docker"
fi

CF="-f docker-compose.ghcr.yml"
[ -f docker-compose.autoupdate.yml ] && CF="$CF -f docker-compose.autoupdate.yml"

if [ "${PURGE:-0}" = "1" ]; then
  say "Removing ADSBuddy AND its database volume (irreversible) ..."
  $DOCKER compose $CF down -v
  cd ..; rm -rf "$DIR"
  say "Done. Containers, network, database, and the '$DIR' directory are gone."
else
  say "Stopping + removing ADSBuddy containers (keeping the database volume) ..."
  $DOCKER compose $CF down
  say "Done. Your data volume (adsbuddy_pgdata) and .env are kept."
  say "Reinstall:        curl -fsSL https://raw.githubusercontent.com/cdibona/ADSBuddy/main/install.sh | sh"
  say "Delete everything: re-run this with PURGE=1 (wipes the database)."
fi
