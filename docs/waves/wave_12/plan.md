# Wave 12 Dispatch â€” "Make It Usable"

**Date:** 2026-03-14
**Status:** Draft â€” pending operator review
**Depends on:** Wave 11 complete (27-event union, Beta confidence, LLM dedup, templates, naming, suggest-team, colony creator, template browser)
**ADR:** 018-frontend-rewrite.md
**Visual spec:** `docs/prototype/formicos-v2.jsx` (1509-line React prototype)
**Implementation reference:** See the "3-Team Parallel Implementation Plan" below (Â§10)

---

## Theme

The backend is sophisticated. The frontend doesn't show it. Wave 12 upgrades every frontend component to match the v2.1 prototype â€” making the system usable by someone who didn't build it.

**This is a frontend-only wave. The backend is frozen.** No new events, no new REST routes, no new WS commands. Every data surface already exists.

---

## Read Order

1. `CLAUDE.md`
2. `AGENTS.md` (updated for Wave 12)
3. `docs/decisions/018-frontend-rewrite.md`
4. `docs/prototype/formicos-v2.jsx` â€” **THE VISUAL SPEC. Read the entire file.**
5. `docs/contracts/types.ts` â€” data shapes
6. `frontend/src/types.ts` â€” current TypeScript types
7. `frontend/src/state/store.ts` â€” current state management
8. `frontend/src/ws/client.ts` â€” current WebSocket client
9. `frontend/src/styles/shared.ts` â€” current design tokens
10. `frontend/src/components/atoms.ts` â€” current design primitives
11. Skim all existing `frontend/src/components/*.ts` for current state

---

## Structure: Step 0 + 3 Parallel Teams

### Step 0 â€” Shared Extraction (serial, before teams diverge)

One coder handles this. ~30 minutes. Must merge before Phase 1 starts.

**Owns:** `frontend/src/styles/shared.ts`, `frontend/src/components/atoms.ts`, `frontend/src/helpers.ts` (new)

Work:
1. **Update design tokens in `shared.ts`** to match the prototype's Luminous Void palette:
   - Verify `V` object values match prototype (void, surface, elevated, recessed, border, fg variants, accent variants, success, warn, danger, purple, blue, glass, pheromone levels)
   - Add provider color map: `--provider-local: var(--v-success)`, `--provider-anthropic: var(--v-accent)`, `--provider-gemini: var(--v-blue)`
   - Verify font stack (`F.display`, `F.body`, `F.mono`) matches

2. **Extend `atoms.ts`** with missing prototype atoms:
   - `fc-sparkline` â€” convergence sparkline (SVG polyline, data array â†’ rendered line)
   - `fc-defense-gauge` â€” circular SVG gauge with threshold coloring
   - `fc-quality-dot` â€” colored dot based on quality score
   - `fc-pheromone-bar` â€” labeled progress bar with trend indicator
   - `fc-gradient-text` â€” gradient-clipped text for headings
   - Verify existing atoms (`fc-pill`, `fc-dot`, `fc-meter`, `fc-btn`, `fc-glass`) match prototype styling

3. **Create `frontend/src/helpers.ts`** â€” shared utilities:
   ```typescript
   export function findNode(nodes, id)    // tree traversal
   export function allColonies(nodes)     // flatten colonies from tree
   export function breadcrumbs(nodes, id) // path from root to node
   export function timeAgo(iso)           // relative time display
   export function colonyName(colony)     // displayName || id
   export function providerOf(model)      // "anthropic" | "gemini" | "llama-cpp" | "local"
   export function providerColor(model)   // CSS variable for provider
   ```

**Acceptance:** All existing tests pass. `npm run build` clean. No visual changes yet â€” just infrastructure.

---

## Phase 1 â€” Three Parallel Teams

### Team A â€” Core Shell + Real-Time Engine

**Owns:** `formicos-app.ts`, `tree-nav.ts`, `queen-chat.ts`, `queen-overview.ts`, `approval-queue.ts`, `breadcrumb-nav.ts`, `state/store.ts`, `ws/client.ts`, `frontend/src/types.ts` (**frontend-only derived-field additions only; no backend contract drift**)

