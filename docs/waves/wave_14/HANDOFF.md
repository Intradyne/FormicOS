# Wave 14 Documentation Handoff

**Date:** 2026-03-14  
**Status:** Dispatch-ready after final verification pass

---

## What was verified against the live repo

I read the actual source files via filesystem access. Here is what I confirmed.

### build_agents() location: correct in docs

- `Runtime.build_agents()` is in `src/formicos/surface/runtime.py`
- `Runtime.spawn_colony()` is also in that file and still takes `caste_names: list[str]`
- `engine/runner.py` contains `RoundRunner` and the round loop; it does not build agents
- the Wave 14 docs now correctly target `surface/runtime.py` for Stream A

### Type system: correct in docs

- `core/types.py` uses `pydantic.BaseModel`, `ConfigDict`, `Field`, and `StrEnum`
- `core/events.py` uses `pydantic.BaseModel` subclasses of `EventEnvelope`
- the Wave 14 docs now specify repo-native Pydantic/`StrEnum` modeling instead of `msgspec`

### ColonySpawned current shape: confirmed

```python
class ColonySpawned(EventEnvelope):
    type: Literal["ColonySpawned"] = "ColonySpawned"
    thread_id: str
    task: str
    caste_names: list[str]
    model_assignments: dict[str, str]
    strategy: CoordinationStrategyName
    max_rounds: int
    budget_limit: float
```

### template_manager.py: confirmed existing module

- `src/formicos/surface/template_manager.py` already exists from Wave 11
- it still uses `caste_names`
- the Wave 14 docs now correctly describe this as a migration/edit, not a greenfield module

### runner.py tool dispatch: confirmed

- `_execute_tool()` is the correct insertion point for Stream B permission checks
- Stream B extends dispatch for `code_execute`
- Stream C adds service-response detection in a different part of the runner flow

### LLMRouter.route(): confirmed current seam

```python
def route(self, caste, phase, round_num, budget_remaining, default_model) -> str
```

Stream A adds a `tier` parameter. Stream B adds cooldown helpers as separate methods.

---

## Corrections made in this pass

| File | Change |
|---|---|
| `docs/waves/wave_14/plan.md` | Status set to `Dispatch-ready`. Step 9 corrected from new module to existing module migration. |
| `AGENTS.md` | Same template-manager correction. |
| `docs/waves/wave_14/algorithms.md` | Module map and migration step corrected for existing `template_manager.py`. |

---

## Verification summary

| Check | Result |
|---|---|
| `build_agents()` in correct file | PASS |
| `engine/runner.py` not touched by Stream A | PASS |
| Type system matches repo | PASS |
| Event-envelope pattern matches repo | PASS |
| `template_manager.py` correctly described as existing | PASS |
| `colony_manager.inject_message()` marked as new | PASS |
| Specs align with plan stream ownership | PASS |
| ADRs 020-024 still hold | PASS |
| Wave 13 residuals addressed in pre-reqs | PASS |

---

## Remaining items

None of these are blockers:

1. Qdrant version confirmation
- ADR-021 treats the Qdrant upgrade as a real pre-req.
- The exact image/version should remain grounded in official Qdrant support for the sparse BM25 path.

2. Sync embedding policy
- Stream B still needs to measure and document the sidecar-vs-MiniLM decision for remaining sync callers.

3. Event-envelope implementation details
- Stream A should follow the existing `EventEnvelope` / `Literal["EventName"]` pattern in `core/events.py`.

---

## Dispatch readiness

Yes. The Wave 14 documentation set is dispatch-ready.

Dispatch set:
- `docs/waves/wave_14/plan.md`
- `docs/waves/wave_14/algorithms.md`
- `docs/waves/wave_14/planning_findings.md`
- `docs/waves/wave_14/HANDOFF.md`
- `AGENTS.md`
- `docs/decisions/020-casteslot-clean-break.md`
- `docs/decisions/021-qdrant-upgrade-bm25.md`
- `docs/decisions/022-budget-regime-injection.md`
- `docs/decisions/023-caste-tool-permissions.md`
- `docs/decisions/024-provider-cooldown.md`
- `docs/specs/wave_14_safety.feature`
- `docs/specs/wave_14_sandbox.feature`
- `docs/specs/wave_14_colony_chat.feature`
- `docs/specs/wave_14_service_colonies.feature`
- `docs/prototype/formicos-v3.jsx`
