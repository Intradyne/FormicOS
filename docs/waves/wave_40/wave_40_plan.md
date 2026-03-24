**Wave:** 40 -- "The Refined Colony"

**Theme:** Seven waves of rapid capability development (33-39) produced strong
architecture on a codebase that has never had a dedicated health pass. Wave 40
is the pit stop. No new event types. No new product capabilities. Every change
should make existing code more coherent, faster, better tested, better
documented, or more consistent. Small enabling refactors are explicitly
allowed when they reduce clear debt in owned seams.

This wave is not about LOC reduction. It is about elegance, correctness, and
removing avoidable failure modes before Wave 41 makes the Queen materially more
capable and Wave 42 asks the Queen to prove the thesis in public.

**Prerequisite:** Wave 39 has landed, including the 39.25 polish pass.
Validator truth is replay-safe through `RoundCompleted`. Config overrides are
durable through event-backed paths. Operator overlays are replay-safe,
reversible, and local-first. The event union is now 58.

**Contract target:** Wave 40 does not expand the event union and does not add
new Queen tools or new proactive-intelligence rules. Small decomposition
sub-components are allowed on the frontend. Thin compatibility surface work is
allowed for protocol honesty as long as it does not create a second execution
path or second task store.

---

## Current Repo Truth At Wave Start

Wave 40 should start from the repo that exists, not from a roadmap abstraction.

### High-traffic backend files

| File | Lines | Current concern density |
|------|-------|-------------------------|
| `src/formicos/engine/runner.py` | 2314 | governance, convergence, tool dispatch, pheromone updates, validators, auto-escalation, audit snapshot |
| `src/formicos/surface/queen_tools.py` | 1885 | Queen tool implementations, parsing, validation, and return-shape drift |
| `src/formicos/surface/projections.py` | 1655 | projection state, overlays, annotations, config overrides, outcomes, audit views |
| `src/formicos/surface/proactive_intelligence.py` | 1623 | rule functions, recommendation classes, briefing assembly |
| `src/formicos/surface/colony_manager.py` | 1575 | lifecycle orchestration, hooks, extraction, admission, confidence updates |
| `src/formicos/surface/runtime.py` | 1315 | routing, model resolution, fallback chain, agent config |
| `src/formicos/core/events.py` | 1358 | 58 event types and contract manifest checks |
| `src/formicos/surface/knowledge_catalog.py` | 908 | scoring, trust, temporal surfacing, overlays, retrieval tiers |

### High-traffic frontend files

| File | Lines | Current concern density |
|------|-------|-------------------------|
| `frontend/src/components/colony-detail.ts` | 1010 | round history, topology, directives, audit view, completion truth, artifacts |
| `frontend/src/components/knowledge-browser.ts` | 845 | catalog, graph, contradictions, score breakdown, overlays, annotations |
| `frontend/src/components/formicos-app.ts` | 622 | shell, routing, state wiring |
| `frontend/src/components/queen-overview.ts` | 561 | command-center layout, briefings, colony cards, config memory |
| `frontend/src/components/workflow-view.ts` | 439 | DAG, launch surfaces, pre-spawn editing |

### Current test shape

| Area | Count |
|------|-------|
| `tests/unit` | 135 |
| `tests/unit/surface` | 92 |
| `tests/integration` | 14 |
| `tests/browser` | 1 |

This repo is not under-tested in the absolute. It is under-tested at the
cross-feature interaction layer.

### Current protocol truth

- `src/formicos/surface/routes/a2a.py` already implements a colony-backed REST
  task lifecycle where `task_id == colony_id` and there is no second task
  store.
- `src/formicos/surface/routes/protocols.py` already advertises A2A honestly
  as a custom colony-backed REST surface rather than full Google A2A JSON-RPC.
- `docs/A2A-TASKS.md` already documents the current REST lifecycle honestly.
- AG-UI is already a real Tier 1 surface and should remain honestly described
  rather than overclaimed.

### Current docs truth

Wave 39.25 already frontloaded part of this wave's docs pass across:

- `README.md`
- `CLAUDE.md`
- `AGENTS.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/KNOWLEDGE_LIFECYCLE.md`
- `docs/decisions/INDEX.md`

Wave 40 should finish and verify those documents rather than treating docs as
untouched greenfield work.

---

## Why This Wave

The repo works, but it is carrying exactly the kind of debt that creates
avoidable failures under capability or benchmark pressure:

- large files with mixed concerns
- behavior spread across multiple waves and multiple teams
- sparse interaction tests relative to single-feature tests
- honest protocol surfaces that are still uneven in implementation
- documentation that has been improved but still needs a final truth pass
- no systematic profiling report grounded in the current workload

