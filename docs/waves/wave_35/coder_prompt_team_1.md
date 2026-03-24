# Wave 35 Team 1 — Queen Parallel Planner + Decision Explanations

## Role

You are building multi-colony orchestration: the Queen gains a DelegationPlan model, generates DAG-based parallel colony groups, dispatches them concurrently, and explains her decisions using system evidence. This is the headline Wave 35 capability.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/045-event-union-parallel-distillation.md` (ADR-045) for the ParallelPlanCreated event schema.
- Read `docs/decisions/046-autonomy-levels.md` (ADR-046) for context on how self-maintenance will consume parallel planning (Team 2 builds that — you don't need to accommodate it).
- The event union goes from 53 to 54 concrete types with ParallelPlanCreated. KnowledgeDistilled (55th) is Team 2's responsibility.
- You run in parallel with Teams 2 and 3. No dependencies between teams.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `core/types.py` | MODIFY | DelegationPlan, ColonyTask models (add after line 696, before `__all__`) |
| `core/events.py` | MODIFY | ParallelPlanCreated event (54th type), update EVENT_TYPE_NAMES + self-check |
| `surface/queen_runtime.py` | MODIFY | Parallel plan generation, concurrent spawn dispatch, convergence check, decision explanations |
| `config/caste_recipes.yaml` | MODIFY | Queen prompt: parallel planning section, decision explanation section |
| `surface/projections.py` | MODIFY | ParallelPlanCreated handler (store plan on thread projection) |
| `surface/event_translator.py` | MODIFY | PARALLEL_PLAN AG-UI event promotion |
| `frontend/src/components/workflow-view.ts` | MODIFY | DAG visualization for parallel groups |
| `tests/unit/surface/test_parallel_planning.py` | CREATE | Plan validation, concurrent dispatch, convergence |
| `tests/unit/core/test_events_55.py` | CREATE | New event deserialization + replay |

## DO NOT TOUCH

- `surface/self_maintenance.py` — Team 2 creates
- `surface/proactive_intelligence.py` — Team 2 modifies (SuggestedColony)
- `surface/maintenance.py` — Team 2 modifies (distillation)
- `surface/knowledge_catalog.py` — Team 3 modifies (score rendering, per-workspace weights)
- `surface/knowledge_constants.py` — Team 3 modifies (per-workspace weight lookup)
- `engine/runner.py` — Team 3 modifies (directive injection)
- `surface/mcp_server.py` — Team 2 + Team 3 modify
- `surface/colony_manager.py` — Team 3 modifies (mastery restoration)
- All integration test files — Validation track owns
- All documentation — Validation track owns

## Overlap rules

- `core/types.py`: Teams 2 and 3 also add models. You add DelegationPlan and ColonyTask. Team 2 adds AutonomyLevel and MaintenancePolicy. Team 3 adds OperatorDirective and DirectiveType. All are independent classes at the end of the file (before `__all__`). Add yours after the existing ValidationFeedback (line 696), before `__all__`.
- `core/events.py`: You add ParallelPlanCreated (54th event). Team 2 adds KnowledgeDistilled (55th). Add yours first in EVENT_TYPE_NAMES — Team 2 appends after.

---

## A1. Queen parallel planner (DelegationPlan with DAG)

### What

The Queen currently plans one colony, watches it complete, plans the next. For complex goals, independent subtasks serialize unnecessarily. The Queen gains a DelegationPlan model: a DAG of ColonyTasks organized into parallel groups, dispatched concurrently.

### Models (in core/types.py)

```python
class ColonyTask(BaseModel):
    task_id: str
    task: str
    caste: str                         # "coder" | "reviewer" | "researcher" | "archivist"
    strategy: str                      # "sequential" | "stigmergic"
    max_rounds: int = 5
    budget_limit: float = 1.0
    depends_on: list[str] = []         # task_ids that must complete first
    input_from: list[str] = []         # colony_ids to chain output from

class DelegationPlan(BaseModel):
    reasoning: str                     # free-form planning rationale
    tasks: list[ColonyTask]
    parallel_groups: list[list[str]]   # task_ids that can run simultaneously
    estimated_total_cost: float
    knowledge_gaps: list[str]          # domains where briefing flagged issues
