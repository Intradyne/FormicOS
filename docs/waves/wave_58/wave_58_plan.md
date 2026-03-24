# Wave 58 Integration Plan

**Date**: 2026-03-22
**Features**: Specificity Gate, Trajectory Storage, Progressive Disclosure
**Teams**: 3 parallel coder teams
**Reference**: `wave_58_design.md` (architecture decisions, pseudocode, rationale)

---

## Pre-flight checklist

### CI baseline

Confirm before dispatch:
- 3448+ tests passing (3456 collected, 8 pre-existing failures)
- 8 pre-existing failures:
  - 3 prompt line-count (`test_prompt_line_counts`, `test_under_130_lines`,
    `test_prompt_within_line_limit`)
  - 2 wave8_wiring MagicMock (`test_runner_receives_tier_budgets`,
    `test_state_pushed_after_completion`)
  - 1 colony_manager confidence delta (`test_high_quality_success_gives_larger_delta`)
  - 1 proactive_intelligence (`test_empty_workspace`)
  - 1 wave34_smoke (`test_clean_state_no_false_positives`)
  - None related to Wave 58 files
- `ruff check src/` clean
- `pyright src/` clean
- `python scripts/lint_imports.py` clean

### Eval harness fixes landed (pre-Wave 58)

These changes landed after the original plan was written but before dispatch.
Wave 58 teams do NOT touch these files, but should be aware of them:

1. **projections.py**: `last_activity_at: float = 0.0` added to
   `ColonyProjection` (line 391). Bumped by AgentTurnStarted,
   AgentTurnCompleted, CodeExecuted, RoundStarted. Used by the eval
   idle watchdog. **Do not touch.**
2. **sequential_runner.py**: productivity-proportional extension with
   staleness guard, idle watchdog (180s no-activity timeout), try/except
   around per-task loop. All eval-layer only.
3. **projections.py line shifts**: `RoundProjection` moved from line 415
   to **line 418**. `tool_calls` field moved from line 424 to **line 427**.
   Team 2 references these by name, not line number, so no prompt change
   needed.

### Line reference audit

All line references verified against the current codebase on 2026-03-22.

| Reference | Design says | Verified actual | Status |
|-----------|-------------|-----------------|--------|
| context.py `if knowledge_items:` | ~line 459 | **line 459** | OK |
| context.py injection loop | lines 459-505 | **lines 459-505** | OK |
| context.py `_MIN_KNOWLEDGE_SIMILARITY` | lines 47-53 | **lines 51-52** | CORRECTED |
| types.py `EntrySubType` enum | line 339 | **line 339** | OK |
| types.py `MemoryEntry` class | line 377 | **line 377** | OK |
| types.py last field `playbook_generation` | line 430-433 | **lines 430-433** | OK |
| colony_manager.py `_post_colony_hooks` | line 1037-1071 | **lines 1041-1074** | CORRECTED (method starts at 1041) |
| colony_manager.py last hook `_hook_auto_template` | line ~1070 | **line 1072** | CORRECTED |
| memory_store.py `upsert_entry` embed_text | lines 44-50 | **lines 44-50** | OK |
| memory_store.py metadata dict | lines 55-71 | **lines 55-71** | OK |
| tool_dispatch.py `knowledge_detail` spec | lines 178-197 | **lines 178-197** | OK |
| tool_dispatch.py description string | lines 180-184 | **lines 180-184** | OK |
| runtime.py `make_knowledge_detail_fn` | line 1142 | **line 1142** | OK |
| runtime.py `_knowledge_detail` inner | line 1150-1164 | **lines 1150-1164** | OK |
| runner_types.py `productive_calls` | line 94 | **line 94** | OK |
| runner_types.py `total_calls` | line 95 | **line 95** | OK |
| colony_manager.py `total_productive_calls` accumulation | line 833 | **line 833** | OK |
| colony_manager.py quality function `productive_ratio` | line 297-298 | **lines 297-298** | OK |

### Corrected references for prompts

- `_MIN_KNOWLEDGE_SIMILARITY` is at context.py **line 51** (not 47). The env var
  read is lines 51-52. The comment block starts at line 47.
- `_post_colony_hooks()` method signature starts at colony_manager.py **line 1041**.
  The section comment is at line 1037-1038.
