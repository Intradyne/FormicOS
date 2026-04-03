# Wave 79 Plan: Dynamic Context Optimization + Quality Uplift

**Theme:** Reduce Queen tool-schema overhead with dynamic toolset loading,
shrink colony prompt overhead for common task shapes, and finish the
structured compaction work so more useful context survives on small models.

**Teams:** 3 mostly independent tracks. Track 1 and Track 3 both touch
`queen_runtime.py`, but in separate functions.

**Estimated total change:** ~360 new lines, ~90 changed lines.

**Research basis:** Swarm experiment results, Wave 77.5 context-budget
measurements, Wave 78/78.5 tool-registry changes, and the live Queen
compaction behavior already present in the repo.

---

## Problem statement

The swarm experiments exposed three real bottlenecks:

1. **Queen tool-schema overhead is still too large.**
   The full Queen tool surface is 45 tool specs and roughly 15.5K prompt
   tokens. On local configs that is an enormous fraction of available
   context. Most operator turns do not need the full tool surface.

2. **Colony prompt overhead is still too large for weak models.**
   Coder colonies still receive the full caste tool list by default.
   For routine coding work, that means paying prompt cost for tools the
   model will never use. Weak local models also keep producing enough
   output variation that the current convergence math often does not
   halt them early.

3. **Queen compaction is already structured, but not complete enough.**
   The repo already has `_prune_old_tool_results()` and
   `_compact_thread_history()` with `Progress`, `Key Decisions`, and
   `Earlier Context` sections. That is better than the old flat prose
   summary, but it still does not reliably preserve:
   - goal
   - blockers
   - relevant files
   - next steps
   - critical context values

Wave 79 should optimize the live system that exists now, not re-propose
work that already landed.

---

## Track 1: Dynamic Toolset Loading for the Queen

### Current state (verified)

- `queen_tools.py` now groups **43 registry-backed tools** into 9 toolsets
  via `_TOOL_META`.
- `tool_specs()` still returns the full **45-spec** Queen surface because
  `archive_thread` and `define_workflow_steps` are delegated thread tools
  that live outside `_TOOL_META`.
- The dispatcher exposes `tool_entries` and `get_tool_entry()`.
- There is **no** existing `get_definitions(toolsets=...)` helper.
- `respond()` in `queen_runtime.py` still loads the full Queen tool surface
  before calling the model.

### What to build

#### 1A: `classify_relevant_toolsets()` in `queen_runtime.py`

Add a deterministic keyword/thread-state classifier that chooses the
smallest reasonable Queen toolset for the current operator turn.

Always include `operations` as the base set. Add domain-specific toolsets
based on the latest operator message and thread state.

Suggested keyword sets:

| Toolset | Keywords | Tools | Est. tokens |
|---------|----------|-------|-------------|
| `operations` (always) | status, config, addon, template, budget | 10 | ~3,500 |
| `colony` | spawn, colony, kill, parallel, team, delegate, swarm, retry | 8 | ~2,800 |
| `workspace` | file, edit, write, read, code, fix, patch, run, test, command | 7 | ~2,450 |
| `knowledge` | knowledge, search, memory, remember, briefing, codebase | 5 | ~1,750 |
| `planning` | plan, milestone, goal, workflow, step, archive, thread | 8 | ~2,800 |
| `documents` | document, draft, summarize, summary | 2 | ~700 |
| `working_memory` | note, working, artifact, promote | 2 | ~700 |
| `analysis` | analyze, outcome, performance, quality | 2 | ~700 |
| `safety` | rollback, undo, revert, checkpoint | 1 | ~350 |

Fallback when no strong keywords match beyond `operations`:
- include `colony` + `workspace` + `knowledge`

Thread-state hint:
- if the workspace has running colonies, include `colony`

#### 1B: `tool_specs_for_toolsets()` in `queen_tools.py`

Do not reimplement filtering inline in `respond()`. Add a small helper on
the dispatcher so the tool/registry truth stays in one place.

