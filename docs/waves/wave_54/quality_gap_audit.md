# Wave 54 Quality Gap Audit

**Date:** 2026-03-21
**Auditor:** Claude (operator-directed)
**Status:** Complete

## Executive summary

Wave 54 produced a categorical behavioral shift: 0 to 45 productive tool calls
across two smoke tasks. Quality scores are flat (0.19-0.25 for moderate tasks,
unchanged from baseline). The root cause is a **structural formula ceiling**,
not a measurement error or model failure.

**Root cause:** `compute_quality_score()` uses a weighted geometric mean where
`round_efficiency = max(1 - rounds_completed/max_rounds, 0.01)`. Any colony
that uses all its rounds gets 0.01, contributing `0.25 * ln(0.01) = -1.15` to
the log sum. This alone caps the maximum possible quality at **exp(-1.15) = 0.316**
regardless of how productive the colony is. Low convergence (a side effect of
productive output changing each round) drags it further to 0.19-0.25.

**Hypothesis verdict:**
- **H1 (model writes garbage): PARTIALLY CONFIRMED.** Simple tasks produce real
  code via `code_execute`. Moderate tasks suffer from a parse pipeline failure
  where `write_workspace_file` content arrives empty (0-byte files) and
  `code_execute` code is sometimes truncated. The model generates code but the
  Hermes JSON parser can't reliably extract large argument values.
- **H2 (formula blind to productivity): CONFIRMED.** The formula has zero
  productivity signal. A colony that writes code 19 times scores the same as
  one that observation-spams, given identical round/convergence/governance stats.
- **H3 (convergence misfires): PARTIALLY CONFIRMED.** Productive colonies have
  LOW convergence (not high stability triggering is_stalled) because each round's
  output is different. The detector correctly says "not stalled" but also says
  "not converged" since progress oscillates. This drags the convergence component.

**Recommended fix:** Path A+B hybrid (see Phase 5).

---

## Phase 1: Artifact classification

### Workspace files: all 0 bytes

Every Python file across all 22 workspace directories on the Docker stack is
**0 bytes**. 15 empty files, 0 non-empty files. The `write_workspace_file`
handler (`runner.py:1941-1954`) receives `arguments.get("content", "")` and
writes it. The path argument survives parsing (correct directory structures
are created), but the content argument arrives empty.

### code_execute: real code for simple tasks, empty for moderate

| Colony | Task | exit_code | code_preview | Classification |
|--------|------|-----------|-------------|----------------|
| colony-f01d2913 | email-validator | 0 | `import re; def validate_email(email)...` (RFC 5322 regex, 15+ test cases, PASS output) | **Real implementation** |
| colony-8ca8a608 | json-transformer | 0 | Real code (department/role grouping) | **Real implementation** |
| colony-bc87cd06 | csv-analyzer | 0 (1st), -1 (4x) | Empty code_preview on all 5 executions | **Parse failure** |
| colony-bd5f3a78 | markdown-parser | mixed | 12 code_execute calls, mixed results | **Partial** |

### Interpretation

The model CAN generate real code at 3.3B active parameters (email-validator
proves it). Simple tasks fit in a single short turn where the parser succeeds.
Moderate tasks require longer tool-call arguments; the Hermes JSON parser
truncates or drops the content/code fields.

**H1 verdict:** The bottleneck for moderate tasks is the parse pipeline, not
model capability. The model calls the right tools in the right order (the
playbook works) but its arguments don't survive parsing.

---

## Phase 2: Quality formula decomposition

### The formula (colony_manager.py:267-291)

```python
round_efficiency = max(1.0 - (rounds_completed / max(max_rounds, 1)), 0.01)
convergence_score = max(convergence, 0.01)
governance_score = max(1.0 - (governance_warnings / 3.0), 0.01)
stall_score = max(1.0 - (stall_rounds / max(rounds_completed, 1)), 0.01)

quality = exp(0.25*ln(re) + 0.30*ln(cs) + 0.25*ln(gs) + 0.20*ln(ss))
```

### Arm 2 (empty knowledge) decomposition

| Task | rounds | q_actual | round_eff | re_contrib | conv | cs_contrib | gov | stall | notes |
|------|--------|----------|-----------|------------|------|------------|-----|-------|-------|
| email-validator | 1/3 | **0.9036** | 0.667 | -0.101 | 1.00 | 0.000 | 1.00 | 1.00 | Governance complete round 1 |
| json-transformer | 1/3 | **0.9036** | 0.667 | -0.101 | 1.00 | 0.000 | 1.00 | 1.00 | Governance complete round 1 |
| haiku-writer | 1/3 | **0.9036** | 0.667 | -0.101 | 1.00 | 0.000 | 1.00 | 1.00 | Governance complete round 1 |
| csv-analyzer | 5/5 | **0.1911** | 0.01 | **-1.151** | 0.19 | **-0.503** | 1.00 | 1.00 | Maxed rounds + low conv |
| markdown-parser | 4+ | **0.0000** | - | - | - | - | - | - | Timeout |
| rate-limiter | 8/? | **0.2477** | 0.01 | **-1.151** | 0.44 | -0.244 | 1.00 | 1.00 | Maxed rounds |
| api-design | 8/? | **0.2359** | 0.01 | **-1.151** | 0.40 | -0.275 | 1.00 | 1.00 | Maxed rounds |
| data-pipeline | 8/? | **0.2517** | 0.01 | **-1.151** | 0.48 | -0.220 | 1.00 | 1.00 | Maxed rounds |

