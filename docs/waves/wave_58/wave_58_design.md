# Wave 58 Design: Specificity Gate + Trajectory Storage + Progressive Disclosure

**Date**: 2026-03-22
**Status**: Design (pre-dispatch)
**Depends on**: Wave 55.5 semantic threshold, Wave 56.5 playbooks, Wave 57 audit findings

---

## Section 1: Specificity Gate Design

### Q1: Where does the gate live?

**Recommendation: `context.py`, line ~459, before the knowledge injection loop.**

Rationale: The gate decides whether to INJECT knowledge, not whether to
RETRIEVE it. Retrieval is already done by `colony_manager.fetch_knowledge_for_colony()`
at colony start (runtime.py:1080-1102, called at colony_manager.py:638-643). Moving
the gate to retrieval time would require changing colony_manager's round loop, which
is high-blast-radius. The context.py injection point is already the narrowest seam —
it receives `knowledge_items` and decides what enters the prompt.

The gate replaces the current unconditional loop at context.py:459 (`if knowledge_items:`)
with a conditional check.

```python
# context.py, replacing line 459
if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
    # ... existing injection loop ...
```

The retrieval call in runtime.py:1080-1102 stays unchanged. Knowledge is still
fetched (needed for access tracking, forage signal detection, and the
`knowledge_detail` tool). The gate only controls injection into the prompt.

### Q2: What triggers retrieval vs skip?

**Recommendation: Knowledge pool relevance check (option C + A hybrid).**

Pure task-class routing (option B) is too coarse — `classify_task()` in
task_classifier.py uses keyword matching across 5 categories (code_implementation,
code_review, research, design, creative). None of these categories distinguish
"general coding" from "project-specific coding." An LLM probe (option D) adds
latency to every round.

The gate uses two fast checks:

```python
# context.py — new function, ~20 lines

_GENERAL_TASK_SIGNALS: frozenset[str] = frozenset({
    # Standard library / well-known patterns the model already knows
    "implement", "write", "build", "create", "function", "class",
    "script", "program", "parse", "validate", "format", "convert",
    "sort", "filter", "merge", "split", "test", "debug",
})

_PROJECT_SIGNALS: frozenset[str] = frozenset({
    # Signals that the task references project-specific knowledge
    "our", "existing", "internal", "custom", "legacy", "current",
    "workspace", "codebase", "repo", "project", "module",
})


def _should_inject_knowledge(
    round_goal: str,
    knowledge_items: list[dict[str, Any]],
) -> bool:
    """Specificity gate: skip injection when knowledge won't help.

    Returns True (inject) when:
    1. Task contains project-specific signals, OR
    2. Top retrieved entry has raw similarity >= 0.55 (strong match exists)

    Returns False (skip) when:
    1. Task is purely general coding (no project signals), AND
    2. Best available entry has similarity < 0.55 (no strong match)
    """
    words = set(round_goal.lower().split())

    # Check 1: project-specific language in the task
    if words & _PROJECT_SIGNALS:
        return True

    # Check 2: does the pool contain a strong match?
    if knowledge_items:
        top_sim = max(
            float(item.get("similarity", item.get("score", 0.0)))
            for item in knowledge_items[:5]
        )
        if top_sim >= 0.55:
            return True

    return False
```

**Why 0.55 and not 0.50?** The existing threshold (0.50) gates individual
entries. The specificity gate decides whether to inject ANY entries. A higher
bar (0.55) means "at least one entry is genuinely relevant" vs "at least one
entry barely passes." The 0.05 gap prevents the specificity gate from being
redundant with the per-entry threshold.

### Q3: Interaction with existing threshold

**Both are needed. They serve different purposes.**

| Gate | Scope | Question it answers |
|------|-------|-------------------|
| Specificity gate | Entire injection block | "Should this task receive ANY knowledge?" |
| Semantic threshold (0.50) | Individual entry | "Is THIS entry relevant enough to inject?" |

Flow:
```
knowledge_items arrive at context.py:459
  → Specificity gate: any project signal OR top_sim >= 0.55?
    → NO: skip entire [System Knowledge] block (0 tokens injected)
    → YES: enter injection loop
      → Per-entry threshold: similarity >= 0.50?
        → NO: skip this entry
        → YES: inject this entry
```

