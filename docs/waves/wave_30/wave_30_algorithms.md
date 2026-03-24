# Wave 30 Algorithms -- Implementation Reference

**Wave:** 30 -- "Knowledge Metabolism"
**Purpose:** Technical implementation guide grounded in post-Wave-29 codebase state.

---

## S1. MemoryEntry Confidence Fields (Track A -- A1)

### In core/types.py -- after thread_id (line 309-312)

```python
class MemoryEntry(BaseModel):
    # ... existing fields through thread_id ...
    conf_alpha: float = Field(
        default=5.0,
        description="Beta distribution alpha. Prior strength 10 split evenly (Wave 30).",
    )
    conf_beta: float = Field(
        default=5.0,
        description="Beta distribution beta. Prior strength 10 split evenly (Wave 30).",
    )
```

Prior (5.0, 5.0) matches legacy `DEFAULT_PRIOR_STRENGTH = 10.0` from `skill_lifecycle.py` line 35. Backward-compatible: existing entries deserialize with defaults, giving confidence = 5.0 / (5.0 + 5.0) = 0.5, matching the existing `confidence` field default.

---

## S2. MemoryConfidenceUpdated Event + Union Expansion (Track A -- A2)

### In core/events.py -- new event

```python
class MemoryConfidenceUpdated(EventEnvelope):
    """Knowledge entry confidence updated from colony outcome or archival decay (Wave 30)."""
    model_config = FrozenConfig

    type: Literal["MemoryConfidenceUpdated"] = "MemoryConfidenceUpdated"
    entry_id: str = Field(..., description="Memory entry being updated.")
    colony_id: str = Field(
        default="",
        description="Colony whose outcome drove the update. Empty for archival decay.",
    )
    colony_succeeded: bool = Field(default=True, description="True for archival decay (neutral).")
    old_alpha: float = Field(...)
    old_beta: float = Field(...)
    new_alpha: float = Field(...)
    new_beta: float = Field(...)
    new_confidence: float = Field(..., description="Posterior mean: alpha / (alpha + beta).")
    workspace_id: str = Field(...)
    thread_id: str = Field(default="")
    reason: str = Field(
        default="colony_outcome",
        description="colony_outcome | archival_decay",
    )
```

### Union expansion (45 -> 48)

After Wave 29 events at lines 828-831:

```python
FormicOSEvent: TypeAlias = Annotated[
    Union[
        # ... existing 45 members ...
        MemoryConfidenceUpdated,   # Wave 30
        WorkflowStepDefined,       # Wave 30
        WorkflowStepCompleted,     # Wave 30
    ],
    Field(discriminator="type"),
]
```

### In core/ports.py

Add `"MemoryConfidenceUpdated"`, `"WorkflowStepDefined"`, `"WorkflowStepCompleted"` to `EventTypeName` literal.

---

## S3. Confidence Update in _post_colony_hooks (Track A -- A3)

### In surface/colony_manager.py -- _post_colony_hooks() after line 741

The method currently ends with institutional memory extraction (fire-and-forget). A3's block goes immediately after, before B4's step completion block.

```python
        # --- Wave 30 A3: Bayesian confidence update from knowledge access traces ---
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None:
            accesses: list[dict[str, Any]] = getattr(
                colony_proj, "knowledge_accesses", [],
            )
            seen_ids: set[str] = set()
            for trace in accesses:
                for item in trace.get("items", []):
                    item_id = item.get("id", "")
                    if not item_id or item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)
                    entry = self._runtime.projections.memory_entries.get(item_id)
                    if entry is None:
                        continue
                    old_alpha = float(entry.get("conf_alpha", 5.0))
                    old_beta = float(entry.get("conf_beta", 5.0))
                    if succeeded:
                        new_alpha = old_alpha + 1.0
                        new_beta = old_beta
                    else:
                        new_alpha = old_alpha
                        new_beta = old_beta + 1.0
                    new_confidence = new_alpha / (new_alpha + new_beta)

                    from formicos.core.events import MemoryConfidenceUpdated
                    address = f"{colony.workspace_id}/{colony.thread_id}/{colony_id}"
                    await self._runtime.emit_and_broadcast(
                        MemoryConfidenceUpdated(
                            seq=0,
                            timestamp=_now(),
                            address=address,
                            entry_id=item_id,
                            colony_id=colony_id,
                            colony_succeeded=succeeded,
                            old_alpha=old_alpha,
                            old_beta=old_beta,
                            new_alpha=new_alpha,
                            new_beta=new_beta,
                            new_confidence=new_confidence,
                            workspace_id=colony.workspace_id,
                            thread_id=getattr(colony, "thread_id", ""),
                            reason="colony_outcome",
                        ),
                    )

        # --- Wave 30 B4: Workflow step completion check (see S11) ---
        # ... goes here, AFTER A3 ...
```

