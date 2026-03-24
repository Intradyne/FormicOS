This document compresses the Wave 46 plan into the smallest set of gates that
must be true before the wave can be accepted as landed.

Primary source of truth:
- [wave_46_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_46/wave_46_plan.md)

---

## Must Ship

### Gate 1: The Forager becomes operator-visible and operator-controllable

All of the following must be true:

1. The operator can trigger a bounded manual forage from a product surface.
2. The operator can inspect forage cycle history without reading raw logs.
3. The operator can see and change domain trust/distrust/reset state.
4. The implementation reuses existing forager service and projection truth.
5. No new event type or subsystem was added just to expose the surface.

Passing evidence:

- route(s) exist for manual forage, domain override, and cycle history
- route(s) call the existing Forager service or emit existing events
- the projection-backed history is served, not rebuilt ad hoc
- no benchmark-only API was introduced

### Gate 2: Web-sourced knowledge is visibly distinct in the normal UI

All of the following must be true:

1. Entries with forager provenance read as web-sourced knowledge.
2. The operator can inspect source URL and at least the core provenance fields.
3. The change reuses existing entry metadata.
4. Colony-generated entries do not regress.

Passing evidence:

- a visible web-source badge or equivalent indicator exists
- source URL is surfaced
- at least one of fetch timestamp / forager query / source credibility is shown
- the UI reads existing provenance fields instead of inventing parallel truth

### Gate 3: Observability and outbound policy become more coherent

All of the following must be true:

1. The OTel adapter is optionally wired beside JSONL.
2. The default local path remains simple when OTel is off.
3. Search/fetch policy becomes more consistent if that change lands.
4. No telemetry or search redesign was required.

Passing evidence:

- app startup can add OTel sink when enabled
- JSONL remains intact
- any search consistency work stays inside the current seams

### Gate 4: The eval harness becomes contamination-safe and causally useful

All of the following must be true:

1. Repeated runs do not reuse the same workspace truth by accident.
2. `knowledge_used` is populated from replay-safe access truth.
3. Entry attribution can point back to prior task/colony output.
4. A manifest or equivalent run-truth artifact is written beside results.

Passing evidence:

- clean-room workspace IDs or equivalent run isolation exists
- eval output includes non-empty `knowledge_used` on real runs
- attribution can identify where an accessed entry came from
- manifest fields include commit/config/run truth

### Gate 5: Measurement begins from honest infrastructure, not wishful thinking

All of the following must be true:

1. Phase 0 harness validation is possible and documented.
2. At least a pilot suite path exists beyond the original 7-task default.
3. The analysis layer can aggregate more than one run if it claims variance.
4. No benchmark-specific runtime path was introduced.

Passing evidence:

- pilot/full/benchmark suites or equivalent structure exist
- analysis tooling can handle multi-run inputs if multi-run reporting is claimed
- the product runtime does not special-case benchmark tasks

### Gate 6: The wave stays product-first

All of the following must be true:

1. Every product change can be defended for real operator use.
2. No suite-only heuristics were added to product code.
3. No new event types, adapters, or subsystems were added.
4. The benchmark is still treated as a demo of the product, not its purpose.

Passing evidence:

- event union stays at 62
- packet scope remains within existing product/eval seams
- no change exists only to score better on a fixed task list

---

## Should Ship

### Gate 7: Forager activity becomes legible in operator briefing surfaces

If this lands, it should:

1. reuse existing forage cycle/domain strategy truth
2. stay inside the current briefing/product surfaces
3. avoid turning the briefing into a new dashboard subsystem

### Gate 8: Multi-run statistics stay bounded and honest

If this lands, it should:

1. add bootstrap/paired comparisons or equivalent bounded rigor
2. avoid a bespoke data-science subsystem
3. remain tied to actual run artifacts

### Gate 9: Documentation tells the post-Wave-46 truth

If the docs pass lands, it should:

1. describe new forager operator surfaces accurately
2. describe eval manifest/clean-room truth accurately
3. avoid overclaiming publication-quality results before the data exists

---

## Gated / If Data Warrants

### Gate 10: Full-rigor sweep happens only after the pilot shows signal

If a larger matrix lands, it should:

1. follow a successful pilot/core-proof phase
2. avoid burning cost before the harness truth is established
3. stop early if the data already answers the question

### Gate 11: Publication artifacts happen only after honest measurement

If leaderboard submission or preprint prep lands, it should:

1. use real measured artifacts
2. report uncertainty and cost honestly
3. avoid framing benchmark score as the product thesis
