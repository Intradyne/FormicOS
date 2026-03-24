# Context Assembly Implementation Reference

Current-state reference for FormicOS context assembly: budget-aware message
construction, position numbering, specificity gate, domain filter, progressive
disclosure, playbook injection. Code-anchored to Wave 59.

---

## Entry Point

`engine/context.py:assemble_context()` builds the LLM message list for each
agent turn. Returns `ContextResult` (messages + retrieval metadata).

```python
async def assemble_context(
    agent: AgentConfig,
    colony_context: ColonyContext,
    round_goal: str,
    routed_outputs: dict[str, str],
    merged_summaries: list[str],
    vector_port: VectorPort | None,
    budget_tokens: int = 4000,
    tier_budgets: TierBudgets | None = None,
    total_colonies: int = 0,
    ucb_exploration_weight: float = 0.1,
    kg_adapter: Any = None,
    input_sources: list[dict[str, Any]] | None = None,
    knowledge_items: list[dict[str, Any]] | None = None,
    operational_playbook: str | None = None,
) -> ContextResult
```

---

## Position Numbering

Assembly order optimized for LLM attention — important content at edges
(start and end of context window get highest attention).

| Position | Content | Role | Budget |
|----------|---------|------|--------|
| 1 | System prompt | `system` | Unlimited |
| 2 | Round goal | `user` | `goal` (500 tokens) |
| 2.5 | Operational playbook | `system` | 400 tokens (~250 actual) |
| 2.6 | Common-mistakes anti-patterns | `system` | — |
| 2a | Structural context | `user` | `routed_outputs` (1500) |
| 2b | Input sources (ADR-033) | `user` | `max_per_source` (500) per source |
| 2c | Knowledge (unified system) | `user` | `skill_bank` (800) |
| 3 | Routed agent outputs | `user` | `routed_outputs` (1500) total |
| 4 | Merge summaries | `user` | `merge_summaries` (500) |
| 5 | Previous round summary | `user` | `prev_round_summary` (500) |
| 6 | Legacy skill bank | `user` | `skill_bank` (800) |

Position 6 (legacy skill bank) is skipped when position 2c injects unified
knowledge (`skip_legacy_skills = True`).

---

## Tier Budgets (ADR-008)

```python
class TierBudgets(BaseModel):
    model_config = ConfigDict(frozen=True)
    goal: int = 500
    routed_outputs: int = 1500
    max_per_source: int = 500
    merge_summaries: int = 500
    prev_round_summary: int = 500
    skill_bank: int = 800
    compaction_threshold: int = 500
```

Token estimation: `len(text) // 4` (1 token ≈ 4 characters).

### Scope Budgets (Wave 34)

Separate budget-aware assembly in `_budget_aware_assembly()` uses percentage
allocation:

| Scope | Budget % |
|-------|----------|
| `task_knowledge` | 35% |
| `observations` | 20% |
| `structured_facts` | 15% |
| `round_history` | 15% |
| `scratch_memory` | 15% |

---

## Gates and Filters

Three mechanisms control what knowledge reaches agent context.

### 1. Similarity Threshold (Wave 55.5)

```python
_MIN_KNOWLEDGE_SIMILARITY = 0.50  # env: FORMICOS_KNOWLEDGE_MIN_SIMILARITY
```

Per-entry gate. Entries with raw vector similarity below 0.50 are retrieved
but not injected. Calibrated for Qwen3-Embedding-0.6B: irrelevant entries
score 0.34–0.41, relevant entries score 0.50–0.70.

### 2. Specificity Gate (Wave 58)

```python
_SPECIFICITY_GATE_ENABLED = True  # env: FORMICOS_SPECIFICITY_GATE (default "1")
```

`_should_inject_knowledge(round_goal, knowledge_items)` returns True (inject)
when any of these conditions hold:

1. Gate is disabled via env var.
2. Any retrieved entry is a trajectory (`sub_type == "trajectory"`).
3. Task contains project-specific signals.
4. Top retrieved entry has raw similarity ≥ 0.55.

Returns False (skip all injection) when none hold.

**Project signals** (frozenset):
```python
_PROJECT_SIGNALS = frozenset({
    "our", "existing", "internal", "custom", "legacy", "current",
    "workspace", "codebase", "repo", "project", "module",
})
```

The gate checks `set(round_goal.lower().split()) & _PROJECT_SIGNALS`.

### 3. Domain-Boundary Filter (Wave 58.5)

Post-retrieval filter in `assemble_context()`. Keeps entries where
`primary_domain` matches the colony's `task_class`, or entries with no
domain tag or "generic".

```python
_task_class = colony_context.task_class
if knowledge_items and _task_class and _task_class != "generic":
    knowledge_items = [
        item for item in knowledge_items
        if item.get("primary_domain", "") in ("", _task_class, "generic")
    ]
```