**Does NOT touch:** `colony-detail.ts`, `colony-creator.ts`, `thread-view.ts`, `skill-browser.ts`, `template-browser.ts`, `model-registry.ts`, `castes-view.ts`, `workspace-config.ts`, `settings-view.ts`, `round-history.ts`

Delegate to 3 sub-agents:

**Sub-agent A1 â€” AppShell + State Store** (~300 LOC changes)

The main shell gets a layout overhaul:
- **Collapsible sidebar** â€” full width (195px) on hover, icon-only (46px) collapsed. Shows tree nav when expanded, running colony icons when collapsed.
- **Top bar** â€” formicOS logo, breadcrumbs (when navigating tree), protocol status strip, cost/VRAM summary, approval badge with pulse animation
- **Content router** â€” view switching based on `view` state: `queen`, `skills`, `templates`, `models`, `castes`, `settings`, `tree` (tree selection renders colony/thread/workspace detail)
- **Navigation tabs** in sidebar: Queen (â™›), Skills (â—ˆ), Templates (â§‰), Models (â¬¢), Castes (â¬¡), Settings (âš™)

State store updates:
- Ensure `displayName` flows through to colony rendering everywhere
- Add `convergenceHistory` array to colony state (populated from `RoundCompleted` events)
- Track `activeQueenThread` for multi-thread chat
- Own any frontend-only type additions needed to support those client-derived fields in `frontend/src/types.ts`

**Sub-agent A2 â€” Queen Chat Panel** (~200 LOC changes)

Upgrade from basic chat to always-accessible panel:
- **Multi-thread tabs** â€” switch between queen threads per workspace
- **Event annotations inline** â€” `ColonySpawned`, `RoundCompleted`, `ModelRouted`, `PheromoneUpdate` appear as compact colored lines (not full messages). Color by `kind`: spawn=green, merge=cyan, metric=purple, route=amber, pheromone=accent.
- **Operator input** â€” text field with "Direct the Queen..." placeholder, Enter to send
- **Position** â€” right side of content area, collapsible. Always visible when expanded, doesn't overlay content â€” it's a flex sibling.

**Sub-agent A3 â€” Queen Overview + Approvals + TreeNav** (~400 LOC changes)

Queen Overview becomes the fleet dashboard:
- **Colony fleet** â€” all colonies as cards grouped by workspace. Each card: display name (not UUID), status dot, round progress `R4/10`, caste icons, provider mix dots (colored circles per provider used), convergence + sparkline, cost, quality dot (if completed), skills extracted badge.
- **Resource meters strip** â€” 4 glass cards: Budget (total cost vs total budgets), VRAM (loaded models vs 32GB), Anthropic spend, Gemini spend. Each uses `fc-meter`.
- **Approval queue** â€” featured glass cards with accent border. Type, agent, detail, colony name. Approve (green) and Deny (red) buttons inline. Badge count in top bar.
- **Template quick-launch** â€” 3 most-used templates as clickable glass cards. Caste icons, tags, use count. Click â†’ open colony creator.
- **Skill bank summary line** â€” "N skills Â· avg confidence X%" with link to skill browser.

TreeNav upgrades:
- Colony nodes show `displayName` (via `colonyName()` helper), not raw ID
- Quality dot beside completed colonies
- Status dot colors match prototype (running=green pulse, completed=cyan, queued=amber, failed/killed=red)

### Team B â€” Colony Lifecycle + Topology

**Owns:** `colony-detail.ts`, `round-history.ts`, `colony-creator.ts`, `thread-view.ts`, new `topology-graph.ts`

**Does NOT touch:** `formicos-app.ts`, `tree-nav.ts`, `queen-chat.ts`, `queen-overview.ts`, `skill-browser.ts`, `template-browser.ts`, `model-registry.ts`, `castes-view.ts`, `workspace-config.ts`, `settings-view.ts`, `state/store.ts`, `ws/client.ts`

Delegate to 3 sub-agents:

**Sub-agent B1 â€” Colony Detail + Round Timeline** (~500 LOC changes)

The main monitoring view. This is where operators spend most of their time.

