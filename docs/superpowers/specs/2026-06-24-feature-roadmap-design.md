# ADSBuddy Feature Roadmap — Design

**Date:** 2026-06-24
**Status:** Draft for review
**Scope:** Seven requested features, designed up front and decomposed into independently-shippable sub-projects. Each phase becomes its own implementation plan when we get to it. Nothing here is built yet.

---

## Overview

Seven asks, ranging from small UI polish to new subsystems (multi-source ingest, a query model change, an auth provider). This document designs all of them, fixes the architecture/ordering, and flags the open decisions to confirm before we build. The build order is chosen so shared surfaces (ingest, the trigger model) are touched once, not repeatedly.

## Phasing & dependencies

| Phase | Feature | Size | Depends on |
|------|---------|------|-----------|
| **A1** | #1 Compact buttons + smarter external links (FAA deep-link) | S | — |
| **A2** | #4 Delivery-log purge (auto + on-demand) | S | — |
| **B**  | #6/#7 Multiple radio sources + push feed | M | — |
| **C**  | #2 Sighting de-duplication + historical downsample | M–L | B (ingest) |
| **D**  | #5 Trigger designer with exclusions (negation) | M–L | — |
| **E**  | #8 OAuth alongside Tailscale/local auth | L | — |

A1/A2 are quick wins. B before C so ingest is reworked once. D and E are independent and can slot wherever.

---

## A1 — Compact buttons + smarter external links (#1)

**Goal:** Tighter row-action buttons; replace the cryptic `↗` superscript with clear, labeled links; make the FAA tail link land on the actual record.

**Design:**
- **Compact actions:** unify row actions (Pause/Activate, Edit, Delete, History, Detail, +Trigger) on a single small button style (`.btn-small` sizing, reduced padding, consistent height). Apply across triggers, firings, aircraft, history, users.
- **External links:** drop `.ext-link` `↗`. Render a short, muted, labeled link after the value — e.g. `N424LF · FAA`, `B738 · Wiki`, `a50b7b · OpenSky` — each opening in a new tab. Labels read clearly and are keyboard/screen-reader friendly.
- **FAA deep-link:** `registration_url()` for US N-numbers now points at the **result** page:
  `https://registry.faa.gov/AircraftInquiry/Search/NNumberResult?nNumberTxt=<N>` (verified 200, lands on the record). Non-US tails keep airframes.org. Wikipedia/OpenSky helpers unchanged.

**Touch:** `app/aircraft_helpers.py` (FAA URL), `app/static/app.css` (button + link styles), the table templates (link markup). Pure-function tests for the FAA URL; render assertions for the new link label.

**Decision to confirm:** label style — `value · FAA` text links (recommended) vs. small inline icons with tooltips.

---

## A2 — Delivery-log purge (#4)

**Goal:** Keep `notification_deliveries` from growing forever; purge automatically on a retention window and on demand.

**Design:**
- New setting `delivery_retention_days` (default e.g. 30; 0/blank disables) — mirrors `sightings_retention_days`.
- Background prune in the ingester's hourly cleanup (`_maybe_cleanup_sightings` gains a sibling `_maybe_cleanup_deliveries`), batched deletes of rows older than the cutoff.
- **On-demand:** a "Purge delivered/old log" button on admin **Diagnostics** (POST `/admin/diagnostics/purge`) with a confirm, deleting by the same cutoff (and/or a "clear all test sends" option). Admin-only.

**Touch:** `app/settings_store.py`, `app/ingest.py`, `app/routes_admin.py`, `admin_diagnostics.html`. Tests for the cutoff parse + purge query (mocked session) + button render.

---

## B — Multiple radio sources + push feed (#6/#7)

**Goal:** Enroll several feeds instead of one hard-coded radio; support both **polled** sources (current behavior) and **pushed** feeds (a feeder posts to us). Re-characterize the existing single connection as the first source.

**Design:**
- **New model `RadioSource`:** `id, name, kind('poll'|'push'), url (poll only), token (push only, secret), is_active, last_seen_at, created_at`. (Receiver-location learning becomes per-source: move `receiver_lat/lon` onto the source, or keep a per-source receiver row.)
- **Ingest (poll):** each tick iterates **active poll sources**; sightings are tagged `source = <source name>` (the `sightings.source` column already exists). One slow/broken source can't block others (per-source try/except + timeout, as today).
- **Ingest (push):** `POST /ingest/{token}` accepting an aircraft.json-shaped body; authenticates by the source's token; runs the same upsert/sighting/trigger pipeline, tagging `source`. Bounded body size; rate-limited.
- **Migration / re-characterization:** on first boot after upgrade, if `radio_sources` is empty, seed one `poll` source named "Local radio" from the existing `radio_base_url` setting. `radio_base_url` is kept read-only/deprecated (or removed) once migrated.
- **Admin UI:** a **Sources** tab (under System, or its own) to add/edit/enable sources, see each one's last-seen + tagged sighting counts, and copy a push source's ingest URL/token.

**#7 mapping:** "fed from the adsb.im radio to this radio" = (a) add the adsb.im box as a **poll** source (covered by the sources model) **and** (b) support a **push** source so a feeder can send to us. Both are in this phase.

**Risks:** push endpoint is the first unauthenticated-by-cookie ingress — gate strictly by per-source token, bound payload size, never trust source-supplied `source` names. Migration must not lose the current radio.

**Decisions to confirm:** push auth via path token vs. header bearer; whether `radio_base_url` is removed or kept as a deprecated alias.

---

## C — Sighting de-duplication + historical downsample (#2)

**Goal:** Stop storing a position every 5s per aircraft. Store on **airspace entry**, at most every **~3 minutes** while present, and the **exit** point — then apply the same reduction to the existing ~8.4M rows to cut storage dramatically.

