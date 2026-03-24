# Context Assembly Seams — Integration Reference

What the model sees, in what order, and where each block is injected.

> **Last updated: 2026-03-23** — aligned with Waves 54–59 (playbook injection,
> convergence status, index-only knowledge format, common mistakes, domain filter).
> See also: `docs/specs/context_assembly.md` for full current-state spec.

---

## Message order (what the LLM receives)

Position assignments are set in `assemble_context()` ([context.py](src/formicos/engine/context.py)).
Post-assembly injections happen in `_run_agent()` ([runner.py](src/formicos/engine/runner.py)).

```
 pos  role     block                  source                              budget (tokens)
 ───  ───────  ─────────────────────  ────────────────────────────────    ──────────────
  0   system   System prompt          context.py                          unlimited
  1*  system   Budget block           runner.py (per-iter)                ~80 (incl convergence)
  1†  system   URGENT directives      runner.py                           unlimited
  2†  system   Normal directives      runner.py                           unlimited
  2   user     Round goal             context.py                          500
  2.5 user     Operational playbook   context.py + playbook_loader.py     300 (Wave 54)
  2.6 user     Common mistakes        context.py + playbook_loader.py     200 (Wave 56.5)
  2a  user     [Workspace Structure]  context.py                          1500 (shared)
  2b  user     [Context from prior…]  context.py                          500/source
  2c  user     [System Knowledge]     context.py                          800
  3   user     [agent_id]: output     context.py                          1500 total
  4   user     Merge summaries        context.py                          500
  5   user     Previous round: …      context.py                          500
  6   user     Relevant skills:       context.py                          800 (skip if 2c)
```

`*` Budget block is re-injected every iteration of the tool-call loop.
`†` Directives are injected after `assemble_context()` returns, at fixed positions.

### Blocks that are always present

