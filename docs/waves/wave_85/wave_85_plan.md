# Wave 85 Plan: Queen Routing And Structural Signal Activation

## Status

Dispatch-ready. Grounded in live repo truth as of 2026-04-01.

## Summary

Wave 84 proved the runtime path is stable again:

- Qwen3.5 is the production profile
- 5/5 real-repo tasks completed
- 0.503 average quality
- zero hangs

Wave 84.5 improved the Queen planning substrate:

- saved plan patterns are retrieved into planning signals
- planning briefs now log structured summaries
- `planning_policy.py` exists with tests
- deterministic planning eval and ablation scaffolding landed

But the next quality lever is not "more infrastructure." It is making
the already-built planning substrate actually influence live Queen
behavior.

Wave 85 is the wiring-and-measurement wave for that.

Two active tracks:

- Track A: make the structural signal actually fire and make saved-pattern
  rendering truthful
- Track B: make `planning_policy.py` the live routing authority and upgrade
  the eval harness so it can measure route changes instead of assuming
  routing is stable

Deferred follow-up, not an active track:

- graph reflection + entry-to-module bridging only if Wave 85 proves that
  better structural seeding still leaves the structural signal as the
  dominant missing lever

## Verified Repo Truth

### 1. Saved patterns are already in the planning brief

`src/formicos/surface/planning_signals.py` already has
`_fetch_saved_patterns()` and `build_planning_signals()` already returns
`saved_patterns`.

`src/formicos/surface/planning_brief.py` already renders a saved-pattern
line.

The recent ablation confirmed:

- matching prompts do surface the saved pattern
- non-matching prompts do not
- retrieval is already keyed by deterministic bundle elements rather than
  raw semantic similarity

So Wave 85 should not rebuild saved-pattern retrieval. The real problem is
truthfulness and usefulness of the rendered signal.

### 2. Planning policy exists but is not the live Queen authority

`src/formicos/surface/planning_policy.py` defines
`decide_planning_route()` and `PlanningDecision`.

But `src/formicos/surface/queen_runtime.py` still uses the older
scattered helpers directly in the live respond path:

- `classify_complexity()`
- `_looks_like_colony_work()`
- `_prefer_single_colony_route()`

That means the Wave 84.5 routing consolidation is scaffolded and tested,
but not yet the production routing seam.

### 3. Structural hints exist, but seed extraction is brittle

`src/formicos/surface/planning_signals.py` already calls
`get_structural_hints()` through `_fetch_coupling()`.

`src/formicos/surface/structural_planner.py` already computes:

- `matched_files`
- `coupling_pairs`
- `suggested_groups`
- `confidence`
- `rationale`

But `_find_mentioned_files()` is still mostly exact-match driven:

- full path mention
- exact file stem mention
- module-style path mention

Natural operator phrases like "workspace roots" do not reliably match
`workspace_roots.py`. When seeding fails, the structural signal never
reaches coupling analysis.

### 4. Graph reflection exists but is not wired

`reflect_structure_to_graph()` exists in
`src/formicos/surface/structural_planner.py` but is not called from the
current reindex/binding path.

That matters, but it is not the first Wave 85 move. The immediate problem
is that the structural signal often fails before graph depth would matter.

### 5. The live eval path is still mostly placeholder

`tests/eval/queen_planning_eval.py` has a deterministic harness and a
`TestLiveEval::test_placeholder` skip.

`tests/eval/test_planning_ablation.py` currently assumes routing should
stay stable across configs. That was acceptable while the new policy was
not live. It becomes the wrong assertion once planning-policy wiring lands.

## Track A: Structural Signal Activation + Saved-Pattern Truthfulness

Goal:

Make the structural signal show up for real operator phrasing and make
saved-pattern rendering honest enough to debug.

### Scope

1. Improve structural seed extraction in
   `src/formicos/surface/structural_planner.py`

- normalize `_`, `-`, `.`, `/`, and spaces into a shared token space
- support phrase-style matching so prompts like "workspace roots" can seed
  `workspace_roots.py`
- keep matching deterministic and cheap; do not add embeddings or fuzzy
  ranking in this wave

2. Add explicit suppression reasons to structural hints

When no coupling line appears, it should be possible to tell why:

- no file/module indicators in the message
- indicators present but no files matched
- files matched but confidence too low

This can be returned in the hint object and/or logged, but it must be
inspectable in tests and debugging.

3. Improve saved-pattern rendering in the planning brief

The current `Saved: ... (q=0.00, ...)` rendering is misleading when the
pattern matched structurally but has no outcome summary.

Render saved patterns with:

- pattern name
- `match_score`
- colony/group count
- outcome quality only when present
- compact match-basis cues when available

Example:

`Saved: workspace-roots-refactor (match=0.70, 1 colony, task-class+files)`

or, when outcome exists:

`Saved: auth-refactor (match=0.80, q=0.87, 3 colonies, files)`

4. Preserve compact planning observability

Do not bloat `QueenMessage.meta`.

If you add structural suppression detail or saved-pattern match-basis
detail, keep it compact and metadata-safe.

### Owned Files

- `src/formicos/surface/structural_planner.py`
- `src/formicos/surface/planning_signals.py`
- `src/formicos/surface/planning_brief.py`
- `tests/unit/surface/test_planning_signals.py`
- `tests/unit/surface/test_planning_brief.py`
- `tests/unit/surface/test_structural_planner.py` if needed

### Validation

- `python -m pytest tests/unit/surface/test_planning_signals.py -q`
- `python -m pytest tests/unit/surface/test_planning_brief.py -q`
- any new targeted structural-planner tests

## Track B: Live Planning Policy + Real Queen Eval

Goal:

Make `planning_policy.py` the production routing seam and upgrade the eval
layer so it measures real route differences.

### Scope

1. Wire `decide_planning_route()` into the live Queen respond path

`queen_runtime.py` should stop re-deciding route through scattered helper
calls in the live path.

Important:

- keep the existing helpers as internal ingredients of the policy object
- do not delete or rewrite all heuristics in this wave
- keep the live route semantics close to the validated Wave 84 production
  behavior unless a test explicitly proves the new route is better

2. Keep behavior flags bounded

Capability behavior flags are real scaffolding, but they are not yet a
proven production lever.

Wave 85 may thread them through the policy decision and surface them in
evaluation, but should not introduce aggressive behavior-flag-driven route
changes without explicit tests.

3. Upgrade deterministic eval to score the live policy seam

`tests/eval/queen_planning_eval.py` should score
`decide_planning_route()`, not reconstruct route solely from the old
helper set.

4. Replace the placeholder live eval with a real guarded smoke

Live eval remains optional behind `FORMICOS_LIVE_EVAL=1`, but the test
should no longer be a placeholder skip. It should:

- call into the real Queen routing/planning path
- capture at least route choice and timing
- remain bounded and small

5. Fix the ablation assumption

`tests/eval/test_planning_ablation.py` should no longer assert that route
must be identical across all signal configurations.

Instead:

- record route deltas
- record structure deltas
- assert signal availability truthfully
- report when added signals do or do not change route

6. Register the live-eval marker

Remove the `PytestUnknownMarkWarning` by registering `live_eval` in the
pytest config.

### Owned Files

- `src/formicos/surface/planning_policy.py`
- `src/formicos/surface/queen_runtime.py`
- `tests/unit/surface/test_planning_policy.py`
- `tests/unit/surface/test_routing_agreement.py`
- `tests/eval/queen_planning_eval.py`
- `tests/eval/test_planning_ablation.py`
- `pyproject.toml` if needed for marker registration

### Validation

- `python -m pytest tests/unit/surface/test_planning_policy.py -q`
- `python -m pytest tests/unit/surface/test_routing_agreement.py -q`
- `python -m pytest tests/eval/queen_planning_eval.py -q`
- `python -m pytest tests/eval/test_planning_ablation.py -q`

## Merge Order

Track A and Track B can start in parallel.

Recommended merge sequence:

1. Track A lands first or rebases first if both are close, because it
   improves the actual planning signal payload.
2. Track B lands second, after rereading the final signal shape from Track A.
3. Final acceptance reruns deterministic eval plus one small live Queen
   smoke behind `FORMICOS_LIVE_EVAL=1`.

## What Wave 85 Does Not Do

- no graph bridge by default
- no entry-to-module retrieval redesign
- no new Queen UI surface
- no worker-loop changes
- no new colony caste or verifier colony
- no benchmark pack rerun as the primary acceptance gate

Those are only reconsidered after Wave 85 data lands.

## Success Criteria

Wave 85 is successful if all of the following are true:

1. Structural seeding recognizes phrase-style file references such as
   "workspace roots" and surfaces a non-empty structural hint when the
   workspace structure supports it, or emits an explicit suppression reason
   when it does not.
2. The live Queen respond path uses `decide_planning_route()` as the
   routing authority.
3. Saved-pattern rendering no longer implies `q=0.00` when the pattern
   simply lacks outcome evidence.
4. Deterministic eval measures the live routing seam.
5. Live eval is no longer a placeholder skip.
6. The `live_eval` pytest warning is gone.

## Post-Wave Decision Gate

After Wave 85 lands, decide the next planning lever from evidence:

- If structural hints start appearing and influence route/plan shape, then
  the next wave should deepen structural intelligence:
  graph reflection + entry-to-module bridging.
- If structural hints still rarely appear even after seed fixes, improve
  the structural planner before investing in graph work.
- If routing changes matter more than structural changes, prioritize
  planning-policy refinement and capability-behavior integration instead of
  graph work.
