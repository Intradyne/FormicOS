# Wave 37 Team 3 - Operator Data + Adaptive Evaporation + Retrieval Stretch

## Role

You own the governance-trust and future-autonomy foundation track of Wave 37.

Your job is to:

- collect operator behavior signals honestly under the closed event model
- make adaptive evaporation recommendation-capable
- and, only if the core work is solid, build the triple-tier retrieval
  foundation as a conservative stretch

This is the "collect the right evidence now so later autonomy is earned" track.

## Read first

1. `CLAUDE.md`
2. `AGENTS.md`
3. `docs/waves/wave_37/wave_37_plan.md`
4. `docs/waves/wave_37/acceptance_gates.md`
5. `docs/research/stigmergy_knowledge_substrate_research.md`

## Coordination rules

- No new event types. The union stays at 55.
- Be honest about what is inferable under the current event stream.
- Do not invent exact suggestion-accept/reject tracking if it is not replay-safe.
- Team 1 shares `surface/proactive_intelligence.py` for branching diagnostics.
- Team 2 shares `surface/knowledge_catalog.py` for trust/provenance surfacing.
- Pillar 5 is stretch. If time gets tight, leave it untouched rather than
  compromising Pillar 4.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `src/formicos/surface/projections.py` | OWN | operator-behavior derived views, additive projection support, triple projection if Pillar 5 ships |
| `src/formicos/surface/proactive_intelligence.py` | MODIFY | adaptive-evaporation recommendation rules only |
| `src/formicos/surface/queen_runtime.py` | MODIFY | Queen recommendation surfacing for adaptive evaporation |
| `src/formicos/surface/knowledge_catalog.py` | MODIFY | Pillar 5 only: additive triple-tier prefilter / escalation path |
| `src/formicos/surface/routes/api.py` | MODIFY | only if additive read-only projection access is required for owned features |
| `tests/unit/surface/test_wave37_operator_behavior.py` | CREATE | operator-signal projection tests |
| `tests/unit/surface/test_wave37_evaporation.py` | CREATE | adaptive-evaporation recommendation tests |
| `tests/unit/surface/test_tiered_retrieval.py` | MODIFY | only if Pillar 5 ships |
| `tests/unit/surface/test_wave37_triples.py` | CREATE | only if Pillar 5 ships |

## DO NOT TOUCH

- `src/formicos/core/*`
- `src/formicos/engine/*`
- `src/formicos/surface/colony_manager.py` - Team 1 owns
- `src/formicos/surface/proactive_intelligence.py` branching diagnostics - Team 1 owns
- `src/formicos/surface/knowledge_catalog.py` retrieval/scoring semantics - Team 1 owns
- `src/formicos/surface/knowledge_catalog.py` trust/provenance surfacing - Team 2 owns
- `.github/*` - Team 2 owns
- `SECURITY.md` - Team 2 owns
- `GOVERNANCE.md` - Team 2 owns
- `CODE_OF_CONDUCT.md` - Team 2 owns
- `CONTRIBUTING.md` - Team 2 owns
- benchmark harness core files - Team 1 owns

## Overlap rules

- `src/formicos/surface/proactive_intelligence.py`
  - You own adaptive-evaporation recommendations only.
  - Team 1 owns branching diagnostics only.
- `src/formicos/surface/knowledge_catalog.py`
  - You touch it only if Pillar 5 ships.
  - Your scope there is only the additive triple-tier prefilter /
    staged-escalation path.
  - Team 1 owns baseline retrieval/scoring.
  - Team 2 owns trust/provenance metadata surfacing.

---

## 4A. Adaptive evaporation recommendations

Build recommendation-only domain-specific decay guidance.

### Required scope

- keep current decay-class defaults untouched
- derive candidate domain overrides from:
  - prediction errors
  - reuse half-life
  - refresh-colony frequency
  - operator `knowledge_feedback`
- surface recommendations through Queen-facing or operator-facing channels

### Constraints

- no automatic tuning
- no new events
- keep the recommendation rationale inspectable

### What success looks like

The Queen can recommend a domain-specific decay adjustment and explain the
evidence behind it.

---

## 4B. Operator behavior data collection

Collect silently. Use later.

### Signals you may collect directly or derive

- `knowledge_feedback` activity inferred from `MemoryConfidenceUpdated` events
  where tool-initiated feedback is attributable, or from colony round
  tool-call traces
- `ColonyKilled`
- directive usage patterns
- suggestion follow-through where accepted behavior is inferable from a
  matching subsequent colony spawn

### Critical honesty constraint

Do **not** claim exact accepted/rejected suggestion tracking unless it is truly
replay-safe under the current event surface.

For Wave 37, the correct behavior is:

- infer **accepted** suggestions when a matching colony spawn follows closely
  enough to be defensible
- do **not** invent exact **rejected** tracking if the event surface does not
  support it cleanly

### What success looks like

After enough use, the projections can answer questions like:

- which categories this operator acts on
- which categories are usually ignored
- which directive patterns tend to be sent to which colony types

without changing the event model.

---

## 4C. Design operator data and adaptive evaporation together

The adaptive-evaporation logic should actually consume the evidence collected in
4B where appropriate. Repeated operator demotions in a domain are exactly the
kind of signal that should influence recommendation output.

Do not implement future earned autonomy. Just make sure the substrate makes
sense for it.

---

## 5. Triple-tier retrieval foundation (stretch only)

Only do this if 4A/4B are solid.

### Required scope if you do it

1. derive a triple-style lightweight projection
2. query that tier first as a cheap prefilter
3. escalate conservatively to richer tiers when confidence is low

### Hard constraints

- no new event types
- projection-first
- fallback-safe
- do not change default retrieval semantics unless measurements justify it

### What success looks like

- the triple tier exists and is testable
- escalation is conservative
- no regression is introduced by default behavior

If the data is not clearly good, leave the projection in place and do not force
default activation.

---

## Acceptance targets for Team 3

1. Operator behavior signals are collected honestly under the current event
   model.
2. Adaptive-evaporation recommendations are evidence-backed and recommendation-only.
3. The operator-data model and evaporation recommendations are designed to work
   together.
4. If Pillar 5 ships, triple-tier retrieval is additive, conservative, and
   non-disruptive.
5. No new event types were added.

## Validation

```bash
python scripts/lint_imports.py
python -m pytest -q
```

If Pillar 5 ships and touches retrieval/UI seams, also run:

```bash
cd frontend && npm run build
```

## Required report

- exact files changed
- which operator signals are directly collected vs inferred
- how you avoided overclaiming exact suggestion rejection tracking
- what adaptive-evaporation recommendation logic landed
- how operator feedback influences those recommendations
- whether Pillar 5 shipped
- if Pillar 5 shipped, how the triple-tier path escalates safely
- confirmation that no new event types were added
