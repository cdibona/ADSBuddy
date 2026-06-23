# Cockpit Design System & Responsive Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give ADSBuddy a cohesive cockpit/avionics design system — CSS tokens, OS-aware day/night theming, a de-duplicated component library, responsive table→card lists — plus a status-colored Discord rich embed for firings.

**Architecture:** All styling moves to CSS custom properties (tokens) on `:root` (night) with a `[data-theme="day"]` override; an inline `<head>` script applies the saved/OS theme before paint. Data tables stay semantic `<table class="grid">` and reflow to stacked cards under 640px via `data-label` + a media query (no JS). Notifications build a Discord embed (and HTML email) server-side; firings snapshot `squawk`/`emergency` so emergencies color the embed red.

**Tech Stack:** FastAPI + Jinja2, vanilla CSS (no framework/build), one small inline `<script>`, SQLAlchemy + Alembic (Postgres), pytest. Tests run via `.venv/bin/python -m pytest -q`; the app runs via `ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build`.

## Global Constraints

- No JS framework, no build step. Theme logic is one inline `<script>` in `base.html`; everything else is CSS.
- All component CSS references tokens (`var(--…)`) — never hardcoded colors.
- Day mode uses heavier weights and darker ink than night (monospace reads thin on light).
- The tar1090 map page (`app/templates/index.html`) is NOT touched.
- Theme preference is per-device in `localStorage["adsbuddy-theme"]` (`auto|day|night`) — no DB column.
- Keep the existing suite green (296 tests at plan time). Run `.venv/bin/python -m pytest -q`.
- One commit per task. Co-author trailer: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Migrations use `op.add_column(... server_default=...)` then `op.alter_column(... server_default=None)` (pattern from migrations 0006–0008). Next revision id: `20260623_0010`, down_revision `20260623_0009`.
- Do NOT `git push` (project rule: human pushes).

---

## File Structure

- `app/static/app.css` — rewritten as: tokens (night) → `[data-theme="day"]` overrides → base/layout → components (buttons, chips, badges, tables, forms, cards, flash, pagination, subnav, user-menu, map, diagnostics) → responsive (table→card) → mobile tweaks. Single definition per component.
- `app/templates/base.html` — `<html data-theme>`, inline theme bootstrap script in `<head>`, theme toggle in the user-menu.
- List templates (`firings.html`, `aircraft.html`, `history_search.html`, `triggers.html`, `admin_users.html`, `admin_diagnostics.html`, `profile.html`, `aircraft_detail.html`) — add `data-label` to `<td>`s.
- `app/notifications.py` — `build_discord_embed(...)`, `build_email_html(...)`, wired into senders; uses `site_base_url`.
- `app/models.py` — `TriggerFiring.squawk`, `TriggerFiring.emergency`.
- `app/triggers.py` — `AircraftFacts.squawk`, `AircraftFacts.emergency`; populate firing snapshot.
- `app/ingest.py` — pass `squawk`/`emergency` into `AircraftFacts`.
- `app/settings_store.py` — `site_base_url` default spec.
- `alembic/versions/20260623_0010_firing_squawk_emergency.py` — new columns.
- Tests: `tests/test_theme.py`, `tests/test_discord_embed.py`, extend `tests/test_routes.py`/`tests/test_diagnostics.py` for `data-label`.

---

## Task 1: CSS token system + day/night palettes

**Files:**
- Modify: `app/static/app.css` (reorganize; introduce tokens; map all colors to `var(--…)`)
- Test: `tests/test_theme.py` (served-CSS assertions)

**Interfaces:**
- Produces: CSS custom properties on `:root` and `[data-theme="day"]`: `--bg --panel --panel-2 --border --ink --muted --accent --ok --danger --watch --info --font-data --font-ui --fw-base --fw-bold --s1..--s6 --radius`. Components reference only these.

- [ ] **Step 1: Write the failing test** (`tests/test_theme.py`)

