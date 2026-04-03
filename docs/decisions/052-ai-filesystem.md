# ADR-052: AI Filesystem — State/Artifact Separation + Amnesiac Forking

**Status:** Proposed
**Date:** 2026-03-29
**Wave:** 77 (Track B)

## Context

FormicOS has two of the three memory tiers that production agent systems
need (per knowledge base entry *Memory Architectures for Agent Systems*):

- **Episodic:** Event-sourced SQLite store (69 events, closed union)
- **Semantic:** Bayesian knowledge bank with Thompson Sampling retrieval

The missing tier is **working memory** — structured, file-backed intermediate
state that persists across context windows and sessions but is not
event-sourced or extracted into the knowledge bank.

The `.formicos/` directory already contains file-backed operational state
(journal, procedures, action queue, session summaries, thread plans, project
plan). But these mix intermediate reasoning artifacts with stable deliverables,
and nothing prevents the knowledge extraction pipeline from ingesting
intermediate scratchpad content.

Pan et al. ("Natural-Language Agent Harnesses," arXiv:2603.25723, March 2026)
validate a file-backed memory architecture with two concrete findings:

1. **State/Artifact separation:** Splitting intermediate state (`STATE_ROOT`)
   from final deliverables (`artifacts/`) prevents "knowledge poisoning" from
   intermediate hallucinations. Only artifacts feed into retrieval.
2. **Amnesiac context forking:** When a child agent fails, the orchestrator
   writes a reflection file and spawns a completely fresh child with only the
   task + reflection. No thread context bleed from the failed attempt. This
   yields 47.2% vs 30.4% task success on OSWorld (55% relative improvement)
   and reduces token waste from re-reading failed attempt context.

FormicOS is 80% aligned: colonies already start with fresh context each round
(budget-assembled, not conversation history). The gap: when the Queen retries
a failed colony via `retry_colony`, the retry currently inherits the Queen's
full thread context, which includes the failure discussion. The retry colony
re-reads the entire failed attempt's narrative instead of receiving a focused
reflection.

## Decision

### 1. Directory structure

Add two workspace-scoped roots under `.formicos/`, following the existing
`{category}/{workspace_id}/` convention used by operations, sessions, and
plans:

```
.formicos/
├── operations/{workspace_id}/  # (existing) journal, procedures, action queue
├── sessions/{thread_id}.md     # (existing) session summaries
├── plans/{thread_id}.md        # (existing) thread plans
├── runtime/{workspace_id}/     # NEW — intermediate state, ephemeral
│   ├── queen/                  # Queen reasoning scratchpad, decision logs
│   ├── colonies/{colony_id}/   # Per-colony working files
│   │   └── reflection.md       # Written on failure, consumed by retry
│   └── shared/                 # Cross-colony coordination state
└── artifacts/{workspace_id}/   # NEW — final deliverables, stable
    ├── plans/                  # Completed plans, milestone summaries
    └── deliverables/           # Colony output products
```

The `{category}/{workspace_id}` pattern matches `operations/{workspace_id}`
(operational_state.py), avoiding a third convention. Sessions and plans use
`{category}/{thread_id}` — these are thread-scoped, not workspace-scoped,
which is a distinct concern.

**Invariant:** `runtime/` files are NEVER extracted as knowledge entries.
The knowledge extraction seam is `extract_institutional_memory()` in
`colony_manager.py:2066` (called by `_hook_memory_extraction`). When colony
deliverables reference `runtime/` paths, extraction must skip them. Only
`artifacts/` content is eligible for knowledge extraction via the existing
`MemoryEntryCreated` path. (`transcript.py` is a pure formatter — the
extraction decision lives in `colony_manager.py`.)

### 2. Amnesiac context forking

When a colony fails and `_post_colony_hooks` runs with `succeeded=False`:

1. **Write reflection.** The hook writes
   `runtime/colonies/{colony_id}/reflection.md` containing:
   - Task description (truncated to 500 chars)
   - Failure reason (`colony.failure_reason` or `status={colony.status}`)
   - Rounds completed, quality score, stall count
   - Last round summary (fetched from `projections.colony_rounds`, truncated
     to 500 chars)
   - Strategy and caste composition

   The hook does NOT write reflection on success (`succeeded=True`) or on
   kill (kill path bypasses `_post_colony_hooks` via the Wave 76 completion
   guard).

2. **Thread `retry_of` through spawn.** The existing `retry_colony` Queen
   tool (`queen_tools.py:2540`) embeds the original colony ID in the retry
   task string (line 2584: `f"Previous attempt failed: {failure_reason}."`).

   **Persistence strategy:** `retry_of` is NOT stored as a projection field
   or event field. Instead, it is encoded in the colony's task text as a
   parseable prefix: `[retry_of:{original_colony_id}]`. The context
   assembly code (`assemble_context` in `context.py`) detects this prefix
   in the `round_goal` / colony task and uses it to locate the reflection
   file. This approach:
   - Is replay-safe (the task string is persisted in `ColonySpawned.task`)
   - Requires no changes to `ColonySpawned` event schema (closed union)
   - Requires no changes to `ColonyProjection` (no metadata bag exists)
   - Follows the existing `retry_colony` pattern of encoding context in task

   The `_on_colony_spawned` handler in `projections.py:993` already stores
   `e.task` on the projection. The prefix is available on replay.

3. **Amnesiac context assembly.** The retry path already lives in
   `_retry_colony()` in `queen_tools.py:2582-2589`, which builds a
   `retry_task` string containing the failure reason and original task.
   The change:

   - `_retry_colony()` stops embedding the failure context inline in the
     task string. Instead, it writes the `[retry_of:{colony_id}]` prefix
     and keeps the original task text clean.
   - `assemble_context()` in `engine/context.py:453` detects the
     `[retry_of:...]` prefix in the colony task. When found, it reads
     `runtime/colonies/{original_id}/reflection.md` from the data
     directory and injects it as an `input_source` (the existing
     `input_sources` parameter, ADR-033). This is the natural seam —
     `input_sources` already provides "chained colony context" at high
     attention position (2b in the assembly order).
   - **No thread context suppression needed.** Colony context assembly
     (`assemble_context`) does not inject Queen thread context — that's a
     Queen-layer concern. Colonies already get fresh context per round.
     The amnesiac benefit comes from replacing the inline failure dump
     (2000-5000 tokens of interleaved failure+retry discussion) with a
     focused reflection file (~300 tokens).

   This is the "amnesiac fork" from Pan et al.: the retry colony is born
   fresh with only the task, reflection (via input_source), and relevant
   knowledge.

### 3. Queen tools (2 new, 43 → 45)

| Tool | Description |
|------|-------------|
| `write_working_note` | Write/append to `runtime/queen/{filename}`. Creates parent dirs on first write. Appends by default, overwrites with `mode=overwrite`. |
| `promote_to_artifact` | Move a file from `runtime/` to `artifacts/`. Marks it as a stable deliverable eligible for knowledge extraction. |

Reading is handled by the `working_memory` budget slot — the Queen sees
`runtime/queen/` and `runtime/shared/` content automatically via context
injection. `list_working_files` and `read_working_note` are deferred until
the Queen demonstrably needs explicit read/list. Every additional tool
increases the tool selection surface and slightly degrades choice accuracy.

### 4. Context budget: 10th slot

Add `working_memory` as the 10th slot in `queen_budget.py`:

Live fractions from `queen_budget.py:27-37` (verified 2026-03-29):

| Slot | Current fraction | New fraction |
|------|-----------------|--------------|
| system_prompt | 0.15 | 0.14 |
| memory_retrieval | 0.13 | 0.12 |
| project_context | 0.08 | 0.08 |
| project_plan | 0.05 | 0.05 |
| operating_procedures | 0.05 | 0.05 |
| queen_journal | 0.04 | 0.04 |
| thread_context | 0.13 | 0.12 |
| tool_memory | 0.09 | 0.09 |
| conversation_history | 0.28 | 0.26 |
| **working_memory** | — | **0.05** |

