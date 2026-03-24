# Wave 52: Task Intelligence Inventory

**Date:** 2026-03-20

Inventory of task-entry paths and their defaults. Which intelligence
mechanisms each path uses or bypasses.

---

## Entry Paths

### 1. Queen Chat (Primary)

**File:** `surface/queen_runtime.py`

The only path that uses the full intelligence substrate.

**Flow:** Operator message -> Queen LLM with enriched context -> tool call
(`spawn_colony` / `spawn_parallel`) -> colony starts.

**Intelligence automatically applied:**
- Pre-spawn knowledge retrieval (last operator message as query; workspace-scoped
  today even though the retrieval layer supports thread-aware ranking)
- System Intelligence Briefing (top 3 knowledge insights + top 2
  performance insights from 14 deterministic rules)
- Decay class recommendations (per-domain ephemeral/stable/permanent)
- Configuration recommendations (strategy, castes, rounds, model tiers)
- Thread context (goal, expected outputs, workflow steps, colony history)
- Queen notes (thread-scoped operator preferences, last 10)
- Metacognitive nudges (memory-available hint, prior-failure warning)
- Budget enforcement (BudgetEnforcer.check_spawn_allowed)
- Intent fallback parser (regex + Gemini Flash if LLM produces prose)

**Intelligence available via tools but not auto-injected:**
- `list_templates` (operator + learned templates with success/failure stats)
- `memory_search` (full knowledge retrieval with score breakdowns)
- `inspect_colony` (prior colony outcomes, quality scores)
- `suggest_config_change` (evidence-backed configuration proposals)

**Intelligence NOT used:**
- Task classifier is not auto-invoked; Queen picks castes directly
- Colony outcome history is not injected into briefing (only feeds
  performance rules indirectly)
- Learned template auto-substitution does not exist; Queen must
  explicitly choose templates

### 2. A2A Task Creation

**File:** `surface/routes/a2a.py` (`POST /a2a/tasks`)

Second-most intelligent path. Uses template matching and classification
but no knowledge retrieval or briefing.

**Flow:** External caller sends `{description}` -> template tag match ->
classifier fallback -> colony spawned with defaults.

**Intelligence applied:**
- Template tag matching (keyword overlap with loaded templates)
- Task classification (deterministic, 5 categories + generic fallback)

**Intelligence NOT applied:**
- Knowledge retrieval
- Proactive intelligence briefing
- Colony outcome routing
- Learned template matching (only checked in preview, not in A2A submit)
- Queen context (thread history, workflow steps, nudges)

**Defaults when no template matches (generic classification):**
- Castes: coder + reviewer
- Strategy: stigmergic
- Max rounds: 10
- Budget: $2.00

### 3. AG-UI Run Creation

**File:** `surface/agui_endpoint.py` (`POST /ag-ui/runs`)

Minimal intelligence. Caller controls everything.

**Flow:** External caller sends `{task, castes?, workspace_id?, thread_id?}`
-> colony spawned with explicit or hardcoded defaults -> SSE stream of events.

**Intelligence applied:**
- None

**Defaults if omitted:**
- Castes: coder + reviewer (standard tier)
- Strategy: stigmergic
- Workspace: "default"
- Thread: "main"
- Budget: runtime default 5.0 (because no explicit budget is passed)

**Intelligence NOT applied:**
- Classification, templates, knowledge, briefing, outcomes, budget check

### 4. Direct Colony Spawn (Internal API)

**File:** `surface/runtime.py::spawn_colony()`

Raw spawn function. No intelligence. All parameters explicit. Used
internally by Queen tools, A2A, AG-UI, and workflow step continuation.

### 5. REST API Preview

**File:** `surface/routes/api.py` (`POST .../preview-colony`)

Does not spawn. Returns structured preview metadata including:
- Matched template (including learned templates with success/failure counts)
- Task classification
- Recommended team composition

Learned template matching is only wired here and in Queen `list_templates`.

### 6. Workflow Step Continuation

