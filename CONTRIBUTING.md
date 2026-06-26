# Contributing to ADSBuddy

## Submitting a trigger

ADSBuddy ships a curated **baseload** of triggers (celebrity/notable aircraft,
emergency squawks, a vintage-aircraft rule). When a release adds new ones, every
deployment picks them up automatically on its next image update — see
[How baseload triggers reach users](#how-baseload-triggers-reach-users). If you
build a trigger others would enjoy, please send it in.

There are two ways, easiest first.

### 1. From the app (recommended)

1. Open the trigger under **Triggers → edit**.
2. In the **Contribute this trigger** card, click **Submit to GitHub ↗**. This
   opens a new issue pre-filled with your trigger as a JSON snippet and a
   `trigger-submission` label. Add a line on *who/what it tracks* and your
   *source*, then submit.

That's it — a maintainer reviews it and, if it's a good general-interest
trigger, adds it to the next release's baseload.

### 2. Open a pull request

Add an entry to [`app/baseload_triggers.py`](app/baseload_triggers.py) in the
`BASELOAD_TRIGGERS` list. Each entry is a dict carrying only the fields it needs;
use **View JSON** in the Contribute card to get the exact snippet for your
trigger, e.g.:

```python
{'name': 'Jane Doe', 'is_active': False, 'cooldown_seconds': 3600, 'tail_patterns': 'N12345'},
```

Guidelines:

- **`name`** is the de-dup key and must be unique. Use a clear, real label.
- New triggers should be **`is_active: False`** (paused) unless they're a
  universal safety/interest rule (like emergency squawks) — users opt in by
  activating them.
- Prefer **tail-number / type / squawk** rules. **Geofenced** triggers carry a
  specific lat/lon and only make sense locally, so they're a poor fit for a
  shared baseload.
- Combine one person's multiple aircraft into a single trigger
  (`'tail_patterns': 'N1ABC,N2DEF'`).
- Include a **source** in the PR description (e.g. a public tracker / news item).
  Don't submit private individuals' aircraft; keep it to public figures /
  notable / safety-relevant.

## How baseload triggers reach users

Baseload triggers live in the image. On boot, `bootstrap.seed_baseload_triggers`
offers each one **exactly once** (tracked in the internal `baseload_applied`
setting):

- **Fresh install** → all current baseload triggers are seeded.
- **Image update that adds triggers** → only the new names (never applied
  before) are inserted on the next restart; existing triggers are untouched.
- **A trigger you deleted** stays deleted — it won't be re-added on update.

So to get new community triggers, deployers just pull the new image and restart
(`ADSBUDDY_IMAGE_TAG=<new> docker compose -f docker-compose.ghcr.yml up -d`).

## Development

See [`README.md`](README.md) for running locally and
[`deploy/README.md`](deploy/README.md) for deployment. Tests:
`.venv/bin/python -m pytest -q`.
