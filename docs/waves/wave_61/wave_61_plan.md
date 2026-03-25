# Wave 61 — The Colleague Colony

**Goal:** Make the Queen powerful, flexible, and deliberate. Close the
remaining pre-launch UX gaps: workspace visibility, budget controls, and
Queen intelligence depth. Aider benchmark handled separately.

**Event union:** stays at 65. No new events.

---

## Track 1 — Queen Deliberation Mode (backend)

**Problem:** The Queen has 21 tools and no tool for "just talk." Every input
routes toward action. The operator asks "what kind of project would be a
good showcase?" and gets a spawned colony. Wave 60.5 added a DELIBERATE
regex guard that blocks spawning on questions — but blocking isn't enough.
The Queen needs to *actively deliberate*: propose options, show tradeoffs,
and wait for confirmation.

**Current state:**
- `_DELIBERATION_RE` in `queen_intent_parser.py:100-106` catches exploratory
  language and returns `{"action": "DELIBERATE"}`
- `intent_to_tool_call()` returns `{}` for DELIBERATE → no tool → prose
  passes through as chat
- System prompt in `caste_recipes.yaml:45-55` says "respond conversationally"
  for questions, but the LLM has no structured output tool

**Design:**

A. **Add `propose_plan` Queen tool** — structured deliberation output.
   The Queen uses this as the DEFAULT first response for any non-trivial
   task, not just questions.

   ```python
   {
     "name": "propose_plan",
     "description": "Present a proposed plan to the operator before executing. DEFAULT first response for any non-trivial task.",
     "parameters": {
       "summary": "string — One-line summary of the proposed approach",
       "options": [  # 1-4 options
         {"label": "string", "description": "string", "colonies": "int"},
       ],
       "questions": ["string — clarifying questions"],
       "recommendation": "string — which option and why",
     }
   }
   ```

   **`estimated_cost` is NOT an LLM parameter.** The handler computes it
   from the runtime's cost_fn and model registry:
   `colonies * avg_rounds * avg_tokens_per_round * rate`. Annotated per
   option before emitting the QueenMessage. Omitted if cost cannot be
   estimated (local-only models).

   Handler returns QueenMessage with `intent="ask"`,
   `render="proposal_card"`.

B. **Spawn-on-question safety net** — when the LLM returns `spawn_colony`
   or `spawn_parallel` AND the operator's message matches
   `_DELIBERATION_RE`, intercept and convert to `propose_plan`. This is
   the SAFETY NET. The primary mechanism is the system prompt making
   `propose_plan` the default.

C. **Update Queen system prompt** — decision tree:
   - Any non-trivial task → `propose_plan` first
   - Operator confirms ("go ahead", "do it") → `spawn_colony` / `spawn_parallel`
   - Pure questions with no task → conversational response (no tool)
   - Follow-up continuations where operator already approved → spawn directly

**New tests required (3 minimum):**
1. `test_queen_intent_parser.py` — question → DELIBERATE, no spawn
2. `test_queen_intent_parser.py` — direct command → SPAWN, works normally
3. `test_queen_tools.py` — `propose_plan` handler returns QueenMessage with
   `intent="ask"`, `render="proposal_card"`, runtime-computed `estimated_cost`

**Owned files:**
- `src/formicos/surface/queen_tools.py` — new `propose_plan` handler
- `src/formicos/surface/queen_runtime.py` — intercept logic
- `src/formicos/adapters/queen_intent_parser.py` — minor updates
- `config/caste_recipes.yaml` — system prompt (queen section only)
- `tests/unit/adapters/test_queen_intent_parser.py` — new tests
- `tests/unit/surface/test_queen_tools.py` — new tests

**Do not touch:** `core/events.py`, `core/types.py`, `engine/runner.py`

