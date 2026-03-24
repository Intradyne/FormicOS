# Wave 37 Acceptance Gates

This document compresses the Wave 37 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- [wave_37_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_37/wave_37_plan.md)

---

## Must Ship

### Gate 1: The stigmergic loop is visibly more closed than in Wave 36

All of the following must be true:

1. Colony topology initialization can be biased by relevant, high-confidence
   knowledge rather than always starting neutral.
2. Accessed knowledge entries receive quality-aware reinforcement rather than a
   flat success/failure update.
3. The system can detect narrowing search breadth through branching-style
   diagnostics and surface it before obvious collapse.

Passing evidence:
- Gate 3 must already have landed; Gate 1 depends on the benchmark harness and
  measurement substrate existing
- repeated-domain benchmark runs show measurable change
- the system can explain the new signals in operator-visible or debug-visible
  form

### Gate 2: The project surface is externally safer and more credible

All of the following must be true:

1. The repo has a documented security disclosure path.
2. Existing CI has been augmented with visible security tooling.
3. The contribution surface is legally and operationally safer:
   - CLA path defined
   - contribution guidance hardened
   - governance and conduct docs exist

Passing evidence:
- repo-owned files and workflows are committed
- admin-owned steps are documented clearly where operator action is required

### Gate 3: FormicOS can measure whether Pillar 1 helped

All of the following must be true:

1. There is an internal benchmark harness for repeated-domain work.
2. Colony outcome calibration is measurable against task correctness.
3. Retrieval cost is instrumented.
4. Branching metrics are logged or inspectable.
5. At least basic ablation support exists for the new Pillar 1 features.

Passing evidence:
- the harness runs locally/CI
- benchmark output can distinguish Wave 36 baseline from Wave 37 features

### Gate 4: Poisoning-defense foundation exists before Wave 38 widens surfaces

All of the following must be true:

1. There is a clear admission-scoring seam in the knowledge-ingestion path.
2. Retrieved entries expose provenance and trust rationale more clearly.
3. Federation trust discounting has been reviewed and does not allow weak
   foreign entries to dominate strong local ones by default.

Passing evidence:
- operator-facing retrieval surfaces can answer "why does the system trust this?"
- the codebase has a clean hook where richer intake gating can land later

---

## Should Ship

### Gate 5: Operator data collection is live and honest about what is inferable

The system should silently collect:

- `knowledge_feedback`
- `ColonyKilled`
- directive usage patterns
- suggestion follow-through where it is legitimately inferable from existing
  replay-safe signals

Important constraint:
- do not claim exact accepted/rejected suggestion tracking unless it is truly
  replay-safe under the current event surface

### Gate 6: Adaptive evaporation is recommendation-capable

The Queen should be able to recommend domain-specific decay adjustments using:

- prediction errors
- reuse half-life
- maintenance activity
- operator feedback

This remains recommendation-only in Wave 37.

### Gate 7: Critical regressions are pinned down

The wave should leave behind fixtures for:

- poisoned-entry retrieval dominance
- decay behavior
- federation trust dominance
- truthful outcome labeling for solved coding colonies

---

## Stretch

### Gate 8: Triple-tier retrieval foundation exists without becoming a premature default

If retrieval compression ships, all of the following must be true:

1. Triple extraction is implemented as a derived projection.
2. Triple-tier retrieval escalates conservatively to richer tiers.
3. Benchmark results show lower retrieval cost with no measurable success-rate
   regression.

If those conditions are not met, the projection may still land, but default
activation should not.

---

## Cut Line

If Wave 37 runs long, cut in this order:

1. staged triple-first retrieval activation
2. triple extraction itself
3. adaptive evaporation recommendations
4. richer operator-behavior inference

Do **not** cut:

1. knowledge-weighted topology initialization
2. outcome-weighted reinforcement
3. branching diagnostics
4. trust foundations
5. benchmark harness
6. poisoning-defense foundation

Those are the wave.

---

## Final Acceptance Statement

Wave 37 should only be called landed if FormicOS is more trustworthy in all
three senses:

- **substrate trust:** the stigmergic loop is more truthful and measurable
- **project trust:** the repo is safer to adopt and contribute to
- **governance trust:** the system collects and surfaces enough evidence to make
  later autonomy and ecosystem expansion responsible
