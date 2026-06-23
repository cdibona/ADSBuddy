# ADSBuddy Aircraft-Centric UX Implementation Plan

**Date:** 2026-06-22  
**Status:** Design approved, ready for implementation  
**Scope:** Aircraft-centric navigation, historical search, trigger creation workflows, table enhancements

---

## Overview

This plan implements a coherent aircraft-centric UX for ADSBuddy, making aircraft identity the focal point for navigation, trigger creation, and historical analysis. All features flow from a single aircraft detail page, eliminating fragmented workflows and setting the foundation for future map-side panel integration.

---

## Design Principles

1. **Aircraft as focal point** — all navigation flows originate from aircraft identity
2. **Reliability first** — existing CRUD operations must work before new features are shipped
3. **Incremental delivery** — one feature per commit, validated live after each step
4. **Reusable patterns** — shared detail page, trigger prefill, external links across all tables

---

## Feature List & Rollout Order

### Phase 1: Reliability Gate ⚠️ **MUST COMPLETE FIRST**

**Objective:** Fix existing bugs and verify all CRUD operations work correctly

- **Task 1a:** Reproduce and fix trigger deletion bug
  - Current behavior: delete doesn't remove trigger
  - Investigation: check route handler, DB operation, frontend removal
  - Success criteria: delete removes trigger from DB and UI
  - Live validation: test delete via running Docker site

- **Task 1b:** Verify trigger create/edit/toggle/delete all persist
  - Spot-check each operation in the live site
  - Confirm DB changes match UI changes
  - Smoke test after Docker restart

**Commits:**
- `fix: correct trigger deletion persistence`
- `test: verify CRUD operations work end-to-end`

**Docker validation:** Restart Docker after both fixes, test live site

---

### Phase 2: Aircraft-Centric Navigation

**Objective:** Make aircraft detail the hub for all aircraft-related workflows

- **Task 2a:** Create aircraft detail page
  - New route: `GET /aircraft/{icao_hex}`
  - Components:
    - Aircraft identity card (tail, hex, type, description, owner/operator, year, last seen)
    - Recent sightings list (with timestamps, callsigns, routes)
    - Recent firings list (recent trigger matches)
    - External reference links (tail → registry pages, type → Wikipedia)
    - Action buttons: Create Trigger, View History
  - Data: query DB for aircraft, sightings, firings; build summary view

- **Task 2b:** Add internal links from existing tables
  - Tail number click → `/aircraft/{icao_hex}`
  - Type code click → `/aircraft/{icao_hex}` (jump to aircraft detail, which has type refs)
  - Route: make sure table rows are navigable

- **Task 2c:** Add external-link icons
  - Small icon next to tail/type text
  - Tail icon links to aircraft registry/manufacturer (curated mapping + fallback)
  - Type icon links to aircraft Wikipedia or reference page
  - Design: subtle, contextual, no visual clutter

**Commits:**
- `feat: add aircraft detail page at /aircraft/{icao_hex}`
- `feat: add internal links from tables to aircraft detail`
- `feat: add external-link icons for registry and reference pages`

**Docker validation:** Restart Docker after each commit, verify navigation works live

---

### Phase 3: Trigger Creation from Context

**Objective:** Make it one click to create a trigger from any aircraft view

- **Task 3a:** Implement trigger prefill flow
  - New route: `GET /triggers/new?tail=...&hex=...&type=...&callsign=...&year=...`
  - Pre-populate trigger form with these values
  - User completes: frequency filters, route, altitude, etc.
  - Submit creates trigger

- **Task 3b:** Add "Create Trigger" button to aircraft detail
  - Button appears on aircraft detail page
  - Clicking it opens `/triggers/new?hex={icao_hex}&tail={tail}&type={type}`
  - Prefilled form fields match aircraft identity

- **Task 3c:** Add "Create Trigger" action to aircraft/firings/history tables
  - Small action menu per row (or inline button)
  - Clicking prefills trigger form with row data
  - Submit creates trigger

**Commits:**
- `feat: add trigger prefill flow from aircraft context`
- `feat: add create-trigger buttons to aircraft detail and tables`

**Docker validation:** Restart Docker after each commit, verify trigger creation works end-to-end

---

### Phase 4: Historical Search v1

**Objective:** Search stored aircraft/sightings data by multiple criteria

- **Task 4a:** Create historical search UI page
  - New route: `GET /history`
  - Filter inputs:
    - Tail number (text)
    - ICAO hex (text)
    - Callsign (text)
    - Type code (text)
    - Owner/operator (text/dropdown)
    - Year (dropdown or range)
    - Route (text)
    - Time range (date picker + time)
  - Search button and clear button

- **Task 4b:** Implement search query logic
  - Query sightings table with AND/OR logic
  - Apply filters: aircraft tail, type, callsign, date range, route, etc.
  - Return results with aircraft + sighting metadata

- **Task 4c:** Display search results
  - Results list view (or table)
  - Each result row:
    - Aircraft summary (tail, hex, type)
    - Sighting summary (callsign, route, timestamp)
    - Actions: View Aircraft Detail, Create Trigger

**Commits:**
- `feat: add historical search page with filter UI`
- `feat: implement multi-filter search query logic`
- `feat: display search results with contextual actions`