Note: `runtime.projections.memory_entries` is a `dict[str, dict[str, Any]]` -- a flat dict on `ProjectionStore`, not nested under workspaces. Each value is a dict with fields including `"conf_alpha"`, `"conf_beta"`, `"id"`, etc.

The `seen_ids` set deduplicates across rounds -- if an entry was used in round 1 and round 3 of the same colony, it gets one update, not two.

---

## S4. Projection Handler for MemoryConfidenceUpdated (Track A -- A4)

### In surface/projections.py

```python
def _on_memory_confidence_updated(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryConfidenceUpdated = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["conf_alpha"] = e.new_alpha
        entry["conf_beta"] = e.new_beta
        entry["confidence"] = e.new_confidence
```

Existing `sync_entry()` in `emit_and_broadcast` pushes the updated entry dict to Qdrant.

**Note for S15 (LLM dedup dismissed pair tracking):** The existing `_on_memory_entry_status_changed` handler must also store `entry["last_status_reason"] = e.reason` so that the dedup handler can scan for previously dismissed pairs. This is a one-line addition to the existing handler.

### Register in _HANDLERS (lines 774-799)

```python
"MemoryConfidenceUpdated": _on_memory_confidence_updated,
"WorkflowStepDefined": _on_workflow_step_defined,       # S10
"WorkflowStepCompleted": _on_workflow_step_completed,    # S10
```

---

## S5. Thompson Sampling in Composite Scoring (Track A -- A5)

### Add _compute_freshness to surface/knowledge_catalog.py

Port from `engine/context.py` lines 176-185. Place above `_composite_key` (before line 106):

```python
import random
import time as _time_mod
from datetime import datetime


def _compute_freshness(created_at: str) -> float:
    """Exponential decay with 90-day half-life. Returns value in [0, 1].

    Ported from engine/context.py. Defaults to 1.0 for empty/invalid strings.
    """
    if not created_at:
        return 1.0
    try:
        ext_dt = datetime.fromisoformat(created_at)
        age_days = (_time_mod.time() - ext_dt.timestamp()) / 86400.0
    except (ValueError, TypeError):
        return 1.0
    return 2.0 ** (-age_days / 90.0)
```

Default is 1.0 for empty strings, matching `engine/context.py` exactly.

### Replace _composite_key in surface/knowledge_catalog.py (lines 106-117)

Current:
```python
_STATUS_BONUS: dict[str, float] = {
    "verified": 0.3, "active": 0.25,
    "candidate": 0.0, "stale": -0.2,
}

def _composite_key(item: dict[str, Any]) -> float:
    return -(
        float(item.get("score", 0.0))
        + _STATUS_BONUS.get(str(item.get("status", "")), -0.5)
        + float(item.get("confidence", 0.0)) * 0.1
    )
```