### Key finding: round_efficiency is the dominant drag

For every moderate task, `round_efficiency = 0.01` contributes **-1.151** to the
log sum. This alone caps quality at `exp(-1.151) = 0.316`.

Convergence adds another -0.22 to -0.50 depending on the task, bringing the
final score to the 0.19-0.25 range.

Governance warnings and stall count are both 0 for all colonies. The convergence
detector does NOT flag these as stalled (stability never exceeds 0.95 because
the model produces different output each round). So the stall/governance
machinery is not the problem -- the round_efficiency floor is.

### Why convergence is low for productive colonies

Convergence is computed via embedding similarity between round summaries and
the goal (`runner.py:2258-2286`):

```python
score = 0.4 * goal_alignment + 0.3 * stability + 0.3 * min(1.0, progress * 5.0)
```

For csv-analyzer, convergence oscillated: `0.57 -> 0.23 -> 0.41 -> 0.69 -> 0.19`.
The model wrote different things each round (incremental progress), so stability
stayed low and progress fluctuated. The last-round convergence (0.19) is what
enters the quality formula, which is essentially random depending on which round
happens to be last.

---

## Phase 3: Differential diagnosis

### email-validator (q=0.90) vs csv-analyzer (q=0.19)

| Component | email-validator | csv-analyzer | Delta | Cause |
|-----------|----------------|-------------|-------|-------|
| round_efficiency | 0.667 (-0.10) | 0.01 (-1.15) | **-1.05** | Used all rounds |
| convergence | 1.00 (0.00) | 0.19 (-0.50) | **-0.50** | Productive output varies |
| governance | 1.00 (0.00) | 1.00 (0.00) | 0.00 | No warnings either way |
| stall | 1.00 (0.00) | 1.00 (0.00) | 0.00 | Not stalled either way |
| **quality** | **0.9036** | **0.1911** | **-0.71** | |

The gap is **entirely** round_efficiency (-1.05) + convergence (-0.50).

email-validator succeeds because it completes in 1 round. The model generates
a working `validate_email()` function in a single turn, governance says
"converged," done. Round 1 of 3 gives round_efficiency = 0.667.

csv-analyzer fails the formula because it needs multiple rounds to build up
the implementation. The model is doing the right thing (writing code, testing,
iterating) but the formula penalizes using rounds and having varied output.

### Tool call comparison (Arm 2)

| Task | productive | observation | total | prod_ratio |
|------|-----------|------------|-------|-----------|
| email-validator | 4 | 1 | 5 | 0.80 |
| csv-analyzer | 11 | 13 | 24 | 0.46 |
| rate-limiter | 20 | 21 | 41 | 0.49 |
| api-design | 10 | 16 | 26 | 0.38 |
| data-pipeline | 9 | 14 | 23 | 0.39 |

The playbook moved moderate tasks from ~0% productive to 38-49% productive.
The formula cannot see this.

---

## Phase 4: Parse pipeline assessment

The AgentTurnCompleted events do not carry parse_defensive metadata (not in the
event schema). Parse failures are visible only in application logs, not in the
event store.

**Indirect evidence:**
- email-validator `code_execute`: real code in `code_preview` (RFC 5322 regex, 200+ chars)
- csv-analyzer `code_execute` #1: empty `code_preview`, exit=0 (empty code runs successfully)
- csv-analyzer `code_execute` #2-5: empty `code_preview`, exit=-1 (empty/broken code fails)
- csv-analyzer Arm 1 `code_execute` #1: `print('Hello, World!')` -- trivial code survived
- csv-analyzer Arm 1 `code_execute` #2: empty `code_preview`
- All `write_workspace_file` calls: 0-byte files (content argument empty)

**Pattern:** Short tool-call arguments survive parsing. Long arguments
(full code implementations in `content` or `code` fields) are truncated to
empty. The parse pipeline has a practical ceiling on argument size that
correlates with task complexity.

**Impact on quality:** Even if the formula were fixed, moderate-task colonies
cannot benefit from `verified_execution_converged` (requires successful
`code_execute`) when the code argument is empty. The parse pipeline is a
prerequisite fix for any quality improvement on moderate tasks.

