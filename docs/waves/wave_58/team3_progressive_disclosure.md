# Team 3: Progressive Disclosure

## Context

Instead of injecting full knowledge entry content into every agent's context
(~200 tokens per entry, ~800 tokens for 5 entries), inject only a lightweight
index (~50 tokens per entry, ~250 tokens total). Agents use the existing
`knowledge_detail` tool to fetch full content on demand.

Evidence: Claude-Mem achieved 26x efficiency improvement with metadata-first
loading. The SKILL.md standard (adopted by Cursor, Windsurf, Claude Code)
uses lightweight index files. Du et al. (EMNLP 2025) showed context length
alone degrades performance 13.9-85%. FormicOS's own playbooks at ~200 tokens
each are near the optimal injection size -- the knowledge index follows the
same principle.

The `knowledge_detail` tool already exists in the codebase
(tool_dispatch.py:178-197, runner.py:1824-1835, runtime.py:1142-1164).
Agents can already fetch full entries by ID. This change only modifies
the injection FORMAT -- from full content to index-only.

---

## Prerequisites

Before starting:

1. **Team 1 has merged** -- context.py now has `_should_inject_knowledge()`
   wrapping the injection block. The line that was `if knowledge_items:` is
   now `if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):`.

2. **Team 2 has merged** -- `sub_type="trajectory"` exists in
   `core/types.py` and trajectory entries flow through the retrieval pipeline
   with `sub_type` populated.