`task_class` is set on `ColonyContext` by `colony_manager.py:classify_task()`
during colony spawn. Default: `"generic"` (bypasses filter).

---

## Progressive Disclosure (Wave 58)

Knowledge injection uses index-only format (~50 tokens/entry instead of ~160
for full content). Agents fetch full content on demand via `knowledge_detail` tool.

### Index Format

```
[Available Knowledge] (use knowledge_detail tool to retrieve full content)
- [TRAJECTORY] "title" -- summary (conf: 0.75, id: mem-xxx)
- [SKILL, VERIFIED] "title" -- summary (conf: 0.80, id: mem-yyy)
```

Up to 8 entries are included. Each entry shows:
- Type label (TRAJECTORY or canonical_type + status)
- Title
- Summary/preview (truncated to 80–100 chars)
- Confidence score
- Entry ID (for knowledge_detail lookup)

---

## Playbook System (Wave 54)

### Operational Playbook (Position 2.5)

Task-class-keyed procedural guidance loaded by `engine/playbook_loader.py`.
YAML files in `config/playbooks/`.

**Resolution order** (first match wins):
1. `{task_class}_{caste}.yaml` — caste-specific variant
2. `{task_class}.yaml` — shared (must list the caste)
3. `generic_{caste}.yaml` — caste-specific fallback
4. `generic.yaml` — universal fallback

Injected as `system` role message, truncated to 400 tokens.

### Common-Mistakes Anti-Patterns (Position 2.6, Wave 56.5)

`load_common_mistakes(caste)` — always on, caste-aware. Loaded from
`config/playbooks/` and injected as `system` role message.

---

## Truncation Strategies

### Simple Truncation

`_truncate(text, budget_tokens)`: Character-based cut at `budget_tokens * 4`.

### Edge-Preserving Truncation

`_truncate_preserve_edges(text, budget_tokens)`: Keeps first and last halves
(edges have highest information density). Inserts `[... truncated ...]` marker.

### Goal-Relevant Compaction

`_compact_summary(text, goal, budget_tokens)`: Splits text into sentences,
scores each by word overlap with goal + position bonus (first/last sentences
get +0.5), selects highest-scoring sentences within budget, reassembles in
original order.

Applied to previous round summary when it exceeds `compaction_threshold` (500 tokens).

---

## Retrieval Pipeline

`RetrievalPipeline` orchestrates hybrid search when a KG adapter is available:

1. **Entity extraction**: Search KG for entities matching query.
2. **Parallel search**: 1-hop BFS on top 3 KG entities + vector search.
3. **Merge**: Combine KG triples and vector hits.

Returns `(vector_hits, kg_triples)`. Timing recorded in ephemeral
`_last_retrieval_timing` dict for operator diagnostics.

Vector search uses `skill_bank_v2` collection (hybrid dense + BM25 + RRF
via Qdrant).

---

## Budget Block Injection

`build_budget_block()` constructs per-turn status:

```
[Budget: $X.XX remaining (Y%) — REGIME]
[Iteration I/M · Round R/N]
Regime advice text
STATUS: ON TRACK|SLOW|STALLED|FINAL ROUND
```

Injected before each LLM call by the runner, not by `assemble_context()`.

---

## Input Sources (ADR-033)

Chained colony context at position 2b. Each `InputSource` provides:
- Summary text (truncated to `max_per_source`)
- Artifact metadata (name, type, preview)

Both injected as `user` role messages.

---

## Key Constants

| Constant | Value | Location |
|----------|-------|----------|
| `_MIN_KNOWLEDGE_SIMILARITY` | 0.50 | `engine/context.py` |
| Specificity gate top-sim threshold | 0.55 | `engine/context.py` |
| `_SPECIFICITY_GATE_ENABLED` | `True` | `engine/context.py` |
| `TierBudgets.goal` | 500 | `engine/context.py` |
| `TierBudgets.routed_outputs` | 1500 | `engine/context.py` |
| `TierBudgets.skill_bank` | 800 | `engine/context.py` |
| `TierBudgets.compaction_threshold` | 500 | `engine/context.py` |
| Playbook truncation | 400 tokens | `engine/context.py` |
| Max knowledge entries | 8 | `engine/context.py` |

---

## Key Source Files

| File | Purpose |
|------|---------|
| `engine/context.py` | assemble_context, gates, truncation, retrieval pipeline |
| `engine/playbook_loader.py` | Playbook resolution, common-mistakes loading |
| `engine/runner.py` | Budget block injection, tool result formatting |
| `engine/scoring_math.py` | exploration_score for Thompson Sampling |
| `core/types.py` | ColonyContext (task_class), TierBudgets shape |
| `config/playbooks/` | YAML playbook definitions |