Colony detail header:
- Display name + UUID subtitle
- Status pill with colored dot
- Strategy badge (stigmergic/sequential)
- Template badge ("from Code Review" if spawned from template)
- Quality pill (if completed: "quality 81%")
- Task description (full text)

Metrics + topology grid (3:2 ratio):
- Left: Topology graph (see B2)
- Right: Convergence meter + sparkline, cost meter ($ used / $ budget), token meter (total k), defense gauge (if present)

Agent table:
- Columns: status dot, name, caste icon, model (with provider-colored dot + address), tokens, pheromone bar, status pill
- Model column is critical â€” shows the *routed* model, not the default

Action buttons:
- Intervene, Extend Rounds, Save as Template, Kill Colony (red, danger variant)

Round timeline (expandable):
- Left border colored by phase (Goal=accent, Execute=blue, Route=amber)
- Collapsed: round number, phase, convergence %, cost, duration, per-agent summary (dot + name + model + tokens)
- Expanded: per-agent details: output summary text (1-2 sentences), tool call pills (purple), model with provider dot, tokens, duration
- This is the biggest new feature in the UI â€” operators can trace what every agent did in every round

**Sub-agent B2 â€” Topology Graph** (~200 LOC new file)

New `topology-graph.ts` component. SVG-based pheromone visualization.
- Nodes = agents as rounded rectangles with caste-colored borders. Label is caste name in mono font.
- Edges = weighted lines. Thickness = pheromone weight. Strong trails (w > 1.2) get accent glow. Weak trails use dashed lines.
- Hover: highlight hovered node + all connected edges. Show faint outer ring on hovered node.
- Arrow markers on edges showing direction.
- `NO TOPOLOGY DATA` empty state for sequential colonies.

Data shape: `{ nodes: [{id, label, x, y, c, caste}], edges: [{from, to, w}] }` â€” positions come from the backend snapshot. Frontend renders, doesn't layout.

**Sub-agent B3 â€” Colony Creator + Thread View** (~200 LOC changes)

Colony creator already exists (`colony-creator.ts`). Upgrades:
- Step indicators as dot + line + dot (not just text). Done steps = green, active = accent, future = border color.
- Step 1: template cards in 2-column grid below the objective. Show name, description, caste names, use count. Selected template gets accent border.
- Step 2: caste rows in glass cards with icon, name, suggestion reasoning, remove button. Available castes shown as "+Name" pills below.
- Step 3: glass summary card with objective, caste pills, budget, template name if used.
- Post-launch: dispatch `spawn-colony` event with `templateId` if from template.
- Public component seam for Team A shell integration:
  - Team B owns the `fc-colony-creator` API
  - It may add optional convenience props such as `initialTemplateId` and `initialObjective`
  - It must keep emitting WS-ready camelCase payload fields: `task`, `casteNames`, `budgetLimit`, optional `templateId`
  - It must keep emitting `cancel`

Thread view upgrades:
- Merge edge SVG arrows between colony cards (curved bezier paths)
- Merge mode: clicking "Merge" toggles crosshair cursor, click source â†’ click target
- Broadcast button
- Each colony card shows the full card treatment from Queen Overview (display name, provider dots, convergence sparkline, etc.)

### Team C â€” Data Views + Configuration

**Owns:** `skill-browser.ts`, `template-browser.ts`, `model-registry.ts`, `castes-view.ts`, `workspace-config.ts`, `settings-view.ts`

**Does NOT touch:** `formicos-app.ts`, `tree-nav.ts`, `queen-chat.ts`, `queen-overview.ts`, `colony-detail.ts`, `colony-creator.ts`, `thread-view.ts`, `round-history.ts`, `state/store.ts`, `ws/client.ts`

Delegate to 3 sub-agents:

**Sub-agent C1 â€” Skill Browser** (~200 LOC changes)

Skill browser already exists. Upgrades to match prototype:
- Sort controls as clickable pills (confidence / freshness / uncertainty)
- Min confidence slider with percentage display
- Each skill card: text preview, source colony pill, age, algorithm version badge, "merged Ã—N" badge
- Right side of each card: large confidence number (colored: â‰¥80% green, â‰¥60% accent, <60% amber), confidence bar, uncertainty range bar (width = uncertainty), Î±/Î² display below