3. **Verify `top_k` was bumped to 8** in `runtime.py:fetch_knowledge_for_colony()`
   (Team 2's Change 4). If it still says `top_k=5`, your `[:8]` slice in
   context.py will never see more than 5 items.

4. **Re-read `src/formicos/engine/context.py`** after both merges. The
   inner block (which you are replacing) starts after the gate condition.
   Verify the exact line numbers before implementing.

---

## Implementation

Two changes across two files.

### Change 1: Replace injection format in context.py

**File**: `src/formicos/engine/context.py`

After Team 1's merge, the injection block looks like:

```python
    if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
        lines = ["[System Knowledge]"]
        for item in knowledge_items[:5]:
            # ... existing full-content injection ...
            ...
        if len(lines) > 1:
            knowledge_text = _truncate("\n".join(lines), budgets.skill_bank)
            messages.append({"role": "user", "content": knowledge_text})
            skip_legacy_skills = True
```

Replace the INNER block (everything inside the `if` condition, from the
`lines = ["[System Knowledge]"]` through `skip_legacy_skills = True`) with:

```python
    if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
        lines = [
            "[Available Knowledge] "
            "(use knowledge_detail tool to retrieve full content)"
        ]
        for item in knowledge_items[:8]:  # wider net: 8 index entries fit in ~400 tokens
            # Wave 55.5: semantic injection gate still applies per-entry
            raw_similarity = float(
                item.get("similarity", item.get("score", 0.0)),
            )
            if raw_similarity < _MIN_KNOWLEDGE_SIMILARITY:
                log.debug(
                    "context.knowledge_below_threshold",
                    entry_id=item.get("id", ""),
                    title=str(item.get("title", ""))[:60],
                    similarity=round(raw_similarity, 3),
                    threshold=_MIN_KNOWLEDGE_SIMILARITY,
                )
                continue

            entry_id = item.get("id", "")
            title = item.get("title", "")
            conf = float(item.get("confidence", 0.5))
            sub_type = str(item.get("sub_type", "") or "")
            status = str(item.get("status", "")).upper()

            # Wave 58: trajectory entries get a distinct tag
            if sub_type == "trajectory":
                summary = str(item.get("summary", item.get("content_preview", "")))[:100]
                lines.append(
                    f'- [TRAJECTORY] "{title}" -- {summary} '
                    f"(conf: {conf:.2f}, id: {entry_id})"
                )
            else:
                ctype = str(item.get("canonical_type", "skill")).upper()
                label = f"{ctype}, {status}"
                summary = str(item.get("summary", item.get("content_preview", "")))[:80]
                lines.append(
                    f'- [{label}] "{title}" -- {summary} '
                    f"(conf: {conf:.2f}, id: {entry_id})"
                )

            knowledge_access_items.append(KnowledgeAccessItem(
                id=entry_id,
                source_system=item.get("source_system", ""),
                canonical_type=item.get("canonical_type", "skill"),
                title=title,
                confidence=conf,
                score=float(item.get("score", 0.0)),
                similarity=raw_similarity,
            ))

        if len(lines) > 1:
            # Keep the existing budget guard even though the index is compact.
            knowledge_text = _truncate("\n".join(lines), budgets.skill_bank)
            messages.append({"role": "user", "content": knowledge_text})
            skip_legacy_skills = True
```

Key differences from the old format:

| Aspect | Old (full content) | New (index-only) |
|--------|-------------------|------------------|
| Header | `[System Knowledge]` | `[Available Knowledge] (use knowledge_detail tool...)` |
| Per-entry | Type + status + source + title + 250-char content + confidence | Type + status + title + 80-char summary + confidence + ID |
| Max entries | 5 | 8 (wider net, cheaper per entry) |
| Tokens per entry | ~160 | ~50 |
| Total budget | ~800 tokens | ~400 tokens max |
| Trajectory tag | `[SKILL, CANDIDATE, INST]` | `[TRAJECTORY]` |
| Entry IDs | Not shown | Shown (for knowledge_detail calls) |
| Truncation | `_truncate(..., budgets.skill_bank)` | Not needed (index is compact) |

### Change 2: Update knowledge_detail tool description

**File**: `src/formicos/engine/tool_dispatch.py`

At lines 180-184, the current description is:

```python
        "description": (
            "Retrieve the full content of a knowledge item by its ID. "
            "Use when the context preview is insufficient and you need "
            "the complete entry."
        ),
```

Replace with:

```python
        "description": (
            "Retrieve the full content of a knowledge item by its ID. "
            "The [Available Knowledge] section in your context lists relevant "
            "entries with their IDs. Call this tool when an entry looks "
            "relevant to your current task."
        ),
```

---

## Tests to write

File: `tests/unit/engine/test_context.py` (add to existing file)

### test_index_injection_format

```
Given: knowledge_items with 3 entries, all above similarity threshold
Expect: The injected message content starts with "[Available Knowledge]"
  and contains "(use knowledge_detail tool to retrieve full content)"
  Each entry line starts with "- ["
  No entry line contains more than 200 characters
```

### test_index_includes_entry_ids

```
Given: knowledge_items = [
    {"id": "mem-abc-s-0", "title": "CSV Patterns", "similarity": 0.65,
     "confidence": 0.72, "status": "verified", "canonical_type": "skill",
     "sub_type": "technique", "summary": "CSV parsing with DictReader"}
]
Expect: The injected message contains "id: mem-abc-s-0"
```

### test_index_skips_low_similarity

```
Given: knowledge_items = [
    {"id": "mem-1", "similarity": 0.65, ...},  # above threshold
    {"id": "mem-2", "similarity": 0.35, ...},  # below threshold
]
Expect: Only mem-1 appears in the injected message. mem-2 is skipped.
  Debug log emitted for mem-2 (same as current behavior).
```

### test_index_token_budget_reduction

```
Given: knowledge_items with 5 entries, all above threshold
Expect: estimate_tokens(injected_message_content) < budgets.skill_bank
  and comfortably below the old full-content format (~800 tokens)
  (Old format would be ~800 tokens for 5 entries)
```

### test_trajectory_display_in_index

```
Given: knowledge_items = [
    {"id": "traj-col-1", "title": "Trajectory: code_implementation (8 steps)",
     "similarity": 0.60, "confidence": 0.65, "status": "verified",
     "canonical_type": "skill", "sub_type": "trajectory",
     "summary": "code_implementation tool sequence, 8 steps, quality 0.50"}
]
Expect: The injected message contains "[TRAJECTORY]"
  Does NOT contain "[SKILL, VERIFIED]" for this entry
  Contains "id: traj-col-1"
```

---

## Files owned

- `src/formicos/engine/context.py` -- inner injection block only
  (Team 1 owns the outer `_should_inject_knowledge()` gate)
- `src/formicos/engine/tool_dispatch.py` -- description string only (lines 180-184)

## Do not touch

- `src/formicos/core/types.py` (Team 2)
- `src/formicos/surface/colony_manager.py` (Team 2)
- `src/formicos/surface/knowledge_catalog.py` (pre-dispatch fix landed
  `sub_type` propagation — `item.get("sub_type")` will return the correct
  value in `knowledge_items` dicts)
- `src/formicos/surface/runtime.py` (Team 2)
- `src/formicos/surface/memory_store.py` (Team 2)

## Validation commands

```bash
uv run ruff check src/formicos/engine/context.py src/formicos/engine/tool_dispatch.py
uv run pyright src/formicos/engine/context.py src/formicos/engine/tool_dispatch.py
uv run pytest tests/unit/engine/test_context.py tests/unit/engine/test_tool_dispatch.py -x -q
```

Run the full CI before declaring done:

```bash
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && uv run pytest
```

## Merge order

You are the **last team to merge**. Both Team 1 and Team 2 must have
merged before you start.

Before writing any code:
1. Pull main (with Team 1 + Team 2 changes)
2. Re-read `src/formicos/engine/context.py` to see Team 1's gate wrapper
3. Verify `sub_type` is populated on knowledge_items flowing through the
   retrieval pipeline (Team 2 added it to memory_store.py metadata)
4. Then implement your changes inside the gate wrapper

## Overlap protocol with Team 1

Team 1 added `_should_inject_knowledge()` and wrapped line 459. You replace
the block INSIDE that wrapper. Specifically:

- Team 1 owns: the gate function, the `_PROJECT_SIGNALS` frozenset, the
  `_SPECIFICITY_GATE_ENABLED` env var, and the outer `if` condition
- You own: the `lines = [...]`, the `for item in knowledge_items[:8]:` loop,
  the formatting, and the `if len(lines) > 1:` block

Do not modify the gate function or the outer condition. Do not move the
`knowledge_access_items` list initialization (it is declared before the
gate block and is used after it).
