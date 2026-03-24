# Wave 32 — Track A Coder Dispatch: Knowledge Tuning

**Wave:** 32
**Track:** A — Knowledge Tuning (After Track B Lands)
**Prerequisite:** Track B MUST be complete. ADR-041 MUST be operator-approved.
**Gate:** Do NOT start this track until Track B is integrated and all tests pass on the post-B codebase.

---

## Coordination rules

- **Read `CLAUDE.md` and `docs/decisions/041-knowledge-tuning.md` before starting.**
- **Read `docs/contracts/` before modifying any interface.**
- **If your change contradicts an ADR, STOP and flag the conflict.**
- **Event types are a CLOSED union of 48 — do NOT add new events.**
- Root `AGENTS.md` may be historical. This dispatch prompt and `docs/waves/wave_32/wave_32_plan.md` are the active coordination source for Wave 32.
- ADR-041 is the authoritative source for all algorithm decisions in this track.

---

## Your file ownership

You may ONLY modify these files:

| File | Task | Notes |
|------|------|-------|
| `surface/colony_manager.py` | A1 | Gamma-decay in `_hook_confidence_update` (post-B3 hook) |
| `surface/projections.py` | A1 | Add `last_confidence_update` field to memory_entries |
| `surface/queen_thread.py` | A2 | Archival decay redesign (post-B2 extraction) |
| `surface/knowledge_catalog.py` | A3 | Scoring normalization + weight recalibration |
| Test files for A1-A3 | A1-A3 | New test files as needed |

**Do NOT touch:** `core/events.py`, `core/types.py`, `engine/runner.py`, `surface/queen_runtime.py`, `surface/queen_tools.py`, `adapters/vector_qdrant.py`, `docs/decisions/041-knowledge-tuning.md` (already written).

**IMPORTANT:** Track B will have restructured the code before you start. The file structure will be different from what you see if you read the pre-B codebase:
- `_post_colony_hooks` in `colony_manager.py` is now decomposed into 6 named hooks. The confidence update is in `_hook_confidence_update`.
- `queen_runtime.py` is split into 3 files. Archival decay logic is in `queen_thread.py` under `QueenThreadManager`.
- `RoundRunner` takes a `RunnerCallbacks` dataclass.

Read the actual post-B code before implementing. The line numbers below reference the PRE-B codebase for context only.

---

## Task A1: Time-based gamma-decay for Thompson Sampling confidence

**Goal:** Replace the current "add 1.0 to alpha or beta" confidence update with time-based gamma-decay that decays toward the prior before adding the new observation. See ADR-041 D1.

### Step 1: Add `last_confidence_update` to projections

In `surface/projections.py`, modify two handlers:

**`_on_memory_entry_created` (pre-B line 724):**
When creating a new memory entry in the `memory_entries` projection dict, add:
```python
"last_confidence_update": e.data.get("created_at", "")
```

**`_on_memory_confidence_updated` (pre-B line 771):**
When updating confidence, also set:
```python
entry["last_confidence_update"] = event_timestamp_as_iso_string
```

The event timestamp comes from the `MemoryConfidenceUpdated` event. Check how the handler currently extracts the timestamp — it may be `e.data["timestamp"]` or similar. Use the event's own timestamp, not `datetime.now()`.

### Step 2: Replace confidence update logic in colony_manager.py

The confidence update is in `_hook_confidence_update` (post-B3 extraction). The current logic (pre-B at `colony_manager.py:778-785`) is:

```python
# CURRENT — replace this
old_alpha = float(entry.get("conf_alpha", 5.0))
old_beta = float(entry.get("conf_beta", 5.0))
if succeeded:
    new_alpha = old_alpha + 1.0
    new_beta = old_beta
else:
    new_alpha = old_alpha
    new_beta = old_beta + 1.0
```

**Replace with (ADR-041 D1):**

```python
from datetime import datetime, timezone

GAMMA_PER_DAY = 0.98
PRIOR_ALPHA = 5.0
PRIOR_BETA = 5.0

old_alpha = float(entry.get("conf_alpha", PRIOR_ALPHA))
old_beta = float(entry.get("conf_beta", PRIOR_BETA))

# Time-based decay: elapsed time since last confidence update
last_updated = entry.get("last_confidence_update", entry.get("created_at", ""))
if last_updated:
    elapsed_days = (event_ts - datetime.fromisoformat(last_updated)).total_seconds() / 86400.0
    elapsed_days = max(elapsed_days, 0.0)  # guard against clock skew
else:
    elapsed_days = 0.0

gamma_eff = GAMMA_PER_DAY ** elapsed_days

# Decay toward prior, then add observation
decayed_alpha = gamma_eff * old_alpha + (1 - gamma_eff) * PRIOR_ALPHA
decayed_beta  = gamma_eff * old_beta  + (1 - gamma_eff) * PRIOR_BETA

if succeeded:
    new_alpha = max(decayed_alpha + 1.0, 1.0)
    new_beta  = max(decayed_beta, 1.0)
else:
    new_alpha = max(decayed_alpha, 1.0)
    new_beta  = max(decayed_beta + 1.0, 1.0)
```