- The last hook call (`_hook_auto_template`) is at colony_manager.py **line 1072**.
  The new trajectory hook should be inserted at **line 1075** (after the
  auto-template block closing at line 1074).

---

## Shared interfaces

### 1. EntrySubType.trajectory

- **Value**: the string `"trajectory"` (Python: `EntrySubType.trajectory`)
- **Added by**: Team 2, in `core/types.py` line 354 (after `bug = "bug"`)
- **Read by**: Team 3, in `engine/context.py` when formatting index lines
- **Contract**: Team 3 checks `item.get("sub_type") == "trajectory"` to apply
  the `[TRAJECTORY]` display tag instead of `[SKILL, TECHNIQUE]` etc.

### 2. MemoryEntry.trajectory_data

- **Type**: `list[dict[str, Any]]` with default `[]`
- **Added by**: Team 2, in `core/types.py` after line 433 (after `playbook_generation`)
- **Each dict has keys**: `tool` (str), `agent_id` (str), `round_number` (int)
- **Why this shape**: it matches the current replay surface truth. The
  projection stores `round_records`, and each `RoundProjection` stores
  `tool_calls: dict[agent_id, list[str]]`. Tool args and per-call success
  status are not currently available without widening event capture.
- **Stored on event**: Serialized as part of the entry dict on `MemoryEntryCreated`
- **Read by**: Team 2's runtime.py change (knowledge_detail formatting)
- **Not read by**: Team 3 (Team 3 only reads `sub_type` for display tag)

### 3. knowledge_items dict shape

Verified keys in the dicts passed to `assemble_context()` via the
`knowledge_items` parameter (from knowledge_catalog normalization):

```
id: str                    # entry ID (e.g., "mem-colony-xxx-s-0")
canonical_type: str        # "skill" or "experience"
source_system: str         # "institutional_memory" or "legacy_skill_bank"
status: str                # "candidate", "verified", etc.
confidence: float          # Beta posterior mean
title: str                 # entry title
summary: str               # one-line summary
content_preview: str       # truncated content (~250 chars)
source_colony_id: str      # source colony
domains: list[str]         # domain tags
tool_refs: list[str]       # tool names
score: float               # composite ranked score
similarity: float          # raw vector similarity (for threshold checks)
sub_type: str | None       # "technique", "trajectory", etc. (NEW in Wave 58)
```

**Pre-dispatch fix landed**: `sub_type` is now propagated through the
retrieval pipeline. `KnowledgeItem` dataclass in `knowledge_catalog.py`
has a `sub_type: str = ""` field (line 90), and `_normalize_institutional()`
populates it from `entry.get("sub_type", "")` (line 151). This ensures
the field survives the Qdrant round-trip and appears in the
`knowledge_items` dicts passed to `assemble_context()`.

Team 2 stores `sub_type` in Qdrant metadata. Team 3 reads it for display
formatting. Team 1 reads it for the trajectory bypass. All three depend
on the retrieval propagation fix that is now in main.

### 4. context.py merge protocol

context.py is touched by Team 1 (outer gate) and Team 3 (inner format).

**Team 1 owns**: The wrapping condition around the injection block.
```
Line 459: change `if knowledge_items:` to
          `if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):`
```
Plus the new function `_should_inject_knowledge()` and its constants,
added above the `assemble_context()` function.

**Team 3 owns**: The block INSIDE the condition (lines 460-505).
Replaces the full-content format with index-only format.

**Merge rule**: Team 1 merges first. Team 3 re-reads context.py after
Team 1's merge, then replaces the inner block.

---

## Merge sequence

```
Day 1:  Team 1 (specificity gate) ---|---> merge to main
        Team 2 (trajectory storage) -|---> merge to main
                                      |
Day 2:  Team 3 pulls main, re-reads context.py
        Team 3 (progressive disclosure) ---> merge to main
                                      |
Day 3:  Integration test (all three features together)
```

1. **Teams 1 + 2 work in parallel** -- no file overlap between them
2. **Team 1 merges** -- context.py gate wrapper
3. **Team 2 merges** -- types.py, colony_manager.py, memory_store.py, runtime.py
4. **Team 3 pulls main**, re-reads updated context.py, then implements
5. **Team 3 merges** -- context.py inner format, tool_dispatch.py
6. **Integration test** after all three merge