```

### Implementation in queen_runtime.py

The Queen's tool-calling loop already iterates: receive message -> reason -> emit tool calls -> observe results -> repeat. Multi-colony orchestration changes the tool-calling pattern, not the loop structure.

**Phase 1 — Plan generation:** When the Queen decides to decompose a goal, she generates a DelegationPlan via structured output (the plan is part of her reasoning, not a tool call). Validate:
- No circular dependencies (topological sort succeeds)
- All `depends_on` references exist in `tasks`
- `parallel_groups` cover all task_ids exactly once

**Phase 2 — Plan emission:** Emit `ParallelPlanCreated` event with the validated plan. Store on thread projection.

**Phase 3 — Concurrent dispatch:** For each parallel group in order:
1. Spawn all colonies in the group via concurrent `asyncio.gather` on `spawn_colony` calls
2. Wait for all colonies in the group to complete (poll or await)
3. For each completed colony, collect output via `read_colony_output`
4. Feed outputs to the next group (colonies with `input_from` get prior outputs injected)

**Phase 4 — Convergence:** After the final group completes, the Queen reviews all results and decides: accept the combined work, spawn a follow-up colony, or re-plan.

**Key insight:** This doesn't require a new execution engine. The existing `asyncio.create_task` infrastructure handles concurrent colony execution. The Queen's change is prompt-driven: she generates a plan, then emits multiple spawn_colony calls per iteration instead of one.

### Fallback

If the Queen generates an invalid plan (circular deps, missing references), log a warning and fall back to sequential execution (one colony at a time, existing behavior). Never block the operator on a planning failure.

---

## A2. ParallelPlanCreated event

### Schema (in core/events.py)

```python
class ParallelPlanCreated(EventEnvelope):
    type: Literal["ParallelPlanCreated"] = "ParallelPlanCreated"
    thread_id: str
    workspace_id: str
    plan: dict[str, Any]              # serialized DelegationPlan
    parallel_groups: list[list[str]]
    reasoning: str
    knowledge_gaps: list[str]
    estimated_cost: float
```

Add to EVENT_TYPE_NAMES and the self-check at the end of events.py.

### Projection handler (in projections.py)

Store the plan on the thread projection:
```python
def _on_parallel_plan_created(self, event):
    thread = self.threads.get(event.thread_id)
    if thread:
        thread["active_plan"] = event.plan
        thread["parallel_groups"] = event.parallel_groups
```

### AG-UI promotion (in event_translator.py)

Emit a PARALLEL_PLAN custom event containing the parallel_groups and reasoning. The frontend workflow-view.ts renders this as a DAG.

---

## A4. Queen decision explanations

### What

The Queen already produces reasoning when spawning colonies. Wave 35 enriches this with system-grounded reasoning that references the proactive briefing and score breakdowns.

### Queen prompt additions (in caste_recipes.yaml)

Add after the existing "Before spawning a colony" section from Wave 34:

```
## Explaining your decisions
When you spawn a colony or make a strategic choice, explain WHY using
system evidence:
- "Chose coder+reviewer because memory_search returned 3 HIGH entries
  for Python API patterns (no knowledge gap)."
- "Spawning research colony first because the briefing flagged a
  contradiction on error handling. Resolving before implementation
  prevents wasted work."
- "Running research and schema colonies in parallel -- they have no
  data dependency. Research results will feed into the implementation
  colony (Group 2, input_from=research)."

When generating a DelegationPlan:
- State why tasks are grouped in parallel vs sequential
- Reference knowledge gaps from the briefing
- Include estimated cost and explain if it exceeds the typical range
```

### Constraints

- Stay under 130 lines total for the Queen prompt (currently 110-120 from Wave 34).
- The explanation is stored in DelegationPlan.reasoning and emitted in ParallelPlanCreated.

---

## Tests

### Parallel planning
- Valid plan with 2 groups: group 1 runs in parallel, group 2 after
- Invalid plan (circular deps): falls back to sequential
- Invalid plan (missing depends_on): falls back to sequential
- Plan with single task: no parallelism, works identically to pre-Wave-35
- Concurrent spawn: multiple colonies started within same iteration

### Event
- ParallelPlanCreated deserializes correctly
- Projection handler stores plan on thread
- Replay produces identical plan state
- AG-UI event promotion includes parallel_groups

### Queen prompt
- Contains "DelegationPlan" or "parallel"
- Contains "Explaining your decisions"
- Under 130 lines total

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
