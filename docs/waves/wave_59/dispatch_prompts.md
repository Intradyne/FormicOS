# Wave 59: Knowledge Curation — Dispatch Prompts

**Date**: 2026-03-23
**Plan**: `docs/waves/wave_59/wave_59_plan.md`
**Pre-existing test failures**: 9 (all pre-existing, none from Wave 58.5)

## Dependency and Parallelism

```
[Track 1] Foundation (event + projection + sync)  LANDS FIRST
                │
                ├──────────────────┐
                │                  │
[Track 2] Curating extraction     [Track 3] Curation maintenance handler
  (memory_extractor.py,             (maintenance.py, app.py)
   colony_manager.py)
                │                  │
          PARALLEL — zero file overlap
```

**Track 1 MUST land before Track 2 or Track 3 start.** Track 1 adds the
MemoryEntryRefined event that both Track 2 and Track 3 emit.

**Track 2 and Track 3 run in parallel.** Zero file overlap. No shared imports
beyond core/events.py (read-only for both).

---

## Track 1: Foundation — MemoryEntryRefined Event

**Goal**: Add the 65th event type, its projection handler, Qdrant sync, and
widen `merge_source` Literal for extraction-triggered merges.

### Owned files

| File | Action |
|------|--------|
| `src/formicos/core/events.py` | Add MemoryEntryRefined class, widen merge_source, update union + manifest |
| `src/formicos/surface/projections.py` | Add `_on_memory_entry_refined` handler + register in HANDLER_MAP |
| `src/formicos/surface/runtime.py` | Add Qdrant sync case for MemoryEntryRefined |
| `frontend/src/types.ts` | Add `'MemoryEntryRefined'` to EVENT_NAMES array |
| `docs/decisions/048-memory-entry-refined.md` | New ADR |
| `docs/decisions/INDEX.md` | Add row for ADR-048 |
| `CLAUDE.md` | Update event count from 64 to 65 where it appears |
| `tests/unit/core/test_events.py` | Add serialization round-trip test for MemoryEntryRefined |

### Do NOT touch

- `surface/memory_extractor.py` — Track 2
- `surface/colony_manager.py` — Track 2
- `surface/maintenance.py` — Track 3
- `surface/app.py` — Track 3
- `engine/context.py` — no changes this wave

### Step 1: Add MemoryEntryRefined class

In `src/formicos/core/events.py`, add after `QueenNoteSaved` (after line 1303):

```python
class MemoryEntryRefined(EventEnvelope):
    """In-place content improvement of a knowledge entry (Wave 59)."""

    model_config = FrozenConfig

    type: Literal["MemoryEntryRefined"] = "MemoryEntryRefined"
    entry_id: str = Field(..., description="Entry being refined.")
    workspace_id: str = Field(default="")
    old_content: str = Field(
        ..., description="Content before refinement (audit trail).",
    )
    new_content: str = Field(..., description="Improved content.")
    new_title: str = Field(
        default="",
        description="Updated title. Empty string = keep existing.",
    )
    refinement_source: Literal["extraction", "maintenance", "operator"] = Field(
        ..., description="What triggered the refinement.",
    )
    source_colony_id: str = Field(
        default="",
        description="Colony whose output informed the refinement. "
        "Empty for maintenance-triggered refinements.",
    )
```

### Step 2: Widen merge_source Literal on MemoryEntryMerged

At line 1027 of `events.py`, change:

```python
# BEFORE:
merge_source: Literal["dedup", "federation"] = Field(
    ..., description="Which code path emitted this event.",
)

# AFTER:
merge_source: Literal["dedup", "federation", "extraction"] = Field(
    ..., description="Which code path emitted this event.",
)
```

This is additive. All existing events with `"dedup"` or `"federation"` continue
to parse. No existing tests assert the Literal set.

### Step 3: Add to FormicOSEvent union

At line 1371 (after `QueenNoteSaved`), add `MemoryEntryRefined` to the Union:

```python
        QueenNoteSaved,                  # Wave 51
        MemoryEntryRefined,              # Wave 59
    ],
```

### Step 4: Add to EVENT_TYPE_NAMES manifest

At line 1444 (after `"QueenNoteSaved"`), add:

```python
    "QueenNoteSaved",
    "MemoryEntryRefined",
]
```

### Step 5: Add to _union_members validation tuple

At line 1479 (after `QueenNoteSaved`), add:

```python
        QueenNoteSaved,
        MemoryEntryRefined,
    )
```

**Import-time self-check at lines 1483-1490 will catch any mismatch.** If you
miss any of Steps 3-5, the import will fail with a RuntimeError.

### Step 6: Add to frontend EVENT_NAMES