**Sub-agent C2 â€” Model Registry + Castes** (~300 LOC changes)

Model registry upgrades:
- Resource meters strip: GPU VRAM + per-cloud-provider spend meters
- Local models as expandable glass cards: name, quant pill, status pill, provider/id, backend, ctx. Expand for full details (GPU, slots, max ctx, VRAM, quant, backend).
- Cloud endpoints: provider name, status dot, models as pills, spend meter
- Default routing cascade: 5-column grid showing caste icon + name + default model

Castes view upgrades:
- Sidebar list with caste icons and selection highlight (left border = caste color)
- Detail panel: large icon, name, description, system default model (with provider dot), workspace override list

**Sub-agent C3 â€” Workspace Config + Template Browser + Settings** (~200 LOC changes)

Workspace config upgrades:
- Model cascade override display: per-caste rows with icon, name, current value (or "null (inherit)"), override badge
- Governance section: budget meter, strategy, max rounds, convergence threshold as labeled values
- Thread list with click navigation

Template browser already exists. Upgrades:
- 2-column grid layout
- Each card: name, version pill, use count, description, caste icons with names, tags as pills, budget/rounds/strategy in mono font
- Click â†’ opens colony creator with template pre-selected

Settings: event store info, strategy pills, protocol status table.

---

## Cross-Team Integration Map

| Integration Point | Who writes it | Who consumes it |
|-------------------|--------------|-----------------|
| `colonyName(colony)` helper | Step 0 | All teams |
| `providerOf(model)` / `providerColor(model)` | Step 0 | All teams |
| `fc-sparkline` atom | Step 0 | Team A (overview), Team B (colony detail) |
| Navigation: `navTree(id)` / `navTab(viewId)` | Team A (shell) | Team B (thread â†’ colony), Team C (template â†’ creator) |
| `ColonyCard` pattern | Team A (overview) | Team B (thread view) â€” uses same visual pattern |
| `fc-colony-creator` public API (`spawn-colony`, `cancel`, optional initial props) | Team B | Team A (global creator host), Team B (thread view host) |
| Colony creator trigger / host state | Team A (`formicos-app.ts`, overview entry points) | Team B (`fc-colony-creator`) |
| State store shape (`convergenceHistory` is client-derived and optional until Team A lands) | Team A (store.ts, `frontend/src/types.ts`) | Team B, C (read defensively) |
| Design tokens + atoms | Step 0 | All teams |

**Rule:** If two teams need the same visual pattern (e.g., a colony card), they implement it independently using shared atoms. No cross-imports between team-owned components. The shell (Team A) routes to the right view; it doesn't pass data between Team B and Team C components.

---

## Backend Wiring Checklist

Every endpoint the frontend calls. No new endpoints needed.

| Frontend action | Backend surface | Wire |
|----------------|----------------|------|
| Connect + get state | WS `subscribe` â†’ `state` message | `ws/client.ts` â†’ `state/store.ts` |
| Real-time updates | WS `event` messages (27 types) | `ws/client.ts` event handlers |
| Send Queen message | WS `send_queen_message` | Queen chat input â†’ WS command |
| Spawn colony | WS `spawn_colony` (with optional `templateId`) | Colony creator Step 3 â†’ WS command |
| Kill colony | WS `kill_colony` | Colony detail Kill button â†’ WS command |
| Create merge | WS `create_merge` | Thread view merge mode â†’ WS command |
| Prune merge | WS `prune_merge` | Thread view prune button â†’ WS command |
| Broadcast | WS `broadcast` | Thread view broadcast button â†’ WS command |
| Approve/deny | WS `approve` / `deny` | Approval queue buttons â†’ WS command |
| Update config | WS `update_config` | Workspace config â†’ WS command |
| Browse skills | `GET /api/v1/skills` | Skill browser fetch |
| List templates | `GET /api/v1/templates` | Template browser + colony creator fetch |
| Create template | `POST /api/v1/templates` | "Save as Template" button â†’ REST POST |
| Suggest team | `POST /api/v1/suggest-team` | Colony creator Step 1 â†’ REST POST |

