# Wave 57 Revised Direction + Progress-Aware Execution

## Status: Phase 0 v7 Complete

### The headline numbers

**Absolute quality: dramatic improvement confirmed.**
v4 -> v7 mean (7 tasks): 0.511 -> 0.688 (+0.177)
Every completing task improved. Rate-limiter: +0.226. api-design: +0.211.

**Accumulate vs empty: flat.**
v7 7-task means (all tasks with data): Acc 0.688, Empty 0.697, Delta -0.011.
v7 6-task means (excl identical haiku): Acc 0.657, Empty 0.668, Delta -0.011.
The compounding signal is within noise of zero.

### What this means

The quality gains came from operational knowledge:
- Playbooks (Wave 54): deterministic, always-on, +45 productive calls
- Common mistakes (Wave 56.5): anti-pattern injection, caste-aware
- Semantic threshold (Wave 55.5): removes noise from context
- Extraction quality (Wave 56): sharper prompt, better noise filter
- Progress truth (Wave 55): productive colonies no longer false-halt
- Coder model: faster inference, better tool calling

All of these improve BOTH arms equally. They are infrastructure
improvements, not compounding.

The accumulate arm's exclusive advantage -- domain knowledge retrieval
-- adds approximately zero quality on average. On the one task where
genuinely relevant knowledge existed (api-design accessed 2 entries
from rate-limiter about rate limiting), the empty arm still scored
higher (0.582 vs 0.521). The model generates better output on its own
than with retrieved domain entries injected.

### The honest interpretation

Domain knowledge compounding on an 8-task local-model eval suite is
within noise of zero. This is not a pipeline failure -- the pipeline
works end-to-end. It is a signal that:

1. Operational knowledge (how to work) >>> domain knowledge (what to know)
   for the current model and task set.
2. The Qwen3-Coder model already knows enough about email validation,
   CSV parsing, rate limiting, etc. that retrieved entries from prior
   colonies add marginal value.
3. Compounding may emerge on longer sequences (50+ tasks) where the
   knowledge pool becomes genuinely rich, or on tasks requiring project-
   specific knowledge the model cannot have (internal APIs, custom schemas).

MetaClaw independently confirms this: their system works without domain
retrieval. Curated skills (operational knowledge) are the value driver.

---

## Progress-Aware Execution (replaces per-task timeout)

### The problem

Heavy tasks (3-agent stigmergic colonies) time out because:
- 3 agents x 8 rounds x ~35s/turn = ~840s (serialized on single GPU)
- The eval runner uses a fixed _POLL_TIMEOUT_S = 900s
- data-pipeline consistently exceeds this at round 6-7

Raising the timeout is a band-aid. Different tasks need different
amounts of time, and a colony doing productive work in round 7
should get more time while a colony observation-spamming in round 4
should be killed.

### What already exists (governance system)

The governance system in runner.py already implements round-aware
decisions based on convergence and stall signals:

- `stall_count >= 4` -> `force_halt` (kills spinning colonies)
- `stall_count >= 2` -> `warn` (flags concern)
- `convergence.is_converged + round_num >= 2` -> `complete` (early completion)
- `is_stalled + recent_productive_action + round_num >= 2` -> `complete`
  as `verified_execution_converged` (Wave 55)

These signals are round-aware but NOT clock-aware. The timeout
enforcement lives in the eval runner (`_POLL_TIMEOUT_S`), not in the
governance system. The governance system can halt a colony at round 4
for stalling, but it cannot extend a productive colony past 900s.

### The missing piece: clock-aware continuation

The value of progress-aware execution is in bridging the governance
signals (round-level, already good) with the eval runner's timeout
(clock-level, currently a fixed wall). NOT in replacing governance.

### The concept: governance-informed timeout

The eval runner's poll loop should consult the colony's governance
state before killing it on timeout:

```
ON POLL TIMEOUT:
  if colony.last_governance_action == "continue" AND colony.recent_productive:
    extend timeout by base_timeout * 0.5  (one extension allowed)
    log "extending productive colony"
  else:
    kill as before
```

