# Wave 52 -- The Coherent Colony

**Theme:** Make the system describe itself consistently and cash in its own
intelligence more evenly. Two bounded packets: control-plane truth first, then
intelligence reach plus two small features that make the learning loop visible.

**Identity test:** Would an external integrator trust the protocol surface?
Would a returning operator notice the system got smarter since last time?

**Prerequisite:** Wave 51 accepted. Stack proven. Wave 52 seam audits complete.

**Contract:**
- No new event types
- No new external dependencies
- No new backend subsystems
- No protocol expansion
- Packet A changes description truth, not core behavior
- Packet B changes wiring plus two bounded features using existing substrate

## Repo Truth At Wave Start

- Version truth is forked:
  - `pyproject.toml`: `2.0.0a1`
  - `src/formicos/__init__.py`: package version constant
  - `src/formicos/surface/app.py`: `0.21.0`
  - `src/formicos/surface/routes/protocols.py`: `0.22.0`
- Actual event union count is **64**.
- The colony runner already hardens tool-result feedback with untrusted-data
  wrapping, per-result truncation, and oldest-first history compaction.
- The Queen tool loop does not yet have that same prompt-boundary protection.
- `retrieve_relevant_memory()` supports `thread_id`, but the Queen path does
  not currently pass it.
- A2A still imports `load_templates` (disk only).
- Queen tools already use `load_all_templates(... projection_templates=...)`.
- A2A already passes a per-colony `budget_limit` from template/classifier selection.
- AG-UI passes no `budget_limit` and silently falls back to the runtime default of `5.0`.
- Neither A2A nor AG-UI currently uses the Queen-style workspace spawn gate
  via `BudgetEnforcer.check_spawn_allowed()`.
- AG-UI omitted-caste fallback is still hardcoded `coder + reviewer`.
- A2A and AG-UI both emit `RUN_FINISHED` with `status=timeout` after 300s of
  inactivity even if the colony may still be running.
- Learned templates and outcome intelligence exist in projections, but the
  Queen briefing still under-surfaces them.
- Packet A stale truth still exists in ADRs 045/046/047, protocol fallback
  text, transport naming, and at least one `/debug/inventory` docs claim.

## Packet A: Control-Plane Coherence

**Purpose:** Make the system describe itself consistently from one source of
truth. This packet is truth-alignment, not capability expansion.

### A1. Canonical version unification

Required outcome:
- one authoritative version source
- CapabilityRegistry reads from it
- Agent Card reads from it
- no hardcoded version forks remain in protocol surfaces

Likely files:
- `src/formicos/__init__.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/protocols.py`

### A2. Event count correction

Required outcome:
- Wave 52-touched docs/status surfaces report `64`, not `62` or `65`

Likely files:
- `AGENTS.md`
- `CLAUDE.md`
- any stale count references touched in this wave

### A3. ADR status correction

Required outcome:
- ADR 045/046/047 stop reading as future design
- status becomes accepted/shipped truth with short historical note

Likely files:
- `docs/decisions/045-event-union-parallel-distillation.md`
- `docs/decisions/046-autonomy-levels.md`
- `docs/decisions/047-outcome-metrics-retention.md`

### A4. Transport naming normalization

Required outcome:
- MCP/transport naming is consistent between Agent Card, protocol snapshot,
  frontend display, and touched docs

Likely files:
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/view_state.py`
- `frontend/src/components/settings-view.ts`

### A5. Dead fallback text cleanup

Required outcome:
- live protocols are not described as `Not implemented`, `planned`, or
  `Agent Card discovery only`

Likely files:
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`

### A6. Stale docs claims cleanup

Known example:
- `/debug/inventory` is mounted and live today

This is not a broad docs rewrite. Fix only obviously false control-plane
claims discovered inside owned files.

### A7. External stream timeout truth

Current repo truth:
- A2A attach and AG-UI run streams emit terminal `RUN_FINISHED` with
  `status=timeout` after 300 seconds without an event
- the underlying colony may still be running

Required outcome:
- inactivity is no longer reported as a terminal run finish unless the run is
  actually terminal
- if idle semantics remain, they are explicit and non-terminal

Likely files:
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`

### Packet A acceptance bar

- package version, registry version, and Agent Card version agree
- event count references agree on `64`
- ADR 045/046/047 no longer read as unlanded work
- protocol status/transport text derives from live truth rather than stale fallback copy
- external inactivity is not reported as terminal completion

## Packet B: Intelligence Reach + Visible Learning

**Purpose:** Make more entry paths benefit from shipped intelligence, and make
the learning loop visible to the operator without adding new substrate.

### B0. Queen tool-result hygiene parity

Required outcome:
- the Queen tool loop matches the colony runner's prompt-boundary hygiene for
  tool feedback
- tool output is treated as untrusted prompt data
- oversized result history is compacted instead of silently bloating context

Likely files:
- `src/formicos/surface/queen_runtime.py`

### B1. Thread-aware Queen retrieval

Required outcome:
- Queen automatic pre-spawn retrieval passes `thread_id`
- returning operators benefit from thread-scoped retrieval on the primary path

Likely files:
- `src/formicos/surface/queen_runtime.py`
- optionally `src/formicos/surface/queen_tools.py` if Team 1 also patches
  manual Queen `memory_search` to use thread context

### B2. A2A learned-template reach

Required outcome:
- A2A uses `load_all_templates(...)` with projection templates
- learned templates are eligible during team selection
- A2A response exposes enough selection metadata for callers to see what was chosen

Guardrails:
- preserve determinism relative to current learned state
- do not silently propose clearly losing learned templates

Likely files:
- `src/formicos/surface/routes/a2a.py`

### B3. External budget truth and spawn-gate parity

Required outcome:
- AG-UI no longer gets a silent runtime-default budget
- AG-UI budget behavior is explicit: caller-provided or server-selected
- if Wave 52 keeps full spawn-gate parity in scope, A2A and AG-UI both use the
  same Queen-style workspace spawn gate before spawn

Likely files:
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`