```python
def tool_specs_for_toolsets(self, toolsets: set[str] | None = None) -> list[dict[str, Any]]:
    if not toolsets:
        return self.tool_specs()

    allowed = {entry.name for entry in self.tool_entries if entry.toolset in toolsets}

    # Delegated thread tools live outside _TOOL_META but belong to planning.
    if "planning" in toolsets:
        allowed.update({"archive_thread", "define_workflow_steps"})

    return [spec for spec in self.tool_specs() if spec["name"] in allowed]
```

This keeps Track 1 honest about the live Queen surface:
- 43 tools come from `_TOOL_META`
- 2 delegated planning tools must be handled explicitly

#### 1C: Integrate in `respond()`

Use the classifier and the filtered-spec helper before the main LLM call.

```python
last_msg = ""
for msg in reversed(thread.queen_messages):
    if msg.role == "operator":
        last_msg = msg.content
        break

active_count = sum(
    1
    for c in self._runtime.projections.colonies.values()
    if c.status == "running" and c.workspace_id == workspace_id
)

relevant = classify_relevant_toolsets(last_msg, active_colonies=active_count)
tools = self._tool_dispatcher.tool_specs_for_toolsets(relevant)
```

#### 1D: Auto-widen on hallucinated/unknown tool

If the model hallucinates a tool outside the filtered set and dispatch
returns an unknown-tool error, widen to the full tool surface for the
next iteration inside the same `respond()` loop.

That is enough. Do not add a meta-tool for requesting more tools.

### Token savings by scenario

| Scenario | Toolsets | Tools | Tokens | Savings |
|----------|----------|-------|--------|---------|
| "what's the status?" | operations | 10 | ~3,500 | ~77% |
| "search knowledge for X" | operations + knowledge | 15 | ~5,250 | ~66% |
| "write a design doc" | operations + documents | 12 | ~4,200 | ~73% |
| "spawn a colony to fix auth" | operations + colony + workspace + knowledge | 30 | ~10,500 | ~32% |
| "rollback the last edit" | operations + safety | 11 | ~3,850 | ~75% |

#### 1E: Fix Queen `write_workspace_file` path flattening (correctness bug)

`_write_workspace_file()` in queen_tools.py:3051 does:

```python
safe_name = Path(filename).name  # strips ALL directory structure
```

This makes the Queen worse than colony coders at multi-file output — the
colony-side handler (runner.py:2002-2019) correctly accepts relative paths
with subdirectories, resolves against the workspace root, blocks `..`
traversal, and creates parent directories. The Queen handler should match.

**Fix** (~5 lines at queen_tools.py:3050-3053):

```python
# Replace:
safe_name = Path(filename).name

# With:
rel = Path(filename)
if rel.is_absolute() or ".." in rel.parts:
    return ("Error: path must be relative with no '..' components.", None)
safe_name = str(rel)
# ... then create parent dirs before writing:
target.parent.mkdir(parents=True, exist_ok=True)
```

This unblocks the swarm experiment v3 — without it, colonies produce
structured addon directories but the Queen flattens them on review/copy.

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/queen_runtime.py` | `classify_relevant_toolsets()` + `respond()` integration |
| `src/formicos/surface/queen_tools.py` | `tool_specs_for_toolsets()` helper + path flattening fix |
| `tests/unit/surface/test_toolset_classifier.py` | NEW |

### Do not touch

- `engine/runner.py`
- any adapter
- any frontend

### Validation

```bash
pytest tests/unit/surface/test_toolset_classifier.py -v