**Where does `event_ts` come from?** This is the timestamp of the colony completion event that triggers the confidence update. Check how the hook receives its timestamp — it may need to be passed from the dispatcher or derived from the colony completion event. Use event timestamps only, never `datetime.now()`.

**Event-sourcing determinism:** The decay computation happens here in the surface layer. The `MemoryConfidenceUpdated` event that gets emitted carries the final `new_alpha` and `new_beta`. The projection handler applies those values directly. This means replay is deterministic — the decay is baked into the event, not recomputed during replay.

### Step 3: Write tests

Create `tests/unit/surface/test_gamma_decay.py` with:

1. **Basic decay test:** Entry at Beta(5,5), elapsed_days=1.0, success → verify `new_alpha = 0.98*5.0 + 0.02*5.0 + 1.0 = 6.0` (within tolerance)
2. **No-decay on same timestamp:** Entry at Beta(5,5), elapsed_days=0.0, success → `new_alpha = 5.0 + 1.0 = 6.0` (no decay component)
3. **Accumulation cap:** After 100 alternating observations (1/day), `alpha + beta < 20` (decay prevents unbounded growth)
4. **Alpha rises after success:** `new_alpha > old_alpha` AND `new_alpha < old_alpha + 1.0` (when elapsed_days > 0)
5. **Hard floor:** Entry decayed to near-minimum → verify `alpha >= 1.0` and `beta >= 1.0`
6. **Replay determinism:** Apply same sequence of (timestamp, success/fail) pairs twice → identical results

**Numerical expectations from ADR-041:**
- Entry starts at Beta(5,5). Observed once per day for 40 days alternating success/failure. Alpha and beta stabilize around ~5.5.
- After 5 more consecutive successes, posterior mean should be in [0.58, 0.72].

**Acceptance:**
- Time-based decay replaces simple increment
- `last_confidence_update` field set on creation and updated on confidence change
- Tests demonstrate decay prevents convergence lock
- Uses event timestamps only — no `datetime.now()` or `time.time()`
- All existing tests pass

---

## Task A2: Archival decay redesign — gamma-burst at 30-day equivalent

**Goal:** Replace the asymmetric archival decay formula with a symmetric gamma-burst. See ADR-041 D2.

**Current formula (pre-B in queen_runtime.py:1330-1331, post-B in queen_thread.py):**
```python
new_alpha = max(old_alpha * 0.8, 1.0)
new_beta = max(old_beta * 1.2, 1.0)
```

**Replace with (ADR-041 D2):**

```python
GAMMA_PER_DAY = 0.98  # same constant as A1 — import or define once
PRIOR_ALPHA = 5.0
PRIOR_BETA = 5.0
ARCHIVAL_EQUIVALENT_DAYS = 30

archival_gamma = GAMMA_PER_DAY ** ARCHIVAL_EQUIVALENT_DAYS  # 0.98^30 ≈ 0.545

new_alpha = max(archival_gamma * old_alpha + (1 - archival_gamma) * PRIOR_ALPHA, 1.0)
new_beta  = max(archival_gamma * old_beta  + (1 - archival_gamma) * PRIOR_BETA, 1.0)
```

**Properties to preserve:**
- Applied uniformly to ALL thread-scoped entries (same as current behavior)
- Hard floor: `max(..., 1.0)` prevents going below Beta(1,1)
- Hardcoded constants — no config toggles

**Location:** Post-B2, the archival decay logic lives in `queen_thread.py` under `QueenThreadManager`. Find the `archive_thread` tool handler and update the decay formula there.

### Write tests

Add to an existing test file or create `tests/unit/surface/test_archival_decay.py`:

1. **Symmetry:** After archival decay, verify `new_alpha / (new_alpha + new_beta)` ≈ `old_alpha / (old_alpha + old_beta)` (posterior mean preserved)
2. **Convergence toward prior:** Entry at Beta(20, 5) → after archival → alpha closer to 5.0, beta closer to 5.0
3. **Magnitude:** Entry at Beta(20, 20) → `archival_gamma = 0.545`, so new_alpha ≈ `0.545*20 + 0.455*5 = 13.17` — verify within tolerance
4. **Hard floor:** Entry at Beta(1.5, 1.5) → after archival → both still ≥ 1.0
5. **Not a reset:** Entry at Beta(50, 2) → after archival → alpha still > PRIOR_ALPHA (strong signal partially retained)

**Acceptance:**
- Archival decay is symmetric (both alpha and beta decay toward prior at same rate)
- Does not bias posterior mean
- Hard floor preserved
- All existing archival decay tests pass (they may need assertion updates since the formula changed)

