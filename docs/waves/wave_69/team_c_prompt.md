# Wave 69 — Team C: Unified Settings & System Awareness

**Theme:** One settings surface, organized by concern. Read from multiple
backends, write only where a write path already exists. The operator can
see at a glance what the system knows and how it's configured.

## Context

Read `docs/waves/wave_69/wave_69_plan.md` first. This is a rendering wave.
Every setting shown already has a backend source — this wave reorganizes
the frontend to present them coherently.

Read `CLAUDE.md` for hard constraints. Read `docs/design-system-v4.md` for
the Void Protocol design system.

## Your Files (exclusive ownership)

### Frontend
- `frontend/src/components/settings-view.ts` — complete redesign as card
  sections
- `frontend/src/components/system-overview.ts` — **new**, capability
  summary header

### Tests
- No backend tests (zero backend changes)

## Do Not Touch

- `frontend/src/components/queen-chat.ts` — Team A owns
- `frontend/src/components/knowledge-browser.ts` — Team B owns
- `frontend/src/components/knowledge-view.ts` — Team B owns
- `frontend/src/types.ts` — Teams A/B own additions
- `src/formicos/surface/routes/api.py` — Teams A/B own additions
- `src/formicos/surface/projections.py`
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `config/caste_recipes.yaml`
- `src/formicos/surface/knowledge_catalog.py`

## Overlap Coordination

- `formicos-app.ts` — You may adjust the nav labels or tab routing if
  the settings surface subsumes some existing tabs. Teams A and B do not
  touch the nav. Coordinate: do not remove tabs that other teams'
  components depend on. Prefer adding deep-links over removing tabs.
- `frontend/src/state/store.ts` — You read from existing state, do not
  add new state. No conflict with Teams A/B.

---

## Critical Constraint: Read/Write Asymmetry

Current config lives in multiple backends:

| Data | Backend | Write path |
|------|---------|------------|
| Governance (strategy, max rounds, budget, convergence, autonomy) | operator override history (`ConfigSuggestionOverridden`) | `POST /api/v1/workspaces/{id}/config-overrides` |
| Taxonomy tags | `WorkspaceConfigChanged` events | No dedicated settings REST write path confirmed; existing Queen tool path only |
| Model registry | `config/formicos.yaml` + model registry YAML | Partial policy PATCH exists at `/api/v1/models/{address}`; registry facts remain read-mostly |
| Caste model assignments | operator override history / caste policy surface | `POST /api/v1/workspaces/{id}/config-overrides` if the existing component already uses it; otherwise read-only |
| Caste recipes (tool lists, system prompts) | `config/caste_recipes.yaml` | `POST /api/v1/castes/{caste_id}` |
| Addon config | Addon manifest + `WorkspaceConfigChanged` | `PUT /api/v1/addons/{addon_name}/config` |

**Rule:** Do NOT unify the backends. The UI reads from all sources and
presents them as unified. Writes go to the correct backend per section.
If a section has no write path today, present it clearly as **read-only**
with a muted label ("Read-only — managed by config file" or similar).

Specifically:
- Model registry entries (provider, context window, cost): **read-only**.
  Managed by `config/formicos.yaml` or model discovery. A partial model-policy
  PATCH exists, but re-exposing that editor is out of scope for this wave.
- Caste recipes (system prompts, tool lists): **read-only** display in
  settings. The existing `POST /api/v1/castes/{caste_id}` endpoint exists
  but is admin-level. Do not expose inline editing for system prompts.
- Governance config: **editable**. Existing write path works.
- Taxonomy tags: **display-first** in Wave 69. Unless you confirm an existing
  direct settings write path, show the tags clearly and add a muted hint like
  "Set via Queen" rather than inventing a new endpoint here.
- Addon config params: **editable** only through the existing addon config
  route, not through config-overrides.

---

## Track 10: Redesigned Settings Page

### Current state of `settings-view.ts`

The component currently renders (settings-view.ts):
- Colony governance: strategy dropdown, max rounds input, budget input,
  convergence threshold slider, autonomy level selector
- Protocol status: MCP/AG-UI/A2A with connection indicators
- Retrieval diagnostics: embedded `<fc-retrieval-diagnostics>` component
- Save/revert controls

State: `_editStrategy`, `_editMaxRounds`, `_editBudget`,
`_editConvergence`, `_editAutonomy`, `_saving`, `_saveMsg`,
`_diagTiming`, `_diagCounts`, `_diagEmbedModel`, `_diagEmbedDim`,
`_diagSearchMode`.

