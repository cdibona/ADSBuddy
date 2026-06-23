# ADSBuddy Aircraft-Centric UX & Historical Search Design

**Date:** 2026-06-22  
**Status:** Approved  
**Scope:** Aircraft detail page, trigger creation workflow, historical search v1, table enhancements

---

## Overview

Transform ADSBuddy from a collection of independent pages into an **aircraft-centric app** where every important workflow flows through a unified aircraft detail view. This improves usability, sets the foundation for later map integration, and makes trigger creation a first-class operation.

---

## Architecture & Information Flow

### Core Principle
**Make aircraft the center.** All workflows (search, trigger creation, history browsing, external references) funnel through a single aircraft detail page.

### Page Structure

#### Aircraft Detail Page (`/aircraft/{icao_hex}`)
- **Identity card**: tail number, ICAO hex, type code, description, owner/operator, year registered
- **Recent activity**: latest sightings, callsigns used, routes, altitude, speed
- **Trigger history**: recent firings from this aircraft
- **Actions**:
  - Create trigger from this aircraft (prefilled with tail/type/callsign)
  - Search history for this aircraft
  - External links: FAA registry (US tails), type reference (Wikipedia/aviation DB)

#### Historical Search Page (`/history` or expanded `/aircraft`)
- **Search filters** (v1):
  - Tail number (registration)
  - ICAO hex
  - Callsign (partial match)
  - Type code
  - Owner/operator (partial match)
  - Year range
  - Route (origin/destination ICAO)
  - Time range
- **Results**: list of aircraft matching criteria, each links to detail page and offers "Create trigger" action
- **No pagination complexity v1** — just ORDER BY last_seen DESC LIMIT 500

#### Trigger Creation Workflow
- Existing `/triggers/new` route enhanced with **query param prefilling**:
  - `?tail_patterns=N123AB&type_codes=B738&flight_patterns=DAL123` 
  - pre-populates form fields
  - form submission works as before, creating a properly scoped trigger
- From aircraft detail, search results, and firings rows: **"Create trigger" button → `/triggers/new?tail_patterns=...&type_codes=...`**

#### Table Enhancements (Aircraft, Firings, Triggers)
1. **Sticky header row** — keeps column names visible while scrolling
2. **Top index/filter bar**:
   - Quick filter buttons (Active/Paused for triggers, time buckets for firings, etc.)
   - Optional: A–Z jumping for tail numbers (if performance permits)
3. **Clickable rows point inward**:
   - Tail/callsign/aircraft type → aircraft detail page
   - Each row has external-link icons (small, subtle) for outbound references
   - "Create trigger from this row" action button

### Data Flow Diagram

```
┌─────────────────────────────────────────────────┐
│         Aircraft Detail Page                     │
│    (/aircraft/{icao_hex})                       │
│  - Identity, recent activity, firings           │
│  - "Create trigger" action                      │
│  - External links (FAA, Wikipedia, etc.)        │
└────────┬─────────────────────────────────────────┘
         │
         ├── Linked from: Tables (tail/type clicks)
         ├── Linked from: Search results
         ├── Linked from: Firings page (aircraft)
         └── Triggers created via prefilled form
             (/triggers/new?tail_patterns=...&type_codes=...)

┌─────────────────────────────────────────────────┐
│         Historical Search                        │
│    (/history)                                   │
│  - Filter by tail, hex, callsign, type, etc.   │
│  - Results → aircraft detail or trigger creation│
└─────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│    Non-Front-Page Tables (Aircraft/Firings/    │
│    Triggers) — Enhanced                         │
│  - Sticky headers                               │
│  - Top filter/index bar                         │
│  - Rows link to aircraft detail                 │
│  - External-link icons on data cells            │
│  - "Create trigger" actions                     │
└──────────────────────────────────────────────────┘

(Later) Map page integration:
  - Selected aircraft link into aircraft detail workflow
  - Path for richer embedded side panel without iframe complexity
```

---

## Feature Rollout Order

