# Wave 30 Plan -- Knowledge Metabolism

**Wave:** 30 -- "Knowledge Metabolism"
**Theme:** Knowledge evolves from colony outcomes. Retrieval uses Thompson Sampling to balance exploitation with exploration. Threads gain workflow steps. Contradictions surface. LLM-confirmed dedup closes the ambiguous band. Thread archival decays orphaned knowledge. Legacy skill system files are deleted. The system becomes self-maintaining.
**Architectural thesis:** Knowledge that helps colonies succeed should be trusted more. Knowledge that correlates with failure should be trusted less. The retrieval system should explore uncertain entries, not just exploit known-good ones.
**Contract changes:** Event union opens from 45 to 48. Three new event types: `MemoryConfidenceUpdated`, `WorkflowStepDefined`, `WorkflowStepCompleted`. Additive `conf_alpha` and `conf_beta` on `MemoryEntry`. New `WorkflowStep` model in `core/types.py`.
**Estimated LOC delta:** ~500 Python, ~200 TypeScript, net negative ~300 LOC from legacy deletion

---

## Why This Wave

After Wave 29, FormicOS has workflow-scoped threads, thread-scoped knowledge retrieval, and deterministic maintenance services. But knowledge is still static: entries start at confidence 0.5 and never change. Retrieval ranking is deterministic -- the same entries always win. Near-duplicate entries in the [0.82, 0.98) band are flagged but never resolved. Threads can be completed but not archived with knowledge implications. Legacy skill system files still sit on disk.

Wave 30 closes all of these.

---

## What Got Frontloaded From Wave 31

**LLM-confirmed dedup.** Gemini Flash evaluates ambiguous-band pairs. The LLM routing infrastructure already exists. Bounded cost: one YES/NO call per pair.

**Thread archival with confidence decay.** Archived thread entries get confidence penalties via real `MemoryConfidenceUpdated` events (not projection-only mutation -- that would violate event-sourcing discipline).

**Legacy file deletion.** `skill_lifecycle.py`, `skill_dedup.py` (in `adapters/`), and `skill-browser.ts`. No reason to keep them another wave.

**Scheduled maintenance timer.** Lightweight periodic dispatch -- trivial addition.

---

## Critical Design Decisions

### D1. Bayesian confidence with proven math

The Beta distribution update from `skill_lifecycle.py` (lines 34-58: `beta_score()`, `beta_uncertainty()`, `migrate_flat_to_beta()`) is ported to institutional memory. After colony completion, each knowledge item in the colony's `KnowledgeAccessRecorded` traces gets a Bayesian update:
- Colony succeeded: `alpha += 1.0`
- Colony failed: `beta += 1.0`
- Posterior mean: `alpha / (alpha + beta)`

Default prior (5.0, 5.0) matches the legacy system's `DEFAULT_PRIOR_STRENGTH = 10.0` split evenly. Entries need several successes before ranking noticeably higher.

### D2. Thompson Sampling replaces the current composite scoring

The current `_composite_key` in `knowledge_catalog.py` is:

```python
_STATUS_BONUS = {"verified": 0.3, "active": 0.25, "candidate": 0.0, "stale": -0.2}

def _composite_key(item):
    return -(score + status_bonus + confidence * 0.1)
```

This uses a negated sum for ascending sort and has no freshness factor. Wave 30 replaces this with a Thompson Sampling-based composite:

```python
def _composite_key(item):
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

The sign convention stays negative (ascending sort) to match existing usage in `merged.sort(key=_composite_key)`. Freshness uses exponential decay with 90-day half-life, matching the function already in `engine/context.py`:

```python
def _compute_freshness(created_at: str) -> float:
    if not created_at:
        return 0.5
    try:
        age_days = (time.time() - datetime.fromisoformat(created_at).timestamp()) / 86400
    except (ValueError, TypeError):
        return 0.5
    return 2.0 ** (-age_days / 90.0)