# Verify tool count reduction
# "what's the status?" -> tool_count < 15
# "spawn a colony" -> tool_count around 30
# Verify unknown-tool auto-widen works
```

---

## Track 2: Colony Tool Pruning + Convergence Recalibration

### 2A: Task-aware colony tool filtering

Colony coders currently load the full caste tool list. For most coding
tasks, the whole list is unnecessary.

This track should prune **within the existing caste allowance**, not
change caste policy and not edit `caste_recipes.yaml`.

#### Tool profiles

| Profile | Tools | Count | Est. tokens |
|---------|-------|-------|-------------|
| coding (default) | `memory_search`, `code_execute`, `workspace_execute`, `list_workspace_files`, `read_workspace_file`, `write_workspace_file`, `patch_file`, `git_status`, `git_diff`, `git_commit` | 10 | ~2,250 |
| research | `memory_search`, `knowledge_detail`, `transcript_search`, `artifact_inspect`, `list_workspace_files`, `read_workspace_file` | 6 | ~1,300 |
| review | `memory_search`, `knowledge_detail`, `list_workspace_files`, `read_workspace_file`, `git_status`, `git_diff` | 6 | ~1,300 |

Key correction: the default coding profile must keep `workspace_execute`.
Without it, the coder loses the normal workspace test/build path.

#### `_select_tool_profile()` in `runner.py`

Make the selector aware of:
- `agent.caste`
- the available tool names from `agent.recipe.tools`
- the task description

It should:
- return one of the compact profiles for `coder`, `reviewer`, `researcher`
- intersect the chosen profile with the actual caste tool list
- fall back to the full caste tool list if no confident profile matches

### 2B: Diminishing returns detector

The current stall/convergence logic does **not** depend on self-reported
quality. It already uses semantic stability and progress. The real issue
is that weak models keep changing wording enough that the current
stability signal often does not trip an early stop.

So the new detector should be framed as a **secondary stall signal**, not
as a replacement for convergence math.

#### `_detect_diminishing_returns()` in `runner.py`

Use lightweight textual similarity between consecutive round outputs
(for example, trigram Jaccard or similar cheap text-overlap logic).

If the last 2-3 outputs are highly overlapping, treat that as an extra
stall signal and feed it into the existing governance path by increasing
the effective stall streak. Do **not** rewrite the whole convergence
subsystem.

That keeps the change small and aligned with the current architecture:
- convergence still comes from embeddings / heuristic fallback
- governance still decides `continue / warn / force_halt / complete`
- the new detector only strengthens the evidence for "we are circling"

### Files

| File | Change |
|------|--------|
| `src/formicos/engine/runner.py` | `_select_tool_profile()` + lightweight diminishing-returns helper + small integration |
| `tests/unit/engine/test_tool_filtering.py` | NEW |
| `tests/unit/engine/test_convergence.py` | NEW or extend |

### Do not touch

- `queen_runtime.py` (Track 1 / Track 3 own it)
- `queen_tools.py`
- `caste_recipes.yaml`
- any adapter
- any frontend

### Validation

```bash
pytest tests/unit/engine/test_tool_filtering.py -v
pytest tests/unit/engine/test_convergence.py -v

# Swarm experiment v3:
# - verify common coder rounds expose ~10 tools, not the full list
# - verify weak-model colonies often finish in 4-6 rounds instead of 8
```

---

## Track 3: Structured Compaction Finisher

### Current state (verified)

This is not greenfield work anymore.

The repo already has:
- `_prune_old_tool_results()`
- `_compact_thread_history()`
- structured compaction sections: `## Progress`, `## Key Decisions`,
  `## Earlier Context`

The real remaining gap is that the current compaction does not reliably
preserve:
- goal
- blockers
- relevant files
- next steps
- critical values / error strings

It also does not need "orphaned tool pair cleanup" because the Queen path
does **not** use provider-native `tool` role messages. It feeds tool
results back as plain text user messages.

### What to build

Polish the existing Queen compaction helpers rather than inventing a new
compression subsystem.

#### 3A: Upgrade `_compact_thread_history()` to a fuller template

Keep the existing structured shape, but expand it to the actual target:

```text
## Goal
...

## Progress
### Done
...
### In Progress
...
### Blocked
...

## Key Decisions
...

## Relevant Files
...

## Next Steps
...

## Critical Context
...
```