The specificity gate is the coarse filter (save the entire 800-token budget
when nothing is relevant). The semantic threshold is the fine filter (skip
individual weak entries when some are relevant).

### Q4: Config surface

**Environment variable toggle, default ON (skip general tasks).**

```python
# context.py, near line 51
_SPECIFICITY_GATE_ENABLED: bool = (
    os.environ.get("FORMICOS_SPECIFICITY_GATE", "1") == "1"
)
```

When disabled (`FORMICOS_SPECIFICITY_GATE=0`), the gate always returns True
(inject). This lets eval runs compare with/without the gate.

No per-workspace or per-task setting needed. The gate is self-adaptive — it
checks the actual retrieved similarity, so project-specific workspaces with
relevant knowledge automatically pass the gate.

### Q5: Production detection of project-specific knowledge

In production, the gate works without changes:

1. **Project-specific workspaces** accumulate domain-specific knowledge
   entries over time. These entries have high semantic similarity to future
   tasks in the same domain. The similarity check (top_sim >= 0.55) naturally
   activates injection.

2. **Task descriptions** in production often reference project concepts:
   "fix the auth middleware", "update our billing pipeline", "refactor the
   existing ingestion service." These hit `_PROJECT_SIGNALS`.

3. **Empty/sparse pools** (new workspaces, general tasks) produce low
   similarity scores (<0.55) and no project signals, so the gate correctly
   skips injection.

### Test cases

| Task | Project signals? | Top similarity | Gate result |
|------|-----------------|---------------|-------------|
| "implement a token bucket rate limiter" | No | 0.41 (email validation entry) | **SKIP** |
| "parse CSV and compute statistics" | No | 0.67 (csv-analyzer entry) | **INJECT** |
| "fix our auth middleware token refresh" | Yes ("our") | any | **INJECT** |
| "write a haiku about spring" | No | 0.30 | **SKIP** |
| "refactor the existing billing pipeline" | Yes ("existing") | any | **INJECT** |
| "implement email validation" (after csv-analyzer ran) | No | 0.67 (email entry) | **INJECT** |

### Files modified

| File | Change |
|------|--------|
| `engine/context.py` | Add `_should_inject_knowledge()`, `_SPECIFICITY_GATE_ENABLED`, wrap line 459 |
| `engine/context.py` | Add `_GENERAL_TASK_SIGNALS`, `_PROJECT_SIGNALS` frozensets |

**No new events. No new types. No config file changes.**

---

## Section 2: Trajectory Storage Design

Implementation reality note (2026-03-22):

- the current replay surface can reliably recover ordered tool names per
  round and per agent from `ColonyProjection.round_records[*].tool_calls`
- it does NOT currently expose tool arguments or per-call success status
  without widening event capture

The dispatch prompts for Wave 58 therefore use a slimmer first-pass
trajectory schema based on:

- `tool`
- `agent_id`
- `round_number`

The richer `key_arg` / `succeeded` design below is still a valid future
direction, but it is not the operative implementation target for this wave.

### Q1: What exactly is stored?

**Recommendation: Compressed trajectory (option B) — tool name + key argument + result status.**

Full tool-call arrays (option A) are too large — a single `write_workspace_file`
call can have 500+ chars of code content. Generalized templates (option C)
require an LLM call for every extraction, adding latency and cost.

Schema:

```python
# A trajectory step — one tool call, compressed
@dataclass(frozen=True)
class TrajectoryStep:
    tool: str            # e.g. "write_workspace_file"
    key_arg: str         # e.g. "pipeline.py" (first string arg or empty)
    succeeded: bool      # did the tool call return without error?
    round_number: int    # which round this happened in

# A complete trajectory — the tool-call sequence from a successful colony
@dataclass(frozen=True)
class ColonyTrajectory:
    colony_id: str
    task_class: str           # from classify_task()
    task_summary: str         # first 200 chars of task description
    steps: list[TrajectoryStep]
    total_rounds: int
    quality_score: float      # from ColonyOutcome
    workspace_id: str
    created_at: str
```

Example compressed trajectory:

```json
{
  "colony_id": "colony-2c5742a4",
  "task_class": "code_implementation",
  "task_summary": "Read CSV file, compute summary statistics...",
  "steps": [
    {"tool": "read_workspace_file", "key_arg": "data.csv", "succeeded": true, "round_number": 1},
    {"tool": "write_workspace_file", "key_arg": "analyzer.py", "succeeded": true, "round_number": 1},
    {"tool": "code_execute", "key_arg": "python analyzer.py", "succeeded": false, "round_number": 2},
    {"tool": "patch_file", "key_arg": "analyzer.py", "succeeded": true, "round_number": 2},
    {"tool": "code_execute", "key_arg": "python analyzer.py", "succeeded": true, "round_number": 3}
  ],
  "total_rounds": 5,
  "quality_score": 0.48,
  "workspace_id": "default",
  "created_at": "2026-03-22T..."
}
```

### Q2: Where is it stored?

**Recommendation: New field on MemoryEntry (option B) with text content for embedding.**

Trajectories are NOT stored as a separate type. They are stored as a regular
`MemoryEntry` with `entry_type="skill"` and `sub_type="trajectory"`.

Add `"trajectory"` to `EntrySubType` enum in `core/types.py:339`:

```python
class EntrySubType(StrEnum):
    # Under "skill"
    technique = "technique"
    pattern = "pattern"
    anti_pattern = "anti_pattern"
    trajectory = "trajectory"     # NEW: tool-call sequence from successful colony
    # Under "experience"
    decision = "decision"
    convention = "convention"
    learning = "learning"
    bug = "bug"
```

The entry's `content` field contains a human-readable description of the
trajectory (for embedding and display). The structured trajectory data lives
in a new optional field:

```python
# core/types.py, add to MemoryEntry class after line 433
trajectory_data: list[dict[str, Any]] = Field(
    default_factory=list,
    description="Compressed tool-call sequence for trajectory entries (Wave 58).",
)
```

**Why not separate storage?** Trajectories benefit from the entire existing
pipeline: Qdrant embedding (the text content gets embedded), composite
scoring (confidence, freshness, status), admission gating, security scanning,
operator overlays (pin/mute), decay, and the `knowledge_detail` tool. A
separate store would duplicate all of this.

**Embedding text for trajectory entries** (constructed at extraction time):

```
Successful code_implementation pattern (5 rounds, quality 0.48):
read_workspace_file → write_workspace_file → code_execute (failed) → patch_file → code_execute (success).
Recovery: read error output, patch source, re-execute.
```

This embeds well because it describes a workflow pattern in natural language.
The structured `trajectory_data` field is stored as Qdrant payload metadata
(alongside domains, tool_refs, etc.) for programmatic access via
`knowledge_detail`.

### Q3: How is a trajectory extracted?

**Recommendation: Deterministic extraction from AgentTurnCompleted events (option A).**

No LLM call needed. The `AgentTurnCompleted` event (events.py:251-266)
already records `tool_calls: list[str]` — the ordered tool names invoked
during the turn. Combine with `RoundCompleted` events (which record round
number and governance status) to build the full trajectory.

**Hook location**: New function `_hook_trajectory_extraction()` added to the
post-colony hooks in `colony_manager.py:1037-1071`, after
`_hook_memory_extraction()` (hook position 5).