### Phase 1: Reliability Gate (CRITICAL FIRST)
**Objective:** Ensure site CRUD operations actually persist to DB.

1. **Reproduce and fix trigger deletion**
   - Verify trigger delete actually removes DB row
   - Verify UI updates reflect DB state
   - Smoke test against live Docker site after fix

2. **Verify create/edit/toggle persist correctly**
   - Test all CRUD operations
   - Restart Docker
   - Re-test the live site

3. **Acceptance**: All trigger operations persist through Docker restarts. Site is reliable before adding features.

### Phase 2: Aircraft Detail Page + Internal/External Links
**Objective:** Create the center of the app, make all tables discoverable.

1. **New route**: `GET /aircraft/{icao_hex}` returning aircraft identity + sightings + firings + actions
2. **Link all tail/type/callsign fields** in aircraft, firings, triggers tables to aircraft detail
3. **External-link icons** next to fields:
   - Tail number → FAA registry (US) or Planespotters (intl)
   - Type code → Wikipedia aircraft type
4. **"Create trigger from aircraft" button** on detail page (links to `/triggers/new?tail_patterns=...`)

### Phase 3: Trigger Creation from Context
**Objective:** Make creating triggers effortless from any view.

1. **Enhance trigger form** to accept query param prefilling
   - `tail_patterns`, `type_codes`, `flight_patterns`, `min_year`, `max_year`, `route_origin`, `route_destination`
   - `/triggers/new?tail_patterns=N123AB&type_codes=B738` pre-populates the form
2. **Add "Create trigger" buttons** to:
   - Aircraft detail page
   - Aircraft table rows
   - Firings table rows (link to trigger form with aircraft prefilled)
   - Search results (each row has the action)

### Phase 4: Historical Search v1
**Objective:** Enable users to browse and query historical aircraft.

1. **New route**: `GET /history` (or expand `/aircraft` with `?search=...` mode)
2. **Search form with filters**:
   - Tail number
   - ICAO hex
   - Callsign (partial)
   - Type code
   - Owner/operator
   - Year range
   - Route (origin/destination)
   - Time range
3. **Results** link to aircraft detail and offer trigger creation
4. **Simple first version**: no faceted drill-down, no export, no saved searches yet

### Phase 5: Table Usability Enhancements
**Objective:** Make tables faster and more discoverable.

1. **Sticky table headers** — keep column names visible while scrolling
2. **Top index/filter bar** on Aircraft, Firings, Triggers pages:
   - Trigger list: Active/Paused toggle filters
   - Firings: Time bucket filters (Today, Last 24h, Last week, All)
   - Aircraft: Optional A–Z quick-jump for registrations
3. **Consistent row actions** — each row on non-front-page tables has "View", "Create trigger", "External link" options

### Phase 6: Future Enhancements (Post-Launch)
- **Map integration**: Link selected aircraft from tar1090 iframe into aircraft detail workflow
- **Rich side panel**: Overlay aircraft detail on top of map without destroying iframe
- **Advanced search**: Saved searches, faceted drill-down, export
- **Trigger templates**: Copy triggers, trigger groups, trigger versioning

---

## Testing & Validation Strategy

### Unit/Integration Testing
- **Aircraft detail route**: query returns correct aircraft + sightings + firings
- **Trigger prefill flow**: query params correctly populate form defaults
- **Search filters**: each filter returns expected DB results
- **External link generation**: tail/type correctly map to external URLs

### Live-Site Validation
**After each completed feature phase:**

1. **Fresh Docker restart**
   ```bash
   docker-compose restart
   docker-compose ps  # verify both services running
   ```

2. **Manual smoke test** against HTTPS site (`https://webstag.tail41807.ts.net:8443/`):
   - Create a trigger → verify persists in /triggers list
   - Edit a trigger → verify change shows
   - Toggle trigger active/paused → verify reflects in UI and DB
   - Delete a trigger → verify removed from list AND gone from DB on page reload
   - Search historical aircraft → verify results link to detail pages
   - Create trigger from aircraft detail → verify trigger saved and prefill fields work
   - Click external-link icons → verify they go to correct destinations

