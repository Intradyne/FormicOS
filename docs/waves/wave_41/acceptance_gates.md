This document compresses the Wave 41 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- `docs/waves/wave_41/wave_41_plan.md`

---

## Must Ship

### Gate 1: Retrieval trust and exploration math become more coherent

All of the following must be true:

1. The retrieval path no longer throws away rich peer-trust posteriors in favor
   of coarse status bands where the live seam can now consume the posterior.
2. The codebase no longer carries two unrelated exploration-confidence
   strategies across adjacent knowledge and context paths when one shared helper
   would do.
3. The improvements stay bounded to the exploration / confidence term rather
   than silently rewriting the full retrieval composite.
4. No replay truth, overlay truth, or federation-locality truth is regressed.

Passing evidence:

- `trust.py` uses richer live posterior statistics in retrieval-facing seams
- `knowledge_catalog.py` and `context.py` share one exploration-confidence
  helper or an equivalent unification
- existing retrieval and federation behavior remains legible and testable

### Gate 2: Contradiction handling stops fragmenting across surfaces

All of the following must be true:

1. There is a single clearer contradiction-detection path instead of scattered
   partial logic staying the de facto truth.
2. The system distinguishes contradiction from complement and temporal update
   instead of treating all disagreement as one scoring problem.
3. If only the early stages land, the code and docs do not overclaim richer
   Bayesian fusion than actually exists.
4. Any new hypothesis-handling behavior remains inspectable and bounded.

Passing evidence:

- `conflict_resolution.py` becomes the clearer shared seam
- `maintenance.py` / `proactive_intelligence.py` delegate to that seam where
  applicable
- tests cover contradiction-vs-complement-vs-update behavior

### Gate 3: Real repo-backed execution is materially stronger

All of the following must be true:

1. FormicOS can operate against real repo workspaces more cleanly than the
   current Python-only sandbox path allows.
2. Workspace execution lifecycle is distinct from sandbox isolation concerns.
3. Test or command failure output is structured enough to support a useful
   second attempt.
4. The execution path stays product-general and does not become a benchmark-only
   adapter.

Passing evidence:

- repo / workspace execution semantics are clearer and more durable
- structured failure output exists for at least the main supported test paths
- no special benchmark-only execution fork is introduced

### Gate 4: Multi-file coordination becomes a first-class capability

All of the following must be true:

1. The Queen can coordinate multi-file work with more file-awareness than the
   current generic colony decomposition provides.
2. There is a validation path that checks cross-file consistency rather than
   only single-step completion signals.
3. The implementation uses the existing colony / knowledge architecture rather
   than introducing a disconnected special planner.

Passing evidence:

- multi-file planning or coordination is visibly stronger
- cross-file validation exists and is exercised in tests
- the colony path remains the canonical execution truth

### Gate 5: Compounding-curve measurement becomes real and publishable

All of the following must be true:

1. There is a sequential task runner or equivalent measured harness that reuses
   one workspace's accumulated knowledge over time.
2. The wave measures the compounding curve in three ways:
   - raw performance
   - cost-normalized performance
   - time-normalized performance
3. Experiment conditions are locked and recorded tightly enough that later gains
   cannot be dismissed as policy drift.
4. The measurement path is useful whether the curve rises or stays flat.

Passing evidence:

- benchmark / eval infra can run sequential tasks under fixed conditions
- outputs include all three curve views
- run configuration records model mix, budget policy, escalation policy, and
  ordering assumptions

---

## Should Ship

### Gate 6: Cost optimization is evidence-backed rather than decorative

The repo should include:

- tiered execution or routing decisions that are grounded in measured cost /
  outcome tradeoffs
- early-stopping or caching logic only where it does not poison the validity of
  the compounding measurement
- reporting that makes "cost per correct task" legible

### Gate 7: Contradiction handling advances beyond pure plumbing if justified

If contradiction work goes beyond stages 1-2, it should:

1. preserve inspectability
2. remain bounded
3. avoid silently redesigning the whole knowledge model in one wave

---

## Stretch

### Gate 8: Richer fusion lands without overreach

If richer Bayesian / hypothesis fusion ships, it should:

1. follow the now-unified contradiction path
2. stay legible in audit / operator surfaces
3. ship with focused tests and clear limits

### Gate 9: Optimization reporting becomes operator-useful

If extra optimization/reporting work ships, it should:

1. help explain when the colony should spend more versus stop earlier
2. remain subordinate to measurement truth
3. avoid turning Wave 41 into a benchmark dashboard wave

---

## Cut Line

Cut from the bottom first:

1. richer contradiction fusion extras
2. secondary optimization polish
3. additional reporting polish

Do not cut:

1. continuous trust weighting
2. TS/UCB unification
3. contradiction stages 1-2
4. stronger repo-backed execution
5. multi-file coordination and validation
6. compounding-curve measurement with locked conditions

---

## Final Acceptance Statement

Wave 41 is acceptable when FormicOS is stronger in three ways:

1. **Retrieval trust** -- the math bridges between posterior knowledge and live
   scoring are tighter and more coherent.
2. **Execution trust** -- the system can tackle real repo-backed, multi-file
   work with a stronger execution and validation path.
3. **Learning evidence** -- the compounding curve is measured honestly enough
   that outsiders can judge whether the shared brain is actually getting
   smarter over time.