```python
# colony_manager.py — new hook, ~40 lines

async def _hook_trajectory_extraction(
    self,
    colony_id: str,
    workspace_id: str,
    succeeded: bool,
    quality: float,
) -> None:
    """Extract and store tool-call trajectory from successful colonies.

    Deterministic: reads AgentTurnCompleted events from projection,
    no LLM call.
    """
    if not succeeded:
        return  # only store successful trajectories
    if quality < 0.30:
        return  # low-quality completions aren't worth learning from

    # Read tool calls from projection's round data
    colony = self._runtime.store.colonies.get(colony_id)
    if colony is None:
        return

    steps: list[dict[str, Any]] = []
    for round_data in colony.get("rounds", []):
        round_num = round_data.get("round_number", 0)
        for turn in round_data.get("turns", []):
            for tool_name in turn.get("tool_calls", []):
                steps.append({
                    "tool": tool_name,
                    "key_arg": "",  # populated from tool_call_results if available
                    "succeeded": True,  # default; refined from tool results
                    "round_number": round_num,
                })

    if not steps or len(steps) < 2:
        return  # trivial trajectories not worth storing

    task_class, _ = classify_task(colony.get("goal", ""))
    task_summary = colony.get("goal", "")[:200]

    # Build human-readable content for embedding
    tool_seq = " → ".join(s["tool"] for s in steps[:15])
    content = (
        f"Successful {task_class} pattern "
        f"({colony.get('rounds_completed', 0)} rounds, quality {quality:.2f}): "
        f"{tool_seq}."
    )

    entry = MemoryEntry(
        id=f"traj-{colony_id}",
        entry_type=MemoryEntryType.skill,
        sub_type=EntrySubType.trajectory,
        status=MemoryEntryStatus.verified,  # from successful colony
        title=f"Trajectory: {task_class} ({len(steps)} steps)",
        content=content,
        summary=f"{task_class} tool sequence with {len(steps)} steps",
        source_colony_id=colony_id,
        source_artifact_ids=[],
        domains=[task_class],
        tool_refs=list({s["tool"] for s in steps}),
        confidence=min(quality, 0.8),  # cap at 0.8
        decay_class=DecayClass.stable,  # trajectories are reusable
        trajectory_data=steps,
        workspace_id=workspace_id,
    )
    # ... emit MemoryEntryCreated, run through admission pipeline ...
```

**Data source**: The projection stores round data with turns. Each turn
records `tool_calls` (from AgentTurnCompleted events). The hook reads this
directly — no event replay needed.

**Note on tool_calls field**: AgentTurnCompleted.tool_calls is `list[str]`
(tool names only, no arguments). The `key_arg` field in TrajectoryStep
requires access to the tool call arguments, which are NOT stored on the
event. Two options:

1. **Accept name-only trajectories** (recommended for Wave 58). The tool
   sequence alone is valuable: `read_workspace_file → write_workspace_file →
   code_execute → patch_file → code_execute` captures the workflow pattern.
2. **Future wave**: Extend AgentTurnCompleted to include `tool_call_details:
   list[dict]` with argument summaries. This is an event schema change
   (requires ADR).

### Q4: How is a trajectory injected?

**Recommendation: As a `[Successful Pattern]` block at position 2c, alongside
text entries, via the progressive disclosure index (see Section 3).**

When a trajectory entry appears in the top-5 retrieval results, it is
injected using the same index format as text entries:

```
[Available Knowledge] (use knowledge_detail tool to access full content)
1. "CSV Parsing Patterns" -- csv module, DictReader, error handling
2. "Trajectory: code_implementation (12 steps)" -- read → write → execute → patch → execute
3. "Error Handling in Data Pipelines" -- try/except, stage isolation
```

When the agent calls `knowledge_detail` on a trajectory entry, the response
includes the structured step list:

```
Title: Trajectory: code_implementation (12 steps)
Content: Successful code_implementation pattern (5 rounds, quality 0.48):
  read_workspace_file → write_workspace_file → code_execute (failed) →
  patch_file → code_execute (success).

Tool Sequence:
  Round 1: read_workspace_file, write_workspace_file
  Round 2: code_execute (failed), patch_file
  Round 3: code_execute (success)
  Round 4: code_execute (success)
  Round 5: write_workspace_file

Domains: code_implementation
Tools referenced: read_workspace_file, write_workspace_file, code_execute, patch_file
```

This is handled by the existing `knowledge_detail` tool (tool_dispatch.py:178-197,
runner.py:1824-1835). The tool's `_knowledge_detail_fn` callback (runtime.py)
already returns the full entry content. No changes needed — the `trajectory_data`
field is stored in the projection and returned alongside `content`.

**Format change in knowledge_detail response**: When `sub_type == "trajectory"`
and `trajectory_data` is non-empty, format the response to include the
step-by-step breakdown. This is a ~10-line change in the
`make_knowledge_detail_fn()` factory in runtime.py.

### Q5: How is matching done?

**Recommendation: Semantic similarity via existing retrieval pipeline (option B).**

