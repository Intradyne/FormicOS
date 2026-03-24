# Phase 0 Measurement Matrix

Defines the ablation dimensions for evaluating FormicOS colony effectiveness.
This is a measurement protocol, not a running benchmark. The goal is to
understand which capabilities contribute real value so that future waves can
invest wisely.

## Dimensions

| Dimension | Baseline (off) | Treatment (on) | What it measures |
|-----------|---------------|----------------|------------------|
| **Grounded recipes** | Pre-Wave 48 generic prompts | Wave 48+ caste-grounded prompts | Recipe quality impact on colony outcomes |
| **Fast path** | All tasks use full colony | Trivial tasks use fast_path=true | Coordination overhead vs. speed for simple work |
| **Knowledge retrieval** | Knowledge disabled (no memory_search results) | Knowledge enabled (normal retrieval) | Whether institutional knowledge improves colony quality |
| **Web foraging** | Forager disabled | Forager enabled (reactive + proactive) | Whether web-acquired knowledge fills real gaps |
| **Template suggestion** | No template matching | Templates proposed in preview (Wave 50) | Whether learned templates improve repeat-task quality |

## Protocol

### Task corpus

Select a repeatable set of tasks across categories:

- Code implementation (simple, moderate, complex)
- Code review
- Research / Q&A
- Multi-step orchestration

Minimum 5 tasks per category to reduce noise. Each task must have a clear
success criterion (test pass, artifact quality, knowledge extraction count).

### Execution

For each dimension:

1. Run the task corpus with the dimension OFF (baseline)
2. Run the same corpus with the dimension ON (treatment)
3. Record per-task: quality_score, rounds, cost, duration, entries_extracted

Hold all other dimensions constant when testing one. Full factorial
(2^5 = 32 combinations) is expensive; start with single-dimension ablations
and add interaction tests only where hypotheses suggest synergy.

### Metrics

| Metric | Source | Higher is better? |
|--------|--------|-------------------|
| Quality score | ColonyOutcome.quality_score | Yes |
| Round efficiency | quality / rounds | Yes |
| Cost efficiency | quality / cost | Yes |
| Knowledge yield | entries_extracted per colony | Yes (with quality floor) |
| Template reuse rate | template-matched tasks / total tasks | Yes (Wave 50 only) |

### Baseline establishment

Before Wave 50 template suggestion can be measured, establish baselines for
the other four dimensions. This gives a clean before/after comparison once
learned templates land.

## What this does NOT measure

- LLM model quality (held constant across runs)
- Operator satisfaction (subjective, needs separate instrument)
- Federation value (requires multi-instance setup)
- Long-term knowledge compounding (requires longitudinal study)

## Sequencing

1. **Now:** Document this matrix (this file)
2. **Next:** Establish baselines for dimensions 1-4 using the outcomes API
   (`GET /api/v1/workspaces/{id}/outcomes`)
3. **After Wave 50 templates land:** Add dimension 5 measurement
4. **After sufficient data:** Identify interaction effects between dimensions