**File:** `surface/colony_manager.py`

When a step colony completes, Queen receives a follow-up summary with
`step_continuation` marker. Thread context includes pending steps.
Queen decides whether to spawn the next colony.

No additional intelligence beyond what the Queen path already provides.

---

## Intelligence Mechanism Matrix

| Mechanism               | Queen | A2A | AG-UI | Direct | Preview |
|-------------------------|:-----:|:---:|:-----:|:------:|:-------:|
| Knowledge retrieval     |  YES  | NO  |  NO   |   NO   |   NO    |
| Proactive briefing      |  YES  | NO  |  NO   |   NO   |   NO    |
| Config recommendations  |  YES  | NO  |  NO   |   NO   |   NO    |
| Decay recommendations   |  YES  | NO  |  NO   |   NO   |   NO    |
| Thread context          |  YES  | NO  |  NO   |   NO   |   NO    |
| Queen notes             |  YES  | NO  |  NO   |   NO   |   NO    |
| Metacognitive nudges    |  YES  | NO  |  NO   |   NO   |   NO    |
| Template tag matching   | tool  | YES |  NO   |   NO   |  YES    |
| Task classification     | tool  | YES |  NO   |   NO   |  YES    |
| Learned template match  | tool  | NO  |  NO   |   NO   |  YES    |
| Budget enforcement      |  YES  | NO  |  NO   |   NO   |   NO    |
| Intent fallback parser  |  YES  | NO  |  NO   |   NO   |   NO    |

---

## Default Parameters by Path

| Parameter    | Queen         | A2A           | AG-UI          | Generic Class |
|--------------|---------------|---------------|----------------|---------------|
| Castes       | LLM decides   | template/class| caller/fallback| coder+reviewer|
| Strategy     | LLM decides   | template/class| stigmergic     | stigmergic    |
| Max rounds   | LLM decides   | template/class| 25 (ceiling)   | 10            |
| Budget       | LLM decides   | template/class, no spawn gate | runtime default 5.0, no spawn gate | $2.00 |
| Model        | tier cascade  | tier cascade  | tier cascade   | system default|

---

## Classification Categories

Deterministic keyword matching in `task_classifier.py`. No LLM.

| Category            | Keywords (sample)       | Castes          | Strategy   | Rounds | Budget |
|---------------------|-------------------------|-----------------|------------|--------|--------|
| code_implementation | implement, build, write | coder+reviewer  | stigmergic | 10     | $2.00  |
| code_review         | review, audit, check    | reviewer        | sequential | 5      | $1.00  |
| research            | research, investigate   | researcher      | sequential | 8      | $1.00  |
| design              | design, architect       | coder+reviewer  | stigmergic | 10     | $2.00  |
| creative            | creative, brainstorm    | researcher      | sequential | 3      | $0.50  |
| generic (fallback)  | (no match)              | coder+reviewer  | stigmergic | 10     | $2.00  |

---

## Static vs Adaptive Defaults

### Static (hardcoded, same every time)
- AG-UI fallback castes (coder+reviewer)
- Generic classification defaults
- Caste recipes (tool lists, iteration limits, output caps)
- System model routing cascade
- Knowledge prior Beta(5,5)
- Composite retrieval weights (unless workspace-overridden)

### Adaptive (change based on workspace state)
- Queen briefing content (14 rules respond to workspace health)
- Knowledge retrieval ranking (Thompson Sampling, co-occurrence, freshness)
- Learned template matching (accumulates from successful colonies)
- Config recommendations (evidence from colony outcomes)
- Decay recommendations (based on prediction error rates)
- Reactive foraging trigger (based on retrieval confidence)
- Evaporation rate (branching factor + stall count)

---

## Key Finding

Intelligence is heavily concentrated in the Queen Chat path. Every other
entry path uses at most classification + template matching. No entry path
uses colony outcome history for routing decisions.

The gap is not "missing substrate" -- the substrate exists. The gap is
that non-Queen paths do not consult it.