---

## Phase 5: Root cause and recommended fix

### Root cause chain (ordered by impact)

1. **Round efficiency structural floor.** `max(1 - rounds/max_rounds, 0.01)`
   gives 0.01 for any colony that uses all rounds. This contributes -1.15 to
   the log sum, capping quality at 0.316. A productive colony that iterates
   across all rounds is penalized identically to one that observation-spams.
   *Files:* `colony_manager.py:279`

2. **No productivity signal in formula.** The formula measures convergence
   hygiene (round efficiency, convergence, governance, stalls). It has zero
   visibility into productive tool calls, workspace artifacts, or code
   execution success.
   *Files:* `colony_manager.py:267-291`

3. **Parse pipeline truncates large arguments.** The Hermes JSON parser
   fails to extract long `content`/`code` arguments from tool calls. This
   means `write_workspace_file` creates 0-byte files and `code_execute`
   often runs empty code. The playbook gets the model to call the right tools,
   but the arguments don't survive.
   *Files:* Parse pipeline in adapter layer (not audited in detail here)

4. **Convergence penalizes productive variation.** Colonies that produce
   different output each round (incremental code progress) get low convergence
   because embedding stability is low. This is correct behavior for the
   convergence detector (the colony isn't converging) but wrong for quality
   assessment (the colony is making progress).
   *Files:* `runner.py:2258-2286`

### Recommended fix: Path A (add productivity signal) + targeted formula fix

**Fix 1: Soften round_efficiency floor** (colony_manager.py:279)

Current: `max(1.0 - (rounds_completed / max(max_rounds, 1)), 0.01)`

This gives 0.01 (a 99% penalty) for using all rounds. A colony that
productively uses 5/5 rounds should not score the same as one that wastes
5/5 rounds.

Proposed: `max(1.0 - (rounds_completed / max(max_rounds, 1)), 0.20)`

Raising the floor from 0.01 to 0.20 means using all rounds contributes
`0.25 * ln(0.20) = -0.40` instead of `-1.15`. This changes the max-rounds
quality ceiling from 0.316 to 0.670, enough to differentiate productive
colonies from non-productive ones via other signals.

**Fix 2: Add productive_ratio as 5th quality signal** (colony_manager.py:267-291)

Add a new parameter `productive_calls: int = 0, total_calls: int = 0` and
compute:

```python
productive_ratio = max(productive_calls / max(total_calls, 1), 0.01)
```

Rebalance weights: re=0.20, cs=0.25, gs=0.20, ss=0.15, pr=0.20.

This directly measures the behavioral shift Wave 54 created.

**Threading:** `productive_calls` and `total_calls` are already tracked in
`runner.py` (Wave 54 reactive correction counters). They need to be returned
in `RoundResult` and accumulated in `colony_manager.py`'s round loop.

**Fix 3: Fix parse pipeline (separate investigation)**

The 0-byte workspace files are the prerequisite for moderate-task quality.
Until the parse pipeline can reliably extract large tool-call arguments,
`write_workspace_file` is behaviorally correct but functionally broken for
anything beyond trivial content. This is NOT a formula fix -- it's an adapter
layer investigation into the Hermes JSON parser's handling of multi-KB
argument values.

### What NOT to fix

- **Convergence detector:** It's working correctly. Low convergence for
  productive-but-not-converging colonies is accurate. The fix belongs in the
  quality formula (productivity signal), not in the convergence computation.
- **Governance evaluator:** Zero warnings and zero stalls for all moderate
  tasks. It's not the bottleneck.
- **verified_execution_converged:** The aggressive `and not round_had_failed_code_execute`
  clause is theoretically too strict (one failed execute zeros out the
  escape hatch even if others succeeded), but it's not firing as a bottleneck
  in these runs because colonies aren't marked as stalled in the first place.

---

## Summary table

| Phase | Finding | Impact |
|-------|---------|--------|
| 1. Artifacts | 0-byte workspace files, real code only in simple-task code_execute | Parse pipeline truncates large arguments |
| 2. Formula | round_efficiency=0.01 contributes -1.15, caps quality at 0.316 | Structural ceiling regardless of productivity |
| 2. Formula | convergence=0.19-0.44 for productive colonies | -0.22 to -0.50 additional drag |
| 2. Formula | governance=1.0, stalls=0 for all moderate tasks | Not contributing to low scores |
| 3. Differential | email-validator vs csv-analyzer gap is entirely round_eff + convergence | Formula can't distinguish productive from non-productive round use |
| 4. Parse | code_preview empty for moderate tasks, real for simple tasks | Argument-size-dependent parse failure |
| 5. Root cause | Formula floor + missing productivity signal + parse pipeline | Three-layer problem |

---

## Fixes applied during audit

None. This was a diagnostic-only audit.
