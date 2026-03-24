## Role

You own the backend coherence and profiling track of Wave 40.

Your job is to:

- profile first
- then refactor targeted backend seams based on evidence
- improve navigability and contract clarity without changing external behavior

This is the "clean up the Python core without changing the thesis" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_40/wave_40_plan.md`
4. `docs/waves/wave_40/acceptance_gates.md`
5. `docs/waves/session_decisions_2026_03_19.md`
6. `src/formicos/surface/colony_manager.py`
7. `src/formicos/engine/runner.py`
8. `src/formicos/surface/proactive_intelligence.py`
9. `src/formicos/surface/queen_tools.py`
10. `src/formicos/surface/projections.py`
11. `src/formicos/surface/runtime.py`
12. `src/formicos/surface/knowledge_catalog.py`

## Coordination rules

- Profile before major refactoring.
- Preserve behavior. This wave is not feature work.
- Do **not** change the event union.
- Do **not** add new Queen tools or new proactive-intelligence rules.
- If you split helpers out of a hot file, preserve import stability where
  practical through re-exports or narrow compatibility shims.
- Audit error handling by boundary, not by raw string-hunt ideology.
- Do **not** touch frontend files or top-level docs in this track.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/colony_manager.py` | OWN | lifecycle clarity, hook / extraction split |
| `src/formicos/engine/runner.py` | OWN | tool-dispatch extraction, audit snapshot decision, clarity improvements |
| `src/formicos/surface/proactive_intelligence.py` | OWN | rule-assembly cleanup, optional registry pattern |
| `src/formicos/surface/queen_tools.py` | OWN | coherence audit and targeted cleanup |
| `src/formicos/surface/projections.py` | OWN | organization audit and targeted cleanup only if needed for coherence |
| `src/formicos/surface/runtime.py` | MODIFY | only if a backend seam actually requires it |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | only if profiling identifies a real bottleneck |
| `src/formicos/engine/tool_dispatch.py` | CREATE | if extracted from `runner.py` |
| `src/formicos/engine/runner_types.py` | CREATE | if data classes are extracted cleanly |
| `src/formicos/surface/colony_hooks.py` | CREATE | if hook extraction is justified |
| `src/formicos/surface/memory_extraction.py` | CREATE | if extraction pipeline split is justified |
| `tests/benchmark/profiling_harness.py` | CREATE | lightweight profiling instrumentation |
| `docs/waves/wave_40/profiling_report.md` | CREATE | measured bottlenecks + fix decisions |

## DO NOT TOUCH

- `src/formicos/core/*` - no event work in this track
- `frontend/src/components/*` - Team 3 owns
- `tests/browser/*` - Team 3 owns
- top-level docs and operator docs - Team 3 owns
- protocol route truth work in `src/formicos/surface/routes/a2a.py` and
  `src/formicos/surface/routes/protocols.py` - Team 3 owns

## Overlap rules

- Team 2 owns the Wave 40 interaction tests.
  - If you move helpers, keep behavior stable and import breakage minimal.
  - Reread their final tests before merge if your refactor was broad.
- Team 3 owns docs and dual-API truth surfaces.
  - If you make a backend contract decision that changes what docs should say,
    leave a clear note in your summary.

---

## 1A. Baseline profiling report

Do this before any non-trivial refactor.

### Required scope

Profile at minimum:

1. `generate_briefing` with large memory state
2. retrieval sorting / scoring path
3. view-state generation or equivalent snapshot path
4. colony spawn-to-first-round latency
5. replay or projection rebuild time

Use lightweight instrumentation. The deliverable is a report that says:

- what was measured
- what was slow
- what was fixed
- what was accepted and why

### Hard constraints

- Do **not** invent micro-benchmarks disconnected from the real app flow.
- Do **not** refactor first and profile later.

---

## 1B. `colony_manager.py` cleanup

Wave 40 expects this file to get cleaner.

### Required scope

1. Separate lifecycle orchestration from post-colony hooks if justified.
2. Separate lifecycle orchestration from the memory-extraction pipeline if
   justified.
3. Make the confidence-update path easier to find and reason about.

### Hard constraints

- Do **not** change colony semantics.
- Do **not** rewrite the file around abstract patterns unless they actually
  reduce confusion.

---

## 1C. `runner.py` cleanup

### Required scope

1. Extract tool-dispatch complexity if it materially improves navigability.
2. Keep governance, convergence, and pheromone-update logic together.
3. Make a clear audit-snapshot decision:
   - either keep the current explanatory-only boundary and document it
   - or add a minimal replay-safe snapshot if it is clean and bounded

### Hard constraints

- Preserve the current validator, escalation, and round-result truth.
- Do **not** widen feature scope under the label of cleanup.

---

## 1D. `queen_tools.py` and `projections.py` audits

You own the coherence review of the two largest surface truth files after the
core execution path.

### Required scope

For `queen_tools.py`:

- identify repeated parsing / validation seams
- identify return-shape inconsistencies for tool callers
- decide whether grouping or helper extraction is justified

For `projections.py`:

- identify organization drift across colony/thread/workspace truth
- identify whether overlay / annotation / override state wants clearer grouping
- keep event-handler truth coherent

If either file is large but still coherent, document that rather than forcing a
split for its own sake.

---

## 1E. `proactive_intelligence.py`

### Required scope

If justified by clarity, land a light registry or family-grouping cleanup so
`generate_briefing` is easier to extend and audit.

### Hard constraints

- No new rules
- No new recommendation families
- No behavior drift hidden behind cleanup

---

## 1F. Error handling by boundary

Audit and normalize the main backend boundaries:

1. route / HTTP boundary
2. UI-facing API responses
3. tool / service return paths

The goal is consistency by boundary, not a repo-wide crusade against any
literal error string.

---

## Validation

Run, at minimum:

1. `python scripts/lint_imports.py`
2. targeted pytest for the files you changed
3. full `python -m pytest -q` if your refactor is broad enough to justify it

Your summary must include:

- the measured bottlenecks
- the actual refactors landed
- any file split decisions you rejected and why
- any backend contract decisions Team 3 needs to reflect in docs
