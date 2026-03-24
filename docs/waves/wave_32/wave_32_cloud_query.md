# Wave 32 — Questions for Cloud Model

**Date:** 2026-03-18
**From:** Local orchestrator (plan audit + codebase verification)
**To:** Cloud planner
**Context:** Your Wave 32 plan has been refined and verified against the codebase. Several corrections were applied (see "Corrections from Local Audit" section at the bottom of the updated `wave_32_plan.md`). Before coder dispatch, we need your input on the following.

---

## 1. ADR-041: Write it or outline the decisions for local to write?

The plan gates Track A behind ADR-041. Three decisions need your architectural reasoning:

### D1: Gamma-decay formulation — confirm or revise

The plan uses:

```
alpha_new = gamma * alpha_old + (1 - gamma) * alpha_0 + reward
beta_new  = gamma * beta_old  + (1 - gamma) * beta_0  + (1 - reward)
```

With gamma=0.98, alpha_0=beta_0=5.0, reward=1 for success, 0 for failure.

**Questions:**
- Is the decay applied once per observation (per knowledge entry accessed by a colony), or once per colony completion (bulk decay across all entries)? The current code iterates per-entry per-colony-completion — so decay fires once per entry per colony. At 5 colonies/day accessing 10 entries each, a popular entry gets ~50 decay steps/day. That's a half-life of <1 day, not the ~7 days the plan assumes. **Should we apply decay only to entries that were actually accessed by the completing colony (current behavior), or to all entries?** If only accessed entries, the half-life depends on access frequency, not a fixed observation rate.
- Should there be a minimum alpha+beta floor to prevent the posterior from becoming too diffuse? The hard floor of 1.0 each means the prior can't go below Beta(1,1) = uniform, which seems reasonable. Confirm?
- The prior values (5.0, 5.0) are currently hardcoded as defaults in `MemoryEntry`. Should the gamma-decay implementation read them from the entry's initial values, or use constants? Constants are simpler and deterministic; reading from entries allows per-entry customization later.

### D2: Archival decay — choose the mechanism

Three options were presented. The plan recommends gamma-burst (option b):

```python
archival_gamma = 0.98 ** 10  # ≈ 0.817
new_alpha = archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA
new_beta  = archival_gamma * old_beta  + (1 - archival_gamma) * PRIOR_BETA
```

**Questions:**
- Why 10 rounds and not 5 or 20? Is there a principled basis, or is this a tuning knob to be calibrated empirically?
- Should the burst magnitude be configurable (e.g., in workspace config) or hardcoded?
- The current archival decay runs on ALL knowledge entries scoped to the archived thread. Should the gamma-burst apply the same way, or should it distinguish between entries that were actively used vs. dormant?

### D3: Scoring normalization — weight recalibration

After normalizing status_bonus and thread_bonus to [0, 1], the existing weights (0.35 semantic, 0.25 thompson, 0.15 freshness, 0.15 status, 0.10 thread) may no longer produce the same ranking behavior.

**Questions:**
- Do you have recommended recalibrated weights, or should the coder run the existing Thompson Sampling tests with normalized values and adjust empirically?
- The current `-0.5` default for unknown status becomes `0.0`. This changes the penalty for unknown-status entries from -0.075 contribution to 0.0 contribution. Is that acceptable, or should unknown remain penalized (e.g., map to a small positive like 0.1)?

---

## 2. B2 queen_runtime split — delegation pattern

The plan says "module-level async functions" for queen_tools.py. But these functions currently access `self` heavily (self._runtime, self._projections, self._emit_queen_message, etc.).

**Two approaches:**

**(a) Module-level functions with explicit params:**
```python
# queen_tools.py
async def tool_spawn_colony(runtime, projections, workspace_id, thread_id, params) -> str:
    ...
```
QueenAgent passes its internals explicitly to each call. Clean separation but verbose call sites.

**(b) Lightweight dispatcher class:**
```python
# queen_tools.py
class QueenToolDispatcher:
    def __init__(self, runtime, projections, emit_fn):
        self._runtime = runtime
        ...
    async def dispatch(self, tool_name, params) -> str:
        ...
```
QueenAgent instantiates the dispatcher once, delegates all tool calls. More OO but cleaner call sites.

**Which do you prefer for the coder prompt?** Or do you want a third option?

---

## 3. Remaining algorithm detail needed for coder prompts

The plan is well-specified for the structural work (B1-B4) and tests (C1-C6). But the coders will need more precision on:

### Gamma-decay test cases

The acceptance criterion says "entry observed 40 times at 50/50 then 5 more at 100% success — alpha rises meaningfully." Can you provide the expected numerical range? E.g., with gamma=0.98 and starting from Beta(5,5), after 40 observations at 50/50, what should alpha and beta approximately be? After 5 more successes, what's the expected alpha?

This matters because the coder needs to write an assertion with a tolerance, not just "meaningfully rises."

### Scoring weight tuning acceptance

How should the coder validate that recalibrated weights preserve the intended ranking behavior? Options:
- (a) Freeze current test rankings as golden — new weights must produce the same ordering
- (b) Define invariants (e.g., "verified entries always outrank stale entries at equal semantic similarity") and test those
- (c) Both

---

## 4. Scope call: C5 and C6

C5 (untested high-risk files) and C6 (MockLLM) are scope-gated. Given Wave 32's structural ambition, do you want to:

**(a)** Include C5+C6 in Wave 32 (adds ~2 coder sessions)
**(b)** Defer both to Wave 33 (keeps Wave 32 focused)
**(c)** Include C6 only (MockLLM is a force multiplier for C5 in Wave 33)

---

## 5. Anything else before coder dispatch?

The refined plan is at `docs/waves/wave_32/wave_32_plan.md`. All corrections from local audit are documented in the "Corrections from Local Audit" table at the bottom. The codebase is verified clean: 0 pyright errors, 0 ruff violations, 0 layer violations, 1,394 tests passing.

Once you answer the above, I'll generate coder dispatch prompts for Tracks B, C (parallel start), and A (after B lands).