Trajectory entries are stored as MemoryEntries with text content that
describes the workflow pattern. The existing retrieval pipeline (knowledge_catalog
→ Qdrant hybrid search → composite scoring) handles matching automatically.

No task-class routing needed. The embedding text ("Successful
code_implementation pattern: read → write → execute → patch → execute")
naturally clusters with similar tasks. A future data-pipeline task will
semantically match because both involve "read → process → write → execute."

**Why not task-class matching?** Task classes are coarse (5 categories).
Two "code_implementation" tasks can have completely different trajectories
(web scraping vs data processing). Semantic similarity on the trajectory
description is more discriminating.

### Files modified

| File | Change |
|------|--------|
| `core/types.py:339` | Add `trajectory = "trajectory"` to EntrySubType |
| `core/types.py:~433` | Add `trajectory_data: list[dict[str, Any]]` field to MemoryEntry |
| `surface/colony_manager.py:~1065` | Add `_hook_trajectory_extraction()` to post-colony hooks |
| `surface/colony_manager.py` | Implement `_hook_trajectory_extraction()` (~40 lines) |
| `surface/runtime.py` | Format trajectory_data in knowledge_detail response (~10 lines) |
| `surface/memory_store.py:44-50` | Include trajectory_data in embed_text if present |

**No new events. One new enum member. One new MemoryEntry field.**
MemoryEntry is serialized as a dict on MemoryEntryCreated events, so the new
field is automatically persisted and replayed.

---

## Section 3: Progressive Disclosure Design

### Q1: When does progressive disclosure activate?

**Recommendation: Always (option A) — index-only injection from the start.**

Rationale:
- The existing `knowledge_detail` tool (tool_dispatch.py:178-197) already
  exists and is registered in the tool dispatch. Agents can already fetch
  full entries by ID.
- Index-only injection costs ~50 tokens per entry (vs ~200 for full content).
  For 5 entries: ~250 tokens vs ~1000 tokens. This is a 4x reduction.
- Playbooks (~200 tokens each) have proven effective at this injection size.
  Knowledge entries should follow the same principle.
- There is no threshold below which full injection is better. Even with 1
  entry, the model benefits from seeing a concise summary and choosing
  whether to fetch details.

### Q2: What does the index look like in context?

Replace the current injection format (context.py:459-504) with:

```
[Available Knowledge] (use knowledge_detail tool to retrieve full content)
1. [SKILL, VERIFIED] "CSV Parsing Patterns" -- csv module, DictReader, type detection (conf: 0.72)
2. [SKILL, TRAJECTORY] "code_implementation (12 steps)" -- read → write → execute → patch (conf: 0.65)
3. [EXPERIENCE, CANDIDATE] "Error Handling in Data Pipelines" -- try/except, stage isolation (conf: 0.50)
```

Each line: ~50 tokens. Budget: up to 5 entries = ~250 tokens (down from 800).

Implementation:

```python
# context.py — replace lines 459-505

if knowledge_items and _should_inject_knowledge(round_goal, knowledge_items):
    lines = [
        "[Available Knowledge] "
        "(use knowledge_detail tool to retrieve full content)"
    ]
    for item in knowledge_items[:5]:
        raw_similarity = float(
            item.get("similarity", item.get("score", 0.0)),
        )
        if raw_similarity < _MIN_KNOWLEDGE_SIMILARITY:
            continue

        ctype = str(item.get("canonical_type", "skill")).upper()
        status = str(item.get("status", "")).upper()
        sub = str(item.get("sub_type", "")).upper()
        label = f"{ctype}, {sub}" if sub and sub != "NONE" else ctype
        title = item.get("title", "")
        summary = str(item.get("summary", item.get("content_preview", "")))[:80]
        conf = float(item.get("confidence", 0.5))
        entry_id = item.get("id", "")

        lines.append(
            f'- [{label}, {status}] "{title}" -- {summary} '
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
        # Index is compact — no need for skill_bank budget (250 << 800)
        knowledge_text = "\n".join(lines)
        messages.append({"role": "user", "content": knowledge_text})
        skip_legacy_skills = True
```

The entry ID is included in the index line so the agent can call
`knowledge_detail(item_id="mem-colony-2c5742a4-s-0")` directly from context.

### Q3: What does the query_knowledge tool look like?

**No new tool needed.** The `knowledge_detail` tool already exists:

```python
# tool_dispatch.py:178-197 (existing)
"knowledge_detail": {
    "name": "knowledge_detail",
    "description": (
        "Retrieve the full content of a knowledge item by its ID. "
        "Use when the context preview is insufficient and you need "
        "the complete entry."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "ID of the knowledge item to retrieve",
            },
        },
        "required": ["item_id"],
    },
},
```

This tool is already registered in:
- `tool_dispatch.py:553` → `ToolCategory.vector_query`
- `runner.py:902` → `knowledge_detail_fn` callback
- `runner.py:1824-1835` → dispatch handler
- `runtime.py` → `make_knowledge_detail_fn()` factory

**One change needed**: Update the tool description to reference the index:

```python
"description": (
    "Retrieve the full content of a knowledge item by its ID. "
    "The [Available Knowledge] section in your context lists entry IDs. "
    "Call this tool when an entry looks relevant to your current task."
),
```

### Q4: Interaction with existing retrieval pipeline

**Retrieval: unchanged. Injection: index-only. On-demand: existing tool.**

```
                          UNCHANGED                    CHANGED
colony_manager.py    →    knowledge_catalog    →    context.py
fetch_knowledge()         search()                  assemble_context()
(runtime.py:1080)         composite scoring         NOW: index-only (~250 tokens)
                          top-5 results              WAS: full content (~800 tokens)
                                                     ↓
                                                  knowledge_detail tool
                                                  (on-demand, ~200 tokens per call)
```

**Retrieval count change**: Consider retrieving top-7 or top-10 for the index
(wider net since tokens per entry dropped from ~200 to ~50). This is a
parameter change in the `fetch_knowledge_for_colony()` call, not a pipeline
change. Recommend: increase `top_k` from 5 to 8 for index entries.

### Q5: How do agents learn to use knowledge_detail?

**The index block tells them directly.** The header line:

```
[Available Knowledge] (use knowledge_detail tool to retrieve full content)
```

...plus the entry IDs in each line, is sufficient for instruction-following
models. The `knowledge_detail` tool appears in the agent's tool list
(controlled by caste_recipes.yaml — it's in the `vector_query` category,
available to all castes).

**No playbook changes needed.** The index format is self-documenting.

### Files modified

| File | Change |
|------|--------|
| `engine/context.py:459-505` | Replace full injection with index-only format |
| `engine/tool_dispatch.py:180-184` | Update knowledge_detail description |
| `surface/runtime.py:1080-1102` | Increase top_k from 5 to 8 |

**Token budget impact**: From ~800 tokens (5 entries × ~160 tokens) to
~250 tokens (5-8 entries × ~50 tokens) base. Agent may spend ~200 tokens
per `knowledge_detail` call, but only for entries it actually needs. Net
reduction: 550+ tokens per round in the common case where the agent doesn't
fetch any entries.

---

## Section 4: Integration Design

### Pipeline flow

```
Task arrives at colony_manager
  │
  ├─ fetch_knowledge_for_colony()          # UNCHANGED
  │   └─ knowledge_catalog.search(top_k=8) # top_k raised from 5
  │       └─ returns 8 normalized entries
  │
  ├─ For each round:
  │   └─ assemble_context()
  │       │
  │       ├─ Specificity gate                # NEW (Feature 1)
  │       │   └─ _should_inject_knowledge()
  │       │       ├─ project signal? → INJECT
  │       │       ├─ top_sim >= 0.55? → INJECT
  │       │       └─ neither? → SKIP (save ~250 tokens)
  │       │
  │       ├─ Index injection                 # CHANGED (Feature 3)
  │       │   └─ [Available Knowledge] block (~250 tokens)
  │       │       └─ entry IDs in each line
  │       │
  │       └─ Agent executes
  │           ├─ Sees index in context
  │           ├─ Optionally calls knowledge_detail(item_id=...)
  │           │   └─ Returns full content (text or trajectory)
  │           └─ Proceeds with task
  │
  └─ Post-colony hooks
      ├─ _hook_memory_extraction()           # UNCHANGED
      └─ _hook_trajectory_extraction()       # NEW (Feature 2)
          └─ Deterministic: reads tool_calls from rounds
          └─ Stores as MemoryEntry(sub_type="trajectory")
```

### Parallel coder team ownership

**Team 1: Specificity Gate** (smallest scope, fastest to ship)

Owned files:
- `engine/context.py` — specificity gate function, word sets, env var

Do not touch:
- `knowledge_catalog.py`, `colony_manager.py`, `runtime.py`, `types.py`

Validation:
- `pytest tests/unit/engine/test_context.py`
- New test: `test_should_inject_knowledge_skip_general`
- New test: `test_should_inject_knowledge_inject_project`
- New test: `test_should_inject_knowledge_inject_high_similarity`
- New test: `test_specificity_gate_env_disable`

**Team 2: Trajectory Storage** (medium scope, core data model)

Owned files:
- `core/types.py` — EntrySubType.trajectory, MemoryEntry.trajectory_data
- `surface/colony_manager.py` — `_hook_trajectory_extraction()`
- `surface/memory_store.py` — include trajectory_data in embed_text
- `surface/runtime.py` — trajectory formatting in knowledge_detail response

Do not touch:
- `context.py`, `tool_dispatch.py`, `knowledge_catalog.py`

Validation:
- `pytest tests/unit/core/test_types.py`
- `pytest tests/unit/surface/test_colony_manager*.py`
- New test: `test_trajectory_extraction_from_successful_colony`
- New test: `test_trajectory_extraction_skips_failed_colony`
- New test: `test_trajectory_extraction_skips_low_quality`
- New test: `test_trajectory_entry_stored_as_memory_entry`
- New test: `test_knowledge_detail_formats_trajectory`
- `ruff check src/ && pyright src/`

**Team 3: Progressive Disclosure** (medium scope, context format change)

Owned files:
- `engine/context.py` — index injection format (lines 459-505)
- `engine/tool_dispatch.py` — knowledge_detail description update (line 180)

Do not touch:
- `types.py`, `colony_manager.py`, `knowledge_catalog.py`, `runtime.py`

Validation:
- `pytest tests/unit/engine/test_context.py`
- `pytest tests/unit/engine/test_tool_dispatch.py`
- New test: `test_index_injection_format`
- New test: `test_index_includes_entry_ids`
- New test: `test_index_skips_low_similarity`
- New test: `test_index_token_budget_reduction`
- `ruff check src/ && pyright src/`

### Shared interfaces

Teams must agree on these before starting:

1. **EntrySubType.trajectory** (Team 2 adds, Team 3 displays). Team 2
   defines the enum member and field. Team 3 references `sub_type` in the
   index format. Interface: the string value `"trajectory"` and the display
   format `[SKILL, TRAJECTORY]`.

2. **knowledge_items dict shape** (all teams read). The dicts passed to
   `assemble_context()` already contain `id`, `title`, `content_preview`,
   `similarity`, `status`, `canonical_type`, `sub_type`, `confidence`. No
   schema change needed.

3. **Specificity gate position** (Team 1 and Team 3). Team 1 adds
   `_should_inject_knowledge()`. Team 3 changes the injection loop. Both
   modify context.py. Resolution: Team 1 adds the gate function and wraps
   the existing `if knowledge_items:` check. Team 3 changes the block
   INSIDE the check. No overlap — Team 1 owns the outer condition, Team 3
   owns the inner format.

4. **Overlap file rule**: `context.py` is touched by Team 1 AND Team 3.
   Team 1 merges first (gate wrapper around existing code). Team 3 merges
   second (replace inner format). Team 3 must re-read context.py after
   Team 1's merge before applying their changes.

---

## Section 5: Eval Implications

### Impact on Phase 0 eval

With the specificity gate enabled:

| Task | Project signals? | Best similarity (est.) | Gate result |
|------|-----------------|----------------------|-------------|
| email-validator | No | 0.0 (first task) | SKIP |
| json-transformer | No | ~0.45 | SKIP |
| haiku-writer | No | ~0.30 | SKIP |
| csv-analyzer | No | ~0.50 | BORDERLINE (may skip) |
| markdown-parser | No | ~0.45 | SKIP |
| rate-limiter | No | ~0.41 | SKIP |
| api-design | No | ~0.40 | SKIP |
| data-pipeline | No | ~0.58 (csv entries) | INJECT |

**Result**: The specificity gate would skip retrieval for 6-7 of 8 Phase 0
tasks. Only data-pipeline consistently passes (csv-analyzer entries are
relevant). This means the accumulate arm behaves like the empty arm for
most tasks — which is exactly what the v7-v10 evidence says should happen.

### New eval tasks needed

To test retrieval meaningfully, Phase 1 eval needs project-specific tasks:

| Task | What makes it project-specific | Expected retrieval benefit |
|------|-------------------------------|--------------------------|
| `extend-csv-analyzer` | "Add median and mode to the existing csv analyzer" | csv-analyzer entries are directly relevant |
| `fix-validator-bug` | "The email validator rejects valid .co.uk domains" | email-validator entries describe the implementation |
| `pipeline-v2` | "Extend the data pipeline to parse nginx access logs" | data-pipeline trajectory shows the workflow |
| `refactor-parser` | "Refactor our markdown parser to support tables" | markdown-parser entries describe AST structure |
| `cross-domain-tool` | "Build a tool that validates CSV email columns" | Both csv and email entries are relevant |

These tasks reference prior work ("existing", "our", "the") and have strong
semantic overlap with accumulated entries. The specificity gate correctly
activates for all of them.

**Eval configuration**: Add `knowledge_gate: bool` to eval task YAML. When
`false`, the gate is disabled for that task (legacy behavior for A/B testing).
Default: `true`.

---

## Section 6: Implementation Sequence

### Dependencies

```
Team 2 (trajectory types) ──→ Team 3 (index format shows trajectories)
                                ↑
Team 1 (specificity gate) ──────┘ (gate wraps the injection that Team 3 changes)
```

### Recommended sequence

**Phase A** (parallel, no dependencies):
- Team 1: Specificity gate (context.py only, self-contained)
- Team 2: Trajectory types + extraction hook (types.py, colony_manager.py,
  memory_store.py, runtime.py)

**Phase B** (after Team 1 + Team 2 merge):
- Team 3: Progressive disclosure (context.py inner format, tool_dispatch.py)
  - Must re-read context.py after Team 1's merge
  - Must handle `sub_type="trajectory"` in index display (from Team 2)

**Phase C** (after all teams merge):
- Integration test: end-to-end trajectory extraction → index injection →
  knowledge_detail fetch → verify format
- Phase 0 re-run with gate enabled vs disabled
- Phase 1 eval task design (project-specific tasks)

### Risk assessment

| Risk | Mitigation |
|------|-----------|
| Specificity gate too aggressive (skips relevant knowledge) | Env var toggle; 0.55 threshold tunable; project signals list extensible |
| Trajectory entries crowd out text entries in retrieval | Max 1 trajectory per top-5 (add diversity rule if needed) |
| Agents don't call knowledge_detail | Self-documenting index header; existing tool already in caste recipes |
| context.py merge conflict (Team 1 + Team 3) | Explicit merge order: Team 1 first, Team 3 re-reads |
| trajectory_data field bloats MemoryEntry | Cap at 20 steps; compress key_arg to 50 chars |
| Progressive disclosure reduces quality (agents need full content) | A/B test: index-only vs full injection in Phase 0 |

### LOC estimate

| Team | New lines | Modified lines | Files touched |
|------|-----------|---------------|---------------|
| Team 1 | ~40 | ~5 | 1 (context.py) |
| Team 2 | ~60 | ~15 | 4 (types.py, colony_manager.py, memory_store.py, runtime.py) |
| Team 3 | ~30 | ~25 | 2 (context.py, tool_dispatch.py) |
| **Total** | **~130** | **~45** | **5 unique files** |

All changes are within the soft LOC limit. No new events (trajectory uses
existing MemoryEntryCreated). One new enum member. One new MemoryEntry field.
Total token budget for injected knowledge DECREASES from ~800 to ~250 base.
