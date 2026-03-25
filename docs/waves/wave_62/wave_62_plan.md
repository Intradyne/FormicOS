# Wave 62 — The Working Queen

**Goal:** Give the Queen direct work capability so she can answer codebase
questions, check test results, and gather context without spawning colonies.
Fix the three retrieval correctness bugs that make the knowledge pipeline
unreliable. Add quality-based escalation. Refactor dispatch to dict registry
(addon Phase 0).

**Event union:** stays at 65. No new events.

**Prerequisite:** Wave 61 (deliberation mode) shipped clean: 25 Queen tools,
proposal cards, workspace browser, budget panel, 3446 tests passing.

---

## Strategic Context

The addon system is post-launch work (Wave 65+). But the registry refactor
that ENABLES addons is free engineering improvement. Replacing the if/elif
chain in `QueenToolDispatcher.dispatch()` with a dict registry and the switch
in `formicos-app.ts` with a component map are refactors with negative LOC
change. They're better code regardless of whether addons ever ship. Do them
alongside the Queen tool additions since the same files are being touched.

The three retrieval correctness bugs (double-ranking truncation, static
retrieval query, 39% untagged entries) are not features — they're bugs that
make the knowledge pipeline unreliable. Every Phase 0/1 eval result sits on
a retrieval path that silently drops good candidates. Fix them first.

---

## Track 1 — Retrieval Correctness (3 bugs, ~50 lines)

Ship FIRST, before any other track merges. These are the foundation that
everything else sits on.

### Bug 1: Double-ranking truncation

**Problem:** `knowledge_catalog.py:search_tiered()` (line 738) passes
`top_k=top_k * 2` to `_search_thread_boosted()`. Qdrant returns the top
results ranked by raw cosine similarity, then `results[:top_k]` (line 742)
truncates to the final set. But the 7-signal composite scorer
(0.38 semantic + 0.25 thompson + 0.15 freshness + 0.10 status + 0.07 thread
+ 0.05 cooccurrence + graph_proximity + pin_boost) never gets to re-rank
entries that were dropped by the initial cosine truncation. An entry ranked
#15 by cosine but #3 by composite gets silently dropped.

**Fix:** Change `top_k * 2` to `top_k * 4` at `knowledge_catalog.py:738`.
One line change. The composite scorer then has 4x the candidate pool to
select from.

**File:** `src/formicos/surface/knowledge_catalog.py` line 738.

### Bug 2: Static retrieval query

**Problem:** `colony_manager.py:646-651` fetches knowledge once before the
round loop using `colony.task` as the query. The only re-fetch happens at
lines 704-708 when the goal changes (redirect). In a 5-round colony, the
agent may be debugging a specific import error in round 3, but knowledge is
still optimized for the original task description from round 1.

**Fix:** Re-query with round context at the start of each round (after
round 1). After each round completes, extract a brief context hint from
`prev_summary` (last 200 chars of the previous round's summary, set at
line 776) and use it to augment the retrieval query. ~30 lines in
`colony_manager.py`.

The insertion point is inside the round loop, AFTER the goal-change
re-fetch block (lines 704-713) and BEFORE the per-round structural
refresh (line 718). This ensures:
- The current round's goal is resolved (line 701)
- Goal-change re-fetch has already run if a redirect happened
- The round-aware re-fetch runs only for round 2+ (`round_num > start_round`)
- Knowledge is fresh when `run_round()` is called at line 748

```python
# Insert between lines 713 and 715 in colony_manager.py:

            # Wave 62 Bug 2: round-aware retrieval refresh
            # Re-query with round context so knowledge stays relevant
            # as the agent's work evolves across rounds.
            if round_num > start_round and goal == _prev_goal:
                # Only re-fetch if goal didn't change (goal-change already
                # re-fetched above at line 705). Use prev_summary from the
                # previous round (set at line 776) as context hint.
                _hint = (prev_summary or "")[-200:]
                if _hint:
                    _round_query = f"{goal} | {_hint}"
                    knowledge_items = await self._runtime.fetch_knowledge_for_colony(
                        task=_round_query, workspace_id=colony.workspace_id,
                        thread_id=colony.thread_id, top_k=8,
                    )
```

**File:** `src/formicos/surface/colony_manager.py` — the round loop,
insert between lines 713 and 715 (after goal-change re-fetch, before
structural refresh).

### Bug 3: Domain filter inert for untagged entries