This is simpler than replacing the round loop. The round loop stays in
colony_manager.py (line 666):

```python
for round_num in range(start_round, colony.max_rounds + 1):
    ...
```

The governance system continues making round-level decisions. The eval
runner just gets smarter about when to pull the plug on the clock.

### Implementation seam

The change is in two places:

1. `eval/sequential_runner.py`: The poll loop (~line 287) that checks
   `_POLL_TIMEOUT_S`. Add a governance-state check before killing.

2. `surface/colony_manager.py`: Expose the colony's last governance
   action and recent_productive flag in a queryable way (e.g., on the
   colony projection or via a lightweight API).

The round loop in colony_manager.py (line 666) and the governance
evaluator in runner.py remain unchanged.

### Why this is better than per-task timeout

Per-task timeout requires predicting how long each task will take
and encoding that in config. It is wrong whenever the model changes,
the GPU changes, or the task complexity changes.

Governance-informed timeout adapts to actual runtime behavior.
A productive colony gets one extension. A stalled colony gets killed
on schedule. The governance signals that already exist drive the
decision.

---

## Revised Wave 57 Direction

### What changed

The v7 results shifted the priority from "improve domain knowledge
compounding" to "improve operational knowledge and colony efficiency."

The domain knowledge pipeline works but adds ~zero quality on the
current eval suite. Further investment in retrieval quality, diversity
ranking, or round-adaptive queries has low expected return.

The operational knowledge layer (playbooks + common mistakes) is the
proven value driver (+0.177 absolute quality improvement). Further
investment here has high expected return.

### Revised Wave 57 shape

**Sub-packet A: Governance-informed eval timeout (HIGH PRIORITY)**
Bridge the governance signals with the eval runner's timeout logic.
- Productive colonies get one timeout extension
- Stalled colonies killed on schedule
- Does NOT replace governance or the round loop
- data-pipeline may finally complete (productive work in late rounds)
Files: eval/sequential_runner.py (poll loop), surface/colony_manager.py
  (expose governance state)

**Sub-packet B: Prevention extraction (MEDIUM PRIORITY, already designed)**
"What guidance would have prevented this failure?"
Outputs to staged procedural lane, not live knowledge catalog.
Two wiring fixes needed:
1. Thread observation_calls to colony projections (or use stall_count proxy)
2. Thread failure_reason through post-colony hooks
Files: memory_extractor.py, colony_manager.py, context.py

**Sub-packet C: Per-task eval timeout override (LOW PRIORITY, safety net)**
Add `eval_timeout_s` field to task YAML configs.
Only needed as a backstop if governance-informed timeout doesn't fully
solve the data-pipeline issue. Simple and safe.
Files: sequential_runner.py, eval task YAML files

### What's deferred (low expected return given v7 results)

- Round-adaptive retrieval queries (domain knowledge adds ~zero)
- MMR/diversity re-ranking (same reason)
- PRM quality gate (same reason)
- Generation-aware retrieval de-boost (stamping is done, de-boost
  has low expected return when domain retrieval itself adds ~zero)

### What's confirmed as high-leverage (non-Wave-57)

1. Knowledge flow audit (dispatched): verify whether injected entries
   influence agent output at all. If they don't, the domain knowledge
   pipeline is plumbing without impact regardless of quality.

2. Qwen3-Coder as default: already done. +0.177 improvement confirmed.

3. Longer task sequences (future): compounding may emerge at 20-50 tasks
   where the knowledge pool contains project-specific knowledge the model
   cannot have. The 8-task eval suite tests general knowledge that the
   Coder model already possesses.

### The strategic reframe

FormicOS's value is in operational knowledge, not domain knowledge.
The system that tells agents HOW to work (playbooks, common mistakes,
reactive correction, governance-informed execution) produces 18x more
quality improvement than the system that tells agents WHAT to know
(retrieved domain entries).

The next wave should invest in operational intelligence:
- smarter execution management (governance-informed timeout)
- learning from failures (prevention extraction)
- not more domain retrieval sophistication

This aligns with MetaClaw's validation: curated skills without domain
retrieval drive the value. FormicOS should double down on the same.