**Validation:**
```bash
pytest tests/unit/adapters/test_queen_intent_parser.py tests/unit/surface/test_queen_tools.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 2 — Proposal Card UI (frontend)

**DEPENDS ON Track 1** (needs the `propose_plan` response shape).

**Design:**

A. **New `proposal-card` component** (`frontend/src/components/proposal-card.ts`)
   — Lit Web Component:
   - Summary header
   - Option cards with runtime-computed cost, colony count, description
   - Clarifying questions section
   - Recommendation highlight
   - "Go ahead" / "Let me adjust" action buttons

B. **Wire into queen-chat.ts** — detect `render="proposal_card"` on
   QueenMessage, render `<proposal-card>` instead of text bubble.

C. **Action buttons** — "Go ahead" sends a message that includes full
   option context: "Go ahead: build a CSV parser with 2 colonies,
   sequential strategy" (not just "Go ahead with Option A"). "Let me
   adjust" opens chat input with proposal context pre-filled.

**Owned files:**
- `frontend/src/components/proposal-card.ts` (NEW)
- `frontend/src/components/queen-chat.ts` — proposal detection
- `frontend/src/types.ts` — ProposalCard type

**Validation:** Visual review. TypeScript compilation passes.

---

## Track 3 — Queen Power Tools (backend)

**Problem:** The Queen orchestrates but can't analyze. Colony outcomes,
knowledge health details, and failure patterns are all computed by the
system but hidden behind hardcoded top-N briefing limits. The Queen
makes decisions with a keyhole view of her own hive's performance.

**Current gaps (from research):**
- Colony outcomes exist in projections but Queen has no direct query tool
- `inspect_colony` shows last round only, truncated at 500 chars
- Proactive briefing capped at top-3 knowledge + top-2 performance insights
- Agents get `knowledge_detail` and `transcript_search` — Queen doesn't
- No colony failure root-cause analysis

**Design — 3 new Queen tools:**

A. **`query_outcomes`** — direct access to colony outcome data with
   filtering. Enables empirical strategy decisions.

   ```python
   {
     "name": "query_outcomes",
     "description": "Query colony outcomes to analyze performance patterns. Use to compare strategies, identify failure patterns, or assess model effectiveness.",
     "parameters": {
       "period": "string — time window (1d, 7d, 30d). Default: 7d",
       "strategy": "string? — filter by strategy (stigmergic, sequential)",
       "succeeded": "bool? — filter by success/failure",
       "min_quality": "float? — minimum quality score",
       "sort_by": "string — cost, quality, rounds, duration. Default: quality",
       "limit": "int — max results. Default: 10",
     }
   }
   ```

   Handler reads from `projections.colony_outcomes`, applies filters,
   returns formatted table with: colony name, task summary (truncated),
   succeeded, rounds, quality, cost (API + local), strategy, entries
   extracted. Plus aggregate stats: avg quality, success rate, total cost.

   Read-only. No new events. Uses existing projection data.

B. **`analyze_colony`** — deep dive into a specific colony beyond what
   `inspect_colony` provides. Shows the full story.

   ```python
   {
     "name": "analyze_colony",
     "description": "Deep analysis of a colony's execution: quality trends, tool failures, cost breakdown, knowledge impact. Use after a colony completes to understand what happened.",
     "parameters": {
       "colony_id": "string",
       "include_rounds": "bool — show per-round quality/cost progression. Default: true",
       "include_tool_calls": "bool — show tool call success/failure. Default: true",
       "include_knowledge": "bool — show knowledge entries accessed/created. Default: true",
     }
   }
   ```

   Handler reads from `ColonyProjection` and `ColonyOutcome`:
   - Per-round quality trend (quality scores per round)
   - Per-round cost progression (cumulative + per-round)
   - Tool call inventory: which tools called, success/failure counts
   - Knowledge impact: entries accessed (with confidence at access time),
     entries extracted (with current confidence)
   - Error summary: last error messages, stall detection triggers
   - Model usage: which models served each agent, fallback events
   - Reasoning token breakdown (from Wave 60.5 accounting)

   Read-only. No new events.

C. **`query_briefing`** — relax hardcoded top-N limits on proactive
   intelligence. Let Queen drill into specific categories.

   ```python
   {
     "name": "query_briefing",
     "description": "Query proactive intelligence insights with filters. Goes deeper than the automatic briefing summary.",
     "parameters": {
       "category": "string? — knowledge_health, performance, learning, evaporation, all. Default: all",
       "rule": "string? — specific rule name (e.g., contradiction, cost_outlier)",
       "limit": "int — max insights. Default: 10",
       "include_suggested_colonies": "bool — show auto-dispatch configs. Default: false",
     }
   }
   ```

   Handler calls `proactive_intelligence.generate_briefing()` with
   relaxed limits, filters by category/rule, returns full insight details
   including `suggested_colony` configs and action metadata.

   Read-only. No new events.

**Owned files:**
- `src/formicos/surface/queen_tools.py` — 3 new tool specs + handlers
- `src/formicos/surface/queen_runtime.py` — register tools in `_queen_tools()`
- `config/caste_recipes.yaml` — add tools to queen tool list
- `tests/unit/surface/test_queen_tools.py` — new tests

**Do not touch:** `core/events.py`, `engine/`, projections (read-only access)

**Validation:**
```bash
pytest tests/unit/surface/test_queen_tools.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 4 — Workspace Browser (frontend)

**Problem:** Colony work product (files, code, diffs) is invisible. The
agent transcript is visible but the deliverable isn't. Backend endpoints
all exist — this is pure frontend.

**Current state (backend, all built):**
- `GET /api/v1/workspaces/{workspace_id}/files` — list workspace files
- `GET /api/v1/workspaces/{workspace_id}/files/{file_name}` — preview
  (20K char truncation)
- `GET /api/v1/colonies/{colony_id}/artifacts` — list with preview
- `GET /api/v1/colonies/{colony_id}/artifacts/{artifact_id}` — full content
- `GET /api/v1/colonies/{colony_id}/export?items=...` — zip export
- `WorkspaceExecutionResult` tracks `files_created`, `files_modified`,
  `files_deleted`

**Design:**

