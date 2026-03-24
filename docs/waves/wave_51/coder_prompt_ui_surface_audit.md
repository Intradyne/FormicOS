Wave 51 — UI Surface Audit Prompt

Mission:
Produce a full operator-surface audit of the current frontend UI and write the
audit context back into `docs/waves/wave_51/` as durable seam documentation.

This is an audit/documentation track, not a feature wave.

Primary question:
What buttons, badges, menus, toggles, forms, settings, cards, and navigation
affordances exist in the shipped UI today; what do they call; what state do
they depend on; what contract fields do they assume; and which surfaces are
truthful, stale, partial, duplicated, confusing, or decorative?

Current repo truth to trust:
- frontend components live under `frontend/src/components/`
- state and websocket flow live under:
  - `frontend/src/state/store.ts`
  - `frontend/src/ws/client.ts`
  - `frontend/src/types.ts`
- backend command and API seams most relevant to UI behavior live under:
  - `src/formicos/surface/ws_handler.py`
  - `src/formicos/surface/commands.py`
  - `src/formicos/surface/routes/`
- current major operator surfaces include:
  - Queen chat / overview
  - colony detail / thread detail
  - knowledge browser
  - config memory
  - settings / model registry / playbook / workflow views

Your job:
Audit the UI as it actually exists today and produce durable docs that make the
surface seams easy to reason about before new Wave 51 work begins.

Owned files:
- `frontend/src/components/**`
- `frontend/src/state/store.ts`
- `frontend/src/types.ts`
- `frontend/src/ws/client.ts`
- `src/formicos/surface/ws_handler.py`
- `src/formicos/surface/commands.py`
- `src/formicos/surface/routes/**`
- docs you create under `docs/waves/wave_51/`

Do not touch:
- product behavior unless you find a tiny factual docs-blocking typo
- wave plans outside `docs/waves/wave_51/`
- backend architecture
- unrelated test cleanup
- broad UI redesign

Required outputs

1. Create `docs/waves/wave_51/ui_surface_inventory.md`
- inventory every operator-visible control and status surface you can find
- group by major surface, for example:
  - Queen / chat-first
  - colony detail
  - thread/workflow
  - knowledge
  - settings / models / playbook
- for each item capture at minimum:
  - label or visible name
  - component file
  - user intent
  - event/API/command target
  - state inputs / contract fields
  - current status:
    - truthful
    - partial
    - stale
    - duplicated
    - unclear
    - decorative

2. Create `docs/waves/wave_51/ui_seam_map.md`
- map the important frontend seams end to end
- at minimum include:
  - component -> event handler -> store/ws/api -> backend command/route
  - preview/result card seams
  - Queen chat seams
  - knowledge browser seams
  - settings/config seams
  - navigation seams
- call out where UI uses:
  - websocket commands
  - REST endpoints
  - snapshot-only state
  - replay-derived metadata
  - optimistic local assumptions

3. Create `docs/waves/wave_51/ui_audit_findings.md`
- findings first, ordered by severity
- focus on:
  - dead or misleading buttons
  - duplicated actions
  - stale labels
  - badges that imply false substrate truth
  - menus/settings that do not map clearly to backend capability
  - controls with missing scroll/overflow/layout affordances
  - controls whose labels encode old vocabulary
- include file references and short evidence
- separate:
  - blockers
  - surface-truth debt
  - docs debt
  - tuning/polish debt

Audit method

Track A: Inventory the visible UI
- enumerate all clickable/operator-settable UI affordances:
  - buttons
  - pills/badges with action semantics
  - dropdowns/selects
  - toggles
  - menu actions
  - tabs
  - settings inputs
  - inline card actions

Track B: Trace each affordance to its seam
- for each significant control, trace:
  - component method
  - emitted custom event or direct fetch/store call
  - receiving component/store/client
  - backend command or route
  - event/projection/state fields used to render result

Track C: Identify stale vocabulary and implied truth mismatches
- call out wording that refers to:
  - removed features
  - frozen compatibility paths
  - old wave terminology
  - misleading cloud/local labels
  - duplicated actions with different names

Track D: Audit layout truth
- identify views where:
  - the intended inner pane does not scroll
  - content escapes the viewport
  - sticky headers/controls hide state
  - mobile/desktop assumptions are inconsistent
- document these as UI seam findings even if you do not patch them

Track E: Settings and menus truth
- inventory all settings/config surfaces and map:
  - where the value comes from
  - whether it is persisted
  - which backend field/event/route owns it
  - whether it is advisory only or actually active

Hard constraints
- This track is about audit truth, not redesign
- Prefer direct evidence from code over inference
- Do not claim a control works unless you can trace its seam
- If a control appears to work only because of stale state or optimistic UI,
  call that out explicitly

Validation
Run at minimum:
1. `rg -n "dispatchEvent|fetch\\(|store\\.send\\(|@click=|@change=|@input=|@submit=" frontend/src/components frontend/src/state frontend/src/ws`
2. `cd frontend; npm run build`
3. If you add helper scripts or touch TS files, keep changes docs-only unless a tiny factual correction is unavoidable

Summary must include
- exact docs files created
- how you grouped the UI surfaces
- the top 10 findings
- the highest-risk seam mismatches
- which controls are clearly truthful today
- which labels/vocabulary should probably change before more UI work