3. **Restart Docker again** and re-verify persistence (no data loss on restart)

### Commit Cadence
**One commit per completed feature phase:**
- `fix: make trigger deletion actually remove DB row`
- `feat: add aircraft detail page with external links`
- `feat: add trigger creation from aircraft views`
- `feat: add historical search with basic filters`
- `feat: add sticky headers and table filters`

Each commit includes tests, live-site validation, and Docker restart verification.

---

## Implementation Specifics

### Database Queries (No Schema Changes)
- Aircraft detail: `SELECT * FROM aircraft WHERE icao_hex = ?; SELECT * FROM sightings WHERE icao_hex = ? ORDER BY seen_at DESC LIMIT 50; SELECT * FROM trigger_firings WHERE icao_hex = ? ORDER BY fired_at DESC LIMIT 20`
- Historical search: Dynamic WHERE clause built from filter params, uses existing indexes
- No new tables, no new columns, no migrations needed

### Routes (New)
- `GET /aircraft/<icao_hex>` — render aircraft detail
- `GET /history` — render search form + results if params present
- `GET /triggers/new?...` — existing route, enhanced to read query params for form prefilling

### Templates (New/Modified)
- **New**: `app/templates/aircraft_detail.html`
- **New**: `app/templates/history.html`
- **Modified**: `app/templates/aircraft.html`, `app/templates/firings.html`, `app/templates/triggers.html` (add external links, "create trigger" buttons)
- **Modified**: `app/templates/trigger_form.html` (read query params, prefill fields)

### Helpers (New)
- **Link generation**: `def external_link_faa(registration)`, `def external_link_type_wikipedia(type_code)`, etc.
- **URL param parsing**: `def parse_trigger_prefill_params(request)` to extract and validate query params

### CSS (Minor Additions)
- Sticky table header styles
- External-link icon styles (small, subtle)
- Filter bar styling

---

## Success Criteria

### Functional
- ✅ Trigger CRUD operations persist through Docker restart
- ✅ Aircraft detail page loads and shows correct data
- ✅ Trigger creation from aircraft detail works and prefill fields are correct
- ✅ Historical search returns expected results for each filter
- ✅ All external links resolve correctly
- ✅ Table sticky headers visible while scrolling
- ✅ Filter bars narrow results as expected

### UX
- ✅ All aircraft/trigger/flight information is discoverable from a single detail page
- ✅ Creating a trigger requires ≤3 clicks from any table view
- ✅ Search results are easy to browse and link to detail pages
- ✅ External reference links are subtle but accessible

### Code Quality
- ✅ New routes pass existing tests
- ✅ No broken references or type errors
- ✅ All CRUD operations tested against live DB
- ✅ Live site tested after Docker restart

---

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| Trigger deletion still broken after first fix | Focus reliability gate as critical blocker; test live site immediately after fix; if not fixed, halt and debug before proceeding |
| Search query too slow on large sighting table | Use existing indexes; start with LIMIT 500 to bound result size; optimize if perf issues arise post-launch |
| iframe/map integration too complex later | Design aircraft detail as standalone page first; map integration is phase 6, not blocking this design |
| Query param prefilling breaks on special characters | Validate and URL-encode params server-side before using in form |
| Table performance regression with sticky headers | CSS-only sticky (no JS); no perf risk |

---

## Notes

- **No architectural changes** — all work is additive on existing FastAPI/Jinja2 stack
- **No schema changes** — uses existing indexes and tables
- **Backwards compatible** — existing URLs and workflows unchanged, new features are additions
- **Incremental validation** — each feature phase tested against live site before proceeding

---

## Approval Sign-Off

**Design approved by user:** 2026-06-22  
**Ready for implementation:** YES  
**Autonomous execution approved:** YES (with Docker restart and live-site validation after each phase)

---

