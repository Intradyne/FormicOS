# Wave 9 Dispatch — "Smart Routing + Living Skills"

**Date:** 2026-03-13
**Status:** Final coder-dispatch document
**Depends on:** Wave 8 complete and validated
**Exit gate:** `docker compose build && docker compose up`, spawn a colony with mixed
castes, verify: routing decisions in structlog (reviewer→local, coder→cloud), skill
ingestion quality gate rejects a duplicate, confidence-weighted retrieval prefers
higher-confidence skills, frontend shows per-agent model in colony detail.
Full `ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest` green.
`cd frontend && npm run build` clean.

---

## Read Order (mandatory before writing any code)

1. `CLAUDE.md` — project rules (esp. Rule 3: no new deps, Rule 7: every state change is an event)
2. `AGENTS.md` — ownership and coordination for THIS wave (below)
3. `docs/decisions/001-event-sourcing.md` — single mutation path
4. `docs/decisions/005-mcp-sole-api.md` — MCP vs WS boundary
5. `docs/decisions/007-agent-tool-system.md` — tool loop design
6. `docs/decisions/009-cost-tracking.md` — cost model and `cost_fn`
7. `docs/decisions/010-skill-crystallization.md` — learning loop, confidence evolution plan
8. `docs/decisions/011-quality-scoring.md` — fitness signal, `compute_quality_score()`
9. `docs/decisions/012-compute-router.md` — **NEW — write before coding starts**
10. `docs/contracts/events.py` — 22-event union (**DO NOT MODIFY**)
11. `docs/contracts/ports.py` — 5 port interfaces (**DO NOT MODIFY**)
12. Current implementations you will modify (see your terminal's file list below)

---

## Scope Locks — 3 Terminals

| Terminal | Owns (may modify) | Does NOT touch |
|----------|-------------------|----------------|
| **T1 — Compute Router** | `engine/runner.py`, `surface/runtime.py`, `core/settings.py`, `config/formicos.yaml`, tests for these | `core/events.py`, `core/ports.py`, `frontend/*`, `docs/contracts/*`, `surface/colony_manager.py`, `engine/context.py` |
| **T2 — Skill Lifecycle** | `engine/context.py`, new `surface/skill_lifecycle.py`, `surface/colony_manager.py`, tests for these | `core/events.py`, `core/ports.py`, `frontend/*`, `docs/contracts/*`, `engine/runner.py`, `surface/runtime.py` |
| **T3 — Snapshot + Frontend** | `surface/view_state.py`, `frontend/src/types.ts`, `frontend/src/components/queen-overview.ts`, `frontend/src/components/colony-detail.ts`, tests for these | `core/*`, `docs/contracts/*`, `engine/*`, `surface/colony_manager.py`, `surface/runtime.py` |

**Merge order: T1 first, T2 second, T3 last.**

T2 depends on T1 because confidence scoring must know which model produced each
result (routing-aware confidence is meaningful; routing-unaware confidence is noise).
T3 depends on T1+T2 because it surfaces data they produce.

### Critical reminders (all terminals)

- **No contract changes.** The 22-event union is frozen. No new event types.
- **No new dependencies.** No LiteLLM, no vLLM, no new packages in `pyproject.toml`.
- **No hidden mutable state.** Every new datum must have documented provenance (see below).
- **Pydantic v2 only.** structlog only. Layer boundaries enforced.

---

## Data Provenance Table

Every new field introduced in Wave 9, with exact source. Coders: if you need data
not listed here, STOP and flag it. Do not invent shadow state.

| Datum | Source | Persisted? | Survives restart? |
|-------|--------|-----------|-------------------|
| Routed model per agent | `AgentTurnStarted.model` field (already exists in event + projection) — T1 populates it with the routed model instead of static default | Event store → projection | Yes (replayed) |
| Per-colony models used | Derived from `AgentProjection.model` values already in `ColonyProjection.agents` | Projection-derived | Yes (derived from events) |
| Routing decision log | structlog entry in `LLMRouter.route()` | Runtime log only | No (log rotation) |
| Colony observation log | structlog entry at colony completion | Runtime log only | No (log rotation) |
| Skill confidence score | LanceDB document metadata field `confidence`, updated via `vector_port.upsert()` | Vector store (mutable) | Yes (LanceDB on disk) |
| Skill algorithm version | LanceDB document metadata field `algorithm_version` | Vector store (mutable) | Yes |
| Retrieved skill IDs per colony | `set[str]` accumulated in colony_manager round loop | Runtime ephemeral | No (lost on restart — acceptable, confidence is best-effort) |
| Skill bank stats (total, avg confidence) | Pre-fetched via `vector_port.search()` at snapshot build time, passed as param to `build_snapshot()` | Not persisted (recomputed per snapshot) | N/A (recomputed) |

---

## T1 — Compute Router

### Goal

Extend the existing `LLMRouter` with a (caste, phase) → model routing table.
Worker agents doing structured extraction route to local. Coders and Queen route
to cloud for critical phases. Budget-aware fallback prevents overspend.

### What changes

**1. `core/settings.py`** — Add routing table config model.

Add to `RoutingConfig`:

```python
class ModelRoutingEntry(BaseModel):
    """Per-caste model override for a specific phase."""
    queen: str | None = None
    coder: str | None = None
    reviewer: str | None = None
    researcher: str | None = None
    archivist: str | None = None

class RoutingConfig(BaseModel):
    # ... existing fields unchanged ...
    model_routing: dict[str, ModelRoutingEntry] = {}
```

The `model_routing` dict is keyed by phase name ("execute", "goal", etc.).
Missing phases or castes inherit the cascade default. Empty dict = no routing
(existing behavior preserved).

Verify: `load_config()` parses the new section without error. Test with and
without the `model_routing` key present.

**2. `surface/runtime.py`** — Extend `LLMRouter` with `route()` method.

```python
def route(
    self,
    caste: str,
    phase: str,
    round_num: int,
    budget_remaining: float,
    default_model: str,
) -> str:
    """Select cheapest adequate model. Falls back to default_model.

    Decision order:
    1. Budget gate: if budget_remaining < 0.10 → cheapest registered model
    2. Routing table: lookup (phase, caste) in model_routing config
    3. Adapter check: if selected model has no adapter → fall back to default
    4. Fallback: return default_model
    """
```

Constructor receives the parsed `RoutingConfig` (or just the `model_routing` dict
and registry list). The `route()` method is pure lookup + validation — no async,
no LLM calls.

Also add a `cheapest_model` property or method that scans the registry for the
model with `cost_per_input_token == 0.0` (local models). If none found, return
the first registry entry.

Log every decision via structlog:

```python
log.info("compute_router.route",
    caste=caste, phase=phase, round_num=round_num,
    selected=selected_model, reason=reason,
    budget_remaining=budget_remaining,
)
```

Where `reason` is one of: `"budget_gate"`, `"routing_table"`, `"adapter_fallback"`,
`"cascade_default"`.

**3. `engine/runner.py`** — Add `route_fn` to `RoundRunner`.

Add parameter to `__init__`:

```python
def __init__(
    self,
    emit: Callable[[FormicOSEvent], Any],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    cost_fn: Callable[[str, int, int], float] | None = None,
    tier_budgets: TierBudgets | None = None,
    route_fn: Callable[[str, str, int, float], str] | None = None,
) -> None:
    # ...
    self._route_fn = route_fn
```

In `_run_agent()`, determine the model to use:

```python
# Before the LLM call, resolve model
if self._route_fn is not None:
    effective_model = self._route_fn(
        agent.caste,
        current_phase,  # thread this through from run_round
        colony_context.round_number,
        budget_remaining,  # tracked in run_round
    )
else:
    effective_model = agent.model
```

Use `effective_model` in:
- `llm_port.complete(model=effective_model, ...)`
- `AgentTurnStarted(model=effective_model, ...)`
- `self._cost_fn(effective_model, ...)`

The `current_phase` needs threading: `run_round` already knows the phase name
when it calls `_emit_phase`. Add a `_current_phase` instance variable or pass
it as an argument to `_run_agent`. Simplest: add `phase: str = "execute"` param
to `_run_agent` and pass it from `run_round` (agents execute in Phase 4 = "execute").

For `budget_remaining`: track cumulative cost in `run_round` and pass
`colony_budget - cumulative_cost` to `_run_agent`. The colony budget comes from
`colony_context` — but `ColonyContext` doesn't have `budget_limit`. Pass it via
a new optional field, or pass as a separate param to `run_round`. Simplest:
add `budget_limit: float = 5.0` param to `run_round`.

**4. `config/formicos.yaml`** — Add routing table.

```yaml
routing:
  # ... existing fields unchanged ...
  model_routing:
    execute:
      queen: "anthropic/claude-sonnet-4.6"
      coder: "anthropic/claude-sonnet-4.6"
      reviewer: "llama-cpp/gpt-4"
      researcher: "llama-cpp/gpt-4"
      archivist: "llama-cpp/gpt-4"
    goal:
      queen: "anthropic/claude-sonnet-4.6"
    # All other (phase, caste) combos inherit the cascade default.
    # Gemini entries for Wave 10 (commented):
    # execute:
    #   researcher: "gemini/gemini-2.5-flash"
```

### Acceptance criteria

- [ ] `RoutingConfig` parses `model_routing` from YAML (test with and without section)
- [ ] `LLMRouter.route()` returns correct model per (phase, caste) lookup
- [ ] Missing (phase, caste) entries → cascade default (no crash)
- [ ] Budget < $0.10 → cheapest registered model regardless of table
- [ ] Routed model with no adapter → silent fallback to cascade default
- [ ] `AgentTurnStarted.model` reflects the routed model (not static default)
- [ ] structlog entry for every routing decision with reason
- [ ] All 391+ existing tests pass
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/core/test_routing_config.py` — YAML parsing, defaults, missing section
- `tests/unit/surface/test_compute_router.py` — route() table lookup, budget gate, adapter fallback, cheapest model selection
- `tests/unit/engine/test_runner_route_fn.py` — route_fn injection, phase arg threading, route_fn=None → static model, budget_remaining threading

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## T2 — Skill Lifecycle

### Goal

Transform the skill bank from a flat pile at confidence 0.5 into a curated library
with quality gates, confidence-weighted retrieval, usage tracking, and time decay.
Add colony observation hooks for future template extraction.

### Depends on: T1 merged (routing-aware model data in projections)

### What changes

**1. `engine/context.py`** — Confidence-weighted retrieval.

Replace the current skill retrieval block in `assemble_context()`:

```python
# CURRENT (plain semantic search):
skills = await vector_port.search(collection="skill_bank", query=round_goal, top_k=3)

# NEW (composite scoring):
raw_skills = await vector_port.search(collection="skill_bank", query=round_goal, top_k=8)
if raw_skills:
    import time as _time
    _now_ts = _time.time()
    scored = []
    for hit in raw_skills:
        confidence = float(hit.metadata.get("confidence", 0.5))
        extracted_at = hit.metadata.get("extracted_at", "")
        # Freshness: 90-day half-life exponential decay
        age_days = 0.0
        if extracted_at:
            try:
                from datetime import datetime, UTC
                ext_dt = datetime.fromisoformat(extracted_at)
                age_days = (_now_ts - ext_dt.timestamp()) / 86400.0
            except (ValueError, TypeError):
                age_days = 0.0
        freshness = 2.0 ** (-age_days / 90.0)
        composite = (hit.score * 0.50) + (confidence * 0.25) + (freshness * 0.25)
        scored.append((composite, hit, confidence))
    scored.sort(key=lambda x: -x[0])
    top_skills = scored[:3]
    skill_parts = []
    for _score, hit, conf in top_skills:
        skill_parts.append(f"[conf:{conf:.1f}] {hit.content[:300]}")
    skill_text = _truncate(
        f"Relevant skills:\n" + "\n".join(skill_parts),
        budgets.skill_bank,
    )
    messages.append({"role": "user", "content": skill_text})
```

**Return retrieved skill IDs to caller.** Change `assemble_context()` return type
from `list[LLMMessage]` to a dataclass or tuple that includes both messages and
retrieved skill IDs:

```python
class ContextResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    messages: list[LLMMessage]
    retrieved_skill_ids: list[str]
```

Update `runner.py`'s call site (in T1's merged code) to unpack both fields.
The runner passes `retrieved_skill_ids` back to the caller (colony_manager)
via the `RoundResult`. Add `retrieved_skill_ids: list[str] = []` field to
`RoundResult`.

**2. New file: `surface/skill_lifecycle.py`** (~100 LOC)

```python
"""Skill bank lifecycle management — confidence, quality gates, observation.

Lives in surface/ because it calls vector_port (an adapter).
"""

CONFIDENCE_DELTA = 0.1
CONFIDENCE_MIN = 0.1
CONFIDENCE_MAX = 1.0
ALGORITHM_VERSION = "v1"
DEDUP_COSINE_THRESHOLD = 0.92
MIN_SOURCE_QUALITY = 0.3
MIN_CONTENT_LENGTH = 20


async def update_skill_confidence(
    vector_port: VectorPort,
    retrieved_skill_ids: list[str],
    colony_succeeded: bool,
) -> int:
    """Adjust confidence on skills retrieved during this colony run.

    +0.1 on success, -0.1 on failure. Clamped to [0.1, 1.0].
    Stores algorithm_version alongside score.
    Returns count of skills updated.
    """
    # For each skill_id:
    #   1. Search skill_bank for that ID
    #   2. Read current confidence from metadata
    #   3. Adjust by delta, clamp
    #   4. Upsert back with new confidence + algorithm_version
    # Fire-and-forget — errors logged, never raised


async def validate_skill_for_ingestion(
    vector_port: VectorPort,
    skill_content: str,
    source_quality_score: float,
) -> bool:
    """Quality gate for skill ingestion.

    Rejects if:
    - source colony quality_score < MIN_SOURCE_QUALITY (0.3)
    - content length < MIN_CONTENT_LENGTH (20 chars)
    - semantic duplicate exists (cosine > DEDUP_COSINE_THRESHOLD with existing skill)
    Returns True if skill should be ingested.
    """


async def get_skill_bank_summary(
    vector_port: VectorPort,
) -> dict:
    """Skill bank stats for the state snapshot.

    Returns: {"total": int, "avgConfidence": float}
    Queries skill_bank collection. Returns zeros if collection doesn't exist.
    """
```

**3. `surface/colony_manager.py`** — Three additions:

**a. Ingestion quality gate.** In `_crystallize_skills()`, before upserting each
skill doc, call `validate_skill_for_ingestion()`. Skip duplicates and low-quality
extractions. Pass `colony.quality_score` as the source quality check.

```python
# Inside _crystallize_skills, before the upsert loop:
from formicos.surface.skill_lifecycle import validate_skill_for_ingestion

valid_docs = []
for doc in docs:
    is_valid = await validate_skill_for_ingestion(
        self._runtime.vector_store,
        doc.content,
        source_quality_score=colony.quality_score,
    )
    if is_valid:
        valid_docs.append(doc)
# Upsert only valid_docs
```

**b. Track retrieved skill IDs across rounds.** Add a `retrieved_skill_ids: set[str]`
accumulator in `_run_colony_inner()`. After each round, extend it from
`result.retrieved_skill_ids`. After colony completion (success or failure),
call `update_skill_confidence()`:

```python
from formicos.surface.skill_lifecycle import update_skill_confidence

# After the round loop ends (both completion paths):
if retrieved_skill_ids:
    await update_skill_confidence(
        self._runtime.vector_store,
        list(retrieved_skill_ids),
        colony_succeeded=(quality > 0),  # True for completed, False for failed
    )
```

This is fire-and-forget — errors logged, never propagated. Acceptable to lose
on crash (confidence is derived, not source-of-truth).

**c. Colony observation hook.** At colony completion (both success and failure paths),
emit a structured structlog entry:

```python
log.info("colony_observation",
    colony_id=colony_id,
    task=colony.task[:200],
    caste_names=colony.caste_names,
    strategy=colony.strategy,
    rounds_completed=round_num,
    quality_score=quality,
    total_cost=total_cost,
    skills_retrieved=list(retrieved_skill_ids),
    skills_extracted=skills_count,
    governance_warnings=governance_warnings,
    stall_rounds=stall_count,
)
```

This is NOT an event — it's observability data for future template extraction
(Wave 10). It goes to structlog only.

### Acceptance criteria

- [ ] Skill retrieval uses composite scoring (semantic 0.50, confidence 0.25, freshness 0.25)
- [ ] Retrieval returns top 3 from initial top 8, sorted by composite score
- [ ] Injected skill text includes `[conf:X.X]` annotation
- [ ] `assemble_context()` returns both messages and retrieved skill IDs
- [ ] `RoundResult` includes `retrieved_skill_ids` field
- [ ] Ingestion gate rejects skills from colonies with quality_score < 0.3
- [ ] Ingestion gate rejects duplicates (cosine > 0.92 with existing skill)
- [ ] Ingestion gate rejects content shorter than 20 chars
- [ ] Confidence adjusts +0.1 on colony success, -0.1 on failure
- [ ] Confidence clamped to [0.1, 1.0]
- [ ] Algorithm version "v1" stored with every confidence update
- [ ] Colony observation hook fires on every colony completion (structlog)
- [ ] All existing tests pass (update existing context assembly tests for new return type)
- [ ] `ruff check src/ && pyright src/ && python scripts/lint_imports.py` clean

### New tests

- `tests/unit/engine/test_skill_weighting.py` — composite score calculation, freshness decay, re-ranking from 8→3, confidence annotation in text
- `tests/unit/surface/test_skill_lifecycle.py` — confidence update (+0.1/-0.1), clamping, algorithm version storage
- `tests/unit/surface/test_skill_ingestion_gate.py` — dedup detection, quality threshold, content length check
- `tests/unit/surface/test_colony_observation.py` — observation hook fires with expected fields (mock structlog)

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

---

## T3 — Snapshot Wiring + Frontend

### Goal

Surface routing decisions and skill bank health in the existing UI. No new
components. Minimal additions to existing views.

### Depends on: T1 + T2 merged

### What changes — Backend

**1. `surface/view_state.py`** — Two additions.

**a. Skill bank stats in snapshot.** Add optional `skill_bank_stats` parameter
to `build_snapshot()`:

```python
def build_snapshot(
    store: ProjectionStore,
    settings: SystemSettings,
    castes: CasteRecipeSet | None = None,
    skill_bank_stats: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        # ... all existing fields unchanged ...
        "skillBankStats": skill_bank_stats or {"total": 0, "avgConfidence": 0.0},
    }
```

The caller (app.py / ws_handler — wherever snapshots are built) pre-fetches
stats from `skill_lifecycle.get_skill_bank_summary(vector_port)` and passes
them in. This keeps `build_snapshot` synchronous and testable.

**Where is build_snapshot called?** Grep for `build_snapshot` in the codebase.
It is called in `ws_handler.py` (for state pushes) and potentially in
`colony_manager.py` (via `ws_manager.send_state_to_workspace`). The async
pre-fetch should happen at each call site. If `send_state_to_workspace`
builds the snapshot internally, that method needs to accept or fetch stats.

**b. Per-colony modelsUsed.** In `_build_tree()`, the colony node already
includes an `agents` array with `model` per agent. Add a derived field:

```python
colony_node["modelsUsed"] = list({a.model for a in colony.agents.values()})
```

This is pure projection derivation — no new data source.

### What changes — Frontend

**2. `frontend/src/types.ts`** — Add to snapshot and colony types:

```typescript
// In OperatorStateSnapshot:
skillBankStats: { total: number; avgConfidence: number };

// In Colony (already has agents with model — add convenience field):
modelsUsed?: string[];
```

**3. `frontend/src/components/queen-overview.ts`** — Two additions:

**a. Skill bank stats line.** Below the workspace header (or in the stats bar area),
render:

```
Skills: {total} | Avg confidence: {avgConfidence.toFixed(2)}
```

Use the `skillBankStats` from the snapshot. Gray text, Void Protocol typography.
Only show if `total > 0`.

**b. Routing badge on colony cards.** Each colony card already shows agent info.
Add a small badge indicating the routing mix:

```
if modelsUsed.length > 1 → badge "mixed" (blue/teal)
if modelsUsed.length === 1 && isLocal → badge "local" (green)
if modelsUsed.length === 1 && isCloud → badge "cloud" (amber)
```

`isLocal` = model address starts with "llama-cpp/" or "ollama/".
Place next to the existing cost display.

**4. `frontend/src/components/colony-detail.ts`** — Two additions:

**a. Model per agent turn.** The agent table already shows id, caste, tokens.
Add a "Model" column showing `agent.model`. Truncate to last segment after "/" for
display (e.g., "claude-sonnet-4.6" not "anthropic/claude-sonnet-4.6").

**b. Skills retrieved count.** If `colony.skillsExtracted > 0`, show a line:
"Skills extracted: {n}". This field already exists in the snapshot from Wave 8.

**5. `frontend/src/state/store.ts`** — The store already replaces itself from
backend snapshots. The new `skillBankStats` and `modelsUsed` fields will flow
through automatically if the types are correct. No structural store changes
needed — just verify the snapshot application handles the new fields.

### Acceptance criteria

- [ ] `build_snapshot()` accepts and includes `skillBankStats`
- [ ] Colony nodes include `modelsUsed` derived from agents
- [ ] Snapshot caller pre-fetches skill bank stats (async) and passes to build_snapshot
- [ ] `frontend/src/types.ts` includes `skillBankStats` and `modelsUsed`
- [ ] Queen overview shows skill bank stats when total > 0
- [ ] Colony cards show routing badge (mixed/local/cloud)
- [ ] Colony detail shows model per agent
- [ ] Colony detail shows skills extracted count
- [ ] TypeScript compiles clean (`npm run build`)
- [ ] No console errors in browser
- [ ] All existing tests pass

### New tests

- `tests/unit/surface/test_snapshot_routing.py` — modelsUsed derivation, skillBankStats passthrough, empty stats default
- Frontend: manual verification (no Lit unit test framework in repo — verify via `npm run build` + browser)

### Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
cd frontend && npm run build
```

---

## Pre-Coding: ADR-012

Write `docs/decisions/012-compute-router.md` BEFORE any terminal starts coding.

Contents:
- **Decision:** Model selection uses a (phase, caste) → model routing table in YAML.
  Engine receives `route_fn: Callable[[str, str, int, float], str]`. Surface constructs
  it from settings. Engine never imports settings.
- **Routing table:** `routing.model_routing` in formicos.yaml. Dict keyed by phase name,
  values are per-caste model addresses. Missing entries inherit cascade default.
- **Budget gate:** budget_remaining < $0.10 → cheapest registered model.
- **Adapter fallback:** routed model with no adapter → cascade default.
- **Observability:** Every routing decision logged via structlog. Colony observation
  hooks log full execution signature at completion. Neither is event-sourced.
- **No new events.** No contract changes.
- **Layer boundary:** engine/runner.py receives route_fn callable. surface/runtime.py
  constructs it. Engine never imports settings or routing config.

---

## Integration Gate

After all three terminals merge (T1 → T2 → T3):

```bash
# Build and start
docker compose build formicos && docker compose up -d
sleep 10 && curl http://localhost:8080/health

# Test 1: Compute routing
# Spawn a colony with reviewer + coder castes.
# Check structlog for routing decisions:
#   compute_router.route caste=reviewer phase=execute selected=llama-cpp/gpt-4 reason=routing_table
#   compute_router.route caste=coder phase=execute selected=anthropic/claude-sonnet-4.6 reason=routing_table
# Verify AgentTurnStarted events show the ROUTED model, not the static default.
# Verify RoundCompleted.cost reflects mixed routing.

# Test 2: Skill lifecycle
# Colony A completes → skills_extracted > 0
# Check structlog for ingestion gate: skill_lifecycle.ingestion_check
# Colony B (similar task) → check skill retrieval log:
#   context.skill_retrieval skills=N top_composite=X
# Colony B completes → confidence updated:
#   skill_lifecycle.confidence_updated skill_id=... delta=+0.1 algorithm=v1

# Test 3: Colony observation
# Check structlog after completion:
#   colony_observation colony_id=... quality_score=... skills_retrieved=[...]

# Test 4: Frontend
# Colony detail → model column shows per-agent model
# Colony cards → routing badge (mixed/local/cloud)
# Queen overview → skill bank stats line (if skills exist)

# Test 5: Budget gate
# Set budget_limit=$0.01 on a colony → verify router forces cheapest model

# Full CI
docker compose exec formicos bash -c \
  "ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest"
cd frontend && npm run build
```

---

## Known Limitations

**Queen tool-calling is model-dependent.** The Queen agent's ability to
invoke `spawn_colony` and other tools depends on the local LLM's tool-call
support. Models with weak or inconsistent function-calling (e.g., some GGUF
quantizations) may respond conversationally instead of emitting tool calls.
This affects the smoke test's Queen-driven spawn path and any operator
workflow that relies on the Queen choosing to use a tool unprompted.

The Docker smoke test (`tests/smoke_test.py`) separates checks into two
tiers:
- **GATE** tests use the direct `spawn_colony` WS command, bypassing the
  Queen entirely. These are the hard acceptance criteria.
- **ADVISORY** tests exercise Queen tool-calling. Failures here indicate
  model-level tool-call limitations, not code defects.

Mitigation options: use a model with strong tool-call support (Qwen3 ≥14B,
Llama 3.3 70B), or route the Queen caste to a cloud endpoint in
`config/formicos.yaml`.

---

## Explicit Deferrals (NOT in Wave 9)

| Deferred | Why | Earliest |
|----------|-----|----------|
| Colony templates | Premature abstraction. Need 3+ colony patterns. Requires first-class events (contract change). | Wave 10 |
| Template events | Bundle with template work. One contract opening, done right. | Wave 10 |
| `SkillConfidenceTierChanged` event | Requires contract change. Bundle with templates. | Wave 10 |
| Skill browser UI component | Backend must stabilize. Build UI when data is real. | Wave 10 |
| Experimentation Engine | Needs router + production data + statistical power. | Wave 10 |
| Gemini adapter | New provider. Best tested via experimentation. | Wave 10 |
| Skill dedup batch job | Need 50+ skills first. Quality gates reduce but don't eliminate dupes. | Wave 10+ |
| Confidence snapshots | Not justified at alpha scale. Add when bank > 100 entries. | Wave 10+ |
| TKG / knowledge graph | No consumer. Flat skill bank covers alpha. | Wave 11+ |
| Sandbox (gVisor) | Multi-week infra, orthogonal. | Wave 11+ |
| ML-based routing | Needs training data from production routing decisions. | Wave 11+ |
| Dashboard composition | Needs A2UI, component registry, more frontend maturity. | Wave 12+ |

---

## Constraints Reminder

1. **No contract changes.** 22-event union stays frozen.
2. **No new dependencies.** Routing uses existing httpx adapters.
3. **Pydantic v2 only.** structlog only. No print().
4. **Layer boundaries.** `engine/` imports only `core/`. `route_fn` is a callable. Engine never imports settings.
5. **No hidden state.** Every datum has documented provenance (see table above).
6. **Tests required.** Every behavioral change needs a test.
7. **Merge order: T1 → T2 → T3.**
8. **ADR-012 before coding.**
