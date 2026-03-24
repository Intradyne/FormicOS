# Wave 51 -- Final Polish / UX Truth

## Theme

Turn the now-working system into a surface that feels intentionally finished.
Wave 51 is judged by what it removes, clarifies, and makes truthful rather than
by how much new substrate it adds.

## Identity Test

Would an operator feel the product is coherent and trustworthy without the
builder in the room to explain it?

## Prerequisite

Wave 50 accepted. Fresh Docker bring-up proven. Local Queen preview/spawn path
working on the local model. Both Wave 51 audits complete.

Relevant audit inputs:

- `docs/waves/wave_51/ui_surface_inventory.md`
- `docs/waves/wave_51/ui_seam_map.md`
- `docs/waves/wave_51/ui_audit_findings.md`
- `docs/waves/wave_51/backend_capability_inventory.md`
- `docs/waves/wave_51/backend_seam_map.md`
- `docs/waves/wave_51/backend_audit_findings.md`

## Contract

- No new backend subsystems
- No new external dependencies
- No wire-contract renames for replay compatibility
- Operator-facing label changes are allowed
- No new event types unless a replay-safety fix genuinely demands one
- Subtractive, not additive

## Governing Tracks

- Track A: Make durable capabilities actually durable, or stop pretending they are
- Track B: Make degraded state visible instead of silent
- Track C: Make the surface speak the current product's language, not its history

## Repo Truth At Wave Start

Wave 50 landed more substrate than the raw UI audit initially reflected. Two
headline UI findings were stale and are explicitly removed from Wave 51 scope:

### Already landed, not Wave 51 work

1. Global promotion substrate is real
- `MemoryEntryScopeChanged` already carries `new_workspace_id`
- projections already set `scope="global"` and clear `workspace_id`
- knowledge promotion already accepts `target_scope="global"`
- retrieval already includes global entries

2. Learned-template enrichment is real
- learned-template additive fields already exist on `ColonyTemplateCreated`
- `TemplateProjection` already carries learned metadata and success/failure counts
- `load_all_templates()` already merges operator YAML templates with learned templates

3. Streaming fallback is a real gap but not a Wave 51 fit
- `complete()` has fallback support
- `stream()` does not
- this is runtime/reliability work, not final polish

Wave 51 therefore focuses on confirmed trust debt:

- replay-safety seams near the Queen/operator surface
- visible degraded-state behavior
- stale or misleading vocabulary and affordances
- dead code and deprecated surface cleanup
- canonical replay-safety / capability truth documentation

---

## Track A -- Capability Truth / Replay Safety

### A1. Fix `escalate_colony` replay safety

Current truth:
- `escalate_colony` mutates `colony.routing_override` directly on the in-memory
  projection
- no event is emitted
- escalation disappears on restart and replay

Why it matters:
- this is a shipped, operator-visible capability
- FormicOS's product identity is replay-safe truth
- restart-loss of an operator action is exactly the kind of trust break this
  wave exists to remove

Implementation direction:
- prefer encoding escalation in replay-safe event truth
- if an existing event can safely carry the override semantics, use it
- if not, this is the one justified exception to the "no new event types"
  rule and should come with an ADR

### A2. Fix Queen note persistence without leaking private notes into visible chat

Current truth:
- `save_queen_note` stores notes in the Queen's in-memory `thread_notes`
- `queen_note` persists notes to YAML files per thread
- neither path is event-sourced

Why it matters:
- thread notes are part of the Queen's working context
- losing them on restart makes the system forget operator-authored thread
  guidance in a way the operator cannot predict

Implementation direction:
- persist notes through a replay-safe event path
- do not casually turn internal thread notes into ordinary visible
  `QueenMessage` chat rows
- prefer a dedicated hidden note event or an explicitly non-chat thread-note
  projection path
- YAML may remain as backup/export, but not as the source of truth

### A5. Fix or explicitly classify `dismiss-autonomy`

Current truth:
- dismissals live in overlay memory only
- restart clears them

Wave 51 decision:
- either make dismissals replay-safe
- or label them honestly as ephemeral/session-only

The important thing is to remove ambiguity, not to force durability where the
product does not need it.

### A7. Wire proactive briefing domain override actions

Current truth:
- the backend endpoint exists
- briefing surfaces trust state
- the operator cannot act inline from the briefing view

Wave 51 goal:
- make the visible capability actually reachable from the surface that already
  displays it

This is interaction-truth work, not new backend invention.

---

## Track B -- Visible Degraded State

### B1. Config-memory must show failed sections as unavailable

Current truth:
- multiple fetches can fail independently
- failed sections disappear into partial silence

Wave 51 goal:
- missing data must not masquerade as complete data
- failed sections should render muted "unavailable" state rather than vanish

### B2. Queen overview should show no-data / unavailable states

Current truth:
- federation and outcomes sections can silently disappear on failure

Wave 51 goal:
- absence should be explained
- render a small explicit placeholder instead of hiding the section

### B3. Model / protocol freshness should be visible

Current truth:
- model and protocol status are snapshot-heavy
- long-lived sessions can show stale information

Wave 51 goal:
- show freshness truth directly in the UI
- add "last updated" / stale-state visibility
- if periodic refresh is cheap, prefer that over a purely cosmetic stale badge

---

## Track C -- Vocabulary / Surface Coherence