```

Note: BOTH `knowledge_catalog.py` and `memory_store.py` have their own composite scoring with the same formula but different sign conventions. `knowledge_catalog.py` returns negative for ascending sort (`merged.sort(key=_composite_key)`). `memory_store.py` (lines 359-367) returns positive for descending sort (`results.sort(key=_composite, reverse=True)`). Both files need the Thompson Sampling change, preserving their respective sign conventions.

### D3. Workflow steps are Queen scaffolding, not a pipeline engine

Steps live on `ThreadProjection` as `workflow_steps`. The Queen defines steps via tool. Steps update on colony completion. Steps are guidance the Queen reasons about -- she can skip, reorder, or add steps. Automatic execution is Wave 31.

### D4. Events are never emitted from projection handlers

Projection handlers process events; they cannot emit events (recursive processing). Two specific consequences:

- **WorkflowStepCompleted** is emitted from `colony_manager._post_colony_hooks()` after colony completion, not from `_on_colony_completed` projection handler.
- **Step "running" status** is derived in `_on_colony_spawned` projection handler by matching optional `step_index` metadata on `ColonySpawned` against step definitions. No separate event needed -- this is derived state.

### D5. Contradiction detection skips entries with empty polarity

New handler: `service:consolidation:contradictions`. Scans verified entries with overlapping domains (Jaccard > 0.3) and opposite polarity (one positive, one negative). **Entries with empty or unset polarity are skipped** -- contradictions require explicit positive/negative assertion. Produces a report artifact.

### D6. LLM dedup tracks dismissed pairs via existing events

Wave 29's dedup handler is extended with a Gemini Flash confirmation stage for [0.82, 0.98) pairs. Dismissed pairs are tracked via `MemoryEntryStatusChanged` with reason `"dedup:dismissed"` (status unchanged, reason serves as durable marker). The dedup handler filters on this reason string to avoid re-evaluating dismissed pairs. No new event type or projection field needed.

### D7. Thread archival decay emits real events

The Queen's existing `complete_thread` tool emits `ThreadStatusChanged(new_status="completed")`. "Completed" means the workflow objective is satisfied. "Archived" means the thread is no longer active and its knowledge should decay.

Wave 30 adds an `archive_thread` Queen tool that emits `ThreadStatusChanged(new_status="archived")`. After emission, the same surface code iterates `runtime.projections.memory_entries` for entries with matching non-empty `thread_id` and emits `MemoryConfidenceUpdated` for each unpromoted entry with `reason="archival_decay"`, `colony_id=""`, decay `alpha *= 0.8`, `beta *= 1.2`. This produces N events for N entries.

The lifecycle is: active -> completed (goal satisfied, knowledge retains full confidence) -> archived (no longer active, unpromoted knowledge decays). The scheduled maintenance timer (A7) can auto-archive threads that have been completed for N days (default 30).

All emission happens in surface-layer code (queen_runtime.py archive handler or runtime archival path), NOT in a projection handler.

### D8. Legacy files are deleted

- `src/formicos/surface/skill_lifecycle.py` -- DELETE
- `src/formicos/adapters/skill_dedup.py` -- DELETE (adapters/, not surface/)
- `frontend/src/components/skill-browser.ts` -- DELETE
- `_crystallize_skills()` method body in `colony_manager.py` -- DELETE

---

## New Types

### WorkflowStep (core/types.py)

```python
class WorkflowStepStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"

class WorkflowStep(BaseModel):
    model_config = FrozenConfig

    step_index: int = Field(description="0-based position in the workflow")
    description: str = Field(description="What this step should accomplish")
    expected_outputs: list[str] = Field(default_factory=list)
    template_id: str = Field(default="")
    strategy: str = Field(default="stigmergic")
    status: str = Field(default="pending")
    colony_id: str = Field(default="", description="Colony executing this step")
    input_from_step: int = Field(default=-1, description="Step to chain from, -1 = none")
```

### MemoryEntry confidence fields (core/types.py)

```python
class MemoryEntry(BaseModel):
    # ... existing fields including thread_id from Wave 29 ...
    conf_alpha: float = Field(default=5.0, description="Beta distribution alpha (Wave 30)")
    conf_beta: float = Field(default=5.0, description="Beta distribution beta (Wave 30)")
