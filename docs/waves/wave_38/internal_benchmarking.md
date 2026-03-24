# Wave 38 Internal Benchmarking

**Status:** Internal measurement only. Not a public benchmark result.

## What the suite measures

The internal benchmark harness extends the Wave 37 repeated-domain suite with
two harder task types inspired by public benchmark styles:

### Task types

| Type | Count | Inspiration | What it tests |
|------|-------|-------------|---------------|
| Repeated-domain | 7 | Wave 37 harness | Knowledge accumulation benefit |
| HumanEval-style | 5 | HumanEval function tasks | Single-function correctness at easy/medium/hard |
| SWE-bench-style | 4 | SWE-bench multi-file fixes | Cross-file reasoning, regression testing |

### Metrics reported per task

- **Success** — binary pass/fail (quality > 0.4 threshold)
- **Quality score** — [0.0, 1.0] composite from architectural signals
- **Wall time** — milliseconds for the benchmark evaluation pass
- **Estimated cost** — token-based cost proxy
- **Retrieval cost** — proportional to knowledge items used

### Ablation configurations

| Label | 1A Knowledge Prior | 1B Quality Reinforcement | 1C Branching Diagnostics |
|-------|-------------------|-------------------------|------------------------|
| baseline | off | off | off |
| 1A | on | off | off |
| 1B | off | on | off |
| 1C | off | off | on |
| 1A+1B+1C | on | on | on |

## What it does NOT prove

- These are not end-to-end LLM execution benchmarks. They exercise the
  architectural signal paths (knowledge prior, quality-weighted reinforcement,
  branching diagnostics) without calling a real LLM.
- Results reflect whether the **architecture distinguishes configurations**,
  not whether any configuration produces correct code in production.
- The suite is intentionally small and deterministic. It is not a stand-in for
  Aider Polyglot or any public leaderboard.

## Where the architecture helped

- **Knowledge accumulation** (1A): Repeated-domain tasks with accumulated
  knowledge entries show measurably stronger topology priors than cold starts.
- **Quality-weighted reinforcement** (1B): Higher-alpha domain knowledge
  produces quality bonuses that differentiate from baseline.
- **Feature composition** (1A+1B+1C): The full feature set consistently
  scores >= any individual feature, confirming the signals are complementary.

## Where it did not help (yet)

- **Novel domains**: Control tasks in domains without prior knowledge show
  minimal benefit from the knowledge prior (expected and correct behavior).
- **Hard algorithmic tasks**: Difficulty penalties dominate the quality signal
  for hard HumanEval-style tasks. The architecture provides modest improvement
  but does not overcome fundamental difficulty.
- **Multi-file reasoning**: SWE-bench-style tasks benefit from knowledge but
  the cross-file cost penalty is significant. Wave 39 adaptation may help.

## What Wave 39 should tune

1. **Knowledge prior strength**: The current prior deviation from neutral is
   modest. Tuning the prior's influence on topology could amplify the benefit
   for repeated-domain tasks without hurting novel-domain cold starts.
2. **Quality-weighted delta range**: The [0.5, 1.5] reinforcement clip is
   conservative. Expanding the range for high-confidence domains could improve
   knowledge exploitation.
3. **Cross-file cost model**: Multi-file tasks accumulate cost linearly with
   files involved. Smarter context assembly could reduce retrieval overhead.
4. **Difficulty-aware escalation**: The escalation outcome matrix now provides
   evidence for when capability escalation helps. Auto-escalation policy
   should reference these outcomes.

## Escalation outcome matrix

The escalation outcome matrix is a replay-derived view that reads from
governance-owned `routing_override` on colony projections. It reports:

| Field | Source |
|-------|--------|
| colony_id | ColonyOutcome |
| starting_tier | Inferred default ("light") |
| escalated_tier | routing_override.tier |
| reason | routing_override.reason |
| round_at_override | routing_override.set_at_round |
| total_cost | ColonyOutcome.total_cost |
| pre_escalation_cost | Sum of round costs before override |
| post_escalation_cost | total_cost - pre_escalation_cost |
| duration_ms | ColonyOutcome.duration_ms |
| quality_score | ColonyOutcome.quality_score |
| succeeded | ColonyOutcome.succeeded |

### What it excludes

Provider fallback is **not** included. Provider fallback is router-owned
infrastructure resilience (LLMRouter._complete_with_fallback). Capability
escalation is governance-owned and visible through routing_override.

### API endpoint

```
GET /api/v1/workspaces/{workspace_id}/escalation-matrix
```

Returns summary statistics and per-colony escalation details.

## Running the suite

```bash
# All benchmarks
pytest tests/integration/test_wave38_benchmarks.py -v

# Escalation matrix tests
pytest tests/integration/test_wave38_escalation_matrix.py -v

# Wave 37 harness (preserved)
pytest tests/integration/test_wave37_stigmergic_loop.py -v

# Full suite
pytest tests/integration/ -v -k "wave3"
```
