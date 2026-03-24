This document compresses the Wave 42 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- `docs/waves/wave_42/wave_42_plan.md`

---

## Must Ship

### Gate 1: Static workspace intelligence is real and bounded

All of the following must be true:

1. The repo includes a lightweight structural analysis path that works on the
   workspace tree without depending on LLM interpretation for basic code
   structure.
2. The resulting structure is usable by the colony path for multi-file work.
3. Structural facts do not get bulk-dumped into the main knowledge substrate by
   default.
4. The first version remains lightweight and understandable.

Passing evidence:

- a code-analysis adapter or equivalent exists
- multi-file coordination can consume structural relationships
- structural storage remains local / bounded unless selectively promoted

### Gate 2: The topology prior stops depending mainly on string overlap

All of the following must be true:

1. `_compute_knowledge_prior()` has a stronger first-order signal than domain
   name overlap.
2. The first version uses simple structural dependency information when
   available.
3. The fallback when no structural signal exists is still clean and neutral.
4. The new prior stays bounded and does not over-bias the topology.

Passing evidence:

- structural priors are visible in the runner seam
- tests cover both structural and fallback behavior
- the pheromone system remains the primary adaptation mechanism

### Gate 3: Contradiction resolution respects classification

All of the following must be true:

1. Contradiction, complement, and temporal update no longer flow through one
   undifferentiated resolver.
2. `resolve_conflict()` behaves differently by relation type.
3. The system does not overclaim competing-hypothesis surfacing if only Stage 2
   lands.
4. Operator-facing truth remains inspectable.

Passing evidence:

- contradiction pairs resolve differently from complement / temporal-update
  pairs
- tests cover class-specific behavior
- any Stage 3 work is explicit rather than implied

### Gate 4: Runtime exploration control becomes more adaptive

All of the following must be true:

1. Evaporation behavior is no longer fully fixed.
2. Runtime control reuses existing branching concepts without coupling itself
   to briefing/reporting code.
3. The normal path remains stable when no stagnation signal is present.
4. Any extra smoothing or reinforcement tweaks stay bounded.

Passing evidence:

- `runner.py` owns the adaptive control logic
- fixed-rate behavior is no longer the only path
- targeted tests cover healthy vs stagnating behavior

### Gate 5: Extraction quality improves without becoming blunt

All of the following must be true:

1. Extraction quality gating is more selective than before.
2. The gate is conjunctive / evidence-aware rather than a naive short-text
   rule.
3. The knowledge substrate gets cleaner input without suppressing obviously
   useful concise entries.

Passing evidence:

- extraction hooks apply bounded quality filters
- admission / extraction behavior remains legible
- tests cover noise reduction without over-pruning

---

## Should Ship

### Gate 6: Stage 3 contradiction surfacing lands cleanly if it ships

If competing-hypothesis surfacing lands, it should:

1. remain bounded
2. stay legible in retrieval / projection truth
3. avoid turning Wave 42 into a whole-surface contradiction redesign

### Gate 7: Structural domain assistance improves extraction or retrieval

If structural context is used for better domain or task tagging, it should:

1. stay supportive rather than replacing content understanding
2. clearly improve a live seam
3. avoid flooding the substrate with low-value structural metadata

### Gate 8: Runtime refinements stay reversible

If extra runtime control refinements land, they should:

1. be easy to disable or reason about
2. remain local to the runtime seam
3. not silently become governance-policy sprawl

---

## Stretch

### Gate 9: Richer structural weighting lands only if v1 proves too weak

If richer structural weighting ships, it should:

1. clearly outperform the simpler prior
2. remain explainable
3. not pre-emptively import complexity just because the research exists

---

## Cut Line

Cut from the bottom first:

1. richer structural weighting beyond v1
2. contradiction Stage 3 extras
3. secondary structural-assisted tagging work
4. runtime refinement extras beyond adaptive evaporation

Do not cut:

1. lightweight structural analysis
2. structural topology prior v1
3. contradiction Stage 2 resolution upgrade
4. adaptive runtime evaporation

---

## Final Acceptance Statement

Wave 42 is acceptable when FormicOS is stronger in four ways:

1. **Structural intelligence** -- it can infer useful workspace/code structure
   cheaply.
2. **Topology intelligence** -- its initial topology prior is no longer mostly
   string matching.
3. **Epistemic intelligence** -- contradiction resolution respects
   contradiction vs complement vs temporal update.
4. **Runtime intelligence** -- exploration pressure adapts more intelligently
   under stagnation without destabilizing the normal path.
