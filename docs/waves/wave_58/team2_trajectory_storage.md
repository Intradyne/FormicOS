# Team 2: Trajectory Storage

## Context

Research shows that storing and replaying tool-call trajectories from
successful colonies dramatically improves future task quality. AgentRR
(trajectory replay) achieved +36.69% improvement. AllianceCoder (targeted
API sequences) gained +20%. FormicOS's own playbooks, which prescribe tool
sequences, outperform retrieved text summaries by 18x.

The principle: **store what the colony DID, not what the LLM said about
what it did.** Text summaries are the LLM's interpretation of the work.
Trajectories are the actual tool-call sequence -- deterministic, structured,
and directly replayable. A trajectory like "read -> write -> execute (fail)
-> patch -> execute (success)" teaches a future colony the recovery pattern,
not just "error handling is important."

---

## Implementation

Five changes across four files.

### Change 1: EntrySubType.trajectory in types.py

**File**: `src/formicos/core/types.py`

**Step A**: Add `trajectory` to the `EntrySubType` enum (currently at line 339).
Insert after line 354 (`bug = "bug"`):

```python
    # Under "skill" -- tool-call sequence from successful colony (Wave 58)
    trajectory = "trajectory"
```

The enum will have 8 members: technique, pattern, anti_pattern, trajectory,
decision, convention, learning, bug. Update the docstring (line 340-343) to
include trajectory:

```python
    """Granular sub-type within skill/experience (Wave 34 B3).

    Skills: technique, pattern, anti_pattern, trajectory.
    Experiences: decision, convention, learning, bug.
    """
```

**Step B**: Add `trajectory_data` field to `MemoryEntry` (currently at
line 377). Insert after the last field `playbook_generation` (line 430-433):

```python
    trajectory_data: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Compressed tool-call sequence for trajectory entries (Wave 58). "
            "Each dict: {tool: str, agent_id: str, round_number: int}."
        ),
    )
```

Note: You will need to add `Any` to the typing imports if not already present.
Check line 8 -- it already imports `Any` via `from typing import Any, Literal, TypeAlias, TypedDict`.

### Change 2: _hook_trajectory_extraction in colony_manager.py

**File**: `src/formicos/surface/colony_manager.py`

**Step A**: Add the hook call to `_post_colony_hooks()`.

The method is at lines 1041-1074. The last hook is `_hook_auto_template()`
at line 1072-1074. After line 1074, add:

```python
        # Wave 58: trajectory extraction from successful colonies
        if succeeded:
            await self._hook_trajectory_extraction(
                colony_id, ws_id, quality,
                productive_calls, total_calls,
            )
```

Note: `total_productive_calls` and `total_total_calls` are accumulated in
the round loop (line 833-834) and are local variables in the `_run_colony()`
method that calls `_post_colony_hooks()`. You need to pass them through.
Add two parameters to `_post_colony_hooks()`:

```python
    async def _post_colony_hooks(
        self,
        colony_id: str,
        colony: Any,
        quality: float,
        total_cost: float,
        rounds_completed: int,
        skills_count: int,
        retrieved_skill_ids: set[str],
        governance_warnings: int,
        stall_count: int,
        succeeded: bool,
        productive_calls: int = 0,   # NEW
        total_calls: int = 0,        # NEW
    ) -> None:
```

And update the call sites in `_run_colony()` to pass them. Search for
`await self._post_colony_hooks(` -- there are **3 call sites** (completion
at ~line 936, halt/force_halt at ~line 991, max-rounds at ~line 1027).
The two `succeeded=True` paths (completion + max-rounds) need the new params:
`productive_calls=total_productive_calls, total_calls=total_total_calls`.
The `succeeded=False` path (halt) can rely on the defaults since the
trajectory hook is gated on `if succeeded:`.

**Test blast radius**: 4 test files call `_post_colony_hooks()` with 11
total calls (test_bayesian_confidence, test_colony_observation,
test_confidence_event, test_step_continuation). All use keyword arguments.
Since the new params have defaults, **no existing tests break**. Verify
this by running `uv run pytest tests/unit/surface/ -x -q` after adding
the parameters.