Wave 40 is the wave that turns "the architecture is interesting" into "the
implementation is disciplined enough that failures mean something real."

The governing principle is:

1. profile first
2. then refactor based on evidence
3. then harden interactions
4. then verify docs, UI, and protocol truth

---

## Pillar 1: Backend Coherence

### Principle

Do not split files for LOC targets. Split when a file mixes concerns that
change for different reasons, or when a coder entering the module cannot
quickly find where to make a change. Preserve external behavior. If import
paths change, re-export from the original module where practical.

### 1A. Baseline profiling report (do this first)

Before major refactors, instrument the key hot paths and produce
`docs/waves/wave_40/profiling_report.md` with:

- measured hotspots
- approximate p50 / p95 where relevant
- fix or accept decisions for the top bottlenecks

Profile at minimum:

1. briefing generation with 500+ entries and the current rule set
2. retrieval latency with Thompson Sampling, trust/temporal scoring, and
   operator overlay checks
3. view-state snapshot generation with many colonies and memory entries
4. colony spawn-to-first-round latency
5. projection replay time on a large event log

Likely candidates that must be confirmed rather than assumed:

- repeated scans inside `generate_briefing`
- per-entry work inside retrieval sorting and co-occurrence scoring
- repeated knowledge re-fetch on redirects or goal changes

### 1B. `colony_manager.py` -- split hooks and extraction

`src/formicos/surface/colony_manager.py` currently mixes:

1. colony lifecycle orchestration
2. post-colony hooks
3. memory extraction pipeline
4. confidence-update logic
5. naming and small service utilities

Recommended outcome:

- lifecycle stays in `colony_manager.py`
- post-colony hooks move to a focused helper or module
- extraction pipeline moves to a focused helper or module
- confidence-update logic is isolated enough to test and read cleanly

This should preserve behavior, not redesign the substrate.

### 1C. `runner.py` -- extract tool dispatch, keep governance together

`src/formicos/engine/runner.py` is large but not shapeless.

Recommended outcome:

- extract tool dispatch into `tool_dispatch.py` or an equivalent focused seam
- optionally extract runner-local data classes into `runner_types.py`
- keep governance, convergence, and pheromone-update logic together
- preserve the current validator and auto-escalation behavior

Wave 40 should also make a clear decision about the current audit-snapshot
gap:

- either keep the current explanatory-only audit boundary and document it
- or add a minimal replay-safe audit snapshot on `RoundResult` if that can be
  done cleanly without contract sprawl

### 1D. `queen_tools.py` -- coherence audit

`src/formicos/surface/queen_tools.py` is one of the largest surface files in
the repo. Wave 40 should explicitly audit:

- repeated parsing / validation helpers
- family grouping by tool type
- return-shape consistency for tool callers
- whether a registry or helper layer improves navigability

This audit may conclude that the file is large but coherent. That is an
acceptable outcome if the reasoning is documented.

### 1E. `projections.py` -- organization audit

`src/formicos/surface/projections.py` is now one of the most central truth
surfaces in the system.

Wave 40 should explicitly audit:

- whether `ProjectionStore` has become a god object
- whether overlay / annotation / config-override state wants more obvious
  organization
- whether event handlers are arranged by concern or just by accumulation
- whether types remain consistent across the 58-event surface

This is an organization and truth-surface audit, not an excuse to redesign the
event model.

### 1F. `proactive_intelligence.py` -- rule registry pattern

`src/formicos/surface/proactive_intelligence.py` currently holds the full
briefing rule set and recommendation assembly in one file.

Wave 40 should evaluate and, if justified, implement:

- a lightweight rule registry
- explicit grouping by family
- clearer assembly flow inside `generate_briefing`

The point is not abstraction theater. The point is to make future rule work
less error-prone.

### 1G. Error handling by boundary

Wave 40 should audit and normalize error behavior by boundary, not by raw
string count.

Three boundaries matter:

1. HTTP / route surfaces
2. UI-facing API responses
3. tool / service return paths

Goals:

- HTTP and route surfaces should use the structured error path consistently
  where they are already meant to
- UI-facing API responses should be shape-consistent enough for uniform
  rendering
- tool / service return paths should have a deliberate contract appropriate to
  tool callers, even if that differs from HTTP error envelopes

This is especially important around the current A2A / specialist / service
surfaces.

---

## Pillar 2: Cross-Feature Integration Testing

### Principle

The repo has many single-feature tests. The primary testing gap is interaction
truth across features that were added in different waves.

### 2A. Critical interaction pairs

Wave 40 should write focused tests for at least the top 5-7 of these:

