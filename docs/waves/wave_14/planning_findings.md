# Wave 14 Planning Findings

**Date:** 2026-03-14  
**Purpose:** Final repo-accurate hardening of the Wave 14 planning surface after Wave 13 completion.

---

## 1. Main findings

### Wave 14 is still the right contract/mechanics wave

The high-level Wave 14 direction remains sound:
- Wave 13 handled infra, retrieval, and Queen reliability
- Wave 14 can now open the contracts once and land the heavier colony mechanics together

The main risk was not direction. It was stale documentation.

### The earlier Wave 14 drafts still contained repo-map mistakes

The biggest corrections needed were:
- `Runtime.build_agents()` is in `src/formicos/surface/runtime.py`, not `engine/runner.py`
- spawn flow is split across `surface/commands.py` and `surface/runtime.py`
- `surface/colony_manager.py` is lifecycle tracking, not the sole spawn owner
- `colony_manager.inject_message()` does not exist yet and must be created if the service-colony design depends on it

Wave 14 is only dispatchable if the docs keep using the real repo seams consistently.

### The type plan must match the repo

The repo still uses:
- `pydantic.BaseModel`
- `ConfigDict`
- `Field`
- `StrEnum`

So new Wave 14 core types should follow that style.

Using `msgspec.Struct` in docs without a deliberate ADR-level type-system change would be a planning error.

### Wave 14 now needs executable specs

Unlike Wave 13, this wave changes visible behavior and contracts.

The existence of Wave 14 specs is correct. The remaining job is to keep them aligned with the corrected repo map and stream ownership.

### Wave 13 carryover needs to remain explicit

The Wave 14 docs must continue to account for:
- Qdrant sparse/BM25 depending on a real server/image upgrade
- KG visibility depending on Archivist participation
- sync embedding callers still needing an explicit policy decision
- config-driven skill collection naming being the live truth

---

## 2. Contract math

Baseline before Wave 14:
- event union: 27
- Wave 13 added no new events
- ports remain frozen

Wave 14 opening:
- event union: 27 -> 35
- add 8 events:
  - `ColonyChatMessage`
  - `CodeExecuted`
  - `ServiceQuerySent`
  - `ServiceQueryResolved`
  - `ColonyServiceActivated`
  - `KnowledgeEntityCreated`
  - `KnowledgeEdgeCreated`
  - `KnowledgeEntityMerged`
- modify `ColonySpawned`:
  - `caste_names` -> `castes`
  - add `template_id`
- add new types:
  - `SubcasteTier`
  - `CasteSlot`
  - `ChatSender`
  - `ToolCategory`
  - `CasteToolPolicy`

Mirrors that must update:
- `docs/contracts/events.py`
- `docs/contracts/types.ts`
- `frontend/src/types.ts`

Frozen:
- `src/formicos/core/ports.py`
- `docs/contracts/ports.py`

---

## 3. Stream shape

The A/B/C/D stream split still works.

### Stream A: Foundation

This remains the critical path because it owns:
- the `caste_names` -> `castes` migration
- core event additions
- template schema migration
- the initial projection/view/type mirror updates

### Stream B: Safety

This should remain a unified stream because:
- iteration caps
- tool permissions
- budget regime injection
- sandbox execution
- provider cooldown

all form one coherent guardrail layer.

### Stream C: Chat + Services + Frontend

This remains a coherent stream because:
- colony chat
- service-colony routing
- creator/detail/service UI

all depend on the same new mechanics and the same new event families.

### Stream D: Hardening

This should stay narrower:
- KG event emission
- Qdrant BM25 verification after the prerequisite upgrade
- SGLang execution or explicit defer decision

Do not let Stream D become a second feature stream.

---

## 4. CasteSlot migration conclusion

Wave 14 is the correct place for the clean-break migration.

It touches all layers:
- `core/types.py`
- `core/events.py`
- `surface/runtime.py`
- `surface/commands.py`
- `surface/mcp_server.py`
- `surface/colony_manager.py`
- `surface/projections.py`
- `surface/view_state.py`
- `surface/template_manager.py`
- `config/templates/*.yaml`
- `frontend/src/types.ts`
- `docs/contracts/*`
- many tests

That is precisely why it belongs in the wave that is already opening the contracts, not in a quieter infra wave.

---

## 5. Service colonies stay in Wave 14

This still looks correct.

Reason:
- colony chat is already shipping in the same wave
- service colonies mainly add a router, activation flow, and query/response matching
- the incremental scope on top of colony chat is moderate, not wave-breaking

What must stay explicit in the docs:
- the service router is new
- `inject_message()` is new
- the implementation is being introduced, not merely wired to an existing seam

---

## 6. What stays deferred

These still belong after Wave 14:
- experimentation engine
- skill synthesis / meta-skills
- research-colony expansion beyond the service-colony baseline
- semantic/circuit-breaker quality controls more complex than cooldown logic
- any large type-system change unrelated to the Wave 14 mechanics

Wave 14 should not become a grab bag.

---

## 7. Dispatch readiness

Wave 14 is close, but only dispatch-ready if the docs stay aligned on three points:

1. repo-accurate module ownership
2. repo-native type modeling instead of accidental `msgspec` drift
3. explicit merge order for shared-workspace overlaps

If those are clean, the Wave 14 plan is strong enough to dispatch.