**Step B**: Implement `_hook_trajectory_extraction()` as a new method.

Place it after the existing hooks section (after `_hook_auto_template`).
The method:

1. Checks quality gate: `quality >= 0.30`
2. Checks productivity gate: `productive_calls / total_calls >= 0.6`
   (if `total_calls == 0`, skip -- no tool calls means no trajectory)
3. Reads `round_records` from the projection to build the tool-call sequence
4. Builds a human-readable content string for embedding
5. Creates a MemoryEntry with `sub_type=EntrySubType.trajectory`
6. Emits `MemoryEntryCreated` event

```python
    async def _hook_trajectory_extraction(
        self,
        colony_id: str,
        workspace_id: str,
        quality: float,
        productive_calls: int,
        total_calls: int,
    ) -> None:
        """Extract tool-call trajectory from successful colonies (Wave 58).

        Deterministic: reads tool_calls from AgentTurnCompleted events
        recorded in the projection. No LLM call.
        """
        # Quality gate
        if quality < 0.30:
            log.debug("trajectory.skip_low_quality", colony_id=colony_id, quality=quality)
            return

        # Productivity gate: at least 60% productive calls
        if total_calls == 0:
            return
        productive_ratio = productive_calls / total_calls
        if productive_ratio < 0.6:
            log.debug(
                "trajectory.skip_low_productivity",
                colony_id=colony_id,
                productive_ratio=round(productive_ratio, 2),
            )
            return

        # Read round records from projection
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is None:
            return

        # Build trajectory steps from round records.
        # Replay truth today:
        # - ColonyProjection has `round_records`, not `rounds`
        # - each RoundProjection has `tool_calls: dict[agent_id, list[str]]`
        # Tool args and per-call success are NOT currently available here.
        steps: list[dict[str, Any]] = []
        round_records = getattr(colony_proj, "round_records", None)
        if round_records is None:
            round_records = (
                colony_proj.get("round_records", [])
                if isinstance(colony_proj, dict) else []
            )

        for round_rec in round_records:
            round_num = (
                round_rec.get("round_number", 0)
                if isinstance(round_rec, dict)
                else getattr(round_rec, "round_number", 0)
            )
            tool_call_map = (
                round_rec.get("tool_calls", {})
                if isinstance(round_rec, dict)
                else getattr(round_rec, "tool_calls", {})
            )
            for agent_id, tool_calls in dict(tool_call_map or {}).items():
                for tool_name in tool_calls:
                    steps.append({
                        "tool": str(tool_name),
                        "agent_id": str(agent_id),
                        "round_number": round_num,
                    })

        if len(steps) < 2:
            log.debug("trajectory.skip_trivial", colony_id=colony_id, steps=len(steps))
            return

        # Classify task
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        goal = ""
        if isinstance(colony_proj, dict):
            goal = colony_proj.get("task", "")
        else:
            goal = getattr(colony_proj, "task", "")
        task_class, _ = classify_task(goal)

        # Build human-readable content for embedding
        tool_seq = " -> ".join(s["tool"] for s in steps[:20])
        rounds_completed = (
            colony_proj.get("round_number", len(round_records))
            if isinstance(colony_proj, dict)
            else getattr(colony_proj, "round_number", len(round_records))
        )

        content = (
            f"Successful {task_class} pattern "
            f"({rounds_completed} rounds, quality {quality:.2f}, "
            f"productivity {productive_ratio:.0%}): {tool_seq}."
        )

        now_str = datetime.now(UTC).isoformat()
        entry = MemoryEntry(
            id=f"traj-{colony_id}",
            entry_type=MemoryEntryType.skill,
            sub_type=EntrySubType.trajectory,
            # Intentional: status=verified + scan_status=safe bypasses the
            # admission pipeline.  Trajectory data is deterministic tool names
            # from the projection, not user-generated content, so security
            # scanning adds no value.
            status=MemoryEntryStatus.verified,
            polarity=MemoryEntryPolarity.positive,
            title=f"Trajectory: {task_class} ({len(steps)} steps)",
            content=content,
            summary=f"{task_class} tool sequence, {len(steps)} steps, quality {quality:.2f}",
            source_colony_id=colony_id,
            source_artifact_ids=[],
            domains=[task_class],
            tool_refs=list({s["tool"] for s in steps}),
            confidence=min(quality, 0.8),
            # Hard constraint #9: Beta(alpha, beta) posteriors, not scalar.
            # Total mass = 10 (same as default prior), mean = quality.
            conf_alpha=max(2.0, quality * 10),
            conf_beta=max(2.0, (1.0 - quality) * 10),
            decay_class=DecayClass.stable,
            scan_status=ScanStatus.safe,
            trajectory_data=steps[:30],  # cap at 30 steps
            workspace_id=workspace_id,
            created_at=now_str,
        )

        # Emit via the standard memory entry path
        await self._runtime.emit_and_broadcast(MemoryEntryCreated(
            seq=0,
            timestamp=datetime.now(UTC),
            colony_id=colony_id,
            workspace_id=workspace_id,
            entry=entry.model_dump(),
        ))
        log.info(
            "trajectory.extracted",
            colony_id=colony_id,
            task_class=task_class,
            steps=len(steps),
            quality=round(quality, 2),
        )
```

