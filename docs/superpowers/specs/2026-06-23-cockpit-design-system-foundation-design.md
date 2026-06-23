# ADSBuddy Cockpit Design System & Responsive Foundation

**Date:** 2026-06-23
**Status:** Approved (design)
**Scope:** A shared visual/UX foundation every page inherits, plus a richer Discord firing notification. The first of several UI workstreams; deeper per-page work and new trigger capabilities are separate specs (see *Deferred*).

---

## Overview

The current UI is functional but visually jumbled: `app.css` (~685 lines) has duplicated rules, ad-hoc per-page spacing, and tables that only scroll sideways on phones. This spec establishes a **cockpit/avionics design system** — design tokens, day/night theming, a component library, and a responsive table→card pattern — so the whole app looks intentional and reads well on any device. It also upgrades the Discord firing notification from plain text to a rich, status-colored embed.

The tar1090 map page (`index.html`) is intentionally left alone.

## Goals

- One source of truth for color, spacing, and type via CSS custom properties.
- A distinctive **cockpit** identity: near-black night mode, amber + instrument-green accents, monospace data, uppercase labels.
- **Day/night** that follows the OS (`prefers-color-scheme`) with a per-device manual override, no flash on load, and heavier type in day mode for legibility.
- Every data list works on a phone (stacked cards, no sideways scroll).
- De-duplicated, organized `app.css`.
- A richer Discord embed for firings, with a status-meaningful accent color.

## Non-goals (this spec)

- Deep per-page information-architecture redesign (later spec).
- New trigger matching capabilities — query builder, **squawk-code triggers**, map-based geofence picker, IATA→ICAO smart input (later specs). This spec only adds `squawk`/`emergency` to the firing snapshot so the Discord red bar can work.
- Static-map thumbnail in notifications (optional, off by default; revisit when a reliable source is chosen).
- Changes to the tar1090 iframe page.

---

## Visual direction

**Cockpit / avionics**, validated via mockups:

- **Night (default in dark OS):** background `#080b0d`, panels `#0d1417`, borders `#20403a`, ink `#cfe3d8`, brand/accent amber `#ffb000`, instrument-green `#4ade80`, danger red `#ff6b6b`, watch/skip purple `#c084fc`.
- **Day (default in light OS):** background `#edefe9`, panels `#ffffff`, borders `#cdd5cd`, ink `#0f1714`, brand/accent amber darkened to `#9a4d06`, green `#15703c`, danger `#b3261e`. Body weight 500 (vs 400), bold data/labels — monospace reads thin on light, so day carries more weight.

## Design tokens

Defined as CSS custom properties on `:root` (night) and overridden under `[data-theme="day"]`:

- Color: `--bg`, `--panel`, `--panel-2`, `--border`, `--ink`, `--muted`, `--accent` (amber), `--ok` (green), `--danger` (red), `--watch` (purple/amber), `--info`.
- Type: `--font-data` (ui-monospace stack), `--font-ui` (system-ui stack), `--fw-base` (400 night / 500 day), `--fw-bold` (700 night / 800 day).
- Space scale: `--s1`…`--s6` (e.g. 0.25/0.4/0.6/0.9/1.25/1.75rem), `--radius` (3px, squared-off avionics feel).

All component CSS references tokens — never hardcoded colors — so theming is a single switch.

## Typography

- **Monospace** (`--font-data`): tail numbers, ICAO/type codes, squawk, timestamps, lat/lon, altitudes — anything tabular/identifier-like.
- **System sans** (`--font-ui`): headings, prose, labels, buttons, nav.
- Labels: small, uppercase, `letter-spacing`, `--muted`.

## Theme switching

- Default = `prefers-color-scheme`. A small **inline script in `<head>`** (before CSS paint) reads `localStorage["adsbuddy-theme"]` (`auto|day|night`); for `auto` it applies the media query result, otherwise it sets `data-theme` on `<html>`. This prevents a flash of the wrong theme.
- A live `matchMedia` listener updates the theme when the OS flips (only while in `auto`).
- **Toggle** in the user-menu dropdown: `Auto · Day · Night`, persisted to `localStorage`. Per-device (works before login). No DB column.

## Component system

Rewrite `app.css` as one organized, de-duplicated sheet (current file has badges, pagination, `.table-scroll`, and `:focus-visible` defined twice). Single definition per component, all token-based:

- **Buttons:** `.btn` (primary), `.btn-secondary`, `.btn-small`, `.danger`.
- **Chips / filter bar:** `.filter-bar`, `.chip`, `.chip-on`, `.reg-jump`.
- **Badges:** status (`badge-active`, `badge-paused`, `badge-sent`, `badge-failed`, `badge-skipped`, `badge-pending`) + severity colors used by tables and Discord parity.
- **Tables:** `table.grid` with sticky header (existing), token borders, zebra-free.
- **Forms:** inputs, selects, textareas, fieldsets, `.filter-grid`, help text.
- **Containers:** `.card`, `.detail-card`, `.detail-grid`, `.page-head`, `.subnav`, `.user-menu`.
- **Feedback:** `.flash` variants, empty-state styling.
- **Pagination.**

## Responsive table → cards

