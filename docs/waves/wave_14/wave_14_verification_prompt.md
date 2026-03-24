# Wave 14 Documentation Verification Prompt

You are verifying the Wave 14 documentation set for FormicOS before coder dispatch.

Working directory: C:\Users\User\FormicOSa

This is a review task only. Do not write code.

## What changed in the latest hardening pass

The Wave 14 docs were revised to correct three major problems:

1. Repo-map drift
- `Runtime.build_agents()` is in `src/formicos/surface/runtime.py`, not `engine/runner.py`
- spawn flow crosses `surface/commands.py` and `surface/runtime.py`
- `colony_manager.inject_message()` is a proposed new method, not an existing seam

2. Type-style drift
- older drafts used `msgspec.Struct` examples
- the repo actually uses Pydantic models and `StrEnum` in `src/formicos/core/types.py`
- the docs were rewritten to match the repo-native style

3. Shared-workspace execution risk
- root `AGENTS.md` was rewritten for Wave 14
- overlap-prone files now have explicit merge order
- the four Wave 14 feature specs were moved into `docs/specs/`

## Docs to verify

Read in this order:

1. `AGENTS.md`
2. `docs/waves/wave_14/plan.md`
3. `docs/waves/wave_14/algorithms.md`
4. `docs/waves/wave_14/planning_findings.md`
5. `docs/decisions/020-casteslot-clean-break.md`
6. `docs/decisions/021-qdrant-upgrade-bm25.md`
7. `docs/decisions/022-budget-regime-injection.md`
8. `docs/decisions/023-caste-tool-permissions.md`
9. `docs/decisions/024-provider-cooldown.md`
10. `docs/specs/wave_14_safety.feature`
11. `docs/specs/wave_14_sandbox.feature`
12. `docs/specs/wave_14_colony_chat.feature`
13. `docs/specs/wave_14_service_colonies.feature`

Then check the live repo files:
- `src/formicos/core/types.py`
- `src/formicos/core/events.py`
- `src/formicos/engine/context.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/mcp_server.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/view_state.py`
- `src/formicos/adapters/vector_qdrant.py`
- `docker-compose.yml`

## Specific checks

### 1. Repo-map accuracy

Confirm:
- `build_agents()` is in `surface/runtime.py`
- the round execution loop is in `engine/runner.py`
- there is no existing `colony_manager.spawn()` that owns all spawn behavior
- there is no existing `colony_manager.inject_message()` before Wave 14
- the plan's file ownership matches the real seams

### 2. Type-plan accuracy

Confirm:
- `core/types.py` still uses Pydantic/`StrEnum`
- the Wave 14 docs now match that style
- no lingering `msgspec` assumption remains in the main Wave 14 docs

### 3. Contract math

Confirm:
- live baseline before Wave 14 is 27 events
- the docs add 8 events, ending at 35
- `core/ports.py` remains frozen
- the mirror update list is complete

### 4. Spec quality

Confirm:
- the four Wave 14 specs are concrete enough to be useful
- the scenarios match the plan's stream ownership
- nothing in the specs contradicts the corrected repo map

### 5. Wave 13 carryover realism

Confirm the docs handle these explicitly:
- Qdrant sparse/BM25 still depends on a real server/image upgrade
- KG visibility still depends on Archivist participation
- sync embedding callers still need an explicit Wave 14 decision
- live skill-bank collection naming is config-driven

## Useful commands

```bash
rg -n "build_agents" src/formicos/surface/runtime.py src/formicos/engine/runner.py
rg -n "class LLMRouter" src/formicos/surface/runtime.py
rg -n "inject_message" src/formicos/surface/colony_manager.py
rg -n "models.Document" src/formicos/adapters/vector_qdrant.py
rg -n "qdrant" docker-compose.yml
rg -n "msgspec" AGENTS.md docs/waves/wave_14 docs/decisions/020-casteslot-clean-break.md docs/decisions/021-qdrant-upgrade-bm25.md docs/decisions/022-budget-regime-injection.md docs/decisions/023-caste-tool-permissions.md docs/decisions/024-provider-cooldown.md
```

## Report format

Respond in these sections:

1. File paths confirmed correct
2. File paths still wrong
3. Spec assessment
4. AGENTS assessment
5. ADR assessment
6. Contract math check
7. Wave 13 carryover check
8. Dispatch readiness
9. Anything else