You will need these imports. **Follow the existing pattern**: colony_manager.py
uses **deferred imports** inside method bodies (see `_hook_memory_extraction`
at ~line 1812 and `_hook_transcript_harvest` at ~line 1219 for examples).
Do NOT add them at the top of the file. Place them inside
`_hook_trajectory_extraction()`:

```python
        from formicos.core.events import MemoryEntryCreated  # noqa: PLC0415
        from formicos.core.types import (  # noqa: PLC0415
            DecayClass,
            EntrySubType,
            MemoryEntry,
            MemoryEntryPolarity,
            MemoryEntryStatus,
            MemoryEntryType,
            ScanStatus,
        )
```

Also import `datetime` and `UTC`:
```python
        from datetime import UTC, datetime  # noqa: PLC0415
```
Check whether `datetime`/`UTC` are already available at module level before
adding the deferred import.

**Important**: The projection structure for colony round records varies.
Read `src/formicos/surface/projections.py` to understand the actual
structure of `store.colonies[colony_id]` and how round data / tool calls
are stored. The implementation above uses both dict-style and attribute-style
access as a safety pattern. Adjust based on what you find in projections.py.

### Change 3: Include trajectory_data in memory_store embedding

**File**: `src/formicos/surface/memory_store.py`

In the `upsert_entry()` method (line 38), the `embed_text` is constructed
at lines 44-50. After line 50 (the `domains` line), add:

```python
        # Wave 58: include trajectory tool sequence in embedding text
        traj = entry.get("trajectory_data", [])
        if traj:
            tool_seq = " -> ".join(str(s.get("tool", "")) for s in traj[:20])
            embed_text += f" trajectory: {tool_seq}"
```

Also add `trajectory_data` to the metadata dict (lines 55-71). After
line 70 (`"created_at": ...`), add:

```python
                "trajectory_data": entry.get("trajectory_data", []),
                "sub_type": str(entry.get("sub_type", "")),
```

Note: `sub_type` is NOT currently stored in the metadata dict. Add it so
that retrieval results carry the sub_type field for Team 1's gate and
Team 3's display formatting.

### Change 4: Increase retrieval top_k for progressive disclosure

**File**: `src/formicos/surface/runtime.py`

In `fetch_knowledge_for_colony()` (line 1080), change the default `top_k`
from 5 to 8:

```python
    async def fetch_knowledge_for_colony(
        self,
        task: str,
        workspace_id: str,
        thread_id: str = "",
        top_k: int = 8,   # Wave 58: wider net for index-only format
    ) -> list[dict[str, Any]]:
```