### B4. AG-UI classifier-informed omitted defaults

Optional if bounded:
- replace hardcoded omitted-caste fallback with deterministic server-selected defaults
- expose honestly as server-selected defaults in response metadata

This does not make AG-UI equal to Queen. It only avoids needless dumbness.

Likely files:
- `src/formicos/surface/agui_endpoint.py`
- maybe a small shared helper if extraction stays clean

### B5. Learned template visibility in Queen briefing

Required outcome:
- briefing can surface learned-template health and availability using existing
  projection data

Likely files:
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py` if needed for selection visibility

### B6. Recent outcome digest in Queen briefing

Required outcome:
- Queen briefing includes a compact recent-outcomes summary grounded in existing
  outcome projections

Likely files:
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py` if needed for selection visibility

### Packet B acceptance bar

- Queen tool feedback is bounded and prompt-safe
- Queen automatic retrieval uses thread-aware retrieval
- A2A can route using learned templates
- external callers can see selected template/team metadata
- external budget behavior is explicit and no longer silently inconsistent
- Queen briefing visibly reflects learned-template and recent-outcome intelligence

## Priority Order

| Priority | Item | Packet | Class |
|----------|------|--------|-------|
| 1 | A1: Canonical version unification | A | Must |
| 2 | A2: Event count correction | A | Must |
| 3 | A3: ADR status correction | A | Must |
| 4 | B0: Queen tool-result hygiene parity | B | Must |
| 5 | B1: Thread-aware Queen retrieval | B | Must |
| 6 | B2: A2A learned-template reach | B | Must |
| 7 | B3: External budget truth and spawn-gate parity | B | Must |
| 8 | B5: Learned template visibility in briefing | B | Must |
| 9 | B6: Recent outcome digest in briefing | B | Must |
| 10 | A5: Dead fallback text cleanup | A | Should |
| 11 | A7: External stream timeout truth | A | Should |
| 12 | B4: AG-UI classifier-informed defaults | B | Should |
| 13 | A4: Transport naming normalization | A | Should |
| 14 | A6: Stale docs claims cleanup | A | Should |

## Team Assignment

### Team 1: Backend Coherence + Intelligence Reach

Owned files:
- `src/formicos/__init__.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_tools.py` if a small Queen retrieval piggyback stays bounded
- backend tests added for this wave

### Team 2: Frontend Protocol Truth

Owned files:
- `frontend/src/components/settings-view.ts`
- `frontend/src/components/formicos-app.ts`
- `frontend/src/state/store.ts` only if strictly needed

### Team 3: Docs + ADR Truth

Owned files:
- `AGENTS.md`
- `CLAUDE.md`
- `docs/A2A-TASKS.md`
- `docs/AG-UI-EVENTS.md`
- ADRs 045/046/047
- `docs/waves/wave_52/status_after_plan.md`

Team 3 starts immediately on Phase 1 prep, then does the final truth-refresh
after rereading Team 1 and Team 2 outcomes.

## Hidden Risks

- A2A selection observability may require a small refactor, not only an import swap.
- Distinguish per-colony budget selection from workspace spawn-gate parity.
- If full spawn-gate parity is too large, at minimum remove AG-UI's silent `5.0`
  default and document any remaining external spawn-gate gap honestly.
- Queen tool-result hardening should stay bounded to the Queen loop; do not
  turn the wave into a broad runner refactor unless extraction is trivial.
- New briefing insights may be crowded out unless `queen_runtime.py` gives them room.
- Team 1 should either create a dedicated learning-loop briefing section or
  raise the non-performance slot count enough for B5/B6 to surface reliably.
- If A2A starts using learned templates, decide explicitly whether Agent Card
  skills should remain disk-only or should also surface learned templates.
- Keep Packet A and Packet B conceptually separate even if they ship in one wave.

## What Wave 52 Does Not Include

- No new event types
- No AG-UI Tier 2 / bidirectional steering
- No full A2A conformance push
- No token streaming work
- No MCP expansion
- No Queen auto-substituting templates silently
- No auto-tuning config from outcomes
- No new external dependencies

## Smoke Test

### Packet A

1. Agent Card version matches the package version source
2. Capability registry version matches the same source
3. Event count references agree on `64`
4. ADR 045/046/047 say `Accepted`
5. Settings/protocol UI shows live protocol truth, not stale fallback text
6. A2A/AG-UI inactivity no longer emits false terminal `RUN_FINISHED`

### Packet B

7. Queen tool results are wrapped as untrusted prompt data and compact under pressure
8. Queen automatic retrieval uses thread-aware retrieval
9. A2A can select a learned template when one matches
10. A2A response exposes selected template/team metadata
11. A2A budget behavior remains explicit and observable
12. AG-UI no longer inherits a silent runtime-default budget
13. AG-UI omitted-caste behavior is either smarter and documented or explicitly unchanged by design
14. Queen briefing surfaces learned template health
15. Queen briefing surfaces a recent outcomes digest
16. Full CI remains clean

## After Wave 52

The system describes itself consistently. External integrators trust the
control plane. A2A benefits from the learned-template substrate the Queen was
already using. External intake paths obey the same budget discipline. The Queen
briefing shows that the system is learning from work, not just storing the
evidence silently.
