# Wave 32 — Cloud Model Response to Orchestrator Questions

**Date:** 2026-03-18
**From:** Cloud planner
**To:** Local orchestrator
**Context:** Response to wave_32_cloud_query.md questions. All decisions below are incorporated into the updated wave_32_plan.md and ADR-041.

---

## 1. ADR-041 Decisions

### D1: Gamma-decay — TIME-BASED, not per-observation

The orchestrator caught a critical flaw. The original plan assumed "5 observations per day" as a fixed rate, but the current code applies confidence updates **per entry per colony completion**. A knowledge entry accessed by 10 colonies/day gets 10 decay steps/day, not 5. A popular entry accessed by every colony gets 50+ decay steps/day. At gamma=0.98, that's a half-life of ~0.7 days — the system would forget everything within 3 days.

**The fix is to apply decay based on wall-clock time, not observation count.**

```python
elapsed_days = (event_timestamp - entry_last_updated_timestamp) / 86400.0
gamma_effective = GAMMA_PER_DAY ** elapsed_days  # GAMMA_PER_DAY = 0.98

alpha_new = gamma_effective * alpha_old + (1 - gamma_effective) * PRIOR_ALPHA + reward
beta_new  = gamma_effective * beta_old  + (1 - gamma_effective) * PRIOR_BETA  + (1 - reward)
```

This way the decay rate is **independent of access frequency**. An entry accessed once per day and an entry accessed 50 times per day both decay at the same calendar rate. The half-life is `ln(0.5) / ln(0.98)` = ~34.3 days (not observations). Multiple observations on the same day barely decay because `elapsed_days` is small between them. Entries not observed at all don't decay at all until they're next accessed — which is fine because they're not influencing retrieval if they're not being accessed.

**`entry_last_updated_timestamp`** comes from the projection's existing `created_at` field or, better, from the timestamp of the most recent `MemoryConfidenceUpdated` event for that entry. The projection handler for `MemoryConfidenceUpdated` already stores `new_alpha` and `new_beta` — add a `last_confidence_update` timestamp field to the `memory_entries` projection dict. This is derived projection state, replay-safe.

**On the alpha+beta floor:** Yes, the hard floor of 1.0 each (Wave 31) is correct. Beta(1,1) is the uniform distribution — maximum uncertainty, maximum exploration. Going below that creates U-shaped distributions that are pathological. Confirm the floor stays.

**On prior source:** Use constants (`PRIOR_ALPHA = 5.0`, `PRIOR_BETA = 5.0`), not per-entry values. Constants are simpler, deterministic, and mean every entry decays toward the same baseline. Per-entry customization is a Wave 33+ feature if ever needed.

### D2: Archival decay — gamma-burst at 30-day equivalent

The "10 rounds" from the original plan was a tuning knob, not a principled derivation. Revised to **30 calendar days equivalent.**

```python
ARCHIVAL_EQUIVALENT_DAYS = 30
archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS  # 0.98^30 ≈ 0.545
```

This means archiving a thread halves the confidence of its knowledge entries — a meaningful but not catastrophic penalty. Entries that were genuinely good will recover if re-accessed. Entries that were mediocre will drift toward the prior and be naturally explored less.

**Hardcoded, not configurable.** This is an internal decay parameter, not an operator-facing tuning knob. If it needs changing, it's a code change with an ADR update, not a config toggle. Keep the system predictable.

**Apply to all thread-scoped entries uniformly** (same as current behavior). Don't distinguish active vs dormant.

### D3: Scoring normalization — specific weights provided

**Normalized status bonus:**
```python
_STATUS_BONUS = {"verified": 1.0, "active": 0.8, "candidate": 0.5, "stale": 0.0}
# Unknown/missing: 0.0 (no penalty — treated as "no information")
```

**Normalized thread bonus:** `{0.0, 1.0}` (was `{0.0, 0.25}`).

**Recalibrated weights:**
```python
WEIGHTS = {
    "semantic": 0.40,   # was 0.35
    "thompson": 0.25,   # unchanged
    "freshness": 0.15,  # unchanged
    "status": 0.12,     # was 0.15
    "thread": 0.08,     # was 0.10
}
# Sum: 1.00
```

**Validate with invariants, not frozen rankings:**
1. At equal semantic similarity and freshness, verified always outranks stale
2. At equal everything else, thread-matched outranks non-matched
3. Thompson Sampling produces different rankings on successive calls (exploration working)
4. Very old entry (freshness=0.0) can still rank highly if verified and semantically relevant

---

## 2. B2 delegation pattern — QueenToolDispatcher class

**(b) QueenToolDispatcher** is the right choice. The tool functions access `self._runtime` on nearly every call — for projections, emit_and_broadcast, llm_router, vector_store, template loading. Passing all of these as explicit parameters to 16+ module-level functions creates verbose call sites that obscure intent. The dispatcher class captures the shared dependencies once at construction.

```python
# queen_tools.py
class QueenToolDispatcher:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime

    async def dispatch(
        self, name: str, inputs: dict, workspace_id: str, thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        if name == "spawn_colony":
            return await self._spawn_colony(inputs, workspace_id, thread_id)
        ...
```

Same pattern for `queen_thread.py` — a `QueenThreadManager` class. Both take `runtime` as their single constructor dependency.

---

## 3. Algorithm precision

### Gamma-decay numerical expectations

With the **time-based** formulation (GAMMA_PER_DAY=0.98, PRIOR=5.0):

**Scenario: Entry starts at Beta(5,5). Colony accesses it once per day for 40 days, alternating success/failure (50/50).**

Each day: `gamma_effective = 0.98^1 = 0.98`.

After observation 1 (success, day 1):
```
alpha = 0.98 * 5.0 + 0.02 * 5.0 + 1.0 = 6.0
beta  = 0.98 * 5.0 + 0.02 * 5.0 + 0.0 = 5.0
```

After 40 days alternating, both alpha and beta stabilize around ~5.5. After 5 more consecutive successes, posterior mean should be in [0.58, 0.72].

**Simpler test assertions:**
- After 100 alternating observations (1/day): `alpha + beta < 20` (decay prevents unbounded accumulation)
- After success: `new_alpha > old_alpha` AND `new_alpha < old_alpha + 1.0` (decay ate some)

### Scoring validation

Use **invariants only** (option b). Four invariants as listed above. Coder constructs synthetic `_composite_key` inputs that exercise each invariant.

---

## 4. Scope call: C6 only (option c)

Include C6 (MockLLM) only. The MockLLM is a force multiplier: once it records calls and returns configurable responses, every test in C5 and every future wave benefits. Defer C5 to Wave 33.

---

## 5. Additional notes

**ADR-041 should be written by the orchestrator, not the coder.** The decisions are fully specified above. Draft ADR-041, get operator approval, then dispatch coders.

**Track A prerequisite:** The `last_confidence_update` timestamp on the projection dict is a new derived field. Set by `_on_memory_entry_created` (initial = created_at) and updated by `_on_memory_confidence_updated` (value = event timestamp). Call this out explicitly in the Track A coder prompt.
