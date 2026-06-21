# Deployment

ADSBuddy runs as a Docker Compose stack managed by a systemd unit so it starts
automatically on boot (and restarts if it crashes, via the per-container
`restart: unless-stopped` policy in `docker-compose.yml`).

## Install the systemd service

```bash
sudo cp deploy/adsbuddy.service /etc/systemd/system/adsbuddy.service
sudo systemctl daemon-reload
sudo systemctl enable --now adsbuddy.service
```

`enable` makes it start on boot; `--now` starts it immediately.

## Operate

```bash
systemctl status adsbuddy            # service state
sudo systemctl restart adsbuddy      # restart the whole stack
sudo systemctl stop adsbuddy         # docker compose down
docker compose ps                    # container-level view (run from repo root)
docker compose logs -f app           # tail app logs
```

## Deploy a new version

The boot unit intentionally does **not** rebuild images (keeps boot fast and
reliable). To ship code changes:

```bash
cd /home/cdibona/ADSBuddy
git pull
docker compose up -d --build
```

## Notes

- The unit runs `docker compose` from `/home/cdibona/ADSBuddy`, so the Compose
  project name is `adsbuddy` and it manages the same containers you'd get from
  running compose by hand in that directory.
- Configuration comes from `.env` (gitignored) in the repo root.