In `frontend/src/types.ts` at line 778, add before the closing `] as const`:

```typescript
  'QueenNoteSaved',
  'MemoryEntryRefined',
] as const;
```

**`scripts/lint_imports.py` validates parity between backend EVENT_TYPE_NAMES
and frontend EVENT_NAMES.** If you miss this step, the lint check will fail.

### Step 7: Projection handler

In `src/formicos/surface/projections.py`, add the handler function near the
other memory handlers (after `_on_memory_entry_merged` at line 1738):

```python
def _on_memory_entry_refined(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryRefined = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is None:
        return
    entry["content"] = e.new_content
    if e.new_title:
        entry["title"] = e.new_title
    entry["refinement_count"] = entry.get("refinement_count", 0) + 1
    entry["last_refined_at"] = e.timestamp.isoformat() if hasattr(e.timestamp, "isoformat") else str(e.timestamp)
```

Add the import at the top of projections.py where other events are imported:
```python
from formicos.core.events import MemoryEntryRefined
```

Register in the `HANDLER_MAP` dict (after line 1999):

```python
    "QueenNoteSaved": _on_queen_note_saved,
    "MemoryEntryRefined": _on_memory_entry_refined,
}
```

**Event ordering note**: MemoryEntryRefined modifies an entry that was
previously created by MemoryEntryCreated. The handler correctly reads from
`store.memory_entries` (populated by the create handler) and modifies in place.
No conflict with other handlers — the entry_id is unique and the create always
precedes the refine.

### Step 8: Qdrant sync

In `src/formicos/surface/runtime.py`, in the `emit_and_broadcast()` Qdrant sync
block (after the MemoryConfidenceUpdated case at line 501), add:

```python
            elif etype == "MemoryConfidenceUpdated":
                sync_id = str(getattr(event_with_seq, "entry_id", ""))
            elif etype == "MemoryEntryRefined":
                sync_id = str(getattr(event_with_seq, "entry_id", ""))
```

The existing `memory_store.sync_entry()` does full re-embed on upsert — the
content change triggers re-embedding automatically.

### Step 9: ADR-048

Create `docs/decisions/048-memory-entry-refined.md` following the existing ADR
format. Key content:

- **Context**: 64 events (current). Knowledge entries can only be created or
  merged. No in-place refinement. Curating archivist needs to improve existing
  entries without creating duplicates.
- **Decision**: Add MemoryEntryRefined event (65th event type). Carries
  entry_id, old_content (audit trail), new_content, new_title (optional),
  refinement_source (extraction/maintenance/operator), source_colony_id.
