# Wave 51: UI Audit Findings

**Date:** 2026-03-20
**Method:** Component-by-component code audit of 36 Lit web components,
cross-referenced with store, WebSocket client, types, and backend routes.

---

## Blockers

None. The UI is functional for its current feature set. No controls cause
data loss or silent corruption.

---

## Surface-Truth Debt

### F1. Global scope UI exists but backend substrate not landed (HIGH)

**Severity:** High
**Components:** [knowledge-browser.ts](frontend/src/components/knowledge-browser.ts),
[config-memory.ts](frontend/src/components/config-memory.ts)
**Evidence:**
- Knowledge browser renders `scope-badge` CSS classes for thread/workspace/global scopes
- "Promote to Global" button renders and calls `POST /api/v1/knowledge/{id}/promote`
  with `target_scope=global`
- Backend endpoint accepts the parameter, but global scope projections, two-phase
  retrieval, and `new_workspace_id` additive field on `MemoryEntryScopeChanged` have
  not landed (Wave 50 Team 1 substrate)
- No knowledge entries will ever have global scope in current state
**Impact:** Operator sees a "Promote to Global" button that appears to succeed but
produces no observable effect. Global scope badge CSS exists but will never render.
**Recommendation:** Either hide global promotion UI behind a feature check, or add
a clear "planned" indicator.

### F2. Learned template badges display without enrichment data (HIGH)

**Severity:** High
**Components:** [fc-preview-card.ts](frontend/src/components/fc-preview-card.ts),
[config-memory.ts](frontend/src/components/config-memory.ts)
**Evidence:**
- Preview card renders template provenance: name, learned/operator badge,
  success/failure counts from `meta.template`
- Config memory fetches `GET /api/v1/workspaces/{id}/templates` and displays
  template cards
- Backend TemplateProjection exists but is not enriched with success_count,
  failure_count, task_category, or learned flag (Wave 50 Team 1 substrate)
- Template consumer merge not landed — Queen tools read disk YAML only
**Impact:** Template section in config-memory will show operator-authored YAML
templates but no learned templates. Preview card template badges will only appear
for operator-authored templates with incomplete metadata.
**Recommendation:** Document current state honestly in template card UI (e.g.,
"Operator-authored templates only. Learned templates planned.").

### F3. Config-memory silently swallows endpoint failures (MEDIUM)

**Severity:** Medium
**Component:** [config-memory.ts](frontend/src/components/config-memory.ts)
**Evidence:**
- Lines 195, 207, 220: Three `fetch()` calls wrapped in try/catch with
  silent return on failure
- Comments read "endpoint may not exist yet"
- If one endpoint fails (e.g., recommendations work but templates 404),
  the component shows partial data with no indication that a data source failed
**Impact:** Operator sees incomplete view without knowing it's incomplete.
**Recommendation:** Show a subtle indicator when a data source fails (e.g.,
a muted "unavailable" label on the missing section).

### F4. fleet-view.ts is dead code (MEDIUM)

**Severity:** Medium
**Component:** [fleet-view.ts](frontend/src/components/fleet-view.ts)
**Evidence:**
- Defines `fc-fleet-view` with Models/Castes tabs delegating to
  `fc-model-registry` and `fc-castes-view`
- `formicos-app.ts` renders `fc-model-registry` directly in the "models" view,
  bypassing `fc-fleet-view` entirely
- No other component references `fc-fleet-view`
**Impact:** Dead code. Increases bundle size and maintenance surface for no value.
**Recommendation:** Remove `fleet-view.ts` or replace the direct `fc-model-registry`
render in `formicos-app.ts` with `fc-fleet-view` if the tabbed layout is desired.

### F5. Settings coordination strategy pills imply configurability (MEDIUM)

**Severity:** Medium
**Component:** [settings-view.ts](frontend/src/components/settings-view.ts)
**Evidence:**
- Renders stigmergic/sequential strategy as styled pills
- No click handlers, no @change, no event emission
- Visual weight and pill styling suggest these are selectable options
**Impact:** Operator may try to click strategy pills expecting to change the
system-wide strategy. Nothing happens.
**Recommendation:** Either make pills visually inert (plain text labels) or
add actual strategy selection functionality.