| Feature A | Feature B | What can go wrong |
|-----------|-----------|-------------------|
| operator overlays | retrieval scoring | pinned entries do not reliably win; muted entries still appear |
| operator overlays | federation | local editorial state leaks into federated truth |
| validators | auto-escalation | validator or completion state reflects pre-escalation truth incorrectly |
| earned autonomy | config memory | recommendations and evidence drift apart |
| bi-temporal edges | graph queries | invalidation filtering diverges across query paths |
| admission scoring | federation trust | weak foreign entries bypass hardened trust expectations |
| topology bias | muted / invalidated entries | suppressed local entries still bias planning surfaces |
| auto-escalation | escalation matrix | reporting truth regresses into another Wave 38-style mismatch |
| co-occurrence | operator invalidation | invalidated entries still reinforce retrieval paths |
| proactive insights | operator annotations | annotation semantics do not surface coherently |

### 2B. Flaky test audit

Run the full suite multiple times, identify genuinely unstable tests, and fix
or quarantine them. Any test relying on stochastic retrieval behavior must
either control randomness or assert something stable.

### 2C. Coverage gap analysis

If time allows, identify the least-covered high-traffic surface functions and
add focused tests. This is stretch work after the interaction matrix is in
place.

---

## Pillar 3: Frontend Consistency

### Principle

Three waves of UI growth by different teams create consistency debt even when
every individual feature works.

### 3A. Component consistency audit

Audit the main surfaces for:

- shared confidence-color tokens
- meaningful empty states
- non-jarring loading states
- consistent typography and stat styling
- action-surface consistency
- overlay badge consistency across views

### 3B. `colony-detail.ts` decomposition assessment

`frontend/src/components/colony-detail.ts` is now large enough that Wave 40
should explicitly decide whether extraction into sub-components improves
navigability. If the answer is yes, small decomposition components are in
scope. If the answer is no, document that conclusion.

### 3C. `knowledge-browser.ts` coherence and performance review

`frontend/src/components/knowledge-browser.ts` now spans catalog, graph,
contradictions, score breakdown, overlays, annotations, provenance, and more.

Wave 40 should:

- verify the Wave 39 overlay UI fits cleanly with older score and provenance
  surfaces
- sanity-check behavior with a large number of entries
- fix obvious coherence or rendering debt if found

### 3D. Demo path re-validation

The Wave 36 demo path must still work after Waves 37-39. Wave 40 should rerun
the demo flow and fix any truth or UX regressions it exposes.

Minimum demo checks:

1. demo workspace creation still works
2. the seeded contradiction still surfaces in the briefing
3. colony execution still renders cleanly in the current workflow view
4. deterministic maintenance still fires as expected
5. completion / quality truth still reads honestly
6. Wave 39 surfaces do not break the flow

---

## Pillar 4: Documentation Truth Pass

### Principle

Every document should describe the post-Wave-39 system as it exists now.

### 4A. Core docs to finish and verify

Wave 39.25 already refreshed parts of the docs layer. Wave 40 should finish the
job and verify those updates against code reality.

Priority documents:

- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `docs/KNOWLEDGE_LIFECYCLE.md`
- `AGENTS.md`
- `README.md`
- `docs/decisions/INDEX.md`
- `CONTRIBUTING.md`
- `docs/A2A-TASKS.md`
- `docs/NEMOCLAW_INTEGRATION.md`

Truth areas that must be correct:

- event union is 58
- operator overlays are local-first and replay-safe
- validator and completion truth is post-Wave-39 truth
- escalation and configuration-override truth is accurate
- federation and admission hardening are described honestly
- current A2A / native task API truth is not overclaimed

### 4B. ADR audit

Read the ADR set that actually exists in the repo. Ensure:

- status markers are current
- superseded decisions are marked honestly
- the index does not pretend missing ADR files already exist

### 4C. Inline documentation

High-traffic functions should have docstrings that match current behavior.

Priority candidates:

- `generate_briefing`
- `_evaluate_governance` and the post-governance escalation path
- `_hook_confidence_update`
- `search` and `search_tiered`
- `_build_colony_outcome`
- `evaluate_entry`

---

## Pillar 5: Dual API Surface

### Decision

The current `/a2a/tasks` implementation is already a useful colony-backed task
API. It shares the spirit of A2A but is not wire-compatible with Google A2A
JSON-RPC. Wave 40 should formalize that truth instead of leaving the project in
an ambiguous middle state.

### Implementation direction

1. **Native Colony Task API**
   - Treat the existing colony-backed task lifecycle as the native first-class
     task API.
   - Keep it honest, powerful, and directly aligned with FormicOS semantics.