**Docker validation:** Restart Docker after each commit, verify search queries work live

---

### Phase 5: Table Usability Enhancements

**Objective:** Improve table navigation and discoverability

- **Task 5a:** Add sticky table headers
  - Header row stays visible while scrolling
  - Applied to: aircraft table, firings table, sightings table, history results
  - CSS: `position: sticky; top: 0; z-index: 10`

- **Task 5b:** Add top filter/index bar to non-front-page tables
  - Quick-filter buttons: A–Z, 0–9, active/paused (where applicable)
  - Time bucket filters (last hour, last day, last week)
  - Clicking filters narrows the table in place
  - Clear filter option

- **Task 5c:** Standardize table actions
  - Each row: View Detail, Create Trigger, External Links
  - Consistent styling and behavior across all tables
  - Responsive on mobile

**Commits:**
- `feat: add sticky table headers to all data tables`
- `feat: add top filter/index bars for table navigation`
- `feat: standardize table row actions across the app`

**Docker validation:** Restart Docker after each commit, verify table interactions work live

---

## Validation Strategy

### Per-Feature Validation

For each task, before commit:

1. **Automated tests** — write or update tests for new routes/helpers/queries
2. **Manual smoke test** — test the feature in the running Docker site
3. **Docker restart** — stop and restart Docker containers
4. **Live re-test** — verify feature still works after restart
5. **Commit** — only if steps 1–4 pass

### Smoke Test Checklist

After each Docker restart, verify:
- [ ] Site loads (home page, login works)
- [ ] Navigation flows work (click aircraft → detail page)
- [ ] Trigger operations work (create, edit, toggle, delete all persist)
- [ ] Search returns results (if phase 4+ is active)
- [ ] External links open correctly
- [ ] Table actions are responsive

### Failure Response

If a feature fails smoke test:
- Do NOT commit
- Debug the issue
- Fix and re-test
- Re-run Docker restart validation
- Then commit only after passing validation

---

## Commit Cadence

**One commit per completed task.** Tasks are granular enough that each commit is meaningful:

```
fix: correct trigger deletion persistence
feat: add aircraft detail page at /aircraft/{icao_hex}
feat: add internal links from tables to aircraft detail
feat: add external-link icons for registry and reference pages
feat: add trigger prefill flow from aircraft context
feat: add create-trigger buttons to aircraft detail and tables
feat: add historical search page with filter UI
feat: implement multi-filter search query logic
feat: display search results with contextual actions
feat: add sticky table headers to all data tables
feat: add top filter/index bars for table navigation
feat: standardize table row actions across the app
```

Each commit includes:
- Implementation code
- Test additions/updates
- Evidence: "Verified live at [URL] after Docker restart"

---

## Autonomous Execution Strategy

Since you're leaving for a while, here's how I'll work:

1. **Fix reliability gate first** (Phase 1)
   - Reproduce trigger delete bug
   - Fix in code
   - Write test
   - Commit
   - Test live
   
2. **Per-feature loop** (Phases 2–5)
   - Delegate to `foundation:modular-builder` for implementation
   - Delegate to `foundation:test-coverage` for test verification
   - Manual Docker restart and smoke test
   - Commit via `foundation:git-ops`
   - Record progress

3. **Parallel work** where possible
   - If frontend and backend are independent, delegate to separate agents
   - Use multiple agent sessions concurrently
   - Reconverge at Docker validation

4. **Safety gates**
   - Never commit without passing Docker restart validation
   - Never skip tests
   - Never ship with broken CRUD operations

---

## Data Model Assumptions

**Existing tables assumed:**
- `aircraft` (icao_hex, tail, type, description, owner_operator, last_seen)
- `sightings` (aircraft_id, callsign, route, timestamp, altitude)
- `triggers` (id, tail, type, callsign, created_at, enabled)
- `firings` (trigger_id, timestamp, status)

**New queries needed:**
- `GET /api/aircraft/{icao_hex}` — aircraft detail + recent sightings + recent firings
- `GET /api/history?filters...` — search sightings with multi-filter support
- `GET /triggers/new?params...` — prefill trigger form from query params

---

## Success Criteria

**Phase 1 (Reliability):**
- Trigger delete removes DB row and UI element
- All CRUD operations verified in live site

**Phases 2–5 (Features):**
- Each feature has automated tests
- Each feature works in live Docker site after restart
- Navigation flows are intuitive and responsive
- Aircraft detail becomes the obvious hub for workflows

**Overall:**
- 12 commits pushed to main
- All features live on your Tailscale HTTPS URL
- Site is stable and usable for daily ADSBuddy monitoring and trigger creation

---

## Estimated Timeline

- Phase 1: 1–2 hours (fixing existing bugs)
- Phase 2: 2–3 hours (aircraft-centric navigation)
- Phase 3: 1–2 hours (trigger prefill)
- Phase 4: 2–3 hours (historical search)
- Phase 5: 1–2 hours (table enhancements)

**Total:** ~9–12 hours of autonomous work, with incremental commits and validation at each step.

---

## Notes

- All work is on `main` branch (per your earlier request)
- Docker restart validation is mandatory before each commit
- Subagent-driven development with per-feature isolation
- User is not in the room — all work must be self-validating
- Reliability gate (Phase 1) is a blocker for all subsequent phases