```python
from pathlib import Path

CSS = Path("app/static/app.css").read_text()

class TestThemeTokens:
    def test_night_root_tokens_present(self):
        assert ":root" in CSS
        for tok in ("--bg", "--panel", "--ink", "--accent", "--ok", "--danger",
                    "--font-data", "--font-ui", "--radius"):
            assert tok in CSS, f"missing token {tok}"

    def test_day_override_block_present(self):
        assert '[data-theme="day"]' in CSS

    def test_no_legacy_hardcoded_bg(self):
        # The old hardcoded slate bg must be gone from component rules
        # (allowed only as a token value definition).
        assert CSS.count("#0f1216") <= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: FAIL (no `[data-theme="day"]`, tokens not all present).

- [ ] **Step 3: Rewrite `app.css` head with tokens**

Replace the current `:root` block and remove duplicated rules (badges, `.table-scroll`, pagination, `:focus-visible` each appear twice today — keep one). Start the file with:

```css
:root {
  /* —— Cockpit · NIGHT (default) —— */
  --bg:#080b0d; --panel:#0d1417; --panel-2:#111c1f; --border:#20403a;
  --ink:#cfe3d8; --muted:#5f8c7e;
  --accent:#ffb000;        /* amber */
  --ok:#4ade80;            /* instrument green */
  --danger:#ff6b6b;
  --watch:#c084fc;         /* purple: skipped/watch */
  --info:#4ea4ff;
  --font-data:ui-monospace,SFMono-Regular,Menlo,monospace;
  --font-ui:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  --fw-base:400; --fw-bold:700;
  --s1:.25rem; --s2:.4rem; --s3:.6rem; --s4:.9rem; --s5:1.25rem; --s6:1.75rem;
  --radius:3px;
}
[data-theme="day"] {
  /* —— Cockpit · DAY (heavier, darker ink) —— */
  --bg:#edefe9; --panel:#ffffff; --panel-2:#f3f5f0; --border:#cdd5cd;
  --ink:#0f1714; --muted:#3f4d46;
  --accent:#9a4d06; --ok:#15703c; --danger:#b3261e; --watch:#7a3fb0; --info:#0b6bcb;
  --fw-base:500; --fw-bold:800;
}
```

Then update `body`, `a`, `.topbar`, `.card`, `table.grid`, badges, chips, buttons, etc. to use tokens (`background:var(--bg)`, `color:var(--ink)`, `border-color:var(--border)`, `font-weight:var(--fw-base)`, `border-radius:var(--radius)`, fonts via `--font-ui`/`--font-data`). Apply `font-family:var(--font-data)` to `code`, `table.grid td` data cells, and timestamp/identifier spans. Delete the duplicate component blocks so each component is defined once.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v`
Expected: PASS.

- [ ] **Step 5: Full suite + visual sanity**

Run: `.venv/bin/python -m pytest -q` → all pass.
Run: `ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build` and `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/healthz` → 200.

- [ ] **Step 6: Commit**

```bash
git add app/static/app.css tests/test_theme.py
git commit -m "feat: CSS design tokens + cockpit night/day palettes

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: No-flash theme bootstrap + Auto/Day/Night toggle

**Files:**
- Modify: `app/templates/base.html`
- Test: `tests/test_theme.py`

**Interfaces:**
- Consumes: tokens + `[data-theme="day"]` from Task 1.
- Produces: `<html data-theme="…">` set before paint; a user-menu control with `data-set-theme="auto|day|night"`; `localStorage["adsbuddy-theme"]`.

- [ ] **Step 1: Add tests**

```python
class TestThemeBootstrap:
    def _base(self):
        return Path("app/templates/base.html").read_text()

    def test_inline_bootstrap_before_css(self):
        b = self._base()
        assert "adsbuddy-theme" in b
        assert "prefers-color-scheme" in b
        # script appears inside <head>, before </head>
        assert b.index("adsbuddy-theme") < b.index("</head>")

    def test_theme_toggle_controls(self):
        b = self._base()
        for v in ("auto", "day", "night"):
            assert f'data-set-theme="{v}"' in b
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_theme.py -k Bootstrap -v` → FAIL.

- [ ] **Step 3: Edit `base.html`**

Set `<html lang="en" data-theme="night">` and add this as the FIRST element in `<head>` (before the stylesheet link):

```html
<script>
  (function () {
    try {
      var pref = localStorage.getItem('adsbuddy-theme') || 'auto';
      var dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      var theme = pref === 'auto' ? (dark ? 'night' : 'day') : pref;
      document.documentElement.setAttribute('data-theme', theme);
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function (e) {
        if ((localStorage.getItem('adsbuddy-theme') || 'auto') === 'auto')
          document.documentElement.setAttribute('data-theme', e.matches ? 'night' : 'day');
      });
      window.__setTheme = function (v) {
        localStorage.setItem('adsbuddy-theme', v);
        var d = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.documentElement.setAttribute('data-theme', v === 'auto' ? (d ? 'night' : 'day') : v);
        document.querySelectorAll('[data-set-theme]').forEach(function (el) {
          el.setAttribute('aria-pressed', el.getAttribute('data-set-theme') === v);
        });
      };
    } catch (e) {}
  })();