Replacement:
```python
_STATUS_BONUS: dict[str, float] = {
    "verified": 0.3, "active": 0.25,
    "candidate": 0.0, "stale": -0.2,
}


def _composite_key(item: dict[str, Any]) -> float:
    """Thompson Sampling composite: semantic + sampled confidence + freshness + status + thread.

    Returns NEGATIVE for ascending sort (used at line 202: merged.sort(key=_composite_key)).
    """
    semantic = float(item.get("score", 0.0))
    alpha = float(item.get("conf_alpha", 5.0))
    beta_p = float(item.get("conf_beta", 5.0))
    thompson = random.betavariate(max(alpha, 0.1), max(beta_p, 0.1))
    freshness = _compute_freshness(item.get("created_at", ""))
    status = _STATUS_BONUS.get(str(item.get("status", "")), -0.5)
    thread_bonus = float(item.get("_thread_bonus", 0.0))
    return -(
        0.35 * semantic
        + 0.25 * thompson
        + 0.15 * freshness
        + 0.15 * status
        + 0.10 * thread_bonus
    )
```

### Replace thread-boosted sort at line 270

Current:
```python
merged.sort(key=lambda x: -float(x.get("score", 0.0)))
```

Replacement:
```python
merged.sort(key=_composite_key)
```

This is the THIRD sort path (used by `_search_thread_boosted`). Replace line 233 entirely:

Current line 233:
```python
item["score"] = float(item.get("score", 0.0)) + self._THREAD_BONUS
```

Replacement:
```python
item["_thread_bonus"] = self._THREAD_BONUS
```

Do NOT modify `item["score"]`. The old direct score boost was a hack for the flat sort. The composite key now handles thread bonus through its dedicated 0.10 term. Modifying score AND setting `_thread_bonus` would double-count: `0.35 * 0.25 + 0.10 * 0.25 = 0.1125` instead of the intended `0.10 * 0.25 = 0.025`.

### Replace _composite in surface/memory_store.py (lines 359-367)

This is a closure defined inside a method body. Current:
```python
_STATUS_BONUS = {"verified": 0.3, "candidate": 0.0, "stale": -0.2}

def _composite(entry: dict[str, Any]) -> float:
    score = float(entry.get("score", 0.0))
    status = str(entry.get("status", "candidate"))
    confidence = float(entry.get("confidence", 0.0))
    return score + _STATUS_BONUS.get(status, -0.5) + confidence * 0.1

results.sort(key=_composite, reverse=True)
```

Replacement:
```python
_STATUS_BONUS = {"verified": 0.3, "candidate": 0.0, "stale": -0.2}

def _composite(entry: dict[str, Any]) -> float:
    """Thompson Sampling composite. Returns POSITIVE (sorted reverse=True)."""
    import random
    semantic = float(entry.get("score", 0.0))
    alpha = float(entry.get("conf_alpha", 5.0))
    beta_p = float(entry.get("conf_beta", 5.0))
    thompson = random.betavariate(max(alpha, 0.1), max(beta_p, 0.1))
    created = entry.get("created_at", "")
    freshness = _ms_compute_freshness(created)
    status = _STATUS_BONUS.get(str(entry.get("status", "candidate")), -0.5)
    return (
        0.35 * semantic
        + 0.25 * thompson
        + 0.15 * freshness
        + 0.15 * status
    )

results.sort(key=_composite, reverse=True)
```

Sign convention: POSITIVE values, `reverse=True` for descending sort. No thread_bonus here because `memory_store.py` does not do thread boosting (that's `knowledge_catalog.py`'s job).

Also add `_ms_compute_freshness` as a module-level helper in `memory_store.py`, identical to the one in `knowledge_catalog.py` (or import from a shared location if preferred -- but the simpler approach is duplication since both are 8-line pure functions).

---

## S6. archive_thread Queen Tool + Archival Decay (Track A -- A6)

### Tool definition -- add to _queen_tools() after complete_thread (after line 1023 area)

```python
{
    "name": "archive_thread",
    "description": (
        "Archive a completed thread. Archived threads' unpromoted knowledge "
        "entries receive a confidence decay. Use after complete_thread when "
        "the workflow is no longer active."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "Why the thread is being archived.",
            },
        },
        "required": ["reason"],
    },
},
```

### Handler -- add after complete_thread handler block (after line 1162)