A. **New `workspace-browser` component**
   (`frontend/src/components/workspace-browser.ts`) — file tree browser:
   - Fetches file list from workspace files endpoint
   - Tree view with folder grouping (parse path separators)
   - Click file → fetch and display content with syntax highlighting
     (`<pre><code>` with language class, same as artifact viewer)
   - File type pills, size display, refresh button

B. **Wire into formicos-app.ts** — add "Workspace" tab in main layout
   (alongside Dashboard, Knowledge, Settings)

C. **Colony file diff view** (REQUIRED) — in colony-detail.ts, show which
   workspace files were created/modified during the colony's execution.
   Without this the workspace browser shows all files but the operator
   can't tell which ones THIS colony produced. Source: round-level
   `tool_calls` data for `write_workspace_file` and `workspace_execute`.
   Render as "Files Changed" section with created/modified/deleted badges.

**Owned files:**
- `frontend/src/components/workspace-browser.ts` (NEW)
- `frontend/src/components/formicos-app.ts` — add Workspace tab
- `frontend/src/components/colony-detail.ts` — file diff section

**Do not touch:** Backend files, other frontend components

**Validation:** Visual review. TypeScript compilation passes.

---

## Track 5 — Budget Control Panel (backend + frontend)

**Problem:** `runtime.budget_summary()` at `runtime.py:1733` returns
comprehensive budget data (workspace totals, per-colony breakdown, model
usage, reasoning/cache tokens, warning/downgrade flags) but has NO REST
endpoint and NO frontend display. The operator can set a budget limit
in settings but can't see spend, utilization, or per-model breakdown.

**Design:**

A. **Wire REST endpoint** — add `GET /api/v1/workspaces/{workspace_id}/budget`
   to `routes/api.py`. Calls `runtime.budget_summary(workspace_id)`.
   Returns the full budget snapshot including Wave 60.5 reasoning/cache
   token fields.

B. **New `budget-panel` component** (`frontend/src/components/budget-panel.ts`)
   or integrate into existing `queen-overview.ts` resource grid:
   - Workspace utilization bar (% of limit, colored by regime:
     green/yellow/red)
   - Total API spend vs local tokens
   - Per-model spend breakdown (table: model, cost, input/output/reasoning
     tokens)
   - Budget state indicators (warning issued, downgrade active)
   - Per-colony cost table (colony name, status, cost, rounds)
   - Reasoning token % and cache hit % (from Wave 60.5 accounting)

C. **Budget limit control** — editable budget limit in settings view.
   Already partially built (settings-view.ts has Default Budget per Colony).
   Add workspace-level budget limit control if missing.

**Owned files:**
- `src/formicos/surface/routes/api.py` — new budget endpoint
- `frontend/src/components/budget-panel.ts` (NEW) OR
  `frontend/src/components/queen-overview.ts` — budget section
- `frontend/src/components/settings-view.ts` — budget limit control

**Do not touch:** `core/events.py`, projections (read-only), runtime.py
(budget_summary already exists)

**Validation:**
```bash
curl localhost:8080/api/v1/workspaces/{id}/budget  # returns full snapshot
pytest tests/unit/surface/ -q
```

---

## Parallel execution plan

```
Track 1 (Queen deliberation)     ────────┐
                                         ├─ Track 2 (Proposal card UI)
Track 3 (Queen power tools)      ────────┤  DEPENDS ON Track 1
                                         │
Track 4 (Workspace browser)      ─────────── independent
Track 5 (Budget control panel)   ─────────── independent
```

Tracks 1, 3, 4, 5 run in parallel. Track 2 waits for Track 1.
Tracks 1 and 3 both touch `queen_tools.py` — coordinate via:
- Track 1 owns: `propose_plan` tool spec + handler, system prompt
- Track 3 owns: `query_outcomes`, `analyze_colony`, `query_briefing`
  tool specs + handlers
- Both add to `_queen_tools()` list — Track 3 appends after Track 1's
  additions (no overlap in tool names)

---

## What this wave does NOT do

- Aider benchmark (separate team)
- New event types (stays at 65)
- Federation testing
- Adaptive retrieval threshold
- Per-caste fine-tuning
- Time-based local budget (cost_tracking spec S4)
- Streaming inference
- CI/CD (already exists: `.github/workflows/ci.yml` + `security.yml`)
- FINDINGS.md / README (already exist and are current)

## Success criteria

1. Operator asks "what would be a good showcase project?" → Queen responds
   with a structured proposal card showing options + runtime-computed costs
2. Operator says "go ahead with Option B" → Queen spawns the selected plan
3. Queen can query "show me all failed colonies this week" via
   `query_outcomes` and get empirical data
4. Queen can deep-analyze why a specific colony failed via `analyze_colony`
5. Queen can drill into specific briefing categories via `query_briefing`
6. Operator can browse workspace files from the Workspace tab
7. Colony detail shows "Files Changed" section with created/modified badges
8. Operator can see budget utilization, per-model spend, and reasoning
   token breakdown
9. 3428+ tests pass, ruff clean, no layer violations