</script>
```

Inside the existing `.user-menu-items` (after Profile / before Logout, with a `.menu-sep`), add:

```html
<div class="menu-sep"></div>
<div class="theme-toggle" role="group" aria-label="Theme">
  <button type="button" class="theme-opt" data-set-theme="auto" onclick="__setTheme('auto')">Auto</button>
  <button type="button" class="theme-opt" data-set-theme="day" onclick="__setTheme('day')">Day</button>
  <button type="button" class="theme-opt" data-set-theme="night" onclick="__setTheme('night')">Night</button>
</div>
<script>
  (function(){var v=localStorage.getItem('adsbuddy-theme')||'auto';
   document.querySelectorAll('[data-set-theme]').forEach(function(el){
     el.setAttribute('aria-pressed', el.getAttribute('data-set-theme')===v);});})();
</script>
```

Add `.theme-toggle`/`.theme-opt` styles to `app.css` (small segmented buttons; `[aria-pressed="true"]` uses `--accent`).

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_theme.py -v` → PASS. Then `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 5: Live check**

Rebuild; load a page; toggle Auto/Day/Night and confirm no flash on reload (manual/user).

- [ ] **Step 6: Commit**

```bash
git add app/templates/base.html app/static/app.css tests/test_theme.py
git commit -m "feat: no-flash day/night theme bootstrap + user-menu toggle

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Responsive table→card across all lists

**Files:**
- Modify: `app/static/app.css` (responsive block), and list templates: `firings.html`, `aircraft.html`, `history_search.html`, `triggers.html`, `admin_users.html`, `admin_diagnostics.html`, `profile.html`, `aircraft_detail.html`
- Test: `tests/test_responsive.py`

**Interfaces:**
- Consumes: `table.grid` markup.
- Produces: every `<td>` in a `.grid` list carries `data-label="<header>"`; `<640px` media query renders rows as cards.

- [ ] **Step 1: Add CSS responsive block** to `app.css`:

```css
@media (max-width: 640px) {
  table.grid, table.grid thead, table.grid tbody, table.grid tr, table.grid td { display:block; width:100%; }
  table.grid thead { position:absolute; left:-9999px; }       /* hide header row */
  table.grid tr {
    margin:0 0 var(--s3); border:1px solid var(--border);
    border-radius:var(--radius); background:var(--panel); padding:var(--s3);
  }
  table.grid td { border:0; padding:var(--s1) 0; display:flex; gap:var(--s3); justify-content:space-between; }
  table.grid td::before {
    content:attr(data-label); color:var(--muted); font-family:var(--font-ui);
    font-size:.72em; text-transform:uppercase; letter-spacing:.04em; flex:0 0 8rem;
  }
  table.grid td[data-label=""]::before, table.grid td.cell-actions::before { content:""; }
}
```