**Problem:** `context.py:541-548` — the specificity gate at line 547 checks
`item.get("primary_domain", "") in ("", _task_class, "generic")`. The empty
string `""` in the allowed set means untagged entries pass through the domain
boundary defense unconditionally. The comment says "entries with no domain
tag" — this was intentional at the time, not a bug. The real issue is
twofold: (1) entries extracted before Wave 58.5 never got a `primary_domain`
tag, and (2) the `knowledge_catalog.py` retrieval path returns dicts that
may not carry `primary_domain` forward from the stored entry metadata
(normalization gap). The filter is structurally inert for any entry where
`primary_domain` is missing from the dict, regardless of whether the stored
entry has one.

**Fix:** Apply a stricter similarity threshold (0.60 instead of the standard
pass-through) for entries with no `primary_domain` tag. Untagged entries must
be MORE relevant to get through, not less. ~20 lines in `context.py`.

**Note:** This fix addresses the gate-level behavior but does NOT fix the
normalization gap where `primary_domain` may be dropped between storage and
retrieval. If the catalog's result dicts don't include `primary_domain`,
all entries appear untagged at the gate regardless of their stored metadata.
A follow-up should verify that `primary_domain` survives the full retrieval
path from Qdrant payload → catalog result dict → context.py filter.

```python
# Wave 62 Bug 3: untagged entries need stricter threshold
_task_class = colony_context.task_class
if knowledge_items and _task_class and _task_class != "generic":
    _filtered: list[dict[str, Any]] = []
    for item in knowledge_items:
        domain = item.get("primary_domain", "")
        if domain in (_task_class, "generic"):
            _filtered.append(item)  # domain match: pass through
        elif domain == "":
            # Untagged: require higher similarity
            sim = float(item.get("similarity", item.get("score", 0.0)))
            if sim >= 0.60:
                _filtered.append(item)
        # else: wrong domain, drop
    knowledge_items = _filtered
```

**File:** `src/formicos/engine/context.py` lines 541-548.

### Validation

```bash
pytest tests/ -q  # all tests pass
# Smoke: 3 Phase 1 tasks, accumulate mode
# Check: (a) >5 unique entries accessed across rounds
#        (b) no cross-domain entries leak through
#        (c) accessed count higher than Phase 1 v2
```

**Owned files:** `knowledge_catalog.py` (Bug 1), `colony_manager.py` (Bug 2),
`context.py` (Bug 3)

**Do not touch:** `core/events.py`, `core/types.py`, `engine/runner.py`

---

## Track 1.5 — Outcome-Informed Proposals (~50 lines)

The Queen's `propose_plan` tool currently generates proposals without
consulting empirical data. ColonyOutcome projections already track
`succeeded`, `total_rounds`, `total_cost`, `strategy`, `caste_composition`,
and `quality_score` for every completed colony. The Queen should cite
this data in her proposals.

**Implementation (~50 lines total across 2 files):**

**A. `outcome_stats()` method in `projections.py` (~30 lines):**

Add a method to the projections layer that aggregates completed colony
outcomes by `(strategy, caste_composition)` tuple:

```python
def outcome_stats(
    self, workspace_id: str,
) -> list[dict[str, Any]]:
    """Aggregate colony outcomes by (strategy, caste_mix) for planning."""
    # No list_outcomes() method exists — iterate colony_outcomes dict
    # and filter by workspace_id (same pattern as get_workspace_outcomes
    # in routes/api.py:437-449).
    outcomes = [
        o for o in self.colony_outcomes.values()
        if o.workspace_id == workspace_id
    ]
    if not outcomes:
        return []
    buckets: dict[tuple[str, str], list[ColonyOutcome]] = {}
    for o in outcomes:
        key = (o.strategy, ",".join(sorted(o.caste_composition)))
        buckets.setdefault(key, []).append(o)
    stats = []
    for (strategy, caste_mix), group in buckets.items():
        successes = sum(1 for o in group if o.succeeded)
        stats.append({
            "strategy": strategy,
            "caste_mix": caste_mix,
            "total": len(group),
            "success_rate": successes / len(group),
            "avg_rounds": sum(o.total_rounds for o in group) / len(group),
            "avg_cost": sum(o.total_cost for o in group) / len(group),
        })
    return stats
```

**B. Enrich `_propose_plan()` in `queen_tools.py` (~20 lines):**

Inside the existing `_propose_plan()` handler, call `outcome_stats()`
and append empirical context to the proposal text:

```python
# Wave 62: enrich proposal with empirical outcome data
stats = self._runtime.projections.outcome_stats(workspace_id)
if stats:
    lines = ["", "**Empirical basis** (from prior colonies):"]
    for s in sorted(stats, key=lambda x: -x["success_rate"])[:5]:
        lines.append(
            f"- {s['strategy']} / {s['caste_mix']}: "
            f"{s['success_rate']:.0%} success rate, "
            f"{s['avg_rounds']:.1f} avg rounds, "
            f"${s['avg_cost']:.2f} avg cost "
            f"({s['total']} colonies)"
        )
    # Append to proposal summary or recommendation field
```

This enables the Queen to say: "Sequential strategy recommended — 2.1 avg
rounds vs 3.8 for stigmergic based on 14 prior colonies."

No new events. No new dependencies. Reads existing projection state.

**Owned files:**
- `src/formicos/surface/projections.py` (outcome_stats method)
- `src/formicos/surface/queen_tools.py` (_propose_plan enrichment)
- `tests/unit/surface/test_queen_tools.py` (test for outcome stats in proposal)

---

## Track 2 — Queen Direct Work Tools (2 tools, ~450 lines)

Two read-only tools that let the Queen answer questions without spawning
colonies. Write tools (`edit_file`, `run_tests`) are deferred to Wave 63 —
they need safety design (backup before edit, diff preview, operator
confirmation gate).

### A. `search_codebase` tool

```python
{
    "name": "search_codebase",
    "description": "Search the workspace codebase for text patterns. Returns matching lines with file paths and line numbers. Use this to find definitions, usages, or patterns without spawning a colony.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text or regex pattern"},
            "path": {"type": "string", "description": "Subdirectory to search within (relative to workspace). Default: entire workspace"},
            "regex": {"type": "boolean", "description": "Treat query as regex. Default: false"},
            "max_results": {"type": "integer", "description": "Max matching lines. Default: 20, max: 50"}
        },
        "required": ["query"]
    }
}
```

**Implementation (~150 lines in `queen_tools.py`):**
- Get workspace directory from runtime (`data_dir/workspaces/{workspace_id}/files`)
- Also search the main source tree if workspace has a repo path
- Use `subprocess.run(["grep", "-rn", ...])` or ripgrep if available
  - `--max-count=5` per file (prevent massive matches)
  - `--max-filesize=1M` (skip binaries)
  - `--color=never --line-number`
  - Timeout: 10 seconds
- If grep not available, fall back to Python `pathlib` + `re` search
- Truncate total output to 4000 chars
- Return structured results: `[{file, line_number, content}]`

This single tool eliminates the most frustrating daily interaction: spawning
a Researcher colony to answer "where is the budget enforcer defined?" The
Queen greps, reads the relevant lines, and answers in 3 seconds.

### B. `run_command` tool

```python
{
    "name": "run_command",
    "description": "Run an allowlisted shell command in the workspace. Use for git status, test results, linting, and other read-only operations.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to run. Must start with an allowlisted program: git, pytest, ruff, python -m py_compile, ls, cat, head, tail, wc, find"},
            "timeout": {"type": "integer", "description": "Timeout in seconds. Default: 30, max: 60"}
        },
        "required": ["command"]
    }
}
```

**Implementation (~300 lines in `queen_tools.py`):**

**ALLOWLIST:**
```python
_QUEEN_CMD_ALLOWLIST = {
    "git": {"status", "diff", "log", "blame", "show", "branch"},
    "pytest": True,       # any pytest args allowed
    "ruff": {"check"},
    "python": {"-m"},     # only -m py_compile
    "ls": True,
    "cat": True,
    "head": True,
    "tail": True,
    "wc": True,
    "find": True,
}
```