Also update the two explicit call sites in `colony_manager.py` that pass
`top_k=5`:
- line ~642: change `top_k=5` to `top_k=8`
- line ~699: change `top_k=5` to `top_k=8`

**Why**: Team 3 changes context.py to slice `knowledge_items[:8]` instead of
`[:5]` because the index-only format is ~50 tokens/entry (vs ~160 before).
But if only 5 items are fetched upstream, the wider slice is a no-op.

### Change 5: Format trajectory in knowledge_detail response

**File**: `src/formicos/surface/runtime.py`

In the `make_knowledge_detail_fn()` method (line 1142), the inner function
`_knowledge_detail()` is at lines 1150-1164. The current response format is:

```python
        async def _knowledge_detail(item_id: str) -> str:
            result = await catalog.get_by_id(item_id)
            if result is None:
                return f"Error: knowledge item '{item_id}' not found"
            content = (
                result.get("content_preview", "") or result.get("summary", "")
            )
            title = result.get("title", "")
            source = result.get("source_system", "")
            return (
                f"[{result.get('canonical_type', 'skill').upper()}, {source}] "
                f"{title}\n\n{content}"
            )
```

Replace with trajectory-aware formatting:

```python
        async def _knowledge_detail(item_id: str) -> str:
            result = await catalog.get_by_id(item_id)
            if result is None:
                return f"Error: knowledge item '{item_id}' not found"

            title = result.get("title", "")
            source = result.get("source_system", "")
            ctype = result.get("canonical_type", "skill").upper()

            # Wave 58: trajectory entries get structured step display
            traj_data = result.get("trajectory_data", [])
            sub_type = result.get("sub_type", "")
            if sub_type == "trajectory" and traj_data:
                content = result.get("content_preview", "") or result.get("content", "")
                lines = [f"[TRAJECTORY, {source}] {title}", "", content, ""]

                # Group steps by round
                rounds: dict[int, list[str]] = {}
                for step in traj_data:
                    rn = step.get("round_number", 0)
                    agent_id = step.get("agent_id", "?")
                    tool = step.get("tool", "?")
                    rounds.setdefault(rn, []).append(f"{agent_id}: {tool}")

                lines.append("Tool sequence:")
                for rn in sorted(rounds):
                    tools_str = ", ".join(rounds[rn])
                    lines.append(f"  Round {rn}: {tools_str}")

                domains = result.get("domains", [])
                tool_refs = result.get("tool_refs", [])
                if domains:
                    lines.append(f"\nDomains: {', '.join(domains)}")
                if tool_refs:
                    lines.append(f"Tools referenced: {', '.join(tool_refs)}")

                return "\n".join(lines)

            # Standard (non-trajectory) format
            content = (
                result.get("content_preview", "") or result.get("summary", "")
            )
            return (
                f"[{ctype}, {source}] "
                f"{title}\n\n{content}"
            )
```

---

## Tests to write

File: `tests/unit/surface/test_trajectory_extraction.py` (NEW file)

### test_trajectory_extraction_from_successful_colony

```
Given: A mock colony projection with:
  - status = "completed"
  - quality = 0.50
  - productive_calls = 8, total_calls = 10 (ratio 0.80)
  - round_records with tool_calls = {"coder-1": ["read_workspace_file", "write_workspace_file", "code_execute"]}
Expect: MemoryEntryCreated event emitted with:
  - entry["sub_type"] == "trajectory"
  - entry["entry_type"] == "skill"
  - entry["status"] == "verified"
  - entry["decay_class"] == "stable"
  - entry["trajectory_data"] has 3 steps
  - entry["content"] contains "Successful" and the tool sequence
```

### test_trajectory_extraction_skips_failed_colony

```
Given: succeeded = False
Expect: _hook_trajectory_extraction is NOT called
  (the hook call is inside `if succeeded:` in _post_colony_hooks)
```

### test_trajectory_extraction_skips_low_quality

```
Given: quality = 0.20 (below 0.30 threshold)
       productive_calls = 8, total_calls = 10
Expect: No MemoryEntryCreated emitted, debug log "trajectory.skip_low_quality"
```