---

## Task A3: Scoring normalization

**Goal:** Normalize status_bonus and thread_bonus to [0,1], recalibrate composite weights. See ADR-041 D3.

**Location:** `surface/knowledge_catalog.py`. The composite scoring function is `_composite_key` (find it — it's the function that computes the weighted sum of semantic, thompson, freshness, status, and thread signals).

### Status bonus normalization

**Current (pre-A at knowledge_catalog.py:124-127):**
```python
_STATUS_BONUS = {"verified": 0.3, "active": 0.25, "candidate": 0.0, "stale": -0.2}
# Unknown/missing defaults to -0.5
```

**Replace with:**
```python
_STATUS_BONUS = {"verified": 1.0, "active": 0.8, "candidate": 0.5, "stale": 0.0}
# Unknown/missing: 0.0 (no information, treated as stale)
```

### Thread bonus normalization

**Current (pre-A at knowledge_catalog.py:137):**
```python
_THREAD_BONUS = 0.25
```

**Replace with:**
```python
_THREAD_BONUS = 1.0  # weight 0.08 already scales contribution
```

### Weight recalibration

**Current weights (find them in `_composite_key` or nearby):**
```python
# Old: 0.35 semantic, 0.25 thompson, 0.15 freshness, 0.15 status, 0.10 thread
```

**Replace with:**
```python
WEIGHTS = {
    "semantic": 0.40,   # dominant signal, slightly increased
    "thompson": 0.25,   # exploration budget, unchanged
    "freshness": 0.15,  # unchanged
    "status": 0.12,     # reduced — [0,1] range wider than old [-0.5, 0.3]
    "thread": 0.08,     # reduced — [0,1] range wider than old [0, 0.25]
}
# Sum: 1.00
```

### Update unknown-status default

Find where the default for unknown/missing status is set (previously `-0.5`). Change to `0.0`.

### Write invariant tests

Create `tests/unit/surface/test_scoring_invariants.py`:

1. **Invariant 1:** At equal semantic similarity and freshness, a verified entry always outranks a stale entry
2. **Invariant 2:** At equal everything else, a thread-matched entry outranks a non-matched entry
3. **Invariant 3:** Thompson Sampling produces different rankings on successive calls with same inputs (exploration working) — use a seeded RNG or run multiple times and assert not-all-identical
4. **Invariant 4:** A very old entry (freshness=0.0) can still rank highly if verified and semantically relevant (freshness doesn't dominate)

Construct synthetic inputs to `_composite_key` (or the scoring function) that exercise each invariant. You'll need to understand the function signature — read the code first.

**Do NOT use frozen golden rankings.** The invariants should be structural properties, not specific numerical values.

**IMPORTANT:** There is NO parallel composite scoring in `surface/memory_store.py`. Memory store delegates to Qdrant's native scoring. Only `knowledge_catalog.py` needs changes.

**Acceptance:**
- All signals in `_composite_key` are in [0, 1]
- Weights sum to 1.00
- 4 invariant tests pass
- Existing Thompson Sampling ranking tests pass after recalibration (they may need assertion updates)
- `pyright src/` clean

---

## Shared constants

Tasks A1 and A2 both use `GAMMA_PER_DAY`, `PRIOR_ALPHA`, `PRIOR_BETA`. Define them once and import. Options:
- A module-level constants block in `colony_manager.py` that `queen_thread.py` imports
- A small `surface/knowledge_constants.py` if you prefer isolation
- Constants in both files (last resort — duplication)

Pick whichever is cleanest. The values are:
```python
GAMMA_PER_DAY = 0.98
PRIOR_ALPHA = 5.0
PRIOR_BETA = 5.0
ARCHIVAL_EQUIVALENT_DAYS = 30
```

---

## Validation (run before declaring done)

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All four must pass. Zero regressions.

**Track A acceptance summary:**
1. Gamma-decay: entry observed 40 times at 50/50 then 5 more at 100% success — alpha rises meaningfully
2. Gamma-decay: replay of same events produces identical confidence values
3. Archival decay: symmetric, converges toward prior not toward zero, hard floor holds
4. Scoring: all signals in [0,1], weights sum to 1.00, 4 invariant tests pass
5. `last_confidence_update` field set on creation and updated on confidence change
6. Uses event timestamps only — no system clock calls
7. All existing tests pass

---

## Do NOT

- Add new events (union stays at 48)
- Reduce the prior from Beta(5,5) — that's deferred to Wave 33 (ADR-041 D4)
- Use Reciprocal Rank Fusion — it's rejected (ADR-041 D5)
- Modify files owned by Track B or Track C
- Use `datetime.now()` or `time.time()` for decay calculations — use event timestamps only
- Make the archival equivalent days configurable — hardcoded per ADR-041 D2