- Parse command, verify first token is in allowlist
- For `git`, verify subcommand is in the allowed set
- Block: `rm`, `mv`, `cp`, `chmod`, `chown`, `kill`, `sudo`, any pipe to
  write commands, any shell metacharacters (`|`, `>`, `>>`, `;`, `&&`, `` ` ``)
- Run via `asyncio.create_subprocess_exec` with timeout (no shell=True)
- Capture stdout + stderr, truncate to 4000 chars
- Return formatted output with exit code

**Security:** Read-only by design. Allowlist prevents write operations.
Timeout prevents resource exhaustion. Output truncation prevents memory
issues. No shell expansion (use `exec`, not `shell`).

This enables: `git status`, `git diff HEAD~3`, `pytest tests/unit/surface/ -q`,
`ruff check src/`, `git log --oneline -10`.

### Register tools

- Add specs to `queen_tools.py` `tool_specs()` method
- Add handlers to dispatch registry (Track 6 refactors dispatch first)
- Add to `caste_recipes.yaml` queen tool list
- Add tests: `search_codebase` finds a known function, `run_command` runs
  `git status` successfully, `run_command` rejects `rm -rf`

**Owned files:**
- `src/formicos/surface/queen_tools.py` (tool specs + handlers)
- `config/caste_recipes.yaml` (queen tool list only)
- `tests/unit/surface/test_queen_tools.py`

**Do not touch:** `core/events.py`, `engine/runner.py`, other castes

---

## Track 3 — Three-Stage Intent Classification (~150 lines)

Replace the regex-based `_DELIBERATION_RE` guard with a procedural gate
sequence in the Queen system prompt. The intent parser adds DIRECT_WORK
as a safety net category.

### Stage 1 — Quick triage (pattern match, zero LLM calls)

- Greeting or social → CHAT (Queen responds conversationally)
- Status inquiry ("what's running", "show budget", "how did X do") →
  STATUS (Queen uses inspect/query tools)
- Config request ("change the model", "set budget to") → CONFIG
- Everything else → Stage 2

### Stage 2 — Depth assessment (Queen uses her tools before deciding)

- Can Queen answer with `search_codebase`, `read_workspace_files`,
  `run_command`, or `memory_search`?
  → DIRECT_WORK. Queen handles it herself with 1-3 tool calls.
- Needs clarification or context gathering?
  → DELIBERATE. Queen asks questions, investigates with tools.
- Clearly multi-step sustained work? → Stage 3.

### Stage 3 — Spawn readiness checklist (4 gates, all must pass)

1. Operator clearly specified the goal (not a vague question)
2. Queen gathered sufficient context via direct tools
3. Scope is defined enough for a colony to work independently
4. Complexity justifies colony overhead vs direct work

Any gate failing → DELIBERATE (ask clarifying questions, gather context).
All gates passing → `propose_plan` first (Wave 61), then SPAWN only
after operator confirms.

**Key behavioral change:** DELIBERATE is the default. DIRECT_WORK is the
preferred action mode. SPAWN is the escalation path.

### Implementation

**System prompt rewrite (~50 lines replacing the existing ~20-line
decision process section in `caste_recipes.yaml`):**

Replace the existing decision process section (lines 46-67) with the
three-stage flowchart:

```
## How to respond to operator messages

STAGE 1 — CLASSIFY
- Greeting/social → respond conversationally
- "What's the status of..." → call get_status or inspect_colony
- "Change the config..." → call suggest_config_change

STAGE 2 — CAN YOU ANSWER DIRECTLY?
- "Where is X defined?" → search_codebase("X"), read the result, answer
- "What does Y do?" → search_codebase("Y"), explain
- "Are the tests passing?" → run_command("pytest -q"), report result
- "What changed recently?" → run_command("git log --oneline -10"), summarize
- If you can answer with 1-3 tool calls: DO IT. No colony needed.

STAGE 3 — IS THIS COLONY WORK?
Only if the task requires:
- Writing/modifying multiple files
- Running iterative code-test-fix cycles
- Multi-agent coordination (coder + reviewer)
- More than 5 minutes of sustained work

Then: call propose_plan first. Wait for operator confirmation.
Never spawn without proposal unless operator already confirmed.
```

**Intent parser updates (~50 lines in `queen_intent_parser.py`):**
- Add DIRECT_WORK category alongside DELIBERATE
- Quick-answer patterns: "where is", "what does", "show me", "are the
  tests", "what changed" → DIRECT_WORK
- DIRECT_WORK returns `{}` (no tool call) same as DELIBERATE — the
  system prompt handles the actual behavior

**Owned files:**
- `config/caste_recipes.yaml` (queen system prompt section)
- `src/formicos/adapters/queen_intent_parser.py`
- `tests/unit/adapters/test_queen_intent_parser.py`

**DEPENDS ON Track 2.** The Stage 2 DIRECT_WORK path routes to
`search_codebase` and `run_command` — those tools must exist before the
intent classifier can reference them. Track 2 ships before or alongside
Track 3.

**caste_recipes.yaml conflict note:** Tracks 2 and 3 both modify the Queen
section. Track 2 adds tool specs and tool list entries. Track 3 rewrites
the decision tree structure. Merge Track 2 first (adds tools), then
Track 3 rewrites the decision tree referencing those tools.

---

## Track 4 — Cloud Routing for Queen Planning (~30 lines)

**Problem:** When the Queen calls `propose_plan`, a local 30B model
produces generic plans. A cloud model (Gemini 2.5 Pro at $1.25/$10 per
MTok) produces plans that account for codebase structure, budget, and
conventions.

**Design:** Route `propose_plan` LLM calls through cloud. Everything
else stays local. Opt-in only.

**Implementation (~30 lines in `queen_runtime.py`):**

In `queen_runtime.py:respond()`, before the LLM call at line ~628, check
the workspace config for a planning model override:

```python
# Wave 62: cloud routing for planning calls
queen_model = self._resolve_queen_model(workspace_id)
ws = self._runtime.projections.workspaces.get(workspace_id)
if ws and ws.config.get("queen_planning_model"):
    # Check if last tool call was propose_plan or operator message
    # looks like a planning request
    _last_tools = [m for m in messages if m.get("role") == "assistant"
                   and m.get("tool_calls")]
    if _last_tools:
        _last_names = [tc.get("name") for tc in
                       _last_tools[-1].get("tool_calls", [])]
        if "propose_plan" in _last_names:
            queen_model = ws.config["queen_planning_model"]
```

The operator enables this via workspace config:
```yaml
queen_planning_model: "gemini/gemini-2.5-pro"
```

Default: no override (stays local). Opt-in only.

**Cost:** ~20 propose_plan calls/day × ~2K tokens each = ~40K tokens/day.
At Gemini 2.5 Pro: ~$0.30/day, ~$7/month.

**Independent.** Cloud routing checks the last tool call name
(`propose_plan`) in the dispatch context — it doesn't need the intent
classifier. It just needs `propose_plan` to exist, which shipped in Wave 61.

**Owned files:**
- `src/formicos/surface/queen_runtime.py` (respond method)
- No new config fields needed — uses existing workspace config override

---

## Track 5 — Quality-Based Auto-Escalation (~60 lines)

**Problem:** When a colony stalls on the local model (0 productive tool
calls in 3+ rounds), it just fails. The multi-provider routing handles
adapter errors but not quality failures.

**Design:** Narrow trigger only — total stall. NOT quality threshold,
NOT partial failure. The Queen proposes, operator decides.

**Implementation (~60 lines in `colony_manager.py`):**

After `ColonyCompleted` / `ColonyFailed` event emission and
`_post_colony_hooks()`, check the colony's productive call count.
The data is already available: `total_productive_calls` is tracked
in the round loop (used by `compute_quality_score`).

Two insertion points — the failure path at line ~1002 and the
max-rounds path at line ~1038:

```python
# Wave 62: stall-based escalation proposal
if (total_productive_calls == 0
    and round_num >= 3
    and not getattr(colony, "routing_override", None)):
    # Don't propose if already running on a cloud model
    from formicos.core.events import ColonyChatMessage
    await self._runtime.emit_and_broadcast(ColonyChatMessage(
        seq=0, timestamp=_now(), address=address,
        colony_id=colony_id,
        workspace_id=colony.workspace_id,
        sender="system", event_kind="escalation_proposal",
        content=(
            f"Colony stalled — 0 productive tool calls in "
            f"{round_num} rounds. Want me to retry with a cloud model?"
        ),
    ))
```

The Queen's existing conversation flow handles the rest — operator
confirms, Queen spawns a new colony with `model_override`.

**Do NOT auto-escalate.** Only propose. Only on total stall (0 productive
calls). Only if not already on a cloud model.

**event_kind convention note:** The code uses `event_kind="escalation_proposal"`.
Existing `event_kind` values in the codebase are: `"complete"` (colony
completion, colony_manager.py:929), `"code_executed"` (sandbox results,
colony_manager.py:166), `"phase"` (round milestones, runner.py:1000),
`"governance"` (stall/convergence warnings, runner.py:1187-1194),
`"iteration_limit"` (agent iteration cap, runner.py:1638), `"service"`
(maintenance/service messages, projections.py), `"agent_turn"` (turn
records, colony_manager.py:1263), `"directive"` (operator directives,
checked in projections.py:2124). The `event_kind` field is an untyped
string, not an enum, so `"escalation_proposal"` is valid. Keep naming
consistent with the `noun_qualifier` pattern used by the existing values.

**Owned files:**
- `src/formicos/surface/colony_manager.py` (post-completion paths)
- `tests/unit/surface/test_colony_manager.py` (new test)

---

## Track 6 — Registry Refactor (Addon Phase 0, ~100 lines changed, net negative LOC)

Replace the if/elif dispatch chain with dict-based registry. This is a
refactor, not a feature. It improves code quality now and happens to
enable addons later.

### Backend: queen_tools.py

The current dispatch method (lines 975-1121) is a 23-branch if/elif chain.
Replace with:

```python
def __init__(self, runtime: Runtime, ...) -> None:
    ...
    self._handlers: dict[str, Callable] = {
        "spawn_colony": self._handle_spawn_colony,
        "spawn_parallel": self._handle_spawn_parallel,
        "kill_colony": self._handle_kill_colony,
        "get_status": self._handle_get_status,
        "propose_plan": self._handle_propose_plan,
        "search_codebase": self._handle_search_codebase,
        "run_command": self._handle_run_command,
        # ... all 27+ tools
    }

async def dispatch(self, tc, workspace_id, thread_id):
    name = tc.get("name", "")
    inputs = self._runtime.parse_tool_input(tc)
    log.info("queen.tool_call", tool=name, inputs=inputs)
    try:
        if name in ("archive_thread", "define_workflow_steps"):
            return DELEGATE_THREAD
        handler = self._handlers.get(name)
        if handler is None:
            return (f"Unknown tool: {name}", None)
        return await handler(inputs, workspace_id, thread_id)
    except Exception as exc:
        log.exception("queen.tool_error", tool=name)
        return (f"Tool {name} failed: {exc}", None)
```

**Note:** Some existing handlers take different argument signatures
(some take only `inputs`, some take `inputs + workspace_id`, some take
`inputs + workspace_id + thread_id`). The refactor must normalize handler
signatures. Options:
- All handlers take `(inputs, workspace_id, thread_id)` and ignore unused args
- Use `**kwargs` for context
- Wrap handlers that need fewer args with lambdas in the registry

Recommended: all handlers take `(inputs, workspace_id, thread_id)`.
Update existing handler signatures to accept and ignore the extra args.

### Frontend: formicos-app.ts

The current `renderView()` (lines 511-603) is a switch statement with 7
cases. Replace with a component registry map:

```typescript
private _viewRegistry: Record<string, () => TemplateResult> = {
    'queen': () => this._renderQueen(),
    'tree': () => this._renderTree(),
    'knowledge': () => this._renderKnowledge(),
    'workspace': () => this._renderWorkspace(),
    'playbook': () => this._renderPlaybook(),
    'models': () => this._renderModels(),
    'settings': () => this._renderSettings(),
};

private renderView() {
    const renderer = this._viewRegistry[this.view];
    return renderer ? renderer() : nothing;
}
```

Each case becomes a private method. Net LOC change is zero or slightly
negative. The `'tree'` case has nested if-statements (colony vs thread
vs workspace) — those stay as internal logic in `_renderTree()`.

### Addon directory

Create `addons/` directory at repo root with `addons/README.md` documenting
the manifest schema (from the extension architecture research). This is
documentation only — zero runtime changes.

**Owned files:**
- `src/formicos/surface/queen_tools.py` (dispatch refactor)
- `frontend/src/components/formicos-app.ts` (renderView refactor)
- `addons/README.md` (new)

---

## Parallel Execution Plan

```
Track 1   (retrieval bugs)     ─────── SHIPS FIRST, independent
Track 1.5 (outcome stats)     ─────── independent (projections.py, queen_tools.py)
Track 2   (Queen tools)        ─────── independent (queen_tools.py, caste_recipes.yaml)
Track 3   (intent classifier)  ─────── DEPENDS ON Track 2 (needs search_codebase + run_command to exist)
Track 4   (cloud routing)      ─────── independent (queen_runtime.py only)
Track 5   (stall escalation)   ─────── independent (colony_manager.py)
Track 6   (registry refactor)  ─────── independent (queen_tools.py shared with Track 2)
```

### Three coder teams

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A | Track 1 (retrieval bugs) + Track 1.5 (outcome stats) + Track 5 (stall escalation) | All read/write projections + colony_manager area, all backend-only, all small |
| Team B | Track 6 (registry refactor) then Track 2 (Queen tools) | Both touch queen_tools.py. Refactor dispatch FIRST, then add tools to new registry. Merge order: Track 6 → Track 2. |
| Team C | Track 3 (intent classification) + Track 4 (cloud routing) | Track 3 rewrites system prompt and intent parser. Track 4 adds cloud routing in queen_runtime.py. Track 4 is independent but colocated with Team C since both are small prompt/routing changes. Sequential within team: Track 3 after Track 2 lands. |

### Merge order

1. **Track 1** first (retrieval foundation)
2. **Track 6** (dispatch refactor — clean merge base for Track 2)
3. **Tracks 1.5, 2, 4, 5** in any order (all land after Track 6)
4. **Track 3** after Track 2 (needs the tools to exist)

**Overlap notes:**
- `queen_tools.py` (Tracks 1.5, 2, 6): Track 6 refactors dispatch first.
  Track 1.5 adds a method call inside `_propose_plan()` — minimal textual
  overlap with Track 2 (which adds new handlers). Both safe after Track 6.
- `colony_manager.py` (Tracks 1, 5): Track 1 inserts in the round loop
  (between lines 713-715). Track 5 inserts in post-completion paths
  (lines ~1002, ~1038). Non-overlapping sections — safe in any order,
  but Track 1 ships first as the critical bug fix.
- `test_queen_tools.py` (Tracks 1.5, 2): Different test classes, no conflict.

### caste_recipes.yaml conflict resolution

Tracks 2 and 3 both modify the Queen section of `caste_recipes.yaml`.
Track 2 adds tool specs and tool list entries. Track 3 rewrites the
decision tree structure referencing those tools. Merge Track 2 first
(adds tools), then Track 3 rewrites the decision tree to reference
`search_codebase` and `run_command`. Call this out in both dispatch
prompts.

---

## What this wave does NOT do

- `edit_file` or `run_tests` Queen tools (Wave 63 — needs safety design:
  backup before edit, diff preview, operator confirmation gate)
- `git_info` as separate tool (subsumed by `run_command` with git allowlist)
- Addon manifest loader or runtime registration (Phase 1-2, Wave 65+)
- Service colony lifecycle (Phase 2, Wave 65+)
- Interactive colonies (Phase 4, deferred until addon system proves out)
- Queen-generated addons (Phase 5, requires workspace executor containerization)
- Negative signal extraction (good idea, defer to Wave 63 — not urgent)
- GEPA/DSPy prompt evolution (research-grade, defer indefinitely)
- Full A2A/AG-UI conformance (no consumers exist)
- New event types (stays at 65)

---

## Validation Gate

```bash
pytest tests/ -q
ruff check src/
python scripts/lint_imports.py
```

Plus manual tests:

1. "Where is the budget enforcer defined?" → Queen greps with
   `search_codebase`, reads file, answers in <5 seconds. No colony.
2. "Are the tests passing?" → Queen runs `pytest -q` via `run_command`,
   reports result. No colony.
3. `run_command("rm -rf /")` → rejected by allowlist, error returned.
4. "What should we build next?" → Queen calls `propose_plan` routed
   through cloud model (if configured), returns project-aware proposal.
5. Colony stalls on local → Queen proposes cloud re-run. Operator
   confirms, retry spawns with cloud model.
6. Retrieval smoke test shows >5 unique entries accessed across rounds.
7. `propose_plan` output includes empirical outcome stats when prior
   colonies exist in the workspace.
8. `dispatch()` uses dict registry (no if/elif chain). `renderView()`
   uses component map (no switch).
9. 3446+ tests pass, ruff clean, no layer violations.

---

## Success Criteria

After Wave 62, the Queen can:
- Answer codebase questions directly (`search_codebase` + `read_workspace_files`)
- Run git status, tests, and linting (`run_command` with allowlist)
- Plan with cloud intelligence (`propose_plan` routed to Gemini)
- Cite empirical outcome data in proposals (success rates, avg rounds/cost)
- Offer cloud retry when local model stalls
- Retrieve knowledge correctly (3 bugs fixed)
- Dispatch tools via registry (no elif chain)

That's the "dispatch router to working colleague" transition. The
operator's daily experience changes from "everything requires a colony"
to "the Queen handles quick tasks herself and only spawns colonies for
real work."