**Critical field mappings** (discovered during Wave 10/11 integration):
- Spawn command uses `budgetLimit` (camelCase), not `budget`
- Suggest-team returns `{ objective, castes: [...] }`, not a bare array â€” handle both
- Template REST returns snake_case (`template_id`, `caste_names`, `budget_limit`, `use_count`, `source_colony_id`). Frontend normalizes to camelCase. Existing `colony-creator.ts` and `template-browser.ts` already handle both.
- Skill REST returns `source_colony` (not `source_colony_id`) â€” compatibility layer in backend handles both
- Colony snapshot carries `displayName` â€” use `colonyName(colony)` helper everywhere

---

## What Changes vs Current Frontend

| Component | Current state | Wave 12 target |
|-----------|--------------|----------------|
| `formicos-app.ts` | Basic shell with tabs | Collapsible sidebar, breadcrumbs, protocol strip, approval badge |
| `tree-nav.ts` | Tree with status dots | + displayName, quality dots, caste colors |
| `queen-chat.ts` | Single thread, basic messages | Multi-thread tabs, event annotations with kind-colored dots |
| `queen-overview.ts` | Colony list, basic stats | Fleet dashboard: colony cards with sparklines/provider dots, resource meters, template quick-launch, approval queue, skill summary |
| `colony-detail.ts` | Header + agents table | + topology graph, round timeline, convergence sparkline, defense gauge, template badge, action buttons |
| `round-history.ts` | Basic round list | Expandable per-round per-agent: output summary, tool call pills, model with provider dot |
| `colony-creator.ts` | 3-step flow (works) | Polish: step indicators, template 2-column grid, caste rows in glass cards |
| `thread-view.ts` | Colony list | + merge edge SVG arrows, merge mode, broadcast |
| `skill-browser.ts` | Confidence bars, sort | + uncertainty bars, Î±/Î² display, merged badges, sort pills |
| `template-browser.ts` | Template list (works) | + 2-column grid, richer cards, version pill |
| `model-registry.ts` | Model list | + expandable cards, spend meters, routing cascade grid |
| `castes-view.ts` | Caste list | + sidebar selection, workspace overrides |
| `workspace-config.ts` | Basic config | + model cascade rows, governance display, thread list |
| `settings-view.ts` | Basic settings | + protocol table, strategy pills |
| `atoms.ts` | Pill, Dot, Meter, Btn, Glass | + Sparkline, DefenseGauge, QualityDot, PheromoneBar, GradientText |
| NEW `topology-graph.ts` | (doesn't exist) | SVG pheromone node-link diagram with hover |

---

## Merge Order

```
Step 0 (shared extraction) -- merges first
         |
         |-- Team B (colony + topology + thread) -- may merge after Step 0
         |-- Team C (skills + models + config)  -- may merge after Step 0
         \-- Team A (shell + overview + chat)   -- merges last as integration shell
```

All three teams can code in parallel after Step 0, but Team A should merge last. Team A owns the shell, routing, store, and frontend-only type additions, so it is the safest terminal to absorb final integration polish once Team B/C component APIs are real.

**Allowed second pass:** If Team A needs a final stitch pass after Team B lands `fc-colony-creator` or after Team C lands `template-browser`, that is expected and lower risk than overlapping files.

**Exception:** If Team B's colony card in thread-view needs the exact same visual treatment as Team A's colony card in queen-overview, they both build it from shared atoms. No cross-import.

---

## Exit Gate

```bash
# Full CI (backend unchanged â€” should still pass)
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build

# Frontend validation
# 1. All 16+ views render without console errors
# 2. Colony cards show displayName everywhere (not UUID)
# 3. Provider dots (green/blue/amber) appear on every model reference
# 4. Convergence sparklines render on colony cards and detail
# 5. Round timeline expands to show per-agent output + tool calls
# 6. Topology graph renders with pheromone edges and hover
# 7. Skill browser shows Â± uncertainty bars with Î±/Î²
# 8. Template browser shows 2-column grid with version/use count
# 9. Colony creator 3-step flow works with suggest-team + templates
# 10. Queen chat shows multi-thread tabs with event annotations
# 11. Approval queue shows approve/deny with badge count
# 12. Sidebar collapses to icon-only and expands on hover
# 13. Breadcrumbs update when navigating tree
# 14. "Save as Template" button on completed colony detail
# 15. Resource meters show VRAM + provider spend
# 16. Bundle size < 60KB gzip

# Docker smoke
docker compose build formicos && docker compose up -d
sleep 15 && curl http://localhost:8080/health
# Open browser â†’ verify all views render with live backend
```

---

## Constraints

1. **Frontend only.** Backend frozen. No new events, endpoints, or WS commands.
2. **Lit Web Components.** Not React. The prototype is the visual spec â€” translate to Lit patterns.
3. **Shared atoms and tokens.** Import from `atoms.ts` and `shared.ts`. No inline color values.
4. **Provider colors everywhere.** Every model reference shows a provider-colored dot.
5. **displayName everywhere.** Use `colonyName()` helper. Never show raw UUID as the primary identifier.
6. **No new dependencies.** Lit, Vite, and the existing frontend stack are sufficient.
7. **Handle missing data gracefully.** Nullish coalescing for optional fields. Empty states for all lists.
8. **Bundle target < 60KB gzip.** Current is ~28KB. The upgrade shouldn't 3Ã— it.

---

## Explicit Deferrals (NOT in Wave 12)

| Deferred | Why | Earliest |
|----------|-----|----------|
| SGLang inference swap | Pending benchmark sprint | Wave 13 (conditional) |
| HDBSCAN batch consolidation | < 100 skills | Wave 13+ |
| Knowledge graph | No consumer beyond stall detection | Wave 13 |
| Embedding model upgrade | Not blocking | Wave 13 |
| Experimentation engine | Needs production data | Wave 14+ |
| AG-UI / A2A live integration | Interface-only currently | Wave 14+ |
| Remove LanceDB dependency | Keep fallback one more wave | Wave 13 |

---

## 10. Implementation Reference â€” 3-Team Parallel Plan

*(This section provides the detailed wiring map for coders. See the full "3-Team Parallel Implementation Plan" document for complete context.)*

### Shared Contracts

All teams work against the same state snapshot (`OperatorStateSnapshot`) delivered via WebSocket on subscribe. The full shape:

```typescript
{
  tree: TreeNode[]              // ws â†’ thread â†’ colony hierarchy
  merges: MergeEdge[]           // cross-colony data flow
  queenThreads: QueenThread[]   // conversation history
  approvals: ApprovalRequest[]  // pending decisions
  protocolStatus: ProtocolStatus
  localModels: LocalModel[]
  cloudEndpoints: CloudEndpoint[]
  castes: CasteDefinition[]
  runtimeConfig: RuntimeConfig
  skillBankStats: SkillBankStats
}
```

### Event Processing

The WS client receives 27 event types. Key processing per team:

- **Team A** cares about: `ColonySpawned`, `ColonyCompleted`, `ColonyFailed`, `ColonyKilled`, `ColonyNamed` (update fleet), `QueenMessage` (append to chat), `ApprovalRequested`/`Granted`/`Denied` (badge + queue), `TokensConsumed` (cost updates)
- **Team B** cares about: `RoundStarted`, `PhaseEntered`, `RoundCompleted` (round timeline), `AgentTurnStarted`/`Completed` (agent table + output), `MergeCreated`/`Pruned` (thread view arrows), `ColonyTemplateUsed` (template badge)
- **Team C** cares about: `SkillConfidenceUpdated`, `SkillMerged` (refresh skill browser), `ColonyTemplateCreated` (refresh template browser), `ModelRegistered`, `ModelAssignmentChanged` (model registry), `WorkspaceConfigChanged` (config view)

### Navigation Contract

View IDs: `queen`, `skills`, `templates`, `models`, `castes`, `settings`, `tree`

When `view === "tree"`, the selected tree node determines what renders:
- `node.type === "colony"` â†’ Team B's `colony-detail`
- `node.type === "thread"` â†’ Team B's `thread-view`
- `node.type === "workspace"` â†’ Team C's `workspace-config`

Team A owns the router. Teams B and C register their views but don't control routing.