### C1. Remove dead code: `fleet-view.ts`

Current truth:
- the component is no longer rendered
- retaining it only increases maintenance surface

Wave 51 goal:
- delete dead surface code rather than keeping decorative archaeology around

### C2. Rename operator-facing "Skill Bank" labels

Current truth:
- internal store/wire contracts still use `skillBankStats`
- operator-facing language should describe the current product, not older
  internal naming

Wave 51 goal:
- rename display labels to "Knowledge"
- leave the underlying contract untouched for replay compatibility

### C3. Rename "Config Memory"

Current truth:
- the surface now combines recommendations, overrides, and templates
- "Config Memory" is historically understandable but operator-ambiguous

Wave 51 goal:
- use a clearer surface label such as "Configuration" or
  "Config Intelligence"

### C4. Deprecate Memory API properly

Current truth:
- deprecated endpoints still serve
- frontend no longer uses them

Wave 51 goal:
- add `Sunset` headers
- add usage logging so future removal is evidence-based, not guessed

### C5. Consolidate duplicate config-override routes

Current truth:
- two routes reach the same event with different parameter names

Wave 51 goal:
- reduce capability ambiguity by documenting or consolidating to one canonical
  path

### C6. Create canonical replay-safety documentation

Current truth:
- the backend audit produced the first coherent replay-safety classification
- no canonical repo doc currently says which capabilities are:
  - event-sourced / durable
  - file-backed / external
  - in-memory / restart-lost
  - intentionally ephemeral

Wave 51 goal:
- create `docs/REPLAY_SAFETY.md`
- make durability truth explicit for operators and contributors

This is a central Wave 51 deliverable, not optional docs polish.

### C7. Mark frozen / legacy event types honestly

Current truth:
- some event types remain for replay compatibility only

Wave 51 goal:
- add clear comments where these remain intentionally frozen
- preserve replay compatibility without implying active behavioral use

### C8. Document the Memory / Knowledge naming bridge

Current truth:
- backend historical names say "Memory"
- operator-facing product language says "Knowledge"

Wave 51 goal:
- explain the bridge once in docs instead of leaving every operator and coder
  to infer it separately

### C9. Make strategy pills visually inert

Current truth:
- strategy pills look interactive
- they are not interactive

Wave 51 goal:
- remove false affordance
- style them as labels, not controls

---

## Priority Order

1. A1 -- `escalate_colony` replay safety
2. A2 -- Queen note replay safety
3. C6 -- `docs/REPLAY_SAFETY.md`
4. B1 -- Config-memory degraded-state visibility
5. C9 -- Inert strategy-pill styling
6. A7 -- Briefing domain override actions
7. C1 -- Remove `fleet-view.ts`
8. C4 -- Deprecated Memory API `Sunset` + usage logging
9. A5 -- `dismiss-autonomy` replay-safe or explicitly ephemeral
10. B2 -- Queen overview no-data states
11. B3 -- Model/protocol freshness visibility
12. C2 -- Operator-facing "Knowledge" labels
13. C3 -- Rename "Config Memory"
14. C5 -- Duplicate config-override route cleanup
15. C7 -- Frozen-event comments
16. C8 -- Memory/Knowledge mapping note

---

## Team Split

### Team 1 -- Replay Safety + Backend Truth

Owns:
- escalation durability
- note durability
- deprecated API signaling
- config-route cleanup
- replay-safety docs and tests

Primary files:
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/commands.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/routes/memory_api.py`
- `src/formicos/surface/routes/api.py`
- `docs/REPLAY_SAFETY.md`

### Team 2 -- Surface Truth + Visible Degradation

Owns:
- unavailable-state rendering
- freshness indicators
- inline briefing controls
- inert settings affordances
- dead UI removal
- operator-facing label cleanup

Primary files:
- `frontend/src/components/config-memory.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/proactive-briefing.ts`
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/components/fleet-view.ts`
- `frontend/src/state/store.ts`

### Team 3 -- Vocabulary + Docs Truth

Owns:
- final naming/doc alignment
- operator-facing docs updates
- frozen-event documentation
- wave packet refresh after implementation

Primary files:
- `CLAUDE.md`
- `AGENTS.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/waves/wave_51/*`

---

## Overlap Risks To Watch

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `docs/REPLAY_SAFETY.md`

These seams should be integrated carefully because they affect both
implementation truth and documentation truth.

---

## Out Of Scope

- No new learning substrate
- No rework of global promotion or learned-template enrichment already landed in Wave 50
- No streaming fallback work in `runtime.py`
- No visual redesign detached from seam truth
- No prompt-optimization wave
- No provider expansion
- No wire-contract renames

---

## Smoke Intent

Wave 51 is complete when all of the following feel true:

1. Restart does not silently drop escalation or Queen note state
2. Degraded sections say they are degraded
3. Inert controls no longer pretend to be configurable
4. Dead surface code is gone
5. Operator-facing language reads as present-tense product truth
6. Replay-safety classification is documented and trustworthy
7. Previously stale findings from the audits remain correctly treated as landed,
   not re-broken or hidden

## After Wave 51

If Wave 51 succeeds, the next work should not be another polish wave by
default. The next step should be Phase 0 measurement: prove the compounding
curve with the now-trustworthy local, replay-safe, chat-first product surface.