```python
if name == "archive_thread":
    reason = inputs.get("reason", "")
    ws = self._runtime.projections.workspaces.get(workspace_id)
    old_status = "completed"
    if ws is not None:
        thread = ws.threads.get(thread_id)
        if thread is not None:
            old_status = thread.status

    await self._runtime.emit_and_broadcast(ThreadStatusChanged(
        seq=0, timestamp=_now(),
        address=f"{workspace_id}/{thread_id}",
        workspace_id=workspace_id, thread_id=thread_id,
        old_status=old_status, new_status="archived", reason=reason,
    ))

    # Archival decay: emit MemoryConfidenceUpdated per unpromoted entry
    from formicos.core.events import MemoryConfidenceUpdated
    decayed = 0
    for entry_id, entry in self._runtime.projections.memory_entries.items():
        if entry.get("thread_id") != thread_id:
            continue
        old_alpha = float(entry.get("conf_alpha", 5.0))
        old_beta = float(entry.get("conf_beta", 5.0))
        new_alpha = old_alpha * 0.8
        new_beta = old_beta * 1.2
        new_confidence = new_alpha / (new_alpha + new_beta)
        await self._runtime.emit_and_broadcast(MemoryConfidenceUpdated(
            seq=0, timestamp=_now(),
            address=f"{workspace_id}/{thread_id}",
            entry_id=entry_id,
            colony_id="",
            colony_succeeded=True,
            old_alpha=old_alpha, old_beta=old_beta,
            new_alpha=new_alpha, new_beta=new_beta,
            new_confidence=new_confidence,
            workspace_id=workspace_id,
            thread_id=thread_id,
            reason="archival_decay",
        ))
        decayed += 1

    return (f"Thread archived: {reason}. {decayed} entries decayed.", None)
```

