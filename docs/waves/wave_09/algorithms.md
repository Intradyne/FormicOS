# Wave 9 Algorithm Reference

## Purpose

This document provides the implementation algorithms for Wave 9 ("Smart Routing +
Living Skills"). Coders implement these procedures. If an algorithm here contradicts
an ADR, the ADR wins. If an algorithm here contradicts `docs/contracts/`, the contract
wins.

Reference ADRs: 009 (cost tracking), 010 (skill crystallization), 011 (quality
scoring), 012 (compute router).

---

## 1. Compute Router Selection (ADR-012, T1)

### 1.1 Routing Table Config Model

Add to `core/settings.py` inside the existing routing section:

```python
class ModelRoutingEntry(BaseModel):
    """Per-caste model override for a specific phase. Null = inherit cascade."""
    queen: str | None = None
    coder: str | None = None
    reviewer: str | None = None
    researcher: str | None = None
    archivist: str | None = None

class RoutingConfig(BaseModel):
    """Pheromone routing + compute routing parameters."""
    default_strategy: CoordinationStrategyName
    tau_threshold: float
    k_in_cap: int
    pheromone_decay_rate: float
    pheromone_reinforce_rate: float
    model_routing: dict[str, ModelRoutingEntry] = {}  # keyed by PhaseName
```

An empty `model_routing` dict is valid — existing behavior is preserved. Missing
phases or castes inherit the cascade default.

### 1.2 Route Selection Algorithm

In `surface/runtime.py`, add to `LLMRouter`:

```python
def route(
    self,
    caste: str,
    phase: str,
    round_num: int,
    budget_remaining: float,
    default_model: str,
) -> str:
    """Select cheapest adequate model. Pure lookup, no async, no LLM calls.

    Decision order (first match wins):
    1. Budget gate:     budget_remaining < 0.10 → cheapest registered model
    2. Routing table:   model_routing[phase][caste] → selected model (if entry exists)
    3. Adapter check:   selected model provider has no adapter → fall back
    4. Cascade default: return default_model
    """
    reason = "cascade_default"
    selected = default_model

    # Step 1: Budget gate
    if budget_remaining < 0.10:
        selected = self._cheapest_model or default_model
        reason = "budget_gate"
    else:
        # Step 2: Routing table lookup
        phase_entry = self._routing_table.get(phase)
        if phase_entry is not None:
            caste_model = getattr(phase_entry, caste, None)
            if caste_model is not None:
                selected = caste_model
                reason = "routing_table"

    # Step 3: Adapter check (only if we changed from default)
    if selected != default_model:
        prefix = selected.split("/", 1)[0]
        if prefix not in self._adapters:
            log.warning("compute_router.no_adapter",
                selected=selected, prefix=prefix, fallback=default_model)
            selected = default_model
            reason = "adapter_fallback"

    log.info("compute_router.route",
        caste=caste, phase=phase, round_num=round_num,
        selected=selected, reason=reason,
        budget_remaining=round(budget_remaining, 4))
    return selected
```

### 1.3 Cheapest Model Resolution

Scan the model registry at `LLMRouter.__init__` for the model with the lowest
non-null `cost_per_input_token`. Local models (0.0) are always cheapest.

```python
@property
def _cheapest_model(self) -> str | None:
    """Return the model address with the lowest input token cost, or None."""
    # Precomputed at __init__ from the registry list.
    # If no models in registry, return None.
    # Prefer models whose provider prefix has a registered adapter.
```

### 1.4 Engine Integration: route_fn Injection

In `engine/runner.py`, the `RoundRunner` accepts an optional `route_fn`:

```python
def __init__(
    self,
    emit: Callable[[FormicOSEvent], Any],
    embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
    cost_fn: Callable[[str, int, int], float] | None = None,
    tier_budgets: TierBudgets | None = None,
    route_fn: Callable[[str, str, int, float], str] | None = None,  # NEW
) -> None:
    self._route_fn = route_fn
```

In `_run_agent`, resolve the effective model:

```python
if self._route_fn is not None:
    effective_model = self._route_fn(
        agent.caste,        # "reviewer", "coder", etc.
        phase,              # "execute" — passed as param from run_round
        round_num,          # colony_context.round_number
        budget_remaining,   # budget_limit - cumulative_cost (tracked in run_round)
    )
else:
    effective_model = agent.model
```

Use `effective_model` everywhere `agent.model` was previously used in the LLM
call, AgentTurnStarted emission, and cost_fn call.

### 1.5 Phase Threading

`run_round` knows the current phase when it calls `_emit_phase`. Agents execute
during Phase 4 ("execute"). Add `phase: str = "execute"` parameter to `_run_agent`.
For alpha, all agent LLM calls happen in the execute phase — the other phases
(goal, intent, route, compress) don't make per-agent LLM calls.

### 1.6 Budget Remaining

Track cumulative cost across agent turns within `run_round`:

```python
# In run_round, before Phase 4:
cumulative_cost = 0.0  # running total for THIS round

# After each agent turn completes:
cumulative_cost += agent_cost

# Pass to _run_agent:
budget_remaining = budget_limit - total_colony_cost - cumulative_cost
```

`budget_limit` is not on `ColonyContext`. Add `budget_limit: float = 5.0` as a
parameter to `run_round()`. The colony_manager passes `colony.budget_limit` when
calling `runner.run_round()`.

### 1.7 Colony Manager Wiring

In `colony_manager.py`, when constructing `RoundRunner`, build the `route_fn`:

```python
# Build route_fn closure
def _make_route_fn(runtime: Runtime) -> Callable[[str, str, int, float], str]:
    def route_fn(caste: str, phase: str, round_num: int, budget_remaining: float) -> str:
        default = runtime.resolve_model(caste, colony.workspace_id)
        return runtime.llm_router.route(
            caste=caste, phase=phase, round_num=round_num,
            budget_remaining=budget_remaining, default_model=default,
        )
    return route_fn

runner = RoundRunner(
    emit=self._runtime.emit_and_broadcast,
    embed_fn=self._runtime.embed_fn,
    cost_fn=self._runtime.cost_fn,
    tier_budgets=engine_budgets,
    route_fn=_make_route_fn(self._runtime),  # NEW
)
```

**Note:** T1 owns `engine/runner.py` and `surface/runtime.py` but does NOT own
`surface/colony_manager.py`. The `route_fn` wiring in colony_manager happens
at T2 merge time, since T2 owns colony_manager. T1 should document the expected
interface in its merge summary so T2 can wire it.

---

## 2. Skill Composite Scoring (ADR-010, T2)

### 2.1 Composite Score Formula

Replace the current flat semantic retrieval with a multi-signal composite:

```
composite(hit) = (semantic_score × 0.50) + (confidence × 0.25) + (freshness × 0.25)
```

Where:
- `semantic_score` = `hit.score` from LanceDB (0.0 = perfect match for cosine distance)
  **Important:** LanceDB returns distance, not similarity. Lower is better.
  Normalize: `semantic_score = 1.0 - min(hit.score, 1.0)` before compositing.
- `confidence` = `float(hit.metadata.get("confidence", 0.5))`, range [0.1, 1.0]
- `freshness` = `2^(-age_days / 90.0)`, where `age_days` is computed from
  `hit.metadata["extracted_at"]` (ISO 8601 timestamp)

### 2.2 Freshness Decay

Exponential decay with 90-day half-life:

```python
freshness = 2.0 ** (-age_days / 90.0)
```

| Age | Freshness |
|-----|-----------|
| 0 days (just extracted) | 1.000 |
| 30 days | 0.794 |
| 90 days | 0.500 |
| 180 days | 0.250 |
| 365 days | 0.059 |

A skill extracted today is 2× more relevant than a 90-day-old skill, all else equal.
If `extracted_at` is missing or unparseable, default `age_days = 0.0` (treat as fresh).

### 2.3 Retrieval and Re-Ranking

```python
# Step 1: Retrieve candidates
raw_skills = await vector_port.search(collection="skill_bank", query=round_goal, top_k=8)

# Step 2: Score each candidate
scored = []
for hit in raw_skills:
    semantic = 1.0 - min(hit.score, 1.0)  # normalize distance → similarity
    confidence = float(hit.metadata.get("confidence", 0.5))
    freshness = _compute_freshness(hit.metadata.get("extracted_at", ""))
    composite = (semantic * 0.50) + (confidence * 0.25) + (freshness * 0.25)
    scored.append((composite, hit, confidence))

# Step 3: Sort descending by composite, take top 3
scored.sort(key=lambda x: -x[0])
top_skills = scored[:3]

# Step 4: Format for injection with confidence annotation
skill_parts = []
retrieved_skill_ids = []
for _score, hit, conf in top_skills:
    skill_parts.append(f"[conf:{conf:.1f}] {hit.content[:300]}")
    retrieved_skill_ids.append(hit.id)
```

### 2.4 Return Type Change

`assemble_context()` changes from returning `list[LLMMessage]` to a frozen
Pydantic model:

```python
class ContextResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    messages: list[LLMMessage]
    retrieved_skill_ids: list[str] = []
```

Callers (runner.py) must unpack:
```python
ctx = await assemble_context(...)
messages = ctx.messages
# Pass ctx.retrieved_skill_ids to RoundResult for colony_manager to accumulate
```

Add `retrieved_skill_ids: list[str] = []` to `RoundResult` in runner.py.

---

## 3. Skill Confidence Update (ADR-010, T2)

### 3.1 Update Algorithm

After colony completion, adjust confidence on all skills that were retrieved
during the colony's rounds:

```python
CONFIDENCE_DELTA = 0.1
CONFIDENCE_MIN = 0.1
CONFIDENCE_MAX = 1.0
ALGORITHM_VERSION = "v1"

async def update_skill_confidence(
    vector_port: VectorPort,
    retrieved_skill_ids: list[str],
    colony_succeeded: bool,
) -> int:
    delta = CONFIDENCE_DELTA if colony_succeeded else -CONFIDENCE_DELTA
    updated = 0

    for skill_id in retrieved_skill_ids:
        try:
            # Retrieve current skill by searching for its ID
            hits = await vector_port.search(
                collection="skill_bank", query=skill_id, top_k=1,
            )
            # Find the exact match by ID (search returns semantic matches)
            hit = None
            for h in hits:
                if h.id == skill_id:
                    hit = h
                    break
            if hit is None:
                continue

            old_conf = float(hit.metadata.get("confidence", 0.5))
            new_conf = max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, old_conf + delta))

            # Update by upserting with same ID (LanceDB overwrites)
            new_meta = dict(hit.metadata)
            new_meta["confidence"] = new_conf
            new_meta["algorithm_version"] = ALGORITHM_VERSION

            doc = VectorDocument(
                id=skill_id,
                content=hit.content,
                metadata=new_meta,
            )
            await vector_port.upsert(collection="skill_bank", docs=[doc])
            updated += 1

            log.info("skill_lifecycle.confidence_updated",
                skill_id=skill_id, old=old_conf, new=new_conf,
                delta=delta, algorithm=ALGORITHM_VERSION)
        except Exception:
            log.warning("skill_lifecycle.confidence_update_failed",
                skill_id=skill_id)
            continue

    return updated
```

**Implementation note:** The `VectorPort.search()` method returns semantic
matches, not ID lookups. To find a skill by ID, the coder may need to search
with the skill's content as query, or check if LanceDB supports ID-based
retrieval directly. If `search()` cannot reliably find by ID, the alternative
is to maintain a local `skill_id → content` index during the colony run and
upsert with the known content. The coder should investigate the LanceDB adapter
and choose the most reliable path.

### 3.2 Confidence Tracking Across Rounds

In `colony_manager._run_colony_inner()`:

```python
retrieved_skill_ids: set[str] = set()  # accumulate across all rounds

for round_num in range(...):
    result = await runner.run_round(...)
    retrieved_skill_ids.update(result.retrieved_skill_ids)

# After colony completion (both success and failure paths):
if retrieved_skill_ids and self._runtime.vector_store is not None:
    await update_skill_confidence(
        self._runtime.vector_store,
        list(retrieved_skill_ids),
        colony_succeeded=(quality > 0),
    )
```

This is fire-and-forget. Errors in confidence update do not affect colony
completion. The `retrieved_skill_ids` set is runtime-ephemeral — lost on
restart. This is acceptable because confidence is a derived metric.

---

## 4. Skill Ingestion Quality Gate (ADR-010, T2)

### 4.1 Validation Algorithm

Before upserting a newly extracted skill into the skill_bank, check:

```python
MIN_SOURCE_QUALITY = 0.3
MIN_CONTENT_LENGTH = 20
DEDUP_COSINE_THRESHOLD = 0.92

async def validate_skill_for_ingestion(
    vector_port: VectorPort,
    skill_content: str,
    source_quality_score: float,
) -> bool:
    # Gate 1: Source colony quality
    if source_quality_score < MIN_SOURCE_QUALITY:
        log.info("skill_lifecycle.ingestion_rejected",
            reason="low_source_quality", quality=source_quality_score)
        return False

    # Gate 2: Content length
    if len(skill_content.strip()) < MIN_CONTENT_LENGTH:
        log.info("skill_lifecycle.ingestion_rejected",
            reason="content_too_short", length=len(skill_content))
        return False

    # Gate 3: Semantic deduplication
    try:
        existing = await vector_port.search(
            collection="skill_bank", query=skill_content, top_k=1,
        )
        if existing:
            similarity = 1.0 - min(existing[0].score, 1.0)  # distance → similarity
            if similarity > DEDUP_COSINE_THRESHOLD:
                log.info("skill_lifecycle.ingestion_rejected",
                    reason="duplicate", similarity=similarity,
                    existing_id=existing[0].id)
                return False
    except Exception:
        pass  # collection may not exist yet — allow ingestion

    return True
```

### 4.2 Integration with Crystallization

In `colony_manager._crystallize_skills()`, after building the `docs` list but
before upserting:

```python
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

if not valid_docs:
    return 0

count = await self._runtime.vector_store.upsert(
    collection="skill_bank", docs=valid_docs,
)
```

---

## 5. Colony Observation Hook (T2)

### 5.1 Payload Schema

At colony completion (both success and failure), emit a structured structlog entry.
This is NOT an event — it goes to structlog only, for future template extraction.

```python
log.info("colony_observation",
    colony_id=colony_id,
    task=colony.task[:200],
    caste_names=colony.caste_names,
    strategy=colony.strategy,
    rounds_completed=round_num,
    quality_score=quality,              # 0.0 for failed colonies
    total_cost=total_cost,
    skills_retrieved=list(retrieved_skill_ids),
    skills_extracted=skills_count,      # 0 if crystallization skipped
    governance_warnings=governance_warnings,
    stall_rounds=stall_count,
)
```

This fires in both completion paths:
- governance "complete" → quality > 0, skills_extracted >= 0
- max rounds exhausted → quality > 0, skills_extracted >= 0
- governance "force_halt" or "halt" → quality = 0.0, skills_extracted = 0
- exception → quality = 0.0 (if reached)

---

## 6. Skill Bank Summary for Snapshot (T3)

### 6.1 Summary Query

```python
async def get_skill_bank_summary(vector_port: VectorPort) -> dict:
    """Return {"total": int, "avgConfidence": float} for the skill bank."""
    try:
        # Use a broad search to get all skills (empty query returns all)
        all_skills = await vector_port.search(
            collection="skill_bank", query="skill", top_k=100,
        )
        if not all_skills:
            return {"total": 0, "avgConfidence": 0.0}

        confidences = [
            float(h.metadata.get("confidence", 0.5)) for h in all_skills
        ]
        return {
            "total": len(all_skills),
            "avgConfidence": round(sum(confidences) / len(confidences), 3),
        }
    except Exception:
        return {"total": 0, "avgConfidence": 0.0}
```

**Note:** This is a best-effort summary. It uses `top_k=100` which caps
at 100 skills. For alpha scale this is sufficient. If the skill bank grows
beyond 100, the summary becomes approximate (which is acceptable for a UI stat).

### 6.2 Snapshot Integration

In `ws_handler.py`, the `send_state()` method calls `build_snapshot()`. Pre-fetch
skill stats before calling:

```python
async def send_state(self, ws: WebSocket) -> None:
    from formicos.surface.skill_lifecycle import get_skill_bank_summary
    from formicos.surface.view_state import build_snapshot

    # Pre-fetch async data
    skill_stats = None
    if self._runtime and self._runtime.vector_store:
        skill_stats = await get_skill_bank_summary(self._runtime.vector_store)

    snapshot = build_snapshot(
        self._projections, self._settings, self._castes,
        skill_bank_stats=skill_stats,
    )
    await ws.send_text(json.dumps({"type": "state", "state": snapshot}))
```

In `view_state.py`, `build_snapshot()` adds a new optional parameter:

```python
def build_snapshot(
    store: ProjectionStore,
    settings: SystemSettings,
    castes: CasteRecipeSet | None = None,
    skill_bank_stats: dict[str, Any] | None = None,  # NEW
) -> dict[str, Any]:
    return {
        # ... all existing fields ...
        "skillBankStats": skill_bank_stats or {"total": 0, "avgConfidence": 0.0},
    }
```

### 6.3 modelsUsed Derivation

In `view_state._build_tree()`, add to each colony node:

```python
colony_node["modelsUsed"] = list({a.model for a in colony.agents.values()})
```

This is pure derivation from existing projection data. No new data source.

---

## 7. LanceDB Score Normalization

**Critical implementation detail.** LanceDB `search()` returns a `score` field
that is a **distance** metric (lower = more similar), not a similarity metric
(higher = more similar). The exact metric depends on the distance type configured
for the collection (cosine distance by default with sentence-transformers).

For cosine distance: `similarity = 1.0 - distance`. Distance range is [0, 2] for
cosine; typical range for good matches is [0, 0.5].

Wherever algorithms in this document compute composite scores using `hit.score`,
normalize first:

```python
semantic_similarity = 1.0 - min(hit.score, 1.0)
```

This produces a value in [0.0, 1.0] where 1.0 = perfect match. The `min(..., 1.0)`
clamp handles edge cases where distance exceeds 1.0 (poor matches).