2. **Thin A2A JSON-RPC compatibility wrapper**
   - If shipped in this wave, it must be a translation layer over the same
     underlying task handlers.
   - No second task store.
   - No second execution path.
   - No divergence in task truth.

3. **Agent Card and docs truth**
   - Advertise native and compatibility surfaces honestly.
   - Make conformance level explicit.
   - Keep AG-UI honestly described as its current Tier 1 surface.

Wave 40 is the right place to make the protocol story cleaner without letting
an external spec drive internal architecture.

---

## Priority Order (cut from the bottom)

| Priority | Item | Pillar | Class |
|----------|------|--------|-------|
| 1 | baseline profiling report | 1A | Must |
| 2 | `colony_manager.py` hook / extraction split | 1B | Must |
| 3 | cross-feature interaction tests for top pairs | 2A | Must |
| 4 | boundary-specific error contract audit and cleanup | 1G | Must |
| 5 | `CLAUDE.md` + `docs/OPERATORS_GUIDE.md` truth pass | 4A | Must |
| 6 | frontend consistency audit | 3A | Must |
| 7 | demo path re-validation | 3D | Must |
| 8 | dual API honesty work | 5 | Must |
| 9 | `proactive_intelligence.py` registry cleanup | 1F | Should |
| 10 | `runner.py` tool-dispatch extraction | 1C | Should |
| 11 | `queen_tools.py` coherence audit | 1D | Should |
| 12 | `projections.py` organization audit | 1E | Should |
| 13 | fix profiled top bottlenecks | 1A | Should |
| 14 | flaky test audit | 2B | Should |
| 15 | remaining docs truth pass | 4A-4C | Should |
| 16 | coverage gap analysis | 2C | Stretch |
| 17 | `colony-detail.ts` decomposition | 3B | Stretch |
| 18 | `knowledge-browser.ts` large-entry perf review | 3C | Stretch |

---

## Team Assignment

### Team 1: Backend Coherence + Profiling

Owns Pillar 1 end-to-end.

Primary files:

- `src/formicos/surface/colony_manager.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/surface/projections.py`
- helper modules created to reduce debt in those seams

Primary responsibility:

- profile first
- then refactor based on evidence
- keep behavior stable
- improve navigability and boundary clarity

### Team 2: Testing + Integration Hardening

Owns Pillar 2.

Primary files:

- `tests/integration/*`
- focused unit tests if an interaction seam is cleaner there

Primary responsibility:

- write the missing cross-feature tests
- identify and fix flaky tests
- improve confidence in multi-wave interactions without inventing new features

### Team 3: Frontend + Docs + Dual API

Owns Pillars 3, 4, and 5.

Primary files:

- major frontend surfaces
- browser smoke test
- top-level docs and operator docs
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/routes/protocols.py`
- a thin compatibility wrapper module if needed

Primary responsibility:

- make the UI consistent
- make docs truthful
- make the protocol story clean and honest

### Overlap

Overlap should remain minimal.

- Team 1 should re-export from original modules if refactors move helpers.
- Team 2 should prefer behavior-level tests over brittle import-coupled tests.
- Team 3 should build any compatibility wrapper over the same underlying task
  truth Team 1 is preserving.

---

## What Wave 40 Does Not Include

- no new event types
- no new Queen tools
- no new proactive-intelligence rules
- no new benchmark adapter
- no Wave 41 capability work
- no public benchmark claim
- no second task store or second hidden task architecture

Wave 40 may include small refactors, decomposition sub-components, or thin
compatibility surfaces when they make the existing system cleaner and more
truthful.

---

## Smoke Test

1. full test suite passes after refactors
2. `python scripts/lint_imports.py` passes
3. `docs/waves/wave_40/profiling_report.md` exists with measured bottlenecks
4. new cross-feature interaction tests pass
5. the guided demo path still works end-to-end
6. core docs describe the post-Wave-39 system honestly
7. error behavior is boundary-consistent on the main surfaced paths
8. confidence tiers, overlay badges, and empty states are visually consistent
9. ADR index and status markers are honest
10. native task API truth is explicit and, if shipped, the A2A wrapper is thin
    and truthful
11. frontend build, ruff, pyright, lint-imports, and pytest are all clean

---

## After Wave 40

The codebase should be more coherent. The biggest files should be easier to
navigate. Cross-feature truth should be tested. The demo should still work.
The docs should match the code. The protocol surfaces should be honest about
what they are.

That sets up Wave 41 to make the Queen genuinely more capable at hard real
tasks, and Wave 42 to ask the Queen to prove the thesis publicly without
incidental repo debt muddying the result.

The honest claim after Wave 40 is:

**FormicOS is not just architecturally novel. It is disciplined enough that
the code, docs, tests, and protocol surfaces all tell the same story.**