Write path: `POST /api/v1/workspaces/{id}/config-overrides`, which records
operator overrides. Treat this as an override/editorial surface, not as a
generic workspace-config writer.

### Implementation

**1. Restructure as a single scrollable page with card sections.**

Each section is a glass card (Void Protocol):

```css
.settings-card {
  background: var(--v-surface);
  border: 1px solid var(--v-border);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 12px;
}
.settings-card h3 {
  font-family: var(--f-display);
  font-size: 13px;
  font-weight: 600;
  color: var(--v-fg);
  margin: 0 0 12px 0;
}
```

**2. Card sections in order:**

#### A. Workspace Identity

- **Workspace name** — display from store state. Unless you confirm an
  existing direct write path, keep this read-only in Wave 69.
- **Taxonomy tags** — from `ws.config.taxonomy_tags`. Render as tag pills.
  If you confirm an existing direct settings write path, you may make them
  editable. Otherwise keep them read-only in this wave and show a subtle
  hint that tags are set through the Queen/tooling path, not through this
  card.
- **Project description** — link to the workspace browser's project
  context editor (`.formicos/project_context.md`). Don't duplicate the
  editor — show a preview (first 2 lines) with a "Edit in Workspace"
  link.

#### B. Models

- **Model registry table** — read from store's `runtimeConfig.models.registry`.
  Columns: Model Name, Provider, Context Window, Max Output, Status.
  Provider shown as a colored dot + label.
  Context window formatted as "128K" / "200K".
  **Read-only in this view.** Show muted label: "Managed by configuration
  file / model policy routes."
- **Caste model assignments** — 5-column grid showing which model is
  assigned to Queen/Coder/Reviewer/Researcher/Archivist. Read from
  caste recipes in store. This IS editable via config-overrides if the
  existing model-registry component already has that write path. Check
  `model-registry.ts` for the cascade save logic and replicate it. If
  no save logic exists, show as read-only.

#### C. Knowledge

- **Domain summary** — count of entries per top-level domain. Read from
  knowledge store state. Simple bar chart or just number + domain name
  pairs.
- **Addon index status** — for each addon with index/search capability data
  already present on the addon summary payload, show:
  name, content type, chunk count (if available from addon status),
  health indicator (`fc-dot`), and a "Reindex" button that calls
  `POST /api/v1/addons/{addon_name}/trigger` with the reindex handler.
  If capability metadata is not already in the addon summary payload,
  fall back to description + status + trigger availability. Do not add a
  backend expansion here.
- **Retrieval diagnostics** — embed the existing
  `<fc-retrieval-diagnostics>` component. It already renders timing,
  counts, and embedding config.

#### D. Governance

- Keep the existing governance controls from `settings-view.ts`:
  strategy dropdown, max rounds, budget, convergence threshold,
  autonomy level.
- Restyle as inline controls within the card (not a separate form).
- Save behavior: instant save on change (debounced 500ms), not a
  separate save button. Show a subtle green checkmark that fades after
  1.5s on successful save.

Read the existing `_saveSettings()` method — it already POSTs to
config-overrides. Wire the same logic to `change` events on each
control.

#### E. Protocols

- Keep the existing MCP/AG-UI/A2A status display.
- Restyle as a card section with status indicators.
- **Read-only.** Protocol status is runtime state, not config.

#### F. Addons

- **Addon summary cards** — for each installed addon, show: name,
  version, health status (`fc-dot`), description, tool count, handler
  count, and capability summary when those fields are already present on
  the addon summary payload.
- This is a summary view, not the full addons-view. The existing
  addons-view tab stays for deep-dive (tool call counts, handler
  errors, manual triggers, panel rendering).
- If an addon has config params defined in the addon summary/config payload,
  show them as editable fields. Write via the existing
  `PUT /api/v1/addons/{addon_name}/config` route.

---

## Track 11: System Capability Summary

### Problem

The operator has no quick way to see what the system knows and can do.
They must visit multiple tabs to piece together: how many knowledge
entries, what addons are installed, how many tools the Queen has, what
models are available.

### Implementation

**1. New component `system-overview.ts`.**

A compact header rendered at the top of the settings page (above the
first card section). One or two lines of summary text:

```
38 Queen tools · 4 addons · 3 providers · 847 knowledge entries
across 12 domains · Code index: 2,341 chunks · Docs index: 489 chunks
```

