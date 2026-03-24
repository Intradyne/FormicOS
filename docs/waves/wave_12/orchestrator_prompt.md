# Wave 12 Orchestrator Handoff — "Make It Usable"

You are the orchestrator for FormicOS Wave 12.

Working directory: C:\Users\User\FormicOSa

This wave is **frontend-only**. The backend is frozen — no new events, no new REST endpoints, no new WS commands. Every data surface the frontend needs already exists.

## What shipped before this wave

Wave 11 ("The Skill Bank Grows Up") is complete and validated:
- Event union opened from 22 → 27 events (ColonyTemplateCreated, ColonyTemplateUsed, ColonyNamed, SkillConfidenceUpdated, SkillMerged)
- Bayesian skill confidence with Beta distribution (conf_alpha, conf_beta, UCB exploration bonus in composite scoring)
- LLM-gated deduplication (two-band: exact/semantic/below-threshold, Gemini Flash classifier)
- Colony templates (YAML storage, REST CRUD, immutable versioning, save-from-colony)
- Queen colony naming (Gemini Flash LLM call, 500ms timeout, ColonyNamed event)
- Suggest-team endpoint (POST /api/v1/suggest-team, LLM-recommended castes with reasoning)
- Colony creator (3-step Lit component: Describe → Configure → Launch with parallel suggest-team + template fetch)
- Template browser (Lit component with caste tags, use counts, source colony links)
- Skill browser updated (uncertainty bars, α/β display, merged badges)
- All CI gates green. 27-event union. 3 LLM providers. Qdrant vector store.

The frontend has real infrastructure: `state/store.ts`, `ws/client.ts`, `styles/shared.ts`, `types.ts`, and 17 Lit Web Components. But most components were built before the backend had its current capabilities.

## Wave 12 goal

Upgrade every frontend component to match the v2.1 React prototype (`docs/prototype/formicos-v2.jsx`, 1509 lines). The prototype is the visual spec — each component must match its layout, data wiring, and interaction patterns, translated from React to Lit Web Components.

## Read in this order

1. `CLAUDE.md` — project rules
2. `AGENTS.md` — **CRITICAL: file ownership and coordination rules for this wave**
3. `docs/decisions/018-frontend-rewrite.md` — ADR for this wave
4. `docs/prototype/formicos-v2.jsx` — **THE VISUAL SPEC. Read the entire 1509-line file.**
5. `docs/waves/wave_12/plan.md` — full dispatch with team assignments, wiring map, exit gate
6. `docs/contracts/types.ts` — backend data shapes (frozen)
7. `frontend/src/types.ts` — current TypeScript types (includes all Wave 11 additions)
8. `frontend/src/state/store.ts` — current state management
9. `frontend/src/ws/client.ts` — current WebSocket client
10. `frontend/src/styles/shared.ts` — current design tokens
11. `frontend/src/components/atoms.ts` — current design primitives
12. Skim all existing `frontend/src/components/*.ts` to understand current state

## Execution structure

### Step 0 — Shared extraction (ONE coder, serial, merges first)

Extract shared atoms, tokens, and helpers that all three teams import. Must complete before Phase 1 starts.

**Files:** `frontend/src/styles/shared.ts` (token updates), `frontend/src/components/atoms.ts` (add Sparkline, DefenseGauge, QualityDot, PheromoneBar, GradientText), new `frontend/src/helpers.ts` (findNode, allColonies, breadcrumbs, timeAgo, colonyName, providerOf, providerColor)

### Phase 1 — Three parallel teams, each with 3 sub-agents

**Team A — Core Shell + Real-Time**
Files: `formicos-app.ts`, `tree-nav.ts`, `queen-chat.ts`, `queen-overview.ts`, `approval-queue.ts`, `breadcrumb-nav.ts`, `state/store.ts`, `ws/client.ts`

Sub-agents: A1 (shell + store), A2 (queen chat), A3 (overview + approvals + tree nav)

Key deliverables: collapsible sidebar, breadcrumbs, protocol strip, fleet dashboard with colony cards (sparklines, provider dots, convergence), resource meters, template quick-launch, multi-thread chat with event annotations, approval queue with badge

**Team B — Colony Lifecycle + Topology**
Files: `colony-detail.ts`, `round-history.ts`, `colony-creator.ts`, `thread-view.ts`, new `topology-graph.ts`

Sub-agents: B1 (colony detail + round timeline), B2 (topology graph), B3 (creator + thread view)

Key deliverables: colony detail with expandable round-by-round agent output, topology SVG with pheromone edges and hover, merge edge arrows in thread view, colony creator polish (step indicators, glass cards)

**Team C — Data Views + Config**
Files: `skill-browser.ts`, `template-browser.ts`, `model-registry.ts`, `castes-view.ts`, `workspace-config.ts`, `settings-view.ts`

Sub-agents: C1 (skill browser), C2 (model registry + castes), C3 (workspace config + templates + settings)

Key deliverables: skill browser with uncertainty bars and sort pills, expandable model cards, routing cascade grid, caste sidebar with overrides, 2-column template grid

### Merge order

```
Step 0 ─── first
   │
   ├── Team A ─── independent
   ├── Team B ─── independent
   └── Team C ─── independent
```

## Critical wiring rules

1. **Provider colors everywhere.** Every model reference shows a provider-colored dot: green = llama-cpp (local), amber = anthropic, blue = gemini. Use `providerColor()` from helpers.ts.
2. **displayName everywhere.** Colony cards, tree nav, detail views all show `colonyName(colony)` (displayName || id). UUID is a subtitle, never the primary label.
3. **No inline color values.** Use CSS variables from shared.ts or atom component props.
4. **No cross-team component imports.** Shared atoms only.
5. **Handle missing data.** Nullish coalescing for optional fields. Empty states for all lists.
6. **The prototype is the visual spec.** Match it.

## Critical backend field mappings (from Wave 10/11 integration)

- Spawn WS command uses `budgetLimit` (camelCase), not `budget`
- Suggest-team REST returns `{ objective, castes: [...] }`, not a bare array — handle both shapes
- Template REST returns snake_case (`template_id`, `caste_names`, `budget_limit`, `use_count`). Frontend normalizes to camelCase. Existing colony-creator.ts and template-browser.ts already handle both.
- Colony snapshot carries `displayName` field (populated by ColonyNamed event)
- Skills REST returns `conf_alpha`, `conf_beta` as optional fields — compute uncertainty client-side: `variance = (α*β) / ((α+β)² * (α+β+1))`

## Backend is frozen

The backend passes all CI gates. Do NOT modify any file in `src/formicos/`. No changes to `core/`, `engine/`, `adapters/`, `surface/`. If a frontend component discovers a missing backend field, handle the absence with nullish coalescing and empty states.

## Exit gate

After all teams merge:

```bash
# Backend still green (frozen)
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest

# Frontend build
cd frontend && npm run build

# Visual verification (manual in browser)
# 1. All views render without console errors
# 2. Colony cards show displayName + provider dots everywhere
# 3. Convergence sparklines render
# 4. Round timeline expands with per-agent output + tool calls
# 5. Topology graph renders with pheromone edges
# 6. Skill browser shows uncertainty bars + α/β
# 7. Queen chat shows event annotations with kind-colored dots
# 8. Sidebar collapses/expands
# 9. Colony creator 3-step flow works
# 10. Bundle size < 60KB gzip
```

## Constraints

- Frontend only. Backend frozen.
- Lit Web Components. Not React.
- No new runtime dependencies.
- Bundle target < 60KB gzip.
- The prototype is the visual spec.