#### 3B: Extract the missing sections from live Queen data

Use the data already available in the thread history:
- thread goal / plan summary -> `Goal`
- result cards / preview cards -> `Progress`
- failure cards, error snippets, moderation / blocked states -> `Blocked`
- path-like snippets and result-card metadata -> `Relevant Files`
- recent operator asks and Queen proposals -> `Next Steps`
- concrete config values, error text, IDs, and quoted parameters -> `Critical Context`

#### 3C: Keep pruning focused on the existing helpers

Do not add a new `compact_conversation()` function. The live seams are:
- `_prune_old_tool_results()`
- `_compact_thread_history()`

If you tune pruning thresholds or protected windows, do it there.

### Files

| File | Change |
|------|--------|
| `src/formicos/surface/queen_runtime.py` | refine `_compact_thread_history()` and, if needed, small threshold tuning in `_prune_old_tool_results()` |
| `tests/unit/surface/test_compaction.py` | NEW or extend |

### Do not touch

- `queen_tools.py`
- `engine/runner.py`
- any adapter
- any frontend

### Validation

```bash
pytest tests/unit/surface/test_compaction.py -v

# Verify compacted history includes:
# - Goal
# - Progress (Done / In Progress / Blocked)
# - Key Decisions
# - Relevant Files
# - Next Steps
# - Critical Context
```

---

## Cross-track file ownership

| File | Track 1 | Track 2 | Track 3 |
|------|---------|---------|---------|
| `src/formicos/surface/queen_runtime.py` | classifier + `respond()` integration | -- | compaction refinements |
| `src/formicos/surface/queen_tools.py` | filtered spec helper + path fix | -- | -- |
| `src/formicos/engine/runner.py` | -- | tool filtering + convergence tuning | -- |

Track 1 and Track 3 both touch `queen_runtime.py`, but in separate
functions. Reread that file after merge; do not work blind.

---

## What this wave does NOT do

- no new event types
- no Queen tools removed (design note invariant 1: direct action stays)
- no MCP changes
- no adapter changes
- no frontend changes
- no caste recipe changes
- no new external registry type

Only a small filtered-spec helper is added on top of the existing Queen
dispatcher.

---

## Success conditions

1. Queen tool payload drops from the full ~15.5K schema budget to
   ~3.5K-5.25K tokens for common requests.
2. Worst-case fallback Queen payload is about ~10.5K tokens rather than
   the full tool surface.
3. Unknown tool hallucinations auto-widen to the full Queen surface on
   the next iteration.
4. Common coder colonies expose about 10 tools instead of the full coder list.
5. Weak-model colonies more often finish in 4-6 rounds instead of always
   reaching the cap.
6. The new diminishing-returns signal feeds governance without replacing
   the existing convergence subsystem.
7. Queen compaction preserves Goal / Progress / Blocked / Decisions /
   Relevant Files / Next Steps / Critical Context.
8. Queen `write_workspace_file` accepts relative paths with subdirectories
   (e.g., `src/formicos/addons/test_sentinel/scanner.py`), matching the
   colony-side behavior.
9. All existing tests pass unchanged.

---

## Follow-on packet

Wave 79.5 is now split into its own packet:

- [design_note.md](/c:/Users/User/FormicOSa/docs/waves/wave_79/design_note.md)
- [wave_79_5_plan.md](/c:/Users/User/FormicOSa/docs/waves/wave_79/wave_79_5_plan.md)

That keeps Wave 79 crisp and dispatchable while giving the file-mediated
workflow work enough space to be product-shaped instead of appended as a
long tail section.

---

## Swarm experiment v3 (post-wave validation)

After Wave 79 ships, re-run test-sentinel with:
- Queen on local 35B (dynamic toolsets should reduce prompt size materially)
- Colony workers on local 4B with tool pruning + convergence tuning

Targets:
- avg quality > 0.55
- avg rounds < 6
- files produced >= 6