**Design:**
- **Visit model:** a "visit" is a contiguous run of sightings for one `icao_hex`; a new visit begins when the gap since that hex's last sighting exceeds `visit_gap_minutes` (default ~10, informed by the `seen` staleness field).
- **Write policy (ingest):** keep an in-memory per-hex `last_stored_at`/`last_seen_at`. Store a sighting when: (1) it's a new visit (**entry**), or (2) `>= sighting_min_interval_seconds` (default 180) since the last stored row for that hex. The most recent position is always reflected by the latest stored row; an explicit **exit** marker is recorded when a visit is detected to have ended (lazily, on the next tick where the hex has aged out). New settings: `sighting_min_interval_seconds`, `visit_gap_minutes`.
- **Historical downsample (one-time, batched maintenance job):** per `icao_hex`, partition existing rows into visits, keep the first row of each visit + one row per `sighting_min_interval_seconds` bucket (+ the last row of each visit), delete the rest. Runs in bounded batches; **irreversible** → ships with a **dry-run that reports how many rows would be deleted** and requires an explicit confirm (admin action or one-shot command). Triggered firings and their snapshots are untouched.

**Risks:** irreversibility of the downsample (mitigated by dry-run + backup guidance); correctness of visit partitioning at scale (do it set-based in SQL with window functions, batched by hex range). Interacts with `store_raw_sightings` (raw rows shrink proportionally).

**Decisions to confirm:** exact defaults (3 min cadence, 10 min visit gap); whether the historical downsample is an admin button or a maintenance CLI; keep-exit-point yes/no.

---

## D — Trigger designer with exclusions / negation (#5)

**Goal:** Support "match X **but not** Y", e.g. *older than 70 years but not a de Havilland Beaver/Otter*.

**Design (recommended — exclusion fields):**
- Add **exclude** counterparts for the high-value dimensions: `exclude_type_codes`, `exclude_tail_patterns`, `exclude_flight_patterns`, `exclude_owner_patterns`. Semantics: a trigger matches when **all positive conditions match AND none of the exclude conditions match**. The example becomes: `min_age_years=70` + `exclude_type_codes=DHC2,DHC3` (Beaver/Otter).
- Matcher: after the existing positive checks, return False if any populated exclude-set matches the aircraft. Pure, unit-testable (mirrors the positive helpers).
- Form: an **"Exclusions"** fieldset grouping the exclude fields; conditions summary shows `not type: …`, etc. Migration adds the columns.
- **Alternative (deferred):** a full boolean expression/group builder (nested AND/OR/NOT). More powerful but a much larger model + UI change; the exclusion-fields approach covers the stated need and the common cases without that complexity.

**Touch:** `app/models.py` (+ migration), `app/triggers.py` (matcher + `AircraftFacts` already has what's needed), `routes_triggers.py` (form apply + condition summary), `trigger_form.html`. Matcher tests for each exclusion + combined positive/negative.

**Decision to confirm:** exclusion-fields (recommended) vs. full boolean builder.

---

## E — OAuth alongside Tailscale/local auth (#8)

**Goal:** Let users sign in via an external identity provider (e.g. Google, GitHub / generic OIDC) in addition to the current local username/password (which already rides the tailnet).

**Design:**
- **Providers:** generic **OIDC** config (issuer, client_id, client_secret, scopes) for one or more providers, stored as admin settings (secret-flagged) — start with Google and GitHub presets. Disabled until configured.
- **Flow:** `/auth/oauth/{provider}/login` → provider → `/auth/oauth/{provider}/callback` → verify, then mint the existing `UserSession` cookie (reuse current session machinery). Login page shows "Sign in with …" buttons only for configured providers.
- **Account model:** a `user_identities` table (`user_id, provider, subject, email`) linking external identities to local `users`. On callback: match an existing identity → log in; else match a local user by verified email and link; else (admin toggle `oauth_auto_provision`) create a new non-admin user or refuse. Local login and `/test/login` remain.
- **Security:** state/nonce/PKCE, HTTPS redirect URIs (we're behind Tailscale Serve TLS on :8443), exact redirect-URI registration, tokens never logged.

**Touch:** new `app/routes_oauth.py`, `app/models.py` (+ identities table migration), `app/settings_store.py` (provider config), `login.html`, deps/session glue. Likely a small dependency (e.g. `authlib`) — to be confirmed.

**Risks:** largest surface; redirect-URI/issuer config must be exact; account-linking edge cases (same email, different provider). Keep it strictly additive — local/tailnet auth keeps working untouched.

**Decisions to confirm:** which providers first (Google/GitHub/generic OIDC); auto-provision vs. invite-only; add a dependency (`authlib`) vs. hand-rolled OIDC.

---

## Cross-cutting

- **Migrations:** chain continues from `0011`; each phase adds its own. All additive/nullable where possible.
- **Tests + live-verify:** every phase keeps the suite green and is Docker-rebuilt + verified before commit, per the established workflow.
- **No push without ask;** each phase merges to `main` on your go-ahead.

## Open decisions (consolidated — please confirm in review)

1. **#1** link style: `value · FAA` text links (rec.) vs. inline icons.
2. **#6** push auth: path token (rec.) vs. header bearer; keep or drop `radio_base_url`.
3. **#2** dedup defaults: 3-min cadence / 10-min visit gap; downsample as admin button (rec.) vs. CLI; irreversible — OK with dry-run + confirm?
4. **#5** exclusion fields (rec.) vs. full boolean builder.
5. **#8** providers first (Google/GitHub?); auto-provision policy; `authlib` dependency OK?

## Out of scope (for now)

- Full boolean trigger expressions (beyond exclusions).
- AIS/boats, smart-glasses/AR clients (longer-term per project vision).
- The tar1090 map page.