```

---

## New Events (45 -> 48)

### MemoryConfidenceUpdated

```python
class MemoryConfidenceUpdated(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["MemoryConfidenceUpdated"] = "MemoryConfidenceUpdated"
    entry_id: str = Field(...)
    colony_id: str = Field(default="", description="Colony that drove the update. Empty for archival decay.")
    colony_succeeded: bool = Field(default=True)
    old_alpha: float = Field(...)
    old_beta: float = Field(...)
    new_alpha: float = Field(...)
    new_beta: float = Field(...)
    new_confidence: float = Field(..., description="Posterior mean: alpha / (alpha + beta)")
    workspace_id: str = Field(...)
    thread_id: str = Field(default="")
    reason: str = Field(default="colony_outcome", description="colony_outcome | archival_decay")
```

### WorkflowStepDefined

```python
class WorkflowStepDefined(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["WorkflowStepDefined"] = "WorkflowStepDefined"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step: WorkflowStep = Field(...)
```

### WorkflowStepCompleted

```python
class WorkflowStepCompleted(EventEnvelope):
    model_config = FrozenConfig

    type: Literal["WorkflowStepCompleted"] = "WorkflowStepCompleted"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    step_index: int = Field(...)
    colony_id: str = Field(...)
    success: bool = Field(...)
    artifacts_produced: list[str] = Field(default_factory=list)
```

---

## Tracks

### Track A -- Confidence Evolution + Thompson Sampling

**Goal:** Knowledge confidence evolves from colony outcomes. Retrieval explores uncertain entries. Thread archival decays knowledge via real events. Maintenance runs on schedule.

**A1. MemoryEntry gains conf_alpha/conf_beta.** Additive fields in `core/types.py`. Default prior (5.0, 5.0) matching legacy `DEFAULT_PRIOR_STRENGTH = 10.0` split evenly.

**A2. MemoryConfidenceUpdated event.** New event with `reason` field distinguishing `"colony_outcome"` from `"archival_decay"`. Union 45 -> 48 shared with Track B.

**A3. Confidence update after colony completion.** In `colony_manager._post_colony_hooks()`. Read traces from `runtime.projections.colonies[colony_id].knowledge_accesses` -- a `list[dict]`, each with `"items"` list containing dicts with `"id"` fields. For each accessed item ID, look up in `runtime.projections.memory_entries`, compute Bayesian update, emit `MemoryConfidenceUpdated(reason="colony_outcome")`.

**A4. Projection handler for confidence.** Updates `conf_alpha`, `conf_beta`, `confidence` on entry. Existing `sync_entry` pushes to Qdrant.

**A5. Thompson Sampling in composite scoring.** Replace current scoring in BOTH `knowledge_catalog.py` (`_composite_key`, negated for ascending sort) and `memory_store.py` (`_composite`, positive for `reverse=True` descending sort). Add `_compute_freshness` to both. Preserve each file's sign convention.

**A6. `archive_thread` Queen tool + archival decay via events.** New Queen tool `archive_thread(reason)` emits `ThreadStatusChanged(new_status="archived")`. After emission, iterate entries with matching thread_id and emit `MemoryConfidenceUpdated(reason="archival_decay")` per unpromoted entry. All in surface code, NOT in projection handler.

**A7. Scheduled maintenance timer.** Background task in `app.py` lifespan.

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | conf_alpha, conf_beta on MemoryEntry |
| `src/formicos/core/events.py` | MemoryConfidenceUpdated, union 45->48 |
| `src/formicos/core/ports.py` | add event names |
| `src/formicos/surface/colony_manager.py` | confidence update in _post_colony_hooks |
| `src/formicos/surface/projections.py` | confidence handler |
| `src/formicos/surface/knowledge_catalog.py` | replace _composite_key with Thompson Sampling + freshness (negated, ascending) |
| `src/formicos/surface/memory_store.py` | replace _composite with Thompson Sampling + freshness (positive, reverse=True) |
| `src/formicos/surface/queen_runtime.py` | archive_thread tool + archival decay emission |
| `src/formicos/surface/app.py` | maintenance timer |

---

### Track B -- Workflow Steps + Contradiction Detection + LLM Dedup

**Goal:** Threads gain workflow steps. Contradictions surface. LLM-confirmed dedup resolves the ambiguous band.

**B1. WorkflowStep type.** In `core/types.py`.

**B2. Workflow step events.** `WorkflowStepDefined`, `WorkflowStepCompleted`. Union shared with Track A.

**B3. ThreadProjection gains workflow_steps.** Handlers for step events. In `_on_colony_spawned`, derive step "running" status from optional `step_index` metadata.

**B4. Step completion from colony_manager.** In `_post_colony_hooks()`, check thread for running step assigned to this colony. If found, emit `WorkflowStepCompleted`.

**B5. Queen `define_workflow_steps` tool.** Emits `WorkflowStepDefined` per step. Extends thread context block with step status.

**B6. Step-aware colony spawning.** Include `step_index` in spawn metadata. Projection derives "running".

**B7. Contradiction detection service.** New handler in `maintenance.py`. Skip pairs with empty polarity. Report artifact.

**B8. LLM-confirmed dedup.** Extend dedup handler with Gemini Flash stage. Track dismissed pairs via `MemoryEntryStatusChanged(reason="dedup:dismissed")`.

| File | Action |
|------|--------|
| `src/formicos/core/types.py` | WorkflowStep, WorkflowStepStatus |
| `src/formicos/core/events.py` | WorkflowStepDefined, WorkflowStepCompleted |
| `src/formicos/core/ports.py` | add event names |
| `src/formicos/surface/projections.py` | workflow_steps + handlers + step-colony binding |
| `src/formicos/surface/colony_manager.py` | step completion in _post_colony_hooks |
| `src/formicos/surface/queen_runtime.py` | define_workflow_steps, step-aware spawning, thread context |
| `src/formicos/surface/maintenance.py` | contradiction handler, LLM dedup extension |
| `src/formicos/surface/app.py` | register contradiction handler |

---

### Track C -- Operator Surfaces + Legacy Cleanup

**Goal:** Operator sees confidence, steps, contradictions, health. Legacy files deleted.

**C1. Thread view workflow steps.** Step timeline with status, colony links, artifacts.

**C2. Knowledge browser confidence display.** Beta posterior mean bar with uncertainty width. Last accessed. Stale badge.

**C3. Contradiction report display.** Flagged pairs with dismiss/reject actions.

**C4. Knowledge health summary.** Entries by status, confidence distribution, freshness, domains, last maintenance.

**C5. Legacy deletion.** `skill_lifecycle.py` (surface/), `skill_dedup.py` (adapters/), `skill-browser.ts`, `_crystallize_skills` body.

**C6. Frontend types.** Step, confidence, contradiction interfaces.

**C7. Test parity.** Event count 45 -> 48. Dead reference removal. New tests.

| File | Action |
|------|--------|
| `frontend/src/components/thread-view.ts` | step timeline |
| `frontend/src/components/knowledge-browser.ts` | confidence, contradictions, health |
| `frontend/src/components/colony-detail.ts` | confidence on trace items |
| `frontend/src/types.ts` | new interfaces |
| `src/formicos/surface/skill_lifecycle.py` | DELETE |
| `src/formicos/adapters/skill_dedup.py` | DELETE |
| `frontend/src/components/skill-browser.ts` | DELETE |
| `src/formicos/surface/colony_manager.py` | delete _crystallize_skills body |
| `tests/*` | parity |

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | Dependencies |
|------|-------|-------------|
| Coder 1 | A (Confidence + Thompson) | None |
| Coder 2 | B (Steps + contradiction + LLM dedup) | Track A union expansion |
| Coder 3 | C (Surfaces + legacy cleanup) | Track A confidence, Track B steps |

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `core/types.py` | A (conf), B (WorkflowStep) | Both additive |
| `core/events.py` | A (confidence), B (steps) | All additive. A owns expansion. |
| `projections.py` | A (confidence handler), B (step handlers) | Both additive |
| `colony_manager.py` | A (confidence), B (step completion), C (delete crystallize) | A3 adds confidence block after line 741 (after institutional memory extraction). B4 adds step completion check after A3's block. C deletes `_crystallize_skills` method body (separate method). Explicit ordering: A3 first, B4 second. |
| `queen_runtime.py` | A (archive_thread tool + decay), B (define_workflow_steps + spawning) | Different tool handlers. No overlap. |

---

## Acceptance Criteria

1. Colony succeeds using item X -> X's alpha increments, confidence rises.
2. Colony fails using item Y -> Y's beta increments, confidence drops.
3. MemoryConfidenceUpdated events survive replay.
4. Thompson Sampling: same query returns varying rankings. Uncertain entries occasionally surface.
5. Thread archival (via `archive_thread`) emits MemoryConfidenceUpdated per unpromoted entry. Entries lose confidence. Thread completion (via `complete_thread`) does NOT trigger decay.
6. Workflow steps appear on thread view as checklist.
7. Queen can define steps via tool.
8. Colony completion emits WorkflowStepCompleted from _post_colony_hooks, not projection handler.
9. Contradiction service flags entries with overlapping domains + opposite polarity. Empty polarity skipped.
10. LLM-confirmed dedup: [0.82, 0.98) pairs -> Gemini Flash -> merge or dismiss.
11. Dismissed pairs excluded from future dedup via reason string filter.
12. Scheduled maintenance runs on timer.
13. Knowledge health summary visible.
14. Legacy files deleted. `skill_lifecycle.py` (surface/), `skill_dedup.py` (adapters/), `skill-browser.ts`.
15. Full CI green.

---

## Not In Wave 30

| Item | Reason |
|------|--------|
| Automatic step execution | Wave 31 |
| Agent-directed knowledge exploration | Wave 31 |
| Cross-workspace knowledge | Different scope |

---

## What Wave 31 Becomes (Ship Polish)

Automatic step execution. Agent progressive disclosure. Documentation pass. Performance tuning. Edge case hardening. Onboarding UX. The system is demonstrable, documented, and ready for real users.