---

## Four refinements from orchestrator session

These refine the original design. Each is assigned to the relevant team.

### Refinement 1: Specificity gate always passes trajectory entries (Team 1)

In `_should_inject_knowledge()`, if ANY retrieved entry has
`sub_type == "trajectory"`, return `True` regardless of similarity or
project signals. Trajectories are action sequences, not redundant prose --
they are always worth showing in the index.

### Refinement 2: Progressive disclosure tags trajectories visually (Team 3)

Use `[TRAJECTORY]` as the display tag for trajectory entries, not
`[SKILL, TRAJECTORY]`. Cleaner display, immediately communicates that the
entry contains a tool sequence the agent can replay.

### Refinement 3: Trajectory extraction gates on productive ratio (Team 2)

Gate on `productive_ratio >= 0.6` in addition to `quality >= 0.30`.
`productive_ratio = productive_calls / total_calls`. The data is available
on the colony projection at extraction time: `total_productive_calls` and
`total_total_calls` are accumulated in the round loop
(colony_manager.py:833-834) and passed to the quality function
(colony_manager.py:903-904). The hook should read these from the same
variables available in `_post_colony_hooks()`.

### Refinement 4: Provider readiness is a separate packet

Do not hide the multi-provider experiment under a vague "out of scope"
note. It has its own seams and should ship as a separate pre-experiment
packet.

Important current-repo nuance:

- normal colony tool-calling already goes through
  `OpenAICompatibleLLMAdapter.complete()`, which is non-streaming today
- so the immediate experiment risk is not "all tool calls stream"
- the immediate experiment risk is "registry truth / provider readiness /
  endpoint behavior"

Treat Ollama readiness as a separate packet with its own owner, prompt, and
acceptance bar.

See: `provider_parallel_readiness.md`

Suggested owned files:

- `config/formicos.yaml`
- `scripts/provider_benchmark.py`
- `src/formicos/surface/view_state.py`
- `src/formicos/surface/ws_handler.py`
- `src/formicos/adapters/llm_openai_compatible.py` (only if a real caller
  needs a stream+tools safeguard)

---

## Acceptance criteria

### CI
- 0 new test failures
- All existing tests pass (3448+ minus 8 pre-existing)
- `ruff check src/` clean
- `pyright src/` clean

### Token budget
- Injected knowledge tokens DECREASE from ~800 (5 entries x ~160 tokens)
  to ~250 (5-8 entries x ~50 tokens index-only)
- Measured via context.py `estimate_tokens()` on the injected block

### Specificity gate
- Skips injection for general coding tasks with no project signals and
  low similarity (< 0.55)
- Injects for tasks with project-specific language ("our", "existing", etc.)
- Injects when top retrieved entry has similarity >= 0.55
- Injects when any retrieved entry is a trajectory (sub_type == "trajectory")
- Toggled via `FORMICOS_SPECIFICITY_GATE` env var (default: "1" = ON)

### Trajectory entries
- Created from successful colonies with quality >= 0.30 and
  productive_ratio >= 0.6
- Stored as MemoryEntry with `sub_type="trajectory"` and `trajectory_data`
- Visible in knowledge browser (GET /api/v1/knowledge endpoint)
- `knowledge_detail` tool returns formatted trajectory with round-by-round
  tool sequence

### Progressive disclosure
- Index-only format with entry IDs in each line
- Header directs agents to use `knowledge_detail` tool
- Trajectory entries display with `[TRAJECTORY]` tag
- `knowledge_detail` tool description updated to reference the index
- Agents can call `knowledge_detail(item_id="...")` to fetch full content

### Provider readiness (separate packet)
- Provider benchmark script runs from the host and reports tool-call success
  per provider
- Any Ollama Cloud registry entry is paired with truthful surface handling
  (not silently treated as a local endpoint)
- Multi-provider experiment proceeds only after benchmark-confirmed providers
  are added to the registry

### Independent toggleability
- Specificity gate: `FORMICOS_SPECIFICITY_GATE=0` disables (always inject)
- Trajectory storage: no toggle needed (hook only fires on successful colonies)
- Progressive disclosure: no toggle needed (replaces old format)
- Each feature can be A/B tested in Phase 0 eval via env vars