- Keep semantic `<table class="grid">`. Add a `data-label="<column>"` attribute to every `<td>` in the list templates.
- One media query (`max-width: 640px`) flips `thead` to hidden and `tr`/`td` to block; each `td` shows its label via `::before { content: attr(data-label) }`. Rows become stacked, labeled cards; the tail/identifier and status lead each card.
- Applied to: `firings.html`, `aircraft.html`, `history_search.html`, `triggers.html`, `admin_users.html`, `admin_diagnostics.html`, `profile.html` (channels), `aircraft_detail.html` (sightings/firings tables).
- No JavaScript; no duplicate markup.

## Light communication pass (in scope)

- Consistent `.page-head` (title + one-line description) on every page.
- Consistent, friendly empty states.
- Clearer flash wording (e.g., success/skip/fail phrasing aligned with the new `skipped` concept).
- Column headers already de-"UTC"'d; keep consistent.

(Deeper IA — reorganizing what each page shows — is a later spec.)

## Discord rich embed

Replace the plain-text Discord `content` with an **embed** built in `notifications.py`:

- **Title** (linked): `✈ <tail> — <type/desc>`, linking to the aircraft detail page.
- **Description:** the most relevant fact — distance from geofence center when the trigger has a geofence, else route/owner.
- **Fields:** callsign, altitude, position (lat/lon), owner, route — whichever are present.
- **Footer:** `ADSBuddy` + localized fire time.
- **Accent color = status:** green (`#3ba55d`) normal, amber (`#faa61a`) geofence/watch, red (`#ed4245`) emergency (squawk 7500/7600/7700 or the `emergency` field). The embed only renders a left bar because the color is meaningful.
- **Links** in the description: View on ADSBuddy · FAA registry · Live map. (Webhook embeds can't have buttons; markdown links only.)
- **Map thumbnail:** optional, off by default.

Other channels: **email** gets a simple HTML version (parity of fields); **SMS** stays terse (unchanged).

### Supporting changes for the embed

- **New setting `site_base_url`** (e.g. `https://webstag.tail41807.ts.net:8443`) so notifications can build absolute links to aircraft/map pages. Empty → links omitted gracefully.
- **Firing snapshot gains `squawk` and `emergency`** (migration) so the embed can color emergencies and so squawk data is captured at fire time. Populated in `triggers.evaluate_and_record` from `AircraftFacts` (which gains `squawk`/`emergency`, set by the ingester).

---

## Data / model changes

1. `TriggerFiring`: add nullable `squawk` (String) and `emergency` (String) columns. Migration `0010`.
2. New runtime setting `site_base_url` (seeded blank, admin-editable).
3. No other schema changes. Theme preference is client-side only.

## Affected files

- **CSS:** `app/static/app.css` (rewrite/organize).
- **Templates:** `base.html` (head theme script, `<html data-theme>`, user-menu theme toggle), all list templates (add `data-label`), `profile.html` (toggle lives in menu, not profile), plus minor header/empty-state tidy across pages.
- **Backend:** `app/notifications.py` (embed builder + email HTML), `app/models.py` (+ firing columns), `app/triggers.py` (`AircraftFacts.squawk/emergency`, populate firing), `app/ingest.py` (pass squawk/emergency), `app/settings_store.py` (`site_base_url`), `alembic/versions/...0010...`.
- **JS:** a tiny inline theme script in `base.html` (no build step, no framework).

## Testing strategy

- **Unit:** theme-decision helper (auto/day/night → resolved theme) if extracted; Discord embed builder (color rules incl. emergency, link building with/without `site_base_url`, field omission); email HTML builder.
- **Template render:** each list renders with `data-label` present; base renders theme script + toggle; day/night token blocks present in served CSS.
- **Live smoke:** rebuild, verify pages render in both themes (toggle), a real firing posts the new embed to a test Discord channel, phone-width reflow visually confirmed by the user.
- Keep the existing 296-test suite green.

## Rollout (implementation phases)

1. Tokens + theme switch + `app.css` rewrite (no behavior change, visual refresh).
2. Responsive `data-label` pass across list templates.
3. Light communication pass (headers/empty states/flash).
4. Discord embed + `site_base_url` + firing `squawk`/`emergency` migration + email HTML.

Each phase: tests + Docker rebuild + live check, one commit per phase.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Theme flash on load | Inline `<head>` script sets `data-theme` before CSS paint |
| CSS rewrite regresses a page | Token-for-token mapping from current styles; render tests; visual pass per page |
| Monospace unreadable in day mode | Heavier weights + darker ink (validated in mockups) |
| Discord embed links broken without base URL | `site_base_url` blank → omit links, never emit a bad URL |
| `slim` image lacks fonts | Pure CSS font stacks (system + ui-monospace); no web fonts |

## Success criteria

- Every non-map page renders in night and day, switched by OS and by the Auto/Day/Night toggle, with no flash.
- Every data list is usable on a phone (stacked cards, no sideways scroll).
- `app.css` has no duplicated component definitions; all colors come from tokens.
- A firing posts a status-colored Discord embed with working links (when `site_base_url` is set).
- Full test suite green; live-verified after a Docker rebuild.

## Deferred (their own specs)

- Flexible trigger **query builder** + **squawk-code triggers** (7500/7600/7700) — this spec only stores squawk/emergency on firings.
- **Map-based geofence** picker (Leaflet click + drag radius).
- **Smart input resolution:** IATA(3-letter)→ICAO inference, `lat,lon` paste, autocomplete.
- Deep per-page **information-architecture** redesign.