This emits N events for N unpromoted entries. Each is processed by the projection handler (S4) and sync_entry pushes to Qdrant. This is the cost of event-sourcing (hard constraint #7).

---

## S7. Scheduled Maintenance Timer (Track A -- A7)

### In surface/app.py -- after service registration (after line 532)

```python
# Wave 30 A7: scheduled maintenance timer
_MAINTENANCE_INTERVAL_S = int(os.environ.get("FORMICOS_MAINTENANCE_INTERVAL_S", "86400"))

async def _maintenance_loop(
    router: ServiceRouter, interval_s: int = _MAINTENANCE_INTERVAL_S,
) -> None:
    """Periodic dispatch of consolidation services."""
    while True:
        await asyncio.sleep(interval_s)
        for svc in [
            "service:consolidation:dedup",
            "service:consolidation:stale_sweep",
            "service:consolidation:contradictions",
        ]:
            try:
                await router.query(
                    service_type=svc, query_text="scheduled_run",
                    timeout_s=300.0,
                )
            except Exception:
                log.debug("maintenance.scheduled_run_failed", service=svc)

if service_router is not None:
    asyncio.create_task(_maintenance_loop(service_router))
```

Configurable via `FORMICOS_MAINTENANCE_INTERVAL_S` environment variable. Default 86400 (daily). Uses the same `service_router.query()` dispatch as operator and Queen triggers.

---

## S8. WorkflowStep + WorkflowStepStatus Types (Track B -- B1)

### In core/types.py -- after MemoryEntry

```python
class WorkflowStepStatus(StrEnum):
    """Status of a workflow step within a thread."""
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class WorkflowStep(BaseModel):
    """A declared step in a thread's workflow (Wave 30)."""
    model_config = FrozenConfig

    step_index: int = Field(description="0-based position in the workflow.")
    description: str = Field(description="What this step should accomplish.")
    expected_outputs: list[str] = Field(default_factory=list)
    template_id: str = Field(default="", description="Optional template to use.")
    strategy: str = Field(default="stigmergic", description="stigmergic | sequential | deterministic.")
    status: str = Field(default="pending")
    colony_id: str = Field(default="", description="Colony executing this step, if any.")
    input_from_step: int = Field(default=-1, description="Step to chain from, -1 = none.")
```

Add both to `__all__`.

---

## S9. WorkflowStepDefined + WorkflowStepCompleted Events (Track B -- B2)

### In core/events.py

```python
class WorkflowStepDefined(EventEnvelope):
    """A workflow step was added to a thread (Wave 30)."""
    model_config = FrozenConfig

    type: Literal["WorkflowStepDefined"] = "WorkflowStepDefined"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step: WorkflowStep = Field(...)


class WorkflowStepCompleted(EventEnvelope):
    """A workflow step's colony completed (Wave 30)."""
    model_config = FrozenConfig

    type: Literal["WorkflowStepCompleted"] = "WorkflowStepCompleted"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step_index: int = Field(...)
    colony_id: str = Field(...)
    success: bool = Field(...)
    artifacts_produced: list[str] = Field(default_factory=list, description="Artifact type list.")
```

Union expansion shared with S2 (45 -> 48). Ports.py gains all three names.

---

## S10. ThreadProjection Workflow Steps + Handlers (Track B -- B3)

### In surface/projections.py -- extend ThreadProjection (lines 194-210)

Add after existing fields:

```python
    workflow_steps: list[dict[str, Any]] = field(default_factory=list)  # Wave 30
```

### Handlers

```python
def _on_workflow_step_defined(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkflowStepDefined = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.workflow_steps.append(e.step.model_dump())


def _on_workflow_step_completed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: WorkflowStepCompleted = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            for step in thread.workflow_steps:
                if step.get("step_index") == e.step_index:
                    step["status"] = "completed" if e.success else "failed"
                    step["colony_id"] = e.colony_id
                    break
```

### Step "running" derivation in _on_colony_spawned (after line 345)

After `thread.colony_count += 1`:

```python
    # Wave 30: derive step "running" from colony spawn metadata
    step_index = getattr(e, "step_index", -1)
    if step_index >= 0 and thread.workflow_steps:
        for step in thread.workflow_steps:
            if step.get("step_index") == step_index and step.get("status") == "pending":
                step["status"] = "running"
                step["colony_id"] = colony_id
                break
```

This is derived state from event data -- no event emission from the projection handler.

---

## S11. Step Completion in _post_colony_hooks (Track B -- B4)

### In surface/colony_manager.py -- AFTER A3's confidence block (S3)

```python
        # --- Wave 30 B4: Workflow step completion check ---
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None:
            thread_id = getattr(colony, "thread_id", "")
            if thread_id:
                ws = self._runtime.projections.workspaces.get(colony.workspace_id)
                if ws is not None:
                    thread = ws.threads.get(thread_id)
                    if thread is not None:
                        for step in thread.workflow_steps:
                            if (
                                step.get("colony_id") == colony_id
                                and step.get("status") == "running"
                            ):
                                # Collect artifact types from the colony
                                art_types = []
                                for a in getattr(colony_proj, "artifacts", []):
                                    ad = a if isinstance(a, dict) else {}
                                    atype = ad.get("artifact_type", "generic")
                                    if atype not in art_types:
                                        art_types.append(atype)

                                from formicos.core.events import WorkflowStepCompleted
                                await self._runtime.emit_and_broadcast(
                                    WorkflowStepCompleted(
                                        seq=0,
                                        timestamp=_now(),
                                        address=f"{colony.workspace_id}/{thread_id}",
                                        workspace_id=colony.workspace_id,
                                        thread_id=thread_id,
                                        step_index=step.get("step_index", -1),
                                        colony_id=colony_id,
                                        success=succeeded,
                                        artifacts_produced=art_types,
                                    ),
                                )
                                break  # one colony matches at most one step
```

Ordering: A3 confidence block first (S3), then B4 step completion (this section). Both live in `_post_colony_hooks()` after line 741.

---

## S12. Queen define_workflow_steps Tool + Thread Context (Track B -- B5)

### Tool definition

```python
{
    "name": "define_workflow_steps",
    "description": (
        "Declare workflow steps for the current thread. Each step describes "
        "a phase of work with expected outputs. Steps guide spawn decisions "
        "and track progress."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "expected_outputs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "template_id": {"type": "string"},
                        "strategy": {"type": "string"},
                        "input_from_step": {"type": "integer"},
                    },
                    "required": ["description"],
                },
            },
        },
        "required": ["steps"],
    },
},
```

### Handler

```python
if name == "define_workflow_steps":
    steps_input = inputs.get("steps", [])
    if not steps_input:
        return ("Error: steps list is required.", None)

    from formicos.core.events import WorkflowStepDefined
    from formicos.core.types import WorkflowStep
    for i, s in enumerate(steps_input):
        step = WorkflowStep(
            step_index=i,
            description=s.get("description", ""),
            expected_outputs=s.get("expected_outputs", []),
            template_id=s.get("template_id", ""),
            strategy=s.get("strategy", "stigmergic"),
            input_from_step=s.get("input_from_step", -1),
        )
        await self._runtime.emit_and_broadcast(WorkflowStepDefined(
            seq=0, timestamp=_now(),
            address=f"{workspace_id}/{thread_id}",
            workspace_id=workspace_id,
            thread_id=thread_id,
            step=step,
        ))

    return (f"Defined {len(steps_input)} workflow steps.", None)
```

### Extend _build_thread_context (line 593-625)

After the existing progress/colonies block, add step display:

```python
    # Wave 30: workflow step status
    if thread_proj.workflow_steps:
        lines.append("Steps:")
        for step in thread_proj.workflow_steps:
            idx = step.get("step_index", "?")
            desc = step.get("description", "")
            status = step.get("status", "pending")
            cid = step.get("colony_id", "")
            colony_ref = f" (colony {cid[:12]})" if cid else ""
            lines.append(f"  [{idx + 1}] [{status}] {desc}{colony_ref}")
```

---

## S13. Additive step_index on ColonySpawned (Track B -- B6)

### In core/events.py -- ColonySpawned (line 127)

Add additive field:

```python
class ColonySpawned(EventEnvelope):
    # ... existing fields (thread_id, task, castes, model_assignments, strategy,
    #                      max_rounds, budget_limit, template_id, input_sources) ...
    step_index: int = Field(
        default=-1,
        description="Workflow step this colony executes. -1 = no step association (Wave 30).",
    )
```

**This is a contract change.** Backward-compatible: existing serialized events without `step_index` deserialize with default -1.

### Step-aware spawn path in queen_runtime.py

When the Queen spawns a colony and references a step (via step_index in spawn parameters), include it in the `ColonySpawned` event. The Queen's `spawn_colony` handler checks if the spawn request includes a `step_index`:

```python
# In spawn_colony handler, when building ColonySpawned:
step_index = inputs.get("step_index", -1)
# ... pass to ColonySpawned(step_index=step_index, ...)
```

Also update the `spawn_colony` tool schema to accept optional `step_index`:
```python
"step_index": {
    "type": "integer",
    "description": "Workflow step index this colony executes (-1 = none).",
},
```

---

## S14. Contradiction Detection Handler (Track B -- B7)

### In surface/maintenance.py -- new factory after make_stale_handler

```python
def make_contradiction_handler(runtime: Runtime):
    """Factory: returns async callable for contradiction detection."""

    async def _handle_contradictions(query_text: str, ctx: dict[str, Any]) -> str:
        projections = runtime.projections

        # Collect verified entries with non-empty polarity and domains
        candidates: list[dict[str, Any]] = []
        for entry_id, entry in projections.memory_entries.items():
            if entry.get("status") != "verified":
                continue
            polarity = entry.get("polarity", "")
            domains = entry.get("domains", [])
            if not polarity or polarity == "neutral" or not domains:
                continue  # Skip empty/neutral polarity
            candidates.append(entry)

        contradictions: list[dict[str, Any]] = []
        for i, entry_a in enumerate(candidates):
            domains_a = set(entry_a.get("domains", []))
            pol_a = entry_a.get("polarity", "")
            for entry_b in candidates[i + 1:]:
                pol_b = entry_b.get("polarity", "")
                if pol_a == pol_b:
                    continue  # Same polarity -- not a contradiction
                domains_b = set(entry_b.get("domains", []))
                # Jaccard coefficient
                intersection = domains_a & domains_b
                union = domains_a | domains_b
                if not union:
                    continue
                jaccard = len(intersection) / len(union)
                if jaccard <= 0.3:
                    continue
                contradictions.append({
                    "entry_a": entry_a.get("id", ""),
                    "entry_b": entry_b.get("id", ""),
                    "polarity_a": pol_a,
                    "polarity_b": pol_b,
                    "shared_domains": sorted(intersection),
                    "jaccard": round(jaccard, 3),
                    "conf_a": entry_a.get("confidence", 0.5),
                    "conf_b": entry_b.get("confidence", 0.5),
                })

        report = {
            "contradictions_found": len(contradictions),
            "entries_scanned": len(candidates),
            "pairs": contradictions,
        }
        return (
            f"Contradiction scan: {len(contradictions)} pairs found "
            f"across {len(candidates)} entries.\n"
            f"{json.dumps(report, indent=2)}"
        )

    return _handle_contradictions
```

### Register at startup in app.py (alongside existing handlers, after line 532 area)

```python
service_router.register_handler(
    "service:consolidation:contradictions",
    make_contradiction_handler(runtime),
)
```

---

## S15. LLM-Confirmed Dedup Extension (Track B -- B8)

### In surface/maintenance.py -- extend make_dedup_handler

After the cosine scan flags [0.82, 0.98) pairs (lines 71-76), add LLM confirmation stage. Uses the Gemini Flash call pattern from `queen_runtime.py` lines 160-189:

```python
        # --- Wave 30 B8: LLM-confirmed dedup for [0.82, 0.98) band ---
        # First, filter out previously dismissed pairs.
        # The projection handler for MemoryEntryStatusChanged stores
        # entry["last_status_reason"] = e.reason (see S4 note below).
        # Scan for entries with "dedup:dismissed" reason and extract pair IDs.
        dismissed_pairs: set[tuple[str, str]] = set()
        for eid, entry in projections.memory_entries.items():
            reason = entry.get("last_status_reason", "")
            if reason.startswith("dedup:dismissed"):
                # Extract paired ID from reason: "dedup:dismissed (pair with <id>)"
                import re
                m = re.search(r"pair with ([^\)]+)", reason)
                if m:
                    other_id = m.group(1).strip()
                    dismissed_pairs.add(tuple(sorted([eid, other_id])))

        # For each flagged pair, call Gemini Flash for confirmation
        llm_router = getattr(runtime, "llm_router", None)
        confirmed_merges = 0
        dismissed_count = 0

        for pair in flagged:
            pair_key = tuple(sorted([pair["entry_a"], pair["entry_b"]]))
            if pair_key in dismissed_pairs:
                continue

            entry_a = projections.memory_entries.get(pair["entry_a"])
            entry_b = projections.memory_entries.get(pair["entry_b"])
            if entry_a is None or entry_b is None:
                continue

            title_a = entry_a.get("title", "")
            preview_a = entry_a.get("content", "")[:300]
            title_b = entry_b.get("title", "")
            preview_b = entry_b.get("content", "")[:300]

            prompt = (
                f'Entry A: "{title_a}" - {preview_a}\n'
                f'Entry B: "{title_b}" - {preview_b}\n'
                f"Are these describing the same knowledge? Reply YES or NO."
            )

            try:
                if llm_router is None:
                    continue
                response = await asyncio.wait_for(
                    llm_router.complete(
                        model="gemini/gemini-2.5-flash",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.0,
                        max_tokens=10,
                    ),
                    timeout=15.0,
                )
                answer = response.content.strip().upper()
            except Exception:
                log.debug("dedup.llm_confirm_failed", pair=pair_key)
                continue

            if answer.startswith("YES"):
                # Auto-merge: reject lower-confidence entry
                survivor, absorbed = (
                    (entry_a, entry_b)
                    if entry_a.get("confidence", 0) >= entry_b.get("confidence", 0)
                    else (entry_b, entry_a)
                )
                from formicos.core.events import MemoryEntryStatusChanged
                await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                    seq=0, timestamp=datetime.now(UTC),
                    address=absorbed.get("workspace_id", ""),
                    entry_id=absorbed.get("id", ""),
                    old_status=absorbed.get("status", "verified"),
                    new_status="rejected",
                    reason=f"dedup:llm_confirmed (similarity {pair['similarity']:.3f}, kept {survivor.get('id', '')})",
                ))
                confirmed_merges += 1
            else:
                # Dismiss: mark pair as reviewed (status unchanged, reason is marker)
                lower = (
                    entry_b if entry_a.get("confidence", 0) >= entry_b.get("confidence", 0)
                    else entry_a
                )
                other = entry_a if lower is entry_b else entry_b
                from formicos.core.events import MemoryEntryStatusChanged
                await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                    seq=0, timestamp=datetime.now(UTC),
                    address=lower.get("workspace_id", ""),
                    entry_id=lower.get("id", ""),
                    old_status=lower.get("status", "verified"),
                    new_status=lower.get("status", "verified"),  # STATUS UNCHANGED
                    reason=f"dedup:dismissed (pair with {other.get('id', '')})",
                ))
                dismissed_count += 1
```

Key: for dismissed pairs, `old_status == new_status` (the entry's status doesn't change). The `reason` field starting with `"dedup:dismissed"` is the durable marker. The dedup handler on future runs filters on this reason to avoid re-evaluation.

Update the report to include LLM results:
```python
        report = {
            "auto_merged_high": merged_count,
            "llm_confirmed_merges": confirmed_merges,
            "llm_dismissed": dismissed_count,
            "flagged_unprocessed": len(flagged) - confirmed_merges - dismissed_count,
        }
```

---

## S16. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | conf_alpha, conf_beta on MemoryEntry (~4 LOC) |
| `src/formicos/core/events.py` | MemoryConfidenceUpdated, union 45->48 (~20 LOC) |
| `src/formicos/core/ports.py` | add 3 event names (~3 LOC) |
| `src/formicos/surface/colony_manager.py` | confidence update in _post_colony_hooks after line 741 (~35 LOC) |
| `src/formicos/surface/projections.py` | confidence handler + register in _HANDLERS (~10 LOC) |
| `src/formicos/surface/knowledge_catalog.py` | _compute_freshness + replace _composite_key + fix line 270 sort (~30 LOC) |
| `src/formicos/surface/memory_store.py` | replace _composite closure + add freshness (~20 LOC) |
| `src/formicos/surface/queen_runtime.py` | archive_thread tool + handler + decay loop (~50 LOC) |
| `src/formicos/surface/app.py` | maintenance timer (~15 LOC) |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | WorkflowStep, WorkflowStepStatus (~20 LOC) |
| `src/formicos/core/events.py` | WorkflowStepDefined, WorkflowStepCompleted, step_index on ColonySpawned (~25 LOC) |
| `src/formicos/core/ports.py` | add event names (shared with Track A) |
| `src/formicos/surface/projections.py` | workflow_steps field, 2 handlers, step "running" in _on_colony_spawned (~30 LOC) |
| `src/formicos/surface/colony_manager.py` | step completion in _post_colony_hooks after A3's block (~25 LOC) |
| `src/formicos/surface/queen_runtime.py` | define_workflow_steps tool + handler, step context in _build_thread_context, step_index in spawn (~50 LOC) |
| `src/formicos/surface/maintenance.py` | contradiction handler (~50 LOC), LLM dedup extension (~60 LOC) |
| `src/formicos/surface/app.py` | register contradiction handler (~5 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `frontend/src/components/thread-view.ts` | step timeline (~80 LOC) |
| `frontend/src/components/knowledge-browser.ts` | confidence display, contradictions, health (~80 LOC) |
| `frontend/src/components/colony-detail.ts` | confidence on trace items (~10 LOC) |
| `frontend/src/types.ts` | WorkflowStepPreview, confidence/contradiction types (~25 LOC) |
| `src/formicos/surface/skill_lifecycle.py` | DELETE |
| `src/formicos/adapters/skill_dedup.py` | DELETE |
| `frontend/src/components/skill-browser.ts` | DELETE |
| `src/formicos/surface/colony_manager.py` | delete _crystallize_skills method body (~-40 LOC) |
| `tests/*` | event count 45->48, dead ref removal, new tests |
