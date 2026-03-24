# Phase 0 Task Set — Wave 53

## Suite: `phase0`

8 tasks calibrated for local Qwen3-30B-A3B (Q4_K_M, RTX 5090).

### Why This Set

- **Simple tasks (3)**: email-validator, json-transformer, haiku-writer
  - Local model can reliably produce working code for these
  - Early tasks seed knowledge entries for later tasks to consume
  - haiku-writer is deliberately cross-domain (creative, not code) as a control

- **Moderate tasks (5)**: csv-analyzer, markdown-parser, rate-limiter, api-design, data-pipeline
  - Within local model capability range but benefit from earlier patterns
  - csv-analyzer and data-pipeline can reuse patterns from json-transformer
  - api-design tests design reasoning, not just code generation
  - rate-limiter tests concurrency concepts (harder for local models)

### Why Not Complex Tasks

The existing complex tasks (event-store, plugin-system, cli-framework, notification-system,
refactor-plan) require multi-file coordination, heavy-tier models, and 15-20 rounds. Local
Qwen3-30B-A3B typically stalls or produces low-quality output on these. Including them would
measure "local model weakness" rather than "system compounding."

### Task Order Rationale

Tasks are ordered so that knowledge produced by earlier tasks *could* be consumed by later
tasks if the retrieval system is working:

1. email-validator → Python validation patterns, test case conventions
2. json-transformer → data structure manipulation, dict/list patterns
3. haiku-writer → creative control (no code knowledge carries over)
4. csv-analyzer → data processing (should benefit from json-transformer patterns)
5. markdown-parser → parsing (independent domain, tests baseline)
6. rate-limiter → concurrency (independent domain, tests baseline)
7. api-design → design reasoning (can reference earlier code patterns)
8. data-pipeline → multi-stage data (strongest compounding candidate)

### Measurement Arms

| Arm | Knowledge Mode | Purpose |
|-----|---------------|---------|
| `accumulate` | Shared workspace, knowledge carries forward | Does retrieval + accumulation help? |
| `empty` | Fresh workspace per task, no carry-over | Baseline without compounding |

### Realistic for Local Model?

Yes. Qwen3-30B-A3B at Q4_K_M can:
- Write working Python functions for simple/moderate tasks
- Follow structured instructions (email validation, CSV parsing)
- Produce test cases when asked
- Struggle but produce partial output for moderate design tasks

The model will likely:
- Score higher on simple tasks (0.4-0.7 range)
- Score mixed on moderate tasks (0.0-0.5 range)
- Not reach the 0.7 threshold needed for learned-template generation on most tasks

This is expected and is itself useful measurement data.

### Per-Task Configuration

All tasks use suite-level overrides: budget=$2.00, max_rounds=10, stigmergic strategy.
Task-level castes are preserved from the task YAML definitions.