| Block | Condition |
|-------|-----------|
| System prompt | Always (from `agent.recipe.system_prompt`) |
| Budget block | Always (built per-iteration by `build_budget_block()` [context.py:318–340](src/formicos/engine/context.py#L318-L340)) |
| Round goal | Always (the colony task text) |

### Blocks that are conditional

| Block | Present when | Absent when |
|-------|-------------|------------|
| Workspace structure | `colony_context.structural_context` is non-empty | No target files or fresh workspace |
| Input sources | `input_sources` list is non-empty | No DAG-chained colony context |
| System Knowledge | `knowledge_items` list is non-empty | Knowledge catalog returned nothing |
| Routed outputs | Other agents produced output this round | First agent in round, or single-agent |
| Merge summaries | Always `[]` in current code ([runner.py:1318](src/formicos/engine/runner.py#L1318)) | Never populated |
| Previous round | `prev_round_summary` exists | First round |
| Skill bank | `vector_port` exists AND no unified knowledge | Unified knowledge present (skip_legacy) |

---

## System prompt content (caste recipes)

The system prompt is the **first message** and carries the highest attention weight.
Currently it contains ([caste_recipes.yaml:176–217](config/caste_recipes.yaml#L176-L217)):

**For coder:**
1. Role identity ("You are a Coder agent in a FormicOS colony")
2. Tool descriptions (12 bullets listing each tool's purpose)
3. Multi-agent git safety rules
4. System context (knowledge tracking, credential scanning)
5. Output guidance ("be explicit about decisions")
6. Execution discipline scaffold (3 rules)

**What is NOT in the system prompt:**
- No task-class workflow guidance ("for a code-writing task, start with write_workspace_file")
- No few-shot tool-use examples
- No operational playbook ("write code first, then execute to test, then iterate")
- No mid-stall correction hints
- No information about the round/iteration lifecycle

---

## Budget block ([context.py](src/formicos/engine/context.py))

Injected at position 1 **every iteration** of the tool-call loop:

```python
def build_budget_block(
    budget_remaining, budget_limit, iteration, max_iterations,
    round_number, max_rounds,
    stall_count=0, convergence_progress="",
) -> str:
```

Produces text like:
```
Budget: $1.50 / $5.00 remaining
Iteration 2/25 | Round 3/10
Budget regime: HIGH
Status: ON TRACK
```

Regime classification ([context.py](src/formicos/engine/context.py)):
- `HIGH`: ≥70% budget remaining
- `MEDIUM`: 30–70%
- `LOW`: 10–30%
- `CRITICAL`: <10%

**Convergence status** (Wave 54): Appended to the budget block based on stall_count
and convergence_progress. Labels: `FINAL ROUND`, `STALLED`, `SLOW`, `ON TRACK`.

---

## Knowledge injection chain

### Retrieval ([knowledge_catalog.py:258–296](src/formicos/surface/knowledge_catalog.py#L258-L296))

6-signal composite score (ADR-044):
```
0.38 * semantic + 0.25 * thompson + 0.15 * freshness
+ 0.10 * status_bonus + 0.07 * thread_bonus + 0.05 * cooccurrence
+ pin_boost (additive)
× federated_retrieval_penalty (multiplicative)
```

Top 5 results returned to colony_manager.

### Fetch call site ([colony_manager.py:614–619](src/formicos/surface/colony_manager.py#L614-L619))

```python
knowledge_items = await self._runtime.fetch_knowledge_for_colony(
    task=colony.task, workspace_id=colony.workspace_id,
    thread_id=colony.thread_id, top_k=5,
)
```

Re-fetched on goal change at [colony_manager.py:661–667](src/formicos/surface/colony_manager.py#L661-L667).

### Format injected ([context.py](src/formicos/engine/context.py))

**Wave 58+ index-only format** (~50 tokens per entry, progressive disclosure):

```
[System Knowledge]
[1] SKILL "Title here" (verified, conf 0.80) → use knowledge_detail for full content
[2] EXPERIENCE "Another title" (active, conf 0.65) → use knowledge_detail for full content
```

**What the model sees:** Numbered index, type, title, status, confidence float, pointer to `knowledge_detail` tool.
**What the model does NOT see initially:** Full content, which scoring signal dominated, thread-scope flag, co-occurrence strength, decay class, provenance chain.

Agents pull full content on-demand via the `knowledge_detail` tool (progressive disclosure).
At `standard`/`full` retrieval tiers, results include `score_breakdown` and `ranking_explanation`.

**Post-retrieval filters** (Wave 58.5):
- Domain-boundary filter: keeps entries where `primary_domain in ("", task_class, "generic")`
- Specificity gate: 4 conditions (see `docs/specs/context_assembly.md`)

---

## Operator directives ([runner.py:1330–1359](src/formicos/engine/runner.py#L1330-L1359))

Injected AFTER `assemble_context()` returns, before the tool-call loop:

- **Urgent:** Inserted at `min(1, len(messages))` — right after system prompt
  ```
  ## URGENT Operator Directives
  [directive text]
  ```
- **Normal:** Inserted at `min(2, len(messages))` — after system prompt + budget
  ```
  ## Operator Directives
  [directive text]
  ```

Source: Drained from `colony_manager.drain_injected_messages()` ([colony_manager.py:677–680](src/formicos/surface/colony_manager.py#L677-L680)).

---

## Tool-call loop context growth ([runner.py:1376–1502](src/formicos/engine/runner.py#L1376-L1502))

Each iteration of the tool-call loop appends to the message list:

```python
# After each tool call:
messages.append({"role": "assistant", "content": response.content or "(tool call)"})
messages.append({"role": "user", "content": tool_result_message})
```

Tool result format:
```
[Tool result from {tool_name}] (untrusted data):
{result_text[:TOOL_OUTPUT_CAP]}
```

`TOOL_OUTPUT_CAP = 2000` characters ([tool_dispatch.py:531](src/formicos/engine/tool_dispatch.py#L531)).

The message list grows by 2 messages per tool call per iteration. With `max_iterations=25` and multiple tool calls per iteration, context can grow rapidly. No mid-loop compaction exists.

---

## Integration points — implementation status

> **All four integration points identified in the original audit are now implemented.**

### Point A: Playbook injection at position 2.5 — ✅ IMPLEMENTED (Wave 54)

Operational playbook loaded by `engine/playbook_loader.py` with caste-aware resolution
order: `{task_class}_{caste}.yaml` → `{task_class}.yaml` → `generic_{caste}.yaml` →
`generic.yaml`. Injected at position 2.5 in `assemble_context()`. Common mistakes
injected at position 2.6 (Wave 56.5).

### Point B: Post-assembly directive injection — ✅ EXISTS (original design)

Operator directives injected after `assemble_context()` returns, at fixed positions
in `_run_agent()`. Unchanged from original design.

### Point C: Per-iteration budget+convergence injection — ✅ IMPLEMENTED (Wave 54)

Convergence status (`FINAL ROUND`, `STALLED`, `SLOW`, `ON TRACK`) appended to the
budget block via `stall_count` and `convergence_progress` parameters to
`build_budget_block()`. Injected every iteration of the tool-call loop.

### Point D: ColonyContext expansion — ✅ IMPLEMENTED (Waves 54, 58.5)

`ColonyContext` now includes `task_class` field (Wave 58.5). Playbook guidance
and convergence status are threaded through the context assembly pipeline.
`stall_count` is tracked in `colony_manager.py` and passed to `build_budget_block()`.
