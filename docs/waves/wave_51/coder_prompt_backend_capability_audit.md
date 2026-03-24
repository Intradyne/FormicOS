Wave 51 — Backend Capability Audit Prompt

Mission:
Produce a full backend capability audit of the current FormicOS surface/API and
write the audit context back into `docs/waves/wave_51/` as durable seam
documentation.

This is an audit/documentation track, not a feature wave.

Primary question:
What capabilities actually exist on the backend today; how are they exposed
(REST, websocket command, Queen tool, operator route, replay-derived state);
what contracts do they assume; and which capabilities are shipped, partial,
frozen, hidden, duplicated, deprecated, or misleadingly named?

Current repo truth to trust:
- event and type truth lives under:
  - `src/formicos/core/events.py`
  - `src/formicos/core/types.py`
  - `src/formicos/core/ports.py`
- surface runtime and command seams live under:
  - `src/formicos/surface/runtime.py`
  - `src/formicos/surface/commands.py`
  - `src/formicos/surface/ws_handler.py`
  - `src/formicos/surface/routes/**`
  - `src/formicos/surface/queen_tools.py`
  - `src/formicos/surface/projections.py`
  - `src/formicos/surface/view_state.py`
- API/UI contract docs already exist in:
  - `docs/contracts/events.py`
  - `docs/contracts/types.ts`

Your job:
Audit what the backend can actually do today and produce docs that make the
capability surface, seams, and truth gaps legible before Wave 51 planning.

Owned files:
- `src/formicos/core/events.py`
- `src/formicos/core/types.py`
- `src/formicos/core/ports.py`
- `src/formicos/surface/runtime.py`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/ws_handler.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/routes/**`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/view_state.py`
- docs you create under `docs/waves/wave_51/`

Do not touch:
- runtime behavior unless you find a tiny factual docs-blocking typo
- frontend redesign
- new features or event types
- unrelated cleanup outside `docs/waves/wave_51/`

Required outputs

1. Create `docs/waves/wave_51/backend_capability_inventory.md`
- inventory the meaningful backend/operator capabilities
- group by exposure type:
  - websocket commands
  - REST routes
  - Queen tools
  - runtime services/internal capabilities surfaced to operator paths
  - replay/snapshot/projection capabilities
- for each capability capture at minimum:
  - name
  - owning file/function
  - exposure surface
  - required inputs
  - primary outputs/events/state effects
  - source of truth:
    - direct event
    - projection-derived
    - runtime-only
    - API wrapper
  - current status:
    - shipped
    - partial
    - hidden
    - frozen compatibility path
    - deprecated/stale

2. Create `docs/waves/wave_51/backend_seam_map.md`
- map the important backend seams end to end
- at minimum include:
  - websocket command -> handler -> runtime -> emitted events -> projection/view-state
  - REST route -> handler -> runtime/store/projection
  - Queen tool -> dispatcher/tool implementation -> runtime/events
  - state snapshot path -> projections/view_state -> frontend consumption assumptions
  - memory/knowledge path
  - template/config memory path
  - provider/router capability path

3. Create `docs/waves/wave_51/backend_audit_findings.md`
- findings first, ordered by severity
- focus on:
  - routes/commands that exist but are not surfaced clearly
  - duplicated or overlapping capability seams
  - stale/deceptive names
  - partial capabilities exposed as if complete
  - replay/snapshot mismatches
  - UI contract mismatches
  - compatibility/frozen paths still present in the surface
- include file references and short evidence
- separate:
  - blockers
  - substrate-truth debt
  - surface-truth debt
  - runtime/deployment debt
  - docs debt

Audit method

Track A: Capability inventory
- enumerate:
  - websocket actions from `commands.py`
  - REST endpoints from `routes/`
  - Queen tools from `queen_tools.py`
  - major runtime operator methods in `runtime.py`
  - replay/snapshot builders in `projections.py` and `view_state.py`

Track B: Contract and exposure audit
- for each major capability, determine:
  - who can call it
  - how it is named at each layer
  - whether the name stays stable across seams
  - whether output is event truth, route truth, or projection truth

Track C: Hidden and frozen paths
- identify capabilities that still exist for:
  - backward compatibility
  - legacy/frozen extraction paths
  - old collections/routes/aliases
  - operator/MCP-only maintenance surfaces
- document whether they should remain visible or be treated as internal compatibility seams

Track D: Replay/state truth audit
- identify where the backend depends on:
  - event truth
  - replay-derived projections
  - view-state snapshots
  - runtime-only ephemeral state
- call out any seams where “capability exists” does not mean “replay-safe and UI-truthful”

Track E: Naming and capability taxonomy
- produce a recommended grouping/taxonomy in the docs:
  - orchestration
  - knowledge
  - templates/config memory
  - governance
  - maintenance/config
  - deployment/runtime health
- note where current names obscure that taxonomy

Hard constraints
- This track is about audit truth, not refactoring
- Prefer source inspection over assumptions
- Do not claim a capability is operator-real unless you can trace its exposure seam
- Distinguish clearly between:
  - backend substrate truth
  - exposed operator capability
  - replay-safe capability

Validation
Run at minimum:
1. `rg -n "^async def _handle_|^def _handle_|^class .*Router|@router\\.|tool_specs\\(|__all__|EVENT_TYPE_NAMES" src/formicos`
2. `python scripts/lint_imports.py`
3. If you add helper scripts or touch Python files, keep changes docs-only unless a tiny factual correction is unavoidable

Summary must include
- exact docs files created
- total websocket commands inventoried
- total REST routes inventoried
- total Queen tools inventoried
- the top 10 findings
- which capabilities are clearly replay-safe and operator-real
- which capabilities are partial/hidden/frozen compatibility seams