- [ ] **Step 2: Write the failing test** (`tests/test_responsive.py`) — render each list and assert `data-label` present. Example for firings (repeat per template with that template's context):

```python
import types
from datetime import datetime, timezone

def _req(path="/"):
    return types.SimpleNamespace(url=types.SimpleNamespace(path=path))

def test_firings_cells_have_data_labels():
    from app.routes_triggers import templates
    from app.models import Trigger, TriggerFiring
    f = TriggerFiring(id=1, trigger_id=1, icao_hex="a1b2c3", registration="N1",
                      fired_at=datetime(2026,6,23,16,tzinfo=timezone.utc))
    t = Trigger(id=1, owner_id=1, name="T")
    out = templates.env.get_template("firings.html").render(
        request=_req("/firings"), user=types.SimpleNamespace(username="a", is_admin=True),
        rows=[(f, t)], delivery_status={1: "sent"}, total=1, page=1, per_page=100,
        total_pages=1, start=1, end=1, since="all",
        loaded_at=datetime(2026,6,23,16,tzinfo=timezone.utc), flash=None)
    assert 'data-label="Aircraft"' in out and 'data-label="When"' in out
```

- [ ] **Step 3: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_responsive.py -v` → FAIL.

- [ ] **Step 4: Add `data-label` to every `<td>`** in each list template, matching its `<th>` text. Example (firings.html row):

```html
<td data-label="When">{{ f.fired_at | localdt }}</td>
<td data-label="Trigger"><a href="/triggers/{{ t.id }}/edit">{{ t.name }}</a></td>
<td data-label="Aircraft"> … </td>
<td data-label="Callsign">{{ f.callsign or "" }}</td>
<td data-label="Type"> … </td>
<td data-label="Year">{{ f.year or "" }}</td>
<td data-label="Route"> … </td>
<td data-label="Altitude">{{ f.altitude_baro or "" }}</td>
<td data-label="Notified"> … </td>
<td data-label="" class="cell-actions"> … </td>
```

Do the same for the other seven templates (use each table's header labels; action cells get `data-label=""`).

- [ ] **Step 5: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/test_responsive.py -v` → PASS. Then `.venv/bin/python -m pytest -q` → all pass.

- [ ] **Step 6: Live check** — rebuild; narrow the browser <640px on Firings/Aircraft/Triggers and confirm cards (manual/user).

- [ ] **Step 7: Commit**

```bash
git add app/static/app.css app/templates/*.html tests/test_responsive.py
git commit -m "feat: responsive table->card layout for all data lists

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Light communication pass

**Files:**
- Modify: list/detail templates (page headers + empty states); `app/static/app.css` (`.empty-state`)
- Test: extend `tests/test_responsive.py` or add inline asserts

**Interfaces:** purely presentational; no new data.

- [ ] **Step 1: Add `.empty-state` CSS**

```css
.empty-state { text-align:center; color:var(--muted); padding:var(--s6) var(--s4);
  border:1px dashed var(--border); border-radius:var(--radius); background:var(--panel); }
```

- [ ] **Step 2: Standardize page heads & empty states**

Ensure every non-map page opens with `<div class="page-head"><h1>…</h1> …</div>` plus a one-line `<p class="muted">` description. Replace bare "No X yet" `<td colspan>` rows' wording with friendly, consistent copy (keep them inside the table for now; the responsive block handles them). Where a whole list is empty, an `.empty-state` block may be used instead of an empty table.

- [ ] **Step 3: Add a test** asserting two representative pages render a `page-head` and a description (render `triggers.html` empty + `firings.html` empty; assert `class="page-head"` and an empty-state/`muted` line present).

- [ ] **Step 4: Run tests** → `.venv/bin/python -m pytest -q` all pass.

- [ ] **Step 5: Commit**

```bash
git add app/templates/*.html app/static/app.css tests/test_responsive.py
git commit -m "feat: consistent page headers + empty states (communication pass)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Firing snapshot squawk/emergency + site_base_url setting

**Files:**
- Modify: `app/models.py` (TriggerFiring), `app/triggers.py` (AircraftFacts + populate), `app/ingest.py` (pass values), `app/settings_store.py` (setting)
- Create: `alembic/versions/20260623_0010_firing_squawk_emergency.py`
- Test: `tests/test_triggers.py` (extend)

**Interfaces:**
- Produces: `AircraftFacts.squawk: str|None`, `AircraftFacts.emergency: str|None`; `TriggerFiring.squawk`, `TriggerFiring.emergency`; setting key `site_base_url`.
- Consumes (Task 6): these fields to color/link the embed.

- [ ] **Step 1: Tests** in `tests/test_triggers.py`

```python
def test_firing_snapshot_captures_squawk_emergency():
    # evaluate_and_record copies squawk/emergency from facts onto the firing
    import asyncio
    from app.triggers import evaluate_and_record
    t = _make_trigger(tail_patterns="N12345")
    facts = _make_facts(registration="N12345", squawk="7700", emergency="general")
    session = _make_session(first_result=None)
    firings, _ = asyncio.run(evaluate_and_record(session, [t], facts))
    assert firings[0].squawk == "7700"
    assert firings[0].emergency == "general"
```

Also extend `_make_facts` defaults with `squawk=None, emergency=None` and `AircraftFacts` accordingly.

- [ ] **Step 2: Run to verify fail** → `.venv/bin/python -m pytest tests/test_triggers.py -k squawk -v` → FAIL.

- [ ] **Step 3: Model + migration**

`app/models.py` (TriggerFiring): add after `type_code`:
```python
    squawk: Mapped[str | None] = mapped_column(String(8))
    emergency: Mapped[str | None] = mapped_column(String(16))
```
Create `alembic/versions/20260623_0010_firing_squawk_emergency.py`:
```python
from alembic import op
import sqlalchemy as sa
revision="20260623_0010"; down_revision="20260623_0009"
branch_labels=None; depends_on=None
def upgrade():
    op.add_column("trigger_firings", sa.Column("squawk", sa.String(8), nullable=True))
    op.add_column("trigger_firings", sa.Column("emergency", sa.String(16), nullable=True))
def downgrade():
    op.drop_column("trigger_firings","emergency"); op.drop_column("trigger_firings","squawk")
```

- [ ] **Step 4: AircraftFacts + populate + ingest + setting**

`app/triggers.py`: add `squawk: str | None` and `emergency: str | None` to `AircraftFacts`; in `evaluate_and_record` set `squawk=facts.squawk, emergency=facts.emergency` on the `TriggerFiring(...)`.
`app/ingest.py`: in the `AircraftFacts(...)` construction add `squawk=_strip(entry.get("squawk")), emergency=_strip(entry.get("emergency"))`.
`app/settings_store.py`: add to `DEFAULT_SETTINGS`:
```python
    SettingSpec(key="site_base_url", default="",
        description="Absolute base URL (e.g. https://webstag.tail41807.ts.net:8443) used to build links in notifications. Blank = links omitted."),
```

- [ ] **Step 5: Run tests** → `.venv/bin/python -m pytest tests/test_triggers.py -q` PASS; full `-q` PASS.

- [ ] **Step 6: Apply migration live**

Run: `ADSBUDDY_GIT_SHA=$(git rev-parse --short HEAD) docker compose up -d --build` then `docker compose exec -T app alembic current` → `20260623_0010 (head)`.

- [ ] **Step 7: Commit**

```bash
git add app/models.py app/triggers.py app/ingest.py app/settings_store.py alembic/versions/20260623_0010_firing_squawk_emergency.py tests/test_triggers.py
git commit -m "feat: snapshot squawk/emergency on firings + site_base_url setting

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Discord rich embed (+ HTML email)

**Files:**
- Modify: `app/notifications.py`
- Test: `tests/test_discord_embed.py`

**Interfaces:**
- Consumes: `TriggerFiring.squawk/emergency` (Task 5), `site_base_url` setting.
- Produces: `build_discord_embed(trigger, firing, base_url) -> dict`; `_send_discord` posts `{"embeds":[embed]}`; `build_email_html(...) -> str` attached as the email HTML alternative.

- [ ] **Step 1: Tests** (`tests/test_discord_embed.py`)

```python
from app.notifications import build_discord_embed
from app.models import Trigger, TriggerFiring

EMERG = {"7500","7600","7700"}

def _firing(**kw):
    d = dict(id=1, trigger_id=1, icao_hex="a50b7b", registration="N424LF",
             type_code="B407", callsign="LIFE1", altitude_baro=1200,
             lat=47.61, lon=-122.33, squawk=None, emergency=None)
    d.update(kw); return TriggerFiring(**d)

def test_color_emergency_red():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(squawk="7700"), "")
    assert e["color"] == 0xED4245

def test_color_geofence_amber():
    t = Trigger(id=1, owner_id=1, name="X", center_lat=47.4, center_lon=-122.3, radius_miles=40)
    assert build_discord_embed(t, _firing(), "")["color"] == 0xFAA61A

def test_color_normal_green():
    assert build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "")["color"] == 0x3BA55D

def test_title_links_when_base_url_set():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "https://h:8443")
    assert e["url"] == "https://h:8443/aircraft/a50b7b"
    assert "N424LF" in e["title"]

def test_no_url_when_base_blank():
    e = build_discord_embed(Trigger(id=1, owner_id=1, name="X"), _firing(), "")
    assert "url" not in e
```

- [ ] **Step 2: Run to verify fail** → `.venv/bin/python -m pytest tests/test_discord_embed.py -v` → FAIL (no `build_discord_embed`).

- [ ] **Step 3: Implement builder** in `app/notifications.py`

```python
_EMERGENCY_SQUAWKS = {"7500", "7600", "7700"}

def _firing_color(trigger, firing) -> int:
    if (firing.squawk in _EMERGENCY_SQUAWKS) or firing.emergency:
        return 0xED4245  # red
    if trigger.center_lat is not None and trigger.radius_miles is not None:
        return 0xFAA61A  # amber: geofence/watch
    return 0x3BA55D      # green: normal

def build_discord_embed(trigger, firing, base_url: str) -> dict:
    ident = firing.registration or firing.icao_hex
    title = f"✈ {ident}" + (f" — {firing.type_code}" if firing.type_code else "")
    fields = []
    if firing.callsign: fields.append({"name": "Callsign", "value": firing.callsign, "inline": True})
    if firing.altitude_baro is not None: fields.append({"name": "Altitude", "value": f"{firing.altitude_baro} ft", "inline": True})
    if firing.lat is not None and firing.lon is not None:
        fields.append({"name": "Position", "value": f"{firing.lat:.4f}, {firing.lon:.4f}", "inline": True})
    if firing.origin_icao or firing.destination_icao:
        fields.append({"name": "Route", "value": f"{firing.origin_icao or '?'} → {firing.destination_icao or '?'}", "inline": True})
    desc_bits = []
    if firing.squawk in _EMERGENCY_SQUAWKS: desc_bits.append(f"**EMERGENCY** squawk {firing.squawk}")
    desc_bits.append(f"trigger: {trigger.name}")
    embed = {
        "title": title,
        "description": " · ".join(desc_bits),
        "color": _firing_color(trigger, firing),
        "fields": fields,
        "footer": {"text": "ADSBuddy"},
    }
    if base_url:
        base = base_url.rstrip("/")
        embed["url"] = f"{base}/aircraft/{firing.icao_hex}"
    if firing.fired_at:
        embed["timestamp"] = firing.fired_at.isoformat()
    return embed
```

Update `_send_discord` to fetch `site_base_url` and post the embed (keep `content` empty or a short fallback):
```python
async def _send_discord(session, client, channel, trigger, firing):
    url = (channel.config or {}).get("webhook_url")
    if not url:
        raise ChannelNotConfigured("Discord channel is missing 'webhook_url' in config.")
    body = {"username": (channel.config or {}).get("username") or "ADSBuddy"}
    if firing is not None:
        base = await get_setting(session, "site_base_url") or ""
        body["embeds"] = [build_discord_embed(trigger, firing, base)]
    else:
        body["content"] = "ADSBuddy test — channel wired up correctly."
    resp = await client.post(url, json=body, timeout=_HTTP_TIMEOUT)
    if resp.status_code >= 300:
        raise RuntimeError(f"Discord webhook returned {resp.status_code}: {resp.text[:200]}")
```

Update `_dispatch_one`'s discord branch to pass `session, client, channel, trigger, firing`. Add `build_email_html(trigger, firing, base_url)` returning a small HTML table mirroring the text fields, and attach via `msg.add_alternative(html, subtype="html")` in `_send_email` (keep the existing `set_content` plain-text part as fallback).

- [ ] **Step 4: Run to verify pass** → `.venv/bin/python -m pytest tests/test_discord_embed.py -v` PASS; full `-q` PASS.

- [ ] **Step 5: Live check**

Set `site_base_url` to `https://webstag.tail41807.ts.net:8443` in admin settings; rebuild; trigger (or `Send test` then a real firing) and confirm the embed posts with the right color and a working title link.

- [ ] **Step 6: Commit**

```bash
git add app/notifications.py tests/test_discord_embed.py
git commit -m "feat: Discord rich embed for firings (status color + links) + HTML email

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes

- **Spec coverage:** tokens/theme (T1), no-flash + toggle (T2), responsive cards (T3), communication pass (T4), site_base_url + firing squawk/emergency (T5), Discord embed + HTML email (T6), CSS de-dup (T1). Map page untouched (constraint). Static-map thumbnail intentionally omitted (spec: optional/off). Deferred features not in plan (correct).
- **Type consistency:** `build_discord_embed(trigger, firing, base_url)` and `_firing_color(trigger, firing)` used consistently; `AircraftFacts.squawk/emergency` and `TriggerFiring.squawk/emergency` named identically across T5/T6; `localStorage["adsbuddy-theme"]` and `data-set-theme` consistent across T2.
- **Placeholders:** none — code shown for every code step.