Data sources (all already in store state or fetchable):
- Queen tool count: hardcoded 38 (from caste_recipes) or read from
  caste recipe data in store
- Addon count: `runtimeConfig` or `/api/v1/addons` response
- Provider count: count unique providers in model registry
- Knowledge entry count + domain count: from knowledge store state or
  `/api/v1/knowledge?limit=1` total field
- Addon index chunk counts: from addon status endpoints if available,
  or omit if not readily available

Style: `var(--f-mono)`, 10.5px, `var(--v-fg-muted)`, single line
wrapping allowed. Separator: centered dot (·). No card wrapper — just
text above the first card.

**2. Mount in `settings-view.ts`.**

At the top of the render method, before the first card section:

```typescript
html`<fc-system-overview .runtimeConfig=${this.runtimeConfig}></fc-system-overview>`
```

---

## Track 12: Inline Editing Details

### Implementation

**1. Instant save with visual feedback.**

Replace the current save/revert button pattern with instant save:

```typescript
private _saveTimeout?: number;

private _onControlChange(field: string, value: unknown) {
  clearTimeout(this._saveTimeout);
  this._saveTimeout = window.setTimeout(() => {
    this._saveField(field, value);
  }, 500);
}

private async _saveField(field: string, value: unknown) {
  const resp = await fetch(
    `/api/v1/workspaces/${this.workspaceId}/config-overrides`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        dimension: 'governance',
        original: {},
        overridden: {[field]: value},
        reason: 'Settings update',
      }),
    },
  );
  if (resp.ok) {
    this._showSaveIndicator(field);
  }
}
```

**2. Save indicator.**

A small green checkmark (✓) that appears next to the control and fades
out after 1.5s:

```css
.save-indicator {
  color: var(--v-success);
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.15s;
}
.save-indicator[visible] {
  opacity: 1;
}
```

**3. Validation.**

Client-side only:
- Budget: must be positive number
- Max rounds: 1–50
- Convergence: 0.80–1.00
- Tags: lowercase strings, max 50 chars each, max 20 tags

Show inline validation errors below the control in
`var(--v-danger)` color, 10px `var(--f-mono)`.

---

## Navigation Decision

The settings surface now shows addon summary, model registry info, and
protocol status. These overlap with the existing Addons and Models tabs.

**Recommendation:** Keep both tabs but adjust their purpose:
- **Settings tab:** Overview + config editing. Shows summary cards for
  addons, models, knowledge. The config surface.
- **Addons tab:** Deep-dive into addon operations. Tool call counts,
  handler errors, manual trigger buttons, panel rendering. The ops
  surface.
- **Models tab:** Deep-dive into model operations. Slot utilization,
  VRAM meters, cloud spend, per-model detail cards. The ops surface.

Do not remove tabs. Adjust tab labels if needed for clarity:
- "Settings" → "Settings" (unchanged)
- "Models" → "Models" (unchanged, or "Model Ops" if you want to
  distinguish)
- "Addons" → "Addons" (unchanged, or "Addon Ops")

If you adjust labels, update the `NAV` array in `formicos-app.ts`
(line 29–37).

---

## Empty States

- **Fresh workspace, no config:** All governance fields show defaults.
  Tags section shows "No tags yet" with a text input to add the first
  one.
- **No addons installed:** Addons card shows "No addons installed."
- **No knowledge entries:** Knowledge section shows "0 entries."
  Domain summary is empty.
- **Model registry unavailable:** Models card shows "Model registry
  not available" with read-only label.

---

## Acceptance Gates

- [ ] Single scrollable settings page with card sections
- [ ] System capability summary at the top
- [ ] Workspace identity card with honest tag handling (editable only if a confirmed write path exists; otherwise clear read-only presentation)
- [ ] Models card with registry table (read-only) and caste assignments
- [ ] Knowledge card with domain summary and addon index status
- [ ] Governance card with instant-save inline editing
- [ ] Protocol card with status indicators (read-only)
- [ ] Addons summary card with capability metadata when already available, otherwise coherent fallback summary
- [ ] Read-only sections clearly labeled as read-only
- [ ] No backend changes
- [ ] No new event types
- [ ] All new components follow Void Protocol design system
- [ ] Existing addons and models tabs preserved
- [ ] Validation on editable fields
- [ ] `prefers-reduced-motion` respected

## Validation

```bash
npm run build
npm run lint  # if lint config exists
```