- **Alternatives rejected**: (1) Self-merge via MemoryEntryMerged — source gets
  marked rejected, semantically wrong for refinement. (2) Reuse
  MemoryEntryStatusChanged — doesn't carry content fields. (3) Direct projection
  mutation — violates event-sourcing (hard constraint #7).
- **Consequences**: Event count 64 to 65. Replay-safe. Audit trail via
  old_content. Qdrant sync automatic via existing upsert path.

Add to `docs/decisions/INDEX.md` after line 57:

```
| [048](048-memory-entry-refined.md) | MemoryEntryRefined Event for Knowledge Curation | Proposed |
```

### Step 10: Update CLAUDE.md event counts

Search CLAUDE.md for "64 events" or "62 events" references and update to 65.
The current text says "64 events, closed union" — change to "65 events, closed
union" after this wave lands.

### Step 11: Test

In `tests/unit/core/test_events.py`, add a serialization round-trip test:

```python
def test_memory_entry_refined_round_trip() -> None:
    from formicos.core.events import MemoryEntryRefined, serialize, deserialize

    event = MemoryEntryRefined(
        seq=1,
        timestamp=datetime.now(UTC),
        address="ws-1/th-1/col-1",
        entry_id="mem-col-1-s-0",
        workspace_id="ws-1",
        old_content="Original content about token buckets.",
        new_content="Token bucket rate limiting: use a counter decremented per request, refilled at fixed rate. Handle burst via bucket capacity.",
        new_title="",
        refinement_source="extraction",
        source_colony_id="col-2",
    )
    json_str = serialize(event)
    restored = deserialize(json_str)
    assert restored.type == "MemoryEntryRefined"
    assert restored.entry_id == "mem-col-1-s-0"
    assert restored.old_content == "Original content about token buckets."
    assert restored.new_content.startswith("Token bucket")
    assert restored.refinement_source == "extraction"
```

### Validation

```bash
uv run ruff check src/formicos/core/events.py src/formicos/surface/projections.py src/formicos/surface/runtime.py
uv run pyright src/formicos/core/events.py src/formicos/surface/projections.py src/formicos/surface/runtime.py
uv run python scripts/lint_imports.py
uv run pytest tests/unit/core/test_events.py -v -k "refined"
uv run pytest tests/unit/core/test_events.py tests/unit/surface/test_memory_entry_merged.py -v
```

---

## Track 2: Curating Extraction Prompt

**Goal**: Transform extraction from append-only to curate-aware. The archivist
sees existing entries before deciding to CREATE, REFINE, MERGE, or NOOP.

**HARD GATE: Track 1 MUST be merged before starting Track 2.** Track 2 emits
MemoryEntryRefined events that don't exist until Track 1 lands.

### Owned files

| File | Action |
|------|--------|
| `src/formicos/surface/memory_extractor.py` | Modify prompt builder + parser |
| `src/formicos/surface/colony_manager.py` | Fetch existing entries, dispatch REFINE/MERGE actions |
| `tests/unit/surface/test_memory_extractor.py` | NEW file — 8 tests |
| `tests/unit/surface/test_trajectory_extraction.py` | Regression only — run, do not modify |

### Do NOT touch

- `core/events.py` — Track 1 (already landed)
- `surface/projections.py` — Track 1
- `surface/runtime.py` — Track 1
- `surface/maintenance.py` — Track 3 (parallel)
- `surface/app.py` — Track 3
- `engine/context.py` — no changes this wave
- `surface/knowledge_catalog.py` — read-only usage

### Step 1: Fetch existing entries in colony_manager.py

In `extract_institutional_memory()` (line 1936), after the `_task_class`
classification (line 1973) and before the `build_extraction_prompt()` call
(line 1979), add:

```python
        # Wave 59: fetch existing entries for curation context
        existing_entries: list[dict[str, Any]] = []
        try:
            _kc = getattr(self._runtime, "knowledge_catalog", None)
            if _kc is not None:
                existing_entries = await _kc.search(
                    query=colony.task,
                    workspace_id=workspace_id,
                    top_k=10,
                )
                # Enrich with access counts
                for _item in existing_entries:
                    _usage = self._runtime.projections.knowledge_entry_usage.get(
                        _item.get("id", ""), {},
                    )
                    _item["access_count"] = _usage.get("count", 0)
        except Exception:  # noqa: BLE001
            log.warning("curation.existing_fetch_failed", colony_id=colony_id)
            existing_entries = []
```

The `knowledge_catalog` attribute is set on runtime in `app.py:364`. Access via
`getattr` for defensive coding — if catalog isn't initialized, degrade to
append-only extraction.

`knowledge_catalog.search()` signature (line 323 of knowledge_catalog.py):
```python
async def search(
    self, query: str, source_system: str = "", canonical_type: str = "",
    workspace_id: str = "", thread_id: str = "", source_colony_id: str = "",
    top_k: int = 10,
) -> list[dict[str, Any]]
```

### Step 2: Pass existing_entries to build_extraction_prompt

Update the `build_extraction_prompt()` call (line 1979) to pass the new
parameter:

```python
        prompt = build_extraction_prompt(
            task=colony.task,
            final_output=final_summary,
            artifacts=art_dicts,
            colony_status=colony_status,
            failure_reason=failure_reason,
            contract_result=None,
            task_class=_task_class,
            existing_entries=existing_entries,  # Wave 59
        )
```

### Step 3: Modify build_extraction_prompt() in memory_extractor.py

Current signature (line 88):
```python
def build_extraction_prompt(
    task: str, final_output: str, artifacts: list[dict[str, Any]],
    colony_status: str, failure_reason: str | None,
    contract_result: dict[str, Any] | None,
    task_class: str = "generic",
) -> str:
```

Add `existing_entries` parameter:
```python
def build_extraction_prompt(
    task: str, final_output: str, artifacts: list[dict[str, Any]],
    colony_status: str, failure_reason: str | None,
    contract_result: dict[str, Any] | None,
    task_class: str = "generic",
    existing_entries: list[dict[str, Any]] | None = None,
) -> str:
```

After the existing artifact section (after line 111) and before the
skills/experiences instruction block (line 113), add the curation context:

```python
    if existing_entries:
        parts.append("\nEXISTING ENTRIES (most relevant to this task domain):")
        for ee in existing_entries[:10]:
            ee_id = ee.get("id", "?")
            ee_title = ee.get("title", "untitled")
            ee_conf = float(ee.get("confidence", 0.5))
            ee_access = int(ee.get("access_count", 0))
            ee_domain = ee.get("primary_domain", "")
            ee_content = str(ee.get("content", ""))[:200]
            parts.append(
                f'- [{ee_id}] "{ee_title}" '
                f"(conf: {ee_conf:.2f}, accessed: {ee_access}x"
                f'{f", domain: {ee_domain}" if ee_domain else ""})\n'
                f"  Content: {ee_content}"
            )
```

Then replace the current instruction block. When existing_entries are provided,
use the curating instruction instead of the append-only instruction:

```python
    if existing_entries and colony_status == "completed":
        parts.append(
            "\nFor each piece of knowledge from this colony, decide:\n"
            '- CREATE: New knowledge not covered by existing entries.\n'
            '  Include all entry fields (title, content, domains, etc.)\n'
            '- REFINE: An existing entry should be updated with insights from\n'
            '  this colony. Provide "entry_id" + "new_content" (+ optional "new_title")\n'
            '- MERGE: Two entries should be combined. Provide "target_id" +\n'
            '  "source_id" + "merged_content"\n'
            '- NOOP: Existing entry already covers this adequately\n\n'
            'Return JSON: {"actions": [{"type": "CREATE"|"REFINE"|"MERGE"|"NOOP", ...}]}\n\n'
            "Be conservative. REFINE only when the colony produced genuinely new\n"
            "information that makes an existing entry more precise, more actionable,\n"
            "or corrects an error. NOOP is the right choice when existing coverage\n"
            "is adequate.\n"
        )
    elif colony_status == "completed":
        # Original append-only instruction (no existing entries available)
```

Keep the existing `colony_status == "completed"` and failure branches as the
else/elif fallback for when no existing_entries are provided.

The `primary_domain` and `decay_class` instructions (lines 133-148) stay as-is
— they apply to CREATE actions in both modes.

**Critical**: The `Return JSON: {"actions": [...]}` instruction replaces the
old `Return JSON: {"skills": [...], "experiences": [...]}` ONLY when
existing_entries are provided. When no existing entries exist, keep the old
format for backward compatibility.

### Step 4: Modify parse_extraction_response() in memory_extractor.py

Current function (line 223) returns `dict[str, Any]`. Change return type to
support both formats:

```python
def parse_extraction_response(text: str) -> dict[str, Any]:
```

After parsing the JSON (line 228), detect format and normalize:

```python
    if isinstance(result, dict):
        # Wave 59: detect curating format
        if "actions" in result:
            # Mixed format: prefer actions, ignore legacy keys
            if "skills" in result or "experiences" in result:
                log.warning("extraction.mixed_format_detected")
            return cast("dict[str, Any]", result)
        # Legacy format: return as-is (skills/experiences)
        return cast("dict[str, Any]", result)
```

### Step 5: Dispatch actions in colony_manager.py

In `extract_institutional_memory()`, after `parse_extraction_response()` (line
2022), replace the current `build_memory_entries()` call with action-aware
dispatch:

```python
        raw = parse_extraction_response(response.content)

        # Wave 59: action-aware dispatch
        if "actions" in raw:
            entries = []
            refine_actions: list[dict[str, Any]] = []
            merge_actions: list[dict[str, Any]] = []
            for action in raw.get("actions", []):
                action_type = action.get("type", "").upper()
                if action_type == "CREATE":
                    # Extract entry from action, use existing pipeline
                    entry_data = action.get("entry", action)
                    # Wrap as single-entry raw for build_memory_entries
                    cat = entry_data.get("canonical_type", entry_data.get("entry_type", "skill"))
                    if cat in ("skill", "technique", "pattern", "anti_pattern"):
                        single_raw = {"skills": [entry_data], "experiences": []}
                    else:
                        single_raw = {"skills": [], "experiences": [entry_data]}
                    entries.extend(build_memory_entries(
                        raw=single_raw,
                        colony_id=colony_id,
                        workspace_id=workspace_id,
                        artifact_ids=artifact_ids,
                        colony_status=colony_status,
                    ))
                elif action_type == "REFINE":
                    refine_actions.append({
                        "entry_id": action.get("entry_id", ""),
                        "new_content": action.get("new_content", ""),
                        "new_title": action.get("new_title", ""),
                    })
                elif action_type == "MERGE":
                    merge_actions.append({
                        "target_id": action.get("target_id", ""),
                        "source_id": action.get("source_id", ""),
                        "merged_content": action.get("merged_content", ""),
                    })
                # NOOP: log and skip
                elif action_type == "NOOP":
                    log.debug("curation.noop", entry_id=action.get("entry_id", ""))
        else:
            # Legacy format fallback
            entries = build_memory_entries(
                raw=raw,
                colony_id=colony_id,
                workspace_id=workspace_id,
                artifact_ids=artifact_ids,
                colony_status=colony_status,
            )
            refine_actions = []
            merge_actions = []
```

### Step 6: Emit REFINE events

After the existing entry emission loop (after the `emitted_count` tracking),
add REFINE dispatch:

```python
        # Wave 59: dispatch REFINE actions
        from formicos.core.events import MemoryEntryRefined  # noqa: PLC0415

        for ra in refine_actions:
            rid = ra["entry_id"]
            existing = self._runtime.projections.memory_entries.get(rid)
            if existing is None:
                log.warning("curation.refine_missing_entry", entry_id=rid)
                continue
            new_content = ra["new_content"].strip()
            if len(new_content) < 20:
                log.warning("curation.refine_empty_content", entry_id=rid)
                continue
            old_content = existing.get("content", "")
            if new_content == old_content:
                log.debug("curation.refine_no_change", entry_id=rid)
                continue
            await self._runtime.emit_and_broadcast(MemoryEntryRefined(
                seq=0,
                timestamp=_now(),
                address=address,
                entry_id=rid,
                workspace_id=workspace_id,
                old_content=old_content,
                new_content=new_content,
                new_title=ra.get("new_title", ""),
                refinement_source="extraction",
                source_colony_id=colony_id,
            ))
            log.info(
                "curation.entry_refined",
                entry_id=rid,
                colony_id=colony_id,
                old_len=len(old_content),
                new_len=len(new_content),
            )
```

### Step 7: Emit MERGE events

After the REFINE block, add MERGE dispatch:

```python
        # Wave 59: dispatch MERGE actions
        for ma in merge_actions:
            target_id = ma["target_id"]
            source_id = ma["source_id"]
            merged_content = ma.get("merged_content", "")
            target = self._runtime.projections.memory_entries.get(target_id)
            source = self._runtime.projections.memory_entries.get(source_id)
            if target is None or source is None:
                log.warning(
                    "curation.merge_missing_entry",
                    target_id=target_id, source_id=source_id,
                )
                continue
            if len(merged_content.strip()) < 20:
                log.warning("curation.merge_empty_content", target_id=target_id)
                continue
            await self._runtime.emit_and_broadcast(MemoryEntryMerged(
                seq=0,
                timestamp=_now(),
                address=address,
                target_id=target_id,
                source_id=source_id,
                merged_content=merged_content,
                merged_domains=list(
                    set(target.get("domains", []) + source.get("domains", [])),
                ),
                merged_from=list(
                    set(target.get("merged_from", [target_id])
                        + source.get("merged_from", [source_id])),
                ),
                content_strategy="llm_selected",
                similarity=0.0,  # Not similarity-based, curator-directed
                merge_source="extraction",
                workspace_id=workspace_id,
            ))
            log.info(
                "curation.entries_merged",
                target_id=target_id,
                source_id=source_id,
                colony_id=colony_id,
            )
```

Ensure `MemoryEntryMerged` is imported — check if it's already imported in the
existing imports at the top of the method. If not, add:

```python
        from formicos.core.events import MemoryEntryMerged  # noqa: PLC0415
```

### Step 8: Tests

Create `tests/unit/surface/test_memory_extractor.py` with 8 tests:

```python
"""Tests for memory_extractor.py curation features (Wave 59)."""

from __future__ import annotations

from typing import Any

from formicos.surface.memory_extractor import (
    build_extraction_prompt,
    parse_extraction_response,
)


def _existing_entries() -> list[dict[str, Any]]:
    return [
        {
            "id": "mem-col-42-s-0",
            "title": "Token bucket implementation",
            "confidence": 0.72,
            "access_count": 8,
            "primary_domain": "code_implementation",
            "content": "Implement rate limiting using a token bucket algorithm "
            "with configurable refill rate and burst capacity.",
        },
        {
            "id": "mem-col-30-e-1",
            "title": "Input validation convention",
            "confidence": 0.55,
            "access_count": 3,
            "primary_domain": "code_implementation",
            "content": "Always validate input types before processing to "
            "prevent runtime errors in downstream functions.",
        },
    ]


class TestCuratingPrompt:
    def test_curating_prompt_includes_existing_entries(self) -> None:
        prompt = build_extraction_prompt(
            task="implement auth endpoint",
            final_output="completed auth implementation",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=_existing_entries(),
        )
        assert "EXISTING ENTRIES" in prompt
        assert "mem-col-42-s-0" in prompt
        assert "Token bucket implementation" in prompt
        assert "conf: 0.72" in prompt
        assert "accessed: 8x" in prompt
        assert '{"actions":' in prompt or "actions" in prompt

    def test_curating_prompt_fallback_without_existing(self) -> None:
        prompt = build_extraction_prompt(
            task="implement something",
            final_output="done",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=None,
        )
        assert "EXISTING ENTRIES" not in prompt
        assert '"skills"' in prompt  # Legacy format instruction
        assert '"experiences"' in prompt

    def test_curating_prompt_empty_list_is_fallback(self) -> None:
        prompt = build_extraction_prompt(
            task="implement something",
            final_output="done",
            artifacts=[],
            colony_status="completed",
            failure_reason=None,
            contract_result=None,
            existing_entries=[],
        )
        assert "EXISTING ENTRIES" not in prompt


class TestActionParsing:
    def test_parse_actions_format(self) -> None:
        text = '{"actions": [{"type": "CREATE", "entry": {"title": "new"}}, {"type": "NOOP", "entry_id": "old-1"}]}'
        result = parse_extraction_response(text)
        assert "actions" in result
        assert len(result["actions"]) == 2
        assert result["actions"][0]["type"] == "CREATE"
        assert result["actions"][1]["type"] == "NOOP"

    def test_parse_legacy_format_fallback(self) -> None:
        text = '{"skills": [{"title": "s1", "content": "skill content"}], "experiences": []}'
        result = parse_extraction_response(text)
        assert "skills" in result
        assert len(result["skills"]) == 1

    def test_parse_refine_action(self) -> None:
        text = '{"actions": [{"type": "REFINE", "entry_id": "mem-1", "new_content": "improved content"}]}'
        result = parse_extraction_response(text)
        assert result["actions"][0]["type"] == "REFINE"
        assert result["actions"][0]["entry_id"] == "mem-1"

    def test_parse_merge_action(self) -> None:
        text = '{"actions": [{"type": "MERGE", "target_id": "t1", "source_id": "s1", "merged_content": "combined"}]}'
        result = parse_extraction_response(text)
        assert result["actions"][0]["type"] == "MERGE"

    def test_parse_mixed_format_prefers_actions(self) -> None:
        text = '{"actions": [{"type": "NOOP"}], "skills": [{"title": "ignored"}]}'
        result = parse_extraction_response(text)
        assert "actions" in result
        # Legacy keys may be present but actions should be preferred by caller
```

### Validation

```bash
uv run ruff check src/formicos/surface/memory_extractor.py src/formicos/surface/colony_manager.py
uv run pyright src/formicos/surface/memory_extractor.py src/formicos/surface/colony_manager.py
uv run pytest tests/unit/surface/test_memory_extractor.py -v
uv run pytest tests/unit/surface/test_trajectory_extraction.py -v  # Regression — must still pass
uv run python scripts/lint_imports.py
```

---

## Track 3: Curation Maintenance Handler

**Goal**: Add a periodic maintenance handler that selects popular-but-unexamined
entries and asks the archivist to refine them.

**HARD GATE: Track 1 MUST be merged before starting Track 3.** Track 3 emits
MemoryEntryRefined events that don't exist until Track 1 lands.

**Track 3 runs PARALLEL with Track 2.** Zero file overlap.

### Owned files

| File | Action |
|------|--------|
| `src/formicos/surface/maintenance.py` | Add `make_curation_handler()` factory |
| `src/formicos/surface/app.py` | Register handler (1 line) |
| `tests/unit/surface/test_curation_maintenance.py` | NEW file — 5 tests |

### Do NOT touch

- `core/events.py` — Track 1 (already landed)
- `surface/projections.py` — Track 1
- `surface/runtime.py` — Track 1
- `surface/memory_extractor.py` — Track 2 (parallel)
- `surface/colony_manager.py` — Track 2
- `surface/self_maintenance.py` — dispatcher infrastructure, read-only
- `surface/proactive_intelligence.py` — popular-unexamined rule already shipped (Wave 58.5)
- `maintenance.py` dedup handler — do not modify existing handlers

### Step 1: Add make_curation_handler factory

In `src/formicos/surface/maintenance.py`, add a new factory function. Follow the
same pattern as `make_dedup_handler()` (line 22).

The inner handler MUST match the service router dispatch signature:
`async def handler(query_text: str, ctx: dict[str, Any]) -> str`

```python
def make_curation_handler(runtime: Runtime):  # noqa: ANN201
    """Factory for periodic knowledge curation (Wave 59).

    Selects popular-but-unexamined entries (access >= 5, confidence < 0.65)
    and asks the archivist to refine them.
    """

    async def _handle_curation(query_text: str, ctx: dict[str, Any]) -> str:
        workspace_id = ctx.get("workspace_id", "")
        if not workspace_id:
            return "no workspace_id in context"

        # Select candidates: popular-but-unexamined
        candidates: list[dict[str, Any]] = []
        usage = getattr(runtime.projections, "knowledge_entry_usage", {})
        for eid, entry in runtime.projections.memory_entries.items():
            if entry.get("status") != "verified":
                continue
            if entry.get("workspace_id", "") != workspace_id:
                continue
            entry_usage = usage.get(eid, {})
            access_count = int(entry_usage.get("count", 0))
            if access_count < 5:
                continue
            alpha = float(entry.get("conf_alpha", 5.0))
            beta_val = float(entry.get("conf_beta", 5.0))
            denom = alpha + beta_val
            if denom <= 0:
                continue
            confidence = alpha / denom
            if confidence >= 0.65:
                continue
            candidates.append({
                **entry,
                "access_count": access_count,
                "confidence": confidence,
            })
            if len(candidates) >= 10:
                break

        if not candidates:
            return "no curation candidates"

        # Build prompt
        lines = [
            "You are reviewing knowledge entries that are frequently accessed "
            "but may need improvement.\n\nENTRIES TO REVIEW:",
        ]
        for c in candidates:
            cid = c.get("id", "?")
            ctitle = c.get("title", "untitled")
            cconf = float(c.get("confidence", 0.5))
            caccess = int(c.get("access_count", 0))
            ccontent = str(c.get("content", ""))
            cdomains = ", ".join(c.get("domains", []))
            lines.append(
                f'- [{cid}] "{ctitle}" (conf: {cconf:.2f}, accessed: {caccess}x)\n'
                f"  Content: {ccontent}\n"
                f"  Domains: {cdomains}"
            )
        lines.append(
            '\nFor each entry, decide:\n'
            '- REFINE: Improve the content to be more precise, actionable, or correct.\n'
            '  Provide "entry_id" + "new_content" (+ optional "new_title")\n'
            '- NOOP: Entry is already adequate. No change needed.\n\n'
            'Return JSON: {"actions": [...]}\n\n'
            "Be conservative. Only refine when you can make the entry genuinely better.\n"
            "Do not add speculative information. Do not generalize away specific details."
        )
        prompt = "\n".join(lines)

        # Call archivist model
        # Do NOT copy the dedup handler's hardcoded model.
        # The dedup handler at line 136 uses "gemini/gemini-2.5-flash" directly.
        # The curation handler MUST use resolve_model for proper fallback chain.
        model = runtime.resolve_model("archivist", workspace_id)
        try:
            response = await runtime.llm_router.complete(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You review knowledge entries for quality improvement. Return valid JSON only.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception:  # noqa: BLE001
            log.warning("curation_maintenance.llm_failed", workspace_id=workspace_id)
            return "archivist call failed"

        # Parse response
        import json  # noqa: PLC0415

        from json_repair import repair_json  # noqa: PLC0415

        try:
            parsed = json.loads(response.content)
        except json.JSONDecodeError:
            try:
                parsed = json.loads(repair_json(response.content))
            except Exception:  # noqa: BLE001
                log.warning("curation_maintenance.parse_failed", workspace_id=workspace_id)
                return "response parse failed"

        # Dispatch REFINE actions only
        from formicos.core.events import MemoryEntryRefined  # noqa: PLC0415

        refined_count = 0
        for action in parsed.get("actions", []):
            action_type = action.get("type", "").upper()
            if action_type != "REFINE":
                if action_type not in ("NOOP", ""):
                    log.warning(
                        "curation_maintenance.unexpected_action",
                        action_type=action_type,
                    )
                continue

            rid = action.get("entry_id", "")
            existing = runtime.projections.memory_entries.get(rid)
            if existing is None:
                log.warning("curation_maintenance.missing_entry", entry_id=rid)
                continue
            new_content = action.get("new_content", "").strip()
            if len(new_content) < 20:
                continue
            old_content = existing.get("content", "")
            if new_content == old_content:
                continue

            address = f"{workspace_id}/_maintenance/{rid}"
            await runtime.emit_and_broadcast(MemoryEntryRefined(
                seq=0,
                timestamp=_now(),
                address=address,
                entry_id=rid,
                workspace_id=workspace_id,
                old_content=old_content,
                new_content=new_content,
                new_title=action.get("new_title", ""),
                refinement_source="maintenance",
                source_colony_id="",
            ))
            refined_count += 1

        return f"curation complete: {refined_count} entries refined, {len(candidates)} reviewed"

    return _handle_curation
```

Ensure `_now` is available — it's already defined in maintenance.py. Also add
`from formicos.surface.runtime import Runtime` if not already imported (check
existing imports at top of file).

Add `"make_curation_handler"` to `__all__` (currently at lines 579-586):

```python
__all__ = [
    "make_dedup_handler",
    "make_stale_handler",
    "make_contradiction_handler",
    "make_confidence_reset_handler",
    "make_cooccurrence_decay_handler",
    "make_credential_sweep_handler",
    "make_curation_handler",  # Wave 59
]
```

### Step 2: Register in app.py

In `src/formicos/surface/app.py`, in the handler registration block (after line
605, after the `credential_sweep` registration), add:

```python
    service_router.register_handler(
        "service:consolidation:curation",
        make_curation_handler(runtime),
    )
```

Add the import alongside the existing maintenance imports (find the block where
`make_dedup_handler`, `make_stale_handler`, etc. are imported):

```python
from formicos.surface.maintenance import make_curation_handler
```

### Step 3: Tests

Create `tests/unit/surface/test_curation_maintenance.py`:

```python
"""Tests for curation maintenance handler (Wave 59 Track 3)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest


@dataclasses.dataclass
class _FakeProjections:
    memory_entries: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    knowledge_entry_usage: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)


def _entry(
    eid: str,
    *,
    status: str = "verified",
    workspace_id: str = "ws-1",
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    content: str = "Some knowledge content that is long enough to pass validation gates.",
    title: str = "Test entry",
    domains: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": eid,
        "status": status,
        "workspace_id": workspace_id,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "content": content,
        "title": title,
        "domains": domains or ["code_implementation"],
    }


class TestCurationCandidateSelection:
    """Test the candidate selection logic (no LLM call needed)."""

    def test_selects_popular_low_conf(self) -> None:
        """Entry with access >= 5 and confidence < 0.65 is selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=5.0, conf_beta=5.0)},
            knowledge_entry_usage={"e1": {"count": 7, "last_accessed": "2026-03-23"}},
        )
        # confidence = 5/(5+5) = 0.50, access = 7 → selected
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 1
        assert candidates[0]["id"] == "e1"

    def test_skips_low_access(self) -> None:
        """Entry with access < 5 is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=5.0, conf_beta=5.0)},
            knowledge_entry_usage={"e1": {"count": 2}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_skips_high_conf(self) -> None:
        """Entry with confidence >= 0.65 is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=7.0, conf_beta=3.0)},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        # confidence = 7/10 = 0.70 → skipped
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_skips_wrong_workspace(self) -> None:
        """Entry from different workspace is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", workspace_id="ws-other")},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_respects_batch_limit(self) -> None:
        """Max 10 candidates selected."""
        entries = {}
        usage = {}
        for i in range(15):
            eid = f"e{i}"
            entries[eid] = _entry(eid)
            usage[eid] = {"count": 10}
        proj = _FakeProjections(memory_entries=entries, knowledge_entry_usage=usage)
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 10


def _select_candidates(
    proj: _FakeProjections, workspace_id: str,
) -> list[dict[str, Any]]:
    """Extract candidate selection logic for unit testing.

    This mirrors the selection logic in make_curation_handler's inner function.
    If the handler's selection logic changes, update this helper to match.
    """
    candidates: list[dict[str, Any]] = []
    usage = getattr(proj, "knowledge_entry_usage", {})
    for eid, entry in proj.memory_entries.items():
        if entry.get("status") != "verified":
            continue
        if entry.get("workspace_id", "") != workspace_id:
            continue
        entry_usage = usage.get(eid, {})
        access_count = int(entry_usage.get("count", 0))
        if access_count < 5:
            continue
        alpha = float(entry.get("conf_alpha", 5.0))
        beta_val = float(entry.get("conf_beta", 5.0))
        denom = alpha + beta_val
        if denom <= 0:
            continue
        confidence = alpha / denom
        if confidence >= 0.65:
            continue
        candidates.append({**entry, "access_count": access_count, "confidence": confidence})
        if len(candidates) >= 10:
            break
    return candidates
```

**Note**: These tests validate candidate selection logic without mocking the LLM.
Full integration tests (LLM call + event emission) would require the runtime mock
pattern from `test_self_maintenance.py`. If time permits, add one async test that
mocks `runtime.llm_router.complete()` and verifies `MemoryEntryRefined` emission.

### Validation

```bash
uv run ruff check src/formicos/surface/maintenance.py src/formicos/surface/app.py
uv run pyright src/formicos/surface/maintenance.py src/formicos/surface/app.py
uv run pytest tests/unit/surface/test_curation_maintenance.py -v
uv run pytest tests/unit/surface/test_maintenance.py -v  # Regression — existing handlers still work
uv run python scripts/lint_imports.py
```

---

## Full CI (run after all three tracks land)

```bash
uv run ruff check src/ && uv run pyright src/ && uv run python scripts/lint_imports.py && uv run pytest
```

Expected: 9 pre-existing failures unchanged, 0 new failures, new tests pass.