---

## Post-Wave 58 investigation: mid-round hang timeout gap

Not in Wave 58 scope, but recorded here for sequencing.

v10 Arm 1 exposed a gap: a colony hung mid-round for 19 minutes without
being caught. The existing timeout layers (runner `max_execution_time_s`,
httpx 120s) should have fired but didn't — likely because the hang was
in `workspace_execute` (a subprocess), not an LLM call, so the runner's
elapsed check at the top of its iteration loop was never reached.

**Immediate fix (landed):** eval-layer idle watchdog (`last_activity_at`
on ColonyProjection, 180s timeout in `_wait_for_colony`). Catches
mid-round hangs at the eval level.

**Next-wave substrate fix:** investigate why `max_execution_time_s` and
httpx timeout didn't catch the 19-minute hang. If `workspace_execute`
has no subprocess timeout, add one. Goal: make mid-round hangs impossible
at the engine layer, not just detectable at the eval layer.

**Future (architecture):** Queen periodic heartbeat checks on running
colonies. If a colony has no events for N seconds, the Queen proactively
inspects. Proper "check in" — but architecture work, not a quick fix.

---

## Post-Wave 58: Asymmetric extraction experiment

### Hypothesis

Phase 0 v2-v10 showed zero compounding delta across accumulate vs. empty
arms. This may not mean "retrieval doesn't help." It may mean "the same
30B model extracting and consuming knowledge produces tautological entries."
When writer == reader, entries contain zero information gain beyond the
model's parametric knowledge. When writer >> reader (a more capable model
produces knowledge for a less capable one), the knowledge gap between
writer and reader creates a positive delta.

### The seam exists

Knowledge extraction already routes through a separate model address:

- `colony_manager.py:1844`: `self._runtime.resolve_model("archivist", workspace_id)`
- `colony_manager.py:1250`: same pattern for transcript harvest
- `formicos.yaml:31`: `archivist: "llama-cpp/gpt-4"` (currently same as coder)

Both extraction paths (`_hook_memory_extraction` and `_hook_transcript_harvest`)
use `llm_router.complete()` with plain text messages — no tools, just
system prompt + user prompt → JSON response. Changing the archivist model
address routes all knowledge extraction to a different endpoint while
agent execution stays on the fast GPU model.

### Viable archivist backends

| Backend | Cost | Speed | Quality | Setup |
|---------|------|-------|---------|-------|
| CPU-hosted Qwen3-235B-A22B Q2_K | $0 (own hardware) | ~3-5 tok/s, ~5 min/extraction | High (235B MoE) | Second llama-cpp on CPU, ~60GB RAM |
| Ollama Cloud qwen3-coder:480b | $0 (free tier) | Rate-limited, ~10-30s/extraction | Very high (480B) | Registry entry + API key |
| Gemini 2.5 Flash free tier | $0 (free tier) | Fast (~2-5s/extraction) | High | Adapter already exists |

The architecture is a hardware-split MetaClaw pattern:
- **Fast loop (GPU, real-time):** 30B coder runs agent turns at full speed
- **Slow loop (CPU/cloud, background):** Larger model analyzes completed
  colony transcripts, produces higher-quality entries that the 30B model
  genuinely doesn't have the capacity to generate on its own

Extraction runs are fire-and-forget async tasks. Multiple extractions from
sequential colonies queue naturally. The adapter's `_semaphore` limits
concurrent requests to local servers. No concurrency changes needed.

### Blocker: httpx timeout

`httpx.Timeout(120.0)` is hardcoded on the adapter client at
`adapters/llm_openai_compatible.py:127`. A CPU model at 3-5 tok/s needs
~200-330s for a ~1K token extraction response. The call hits the 120s
timeout and silently fails (`memory_extraction.llm_failed`).

Fix is in the provider readiness packet: per-request timeout derived from
the existing `time_multiplier` field on `ModelRecord`. See
`provider_parallel_readiness.md` "Adapter Timeout Parameterization."

### Test plan

After the timeout fix lands, this is testable with one config change:

```yaml
archivist: "ollama-cloud/qwen3-coder:480b"
```

Run Phase 0 with this archivist. If compounding appears in the accumulate
arm, the hypothesis is confirmed: writer >> reader produces positive
knowledge delta.