The rebalancing shaves small amounts from the four largest slots
(conversation_history -0.02, system_prompt -0.01, memory_retrieval -0.01,
thread_context -0.01). New fractions sum to 1.00. No slot drops below its
fallback floor (the `max(fallback, proportional)` rule from ADR-051).

Fallback for `working_memory`: 400 tokens (matches `project_plan` floor).

Working memory injection reads all files under `runtime/queen/` and
`runtime/shared/`, prefixes each with a file manifest header (path + size),
and **truncates** oversized files tail-biased (keep the last N tokens within
the budget slot). The on-disk file is never modified during injection.

### 5. Summarize-on-overflow (background)

Actual file summarization runs during the operational sweep, not in the
write path:

1. The sweep identifies runtime files exceeding 2000 tokens
2. Schedules archivist-caste summarization (single LLM call)
3. Replaces the file with the summary + `[summarized at {timestamp}]` marker

This avoids introducing LLM calls into file I/O paths. The sweep already
runs every 30 minutes and has budget controls.

### 6. Colony write invariant

Colonies do NOT write to `runtime/` or `artifacts/` during round execution.
The events-only invariant for round execution is preserved. File writes
happen at two boundaries:

- **Post-colony hooks** (`_post_colony_hooks`): Write `reflection.md` on
  failure. Write deliverables to `artifacts/` on success (when the colony
  produces a final output artifact).
- **Queen tool invocation:** Queen writes to `runtime/queen/` via
  `write_working_note`, promotes files via `promote_to_artifact`.

### 7. No new events

Working memory is file-backed, not event-sourced. This is intentional:

- Working files are ephemeral task state, not institutional memory
- The knowledge bank (event-sourced) remains the durable store
- Events record *what happened* (colony succeeded/failed); files record
  *how the system reasoned about it*
- Pan et al. validate this: "frozen weights + file-backed state is the
  correct production architecture"

The `retry_of` field is projection metadata, not an event field. No changes
to the closed 69-event union.

## Consequences

### Positive

- **Amnesiac forking reduces retry token waste.** Failed attempt context
  (2000-5000 tokens of stack traces) no longer re-read by retry colonies.
  More retries within the same daily budget.
- **Knowledge poisoning prevented.** Intermediate scratchpad content cannot
  enter the Bayesian knowledge system. Only promoted artifacts are eligible.
- **Queen gains persistent scratchpad.** Multi-step reasoning survives
  context window compression and session boundaries.
- **Zero event-schema impact.** No new events, no changes to the closed
  union, no migration.

### Negative

- **File I/O in the critical path.** Reflection writes in `_post_colony_hooks`
  add disk I/O to the colony completion path. Mitigated: single small file
  write, async-compatible.
- **Stale runtime files accumulate.** Workspace completion should clean up
  `runtime/`. Sweep summarization handles oversized files but not abandoned
  workspaces.
- **Two new Queen tools.** Tool selection surface grows from 43 to 45.
  Minimal impact given the existing tool surface size.

### Deferred (Wave 78+)

- **Executable NLAHs:** Elevating operating procedures to stage-gated
  contracts (NLAH Recommendation 2). Requires a `StageGate` concept in the
  operational state layer.
- **Orchestrator-only charter hardening:** Auditing Queen tools for
  delegation-only purity (NLAH Recommendation 3).

## References

- Pan, Zou, Guo, Ni, Zheng. "Natural-Language Agent Harnesses."
  arXiv:2603.25723, March 2026.
- Knowledge base: *Memory Architectures for Agent Systems* (score 1.0)
- Knowledge base: *Scratchpads and Working Memory Patterns* (score 1.0)
- Knowledge base: *Context Window Budget Allocation* (score 1.0)
- Knowledge base: *Context Compression Techniques* (score 0.667)
- ADR-051: Dynamic Queen Context Caps (budget slot system)
- ADR-046: Self-Maintenance (post-colony hooks, sweep)