### F6. Proactive briefing domain override actions not fully wired (MEDIUM)

**Severity:** Medium
**Component:** [proactive-briefing.ts](frontend/src/components/proactive-briefing.ts)
**Evidence:**
- Fetches domain strategies and overrides from forager endpoints
- Displays domain chips with trust/distrust state
- Domain override action buttons (trust/distrust/reset) extracted from data
  but inline action UI incomplete — displays data without providing operator
  controls to change trust from within the briefing view
- Full domain override available via `POST /api/v1/workspaces/{id}/forager/domain-override`
  but not surfaced as clickable actions in briefing
**Impact:** Operator can see domain trust state but must use a different path
to change it.
**Recommendation:** Wire trust/distrust/reset buttons in briefing to the
existing REST endpoint.

### F7. Snapshot-only state for models and protocols (LOW)

**Severity:** Low
**Components:** [formicos-app.ts](frontend/src/components/formicos-app.ts),
[model-registry.ts](frontend/src/components/model-registry.ts),
[settings-view.ts](frontend/src/components/settings-view.ts)
**Evidence:**
- Local models, cloud endpoints, and protocol status are only populated
  from the initial WebSocket state snapshot
- No live events update these values during a session
- If a local model loads/unloads or a cloud endpoint enters cooldown,
  the UI does not reflect this until page refresh or reconnect
**Impact:** Stale model/protocol status during long sessions. Operator may
not realize a model has entered error/cooldown state.
**Recommendation:** Either add periodic polling for model/protocol status,
or emit model-change events from backend on state transitions.

### F8. Queen overview federation/outcomes sections fail silently (LOW)

**Severity:** Low
**Component:** [queen-overview.ts](frontend/src/components/queen-overview.ts)
**Evidence:**
- Fetches federation status and colony outcomes in parallel
- Both wrapped in try/catch with silent failure
- If federation is not configured or outcomes endpoint fails, sections
  simply don't render — no "unavailable" indicator
**Impact:** Minor — absence of a section is less confusing than presence of
wrong data. But operator cannot distinguish "no data" from "endpoint failed."
**Recommendation:** Show a muted "no data available" state rather than
hiding the section entirely.

### F9. Memory API endpoints still exist with deprecation notice (LOW)

**Severity:** Low
**Component:** Backend routes/memory_api.py
**Evidence:**
- Three `/api/v1/memory` endpoints exist alongside `/api/v1/knowledge`
- Each returns `_deprecated: "Use /api/v1/knowledge instead"`
- No frontend component references `/api/v1/memory` — all use `/api/v1/knowledge`
**Impact:** API surface bloat. External consumers (A2A, MCP) might discover
and use deprecated endpoints.
**Recommendation:** Remove deprecated endpoints or add explicit routing
redirect from `/api/v1/memory` → `/api/v1/knowledge`.

---

## Vocabulary Debt

### V1. "Skill Bank" label persists in store state

**Location:** [store.ts](frontend/src/state/store.ts) — `skillBankStats` property
**Issue:** Pre-Wave 38 vocabulary. System uses "knowledge entries" with canonical
types (skill/experience). "Skill bank" is a legacy name from when skills were
the only entry type.
**Recommendation:** Rename `skillBankStats` → `knowledgeStats` in store and
consuming components.

### V2. "Memory" vs "Knowledge" naming inconsistency

**Location:** Multiple — `memoryStats` in store, `MemoryEntryPreview` in types,
`memoryExtractionCompleted` in events
**Issue:** Backend events use "Memory" (MemoryEntryCreated, MemoryEntryScopeChanged)
while UI labels say "Knowledge." Both refer to the same entries.
**Recommendation:** This is a known historical layer — events are frozen
(replay-safe), but UI labels should consistently say "Knowledge." Document
the mapping rather than rename events.

### V3. "Config Memory" view name

**Location:** [config-memory.ts](frontend/src/components/config-memory.ts)
**Issue:** "Config Memory" as a view name is ambiguous. The component shows
three things: configuration recommendations, override history, and templates.
None of these are "memory" in the knowledge-system sense.
**Recommendation:** Consider renaming to "Configuration" or "Config Intelligence."