### test_trajectory_extraction_skips_low_productivity

```
Given: quality = 0.50
       productive_calls = 3, total_calls = 10 (ratio 0.30, below 0.60)
Expect: No MemoryEntryCreated emitted, debug log "trajectory.skip_low_productivity"
```

### test_trajectory_entry_stored_as_memory_entry

```
Given: A valid trajectory entry dict with trajectory_data field
Expect: MemoryStore.upsert_entry() embeds the trajectory tool sequence
  in embed_text, and stores trajectory_data in metadata
```

### test_knowledge_detail_formats_trajectory

```
Given: catalog.get_by_id returns a result with:
  - sub_type = "trajectory"
  - trajectory_data = [
      {"tool": "read_workspace_file", "agent_id": "coder-1", "round_number": 1},
      {"tool": "write_workspace_file", "agent_id": "coder-1", "round_number": 1},
      {"tool": "code_execute", "agent_id": "coder-1", "round_number": 2},
      {"tool": "patch_file", "agent_id": "coder-1", "round_number": 2},
      {"tool": "code_execute", "agent_id": "coder-1", "round_number": 3},
    ]
Expect: Response contains:
  - "[TRAJECTORY," header
  - "Tool sequence:" section
  - "Round 1: coder-1: read_workspace_file, coder-1: write_workspace_file"
  - "Round 2: coder-1: code_execute, coder-1: patch_file"
  - "Round 3: coder-1: code_execute"
```

---

## Files owned

- `src/formicos/core/types.py` (EntrySubType enum, MemoryEntry field)
- `src/formicos/surface/colony_manager.py` (hook call + implementation)
- `src/formicos/surface/memory_store.py` (embed text + metadata)
- `src/formicos/surface/runtime.py` (knowledge_detail formatting)

## Do not touch

- `src/formicos/engine/context.py` (Team 1 + Team 3)
- `src/formicos/engine/tool_dispatch.py` (Team 3)
- `src/formicos/surface/knowledge_catalog.py` (pre-dispatch fix landed
  `sub_type` on `KnowledgeItem` and `_normalize_institutional()` — the
  field now propagates through the retrieval round-trip)
- `src/formicos/surface/projections.py` -- read it for structure reference,
  but do NOT modify it. Recent eval harness work added `last_activity_at`
  (line 391) to `ColonyProjection`. Your hook reads from the projection
  but does not write to it.
- `src/formicos/eval/sequential_runner.py`

## Validation commands

```bash
uv run ruff check src/
uv run pyright src/
uv run pytest tests/unit/core/test_types.py tests/unit/surface/ -x -q
```

Run the full CI before declaring done:

```bash
uv run ruff check src/ && uv run pyright src/ && python scripts/lint_imports.py && uv run pytest
```

## Merge order

You merge in **parallel with Team 1** (no file overlap). Team 3 depends
on your merge -- they need `sub_type="trajectory"` to exist in types.py
and to be populated on entries flowing through the retrieval pipeline.

## Important: Projection structure

Before implementing `_hook_trajectory_extraction()`, READ
`src/formicos/surface/projections.py` to understand:

1. `ColonyProjection` is a **dataclass** (not dict, not Pydantic). Access via
   `self._runtime.projections.get_colony(colony_id)` -- this is the universal
   pattern in colony_manager.py (~20 call sites use it). The task description
   is `colony_proj.task` (not `.goal`).
2. Round records: `colony_proj.round_records` (a `list[RoundProjection]`)
3. Tool calls: `round_rec.tool_calls` is `dict[str, list[str]]` mapping
   `agent_id -> [tool_name, ...]`

The implementation above uses defensive dict/attribute dual-access as a
safety pattern. Since `ColonyProjection` is a dataclass, the attribute
access path is the one that will execute. Adjust if you find otherwise.

Also check how `_hook_memory_extraction()` (the existing text extraction
hook) accesses the colony projection -- follow the same pattern for
consistency.