---

## Tuning / Polish Debt

### P1. Colony creator wizard Step 2 template fetch

**Component:** [colony-creator.ts](frontend/src/components/colony-creator.ts)
**Issue:** Step 2 fetches all templates from `GET /api/v1/templates` but does
not filter by task category or relevance. With many templates, the list may
become unwieldy.
**Recommendation:** Add category-first filtering once task_classifier is
integrated (Wave 50 follow-on).

### P2. Knowledge browser debounce timing

**Component:** [knowledge-browser.ts](frontend/src/components/knowledge-browser.ts)
**Issue:** Search input debounce exists but timing not tunable. For large
knowledge stores, short debounce may cause excessive API calls.
**Recommendation:** Minor polish — adjust debounce if performance issues arise.

### P3. Thread timeline filter persistence

**Component:** [thread-timeline.ts](frontend/src/components/thread-timeline.ts)
**Issue:** Filter selections are local state only. Navigating away and back
resets all filters.
**Recommendation:** Minor polish — store filter state in URL params or
session storage.

---

## Docs Debt

### D1. No inline help or tooltips for operator controls

**Issue:** Complex controls (governance inputs, model policy fields, retrieval
diagnostics) have no inline explanations. Operator must consult
OPERATORS_GUIDE.md separately.
**Recommendation:** Add `title` attributes or help icons for non-obvious fields.

### D2. A2A/AG-UI protocol status shows but is not documented in-UI

**Component:** [settings-view.ts](frontend/src/components/settings-view.ts)
**Issue:** Protocol rows show MCP/AG-UI/A2A status but don't explain what
these protocols are or how to configure them.
**Recommendation:** Link to DEPLOYMENT.md or add one-line descriptions.

---

## Clearly Truthful Controls

The following surfaces are fully wired, produce correct behavior, and have
no known truth mismatches:

- **Queen chat** — message send, thread tabs, new thread creation
- **Preview/result cards** — confirm/cancel/navigate actions
- **Colony creator wizard** — all 4 steps, suggest-team, template selection, launch
- **Colony detail** — chat, audit trail, round history, export, topology
- **Thread view** — rename, merge mode, timeline, workflow steps
- **Approval queue** — approve/deny actions
- **Tree navigation** — expand/collapse, node selection, breadcrumbs
- **Knowledge browser** — search, filter, sort, operator overlays (pin/mute/invalidate), annotations
- **Knowledge library** — file upload, ingest, file listing
- **Playbook** — template CRUD, caste CRUD, caste editor
- **Model registry** — model cards, endpoint cards, policy editing
- **Workspace config** — model overrides, governance settings
- **Directive panel** — type selection, priority toggle, send
- **Demo guide** — trigger maintenance, dismiss

---

## Top 10 Findings (ordered by severity)

1. **F1** — Global scope UI exists but backend substrate not landed
2. **F2** — Learned template badges display without enrichment data
3. **F3** — Config-memory silently swallows endpoint failures
4. **F4** — fleet-view.ts is dead code
5. **F5** — Settings strategy pills imply configurability
6. **F6** — Proactive briefing domain override actions not fully wired
7. **V1** — "Skill Bank" legacy vocabulary in store state
8. **F7** — Snapshot-only state for models and protocols
9. **F8** — Queen overview sections fail silently
10. **V3** — "Config Memory" view name is ambiguous

---

## Highest-Risk Seam Mismatches

1. **Global scope promotion** — UI calls endpoint, endpoint accepts request,
   but downstream projections and retrieval don't act on it. Operator gets
   false success signal.

2. **Learned template display** — Preview card renders template provenance
   from metadata that the backend doesn't yet populate. Cards will appear
   correct for operator-authored templates but show incomplete data.

3. **Config-memory three-endpoint pattern** — Silent failure on any of three
   independent data sources produces a partial view indistinguishable from
   "no data available."

4. **Model/protocol staleness** — Long-running sessions show initial state
   with no live updates for model availability or protocol health changes.
