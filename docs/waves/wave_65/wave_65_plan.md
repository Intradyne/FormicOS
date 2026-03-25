# Wave 65: The Operational OS

**Status:** Complete (Wave 65.5 polish pass landed)
**Predecessor:** Wave 64 (Parallel Execution + Addon Infrastructure)
**Theme:** Make every addon functional, make the Queen autonomous, ship launch docs.

Wave 64 built the addon system infrastructure (loader, manifests, events,
triggers, proactive extraction). Wave 65 makes it real: every placeholder
becomes working code, the Queen gains general-purpose project management
tools, and the system ships with documentation an external developer can
follow.

## Strategic Context

The operator will add a GitHub MCP server to the Docker toolkit. This
changes the wave shape. Instead of building GitHub-specific tools for the
Queen, we make her effective at discovering and chaining external MCP tools
she hasn't seen before. The GitHub MCP server adds issue/PR/review tools
directly to the Queen's tool surface without FormicOS code changes.

**Implication:** Addons provide persistent intelligence on top of external
services (watch for PR reviews, auto-stage after colony work, index the
codebase semantically). MCP provides external service access (GitHub, Slack).
The Queen chains both. No special integration code -- the Queen's system
prompt guides the chaining, and smarter models will chain better.

**Design principle:** General-purpose tools over bespoke workflows. A
`batch_command` that runs arbitrary allowlisted commands is more future-proof
than a `check_ci_status` that does one thing. Bet on the LLM capability
ceiling continuing to drop fast.

## Pre-existing State

**Reasoning/cache token accounting:** Already fully implemented. The plan
file at `C:\Users\User\.claude\plans\snazzy-wiggling-hummingbird.md` is
stale -- all 11 files are already wired:
- `core/types.py:562-566` -- LLMResponse fields
- `core/events.py:453-456` -- TokensConsumed fields
- `adapters/llm_openai_compatible.py:278-287` -- OpenAI extraction
- `adapters/llm_anthropic.py:175-181` -- Anthropic extraction
- `adapters/llm_gemini.py:252-270` -- Gemini extraction
- `engine/runner.py:1423-1424,1500-1501,1693-1694` -- accumulation
- `surface/projections.py:288-289,329-345,1369-1378` -- BudgetSnapshot
- `surface/runtime.py:1797-1798` -- REST response
- `frontend/src/components/budget-panel.ts:6-12,29-30,159-160,188-225` -- UI

No Track 7 needed for token accounting.

**Queen tools:** 31 defined in `queen_tools.py:217-1198`, 27 configured in
`config/caste_recipes.yaml:194`. 4 Wave 63-64 tools (edit_file, run_tests,
delete_file, retry_colony) need adding to the caste recipe.

**MCP tools:** 19 tools in `mcp_server.py:24-44`. Queen has no visibility
into what MCP tools are available -- MCP and Queen are separate surfaces.

---

## Track 1: Addon Runtime Context (shared prerequisite)

**Problem:** Addon handlers receive `(inputs, workspace_id, thread_id)` but
cannot access runtime ports (vector store, embedding, event store, workspace
filesystem root). The tool wrapper in `addon_loader.py:183-190` closes over
the handler function but passes no runtime context. This makes all addons
that need infrastructure (codebase-index, git-control) structurally unable
to function.

**Fix:** Extend `register_addon()` (`addon_loader.py:150`) to accept an
optional `runtime_context: dict[str, Any]` parameter. Store it on the
`AddonRegistration` result. Modify the tool wrapper closure to pass
`runtime_context` as a keyword argument to handlers that accept it:

```python
# addon_loader.py ~line 183
async def _tool_wrapper(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    _bound_fn: Callable[..., Any] = _fn,
    _ctx: dict[str, Any] = runtime_context or {},
) -> Any:
    sig = inspect.signature(_bound_fn)
    if "runtime_context" in sig.parameters:
        return await _bound_fn(inputs, workspace_id, thread_id, runtime_context=_ctx)
    return await _bound_fn(inputs, workspace_id, thread_id)
```

Same pattern for event handlers (`addon_loader.py:207-227`).

In `app.py` lifespan (after line 739), construct the context dict:

```python
_addon_runtime_context = {
    "vector_port": runtime.memory_store,
    "embed_fn": runtime.embed_fn,
    "workspace_root_fn": lambda ws_id: Path(runtime.data_dir) / "workspaces" / ws_id / "files",
    "event_store": runtime.event_store,
    "settings": runtime.settings,
}
```

Pass to `register_addon(..., runtime_context=_addon_runtime_context)`.

**Files:**
- `src/formicos/surface/addon_loader.py` -- wrapper change (~30 lines)
- `src/formicos/surface/app.py` -- context construction (~10 lines)

**Tests:** 2 new (handler receives context, handler without context param
still works).

**Owner:** Team A. Merge first -- unblocks Tracks 2 and 3.

---

## Track 2: Codebase Index Addon -- Make It Real

**Problem:** `search.py:54-59` returns a placeholder string. The indexer
(`indexer.py:115-215`) has working chunking, embedding, and upsert logic
but `handle_semantic_search` never calls it.

**Fix:** Rewrite `handle_semantic_search` (`search.py:26-59`) to use
`runtime_context["vector_port"].search()` for real vector similarity search.
Parse `inputs["query"]`, `inputs.get("top_k", 10)`, call the vector port,
format results with file path, line range, and content snippet.

Add a `reindex_codebase` tool to `addons/codebase-index/addon.yaml` with a
handler that calls `indexer.py::incremental_reindex` using the runtime
context's embed_fn and vector_port. This gives the Queen an on-demand
"index the codebase now" capability.

**Files:**
- `src/formicos/addons/codebase_index/search.py` -- real search (~60 lines,
  replaces 34-line placeholder)
- `src/formicos/addons/codebase_index/indexer.py` -- add runtime_context
  parameter to `full_reindex` and `incremental_reindex` signatures (~10 lines)
- `addons/codebase-index/addon.yaml` -- add reindex_codebase tool entry

**Tests:** 4 new (search returns results, search with no index returns empty,
reindex populates collection, incremental reindex detects changes).

**Owner:** Team A. Depends on Track 1.

---

## Track 3: Git Control Addon -- Make It Real

**Problem:** `tools.py` has a working `_run_git` helper (lines 19-33) that
is never called. `handle_smart_commit` (lines 36-74) returns structured
context but doesn't execute. `handle_branch_analysis` (lines 77-103)
returns analysis but doesn't run git commands. `handlers.py:12-37` logs
intent but doesn't stage files.

**Fix:**

1. `handle_smart_commit`: Call `_run_git("diff", "--cached")` and
   `_run_git("log", "--oneline", "-5")` to get real staged diff and recent
   commit style. Return actual diff context, not instructions. The Queen
   uses this context to generate a commit message, then calls
   `git_smart_commit` again with `inputs["message"]` to execute
   `_run_git("commit", "-m", message)`. Two-phase: inspect then commit.

2. `handle_branch_analysis`: Call `_run_git("branch", "-vv")`,
   `_run_git("log", "--oneline", "main..HEAD")` to get real divergence
   data. Return actual ahead/behind counts and commit list.

3. `on_colony_completed_auto_stage` (`handlers.py`): When
   `workspace_config.get("git_auto_stage")` is true, use runtime_context
   to find the workspace root, enumerate modified files (compare against
   last known state or use `_run_git("status", "--porcelain")`), and run
   `_run_git("add", *modified_files)`.

4. Add `git_create_branch` and `git_stash` tools to manifest. Simple
   20-line handlers wrapping `_run_git`.

**Files:**
- `src/formicos/addons/git_control/tools.py` -- rewrite handlers (~120
  lines net, replacing ~80 lines of stubs)
- `src/formicos/addons/git_control/handlers.py` -- real auto-stage (~40
  lines, replacing 25-line stub)
- `addons/git-control/addon.yaml` -- add 2 new tools

**Tests:** 6 new (smart_commit returns real diff, branch_analysis returns
real data, auto_stage stages files, create_branch creates branch,
stash saves/restores, commit with message executes).

**Owner:** Team A. Depends on Track 1.

---

## Track 4: Wire TriggerDispatcher into Lifespan

**Problem:** `trigger_dispatch.py` (152 lines) is complete and tested but
nothing instantiates `TriggerDispatcher` or calls `evaluate_cron_triggers`.
Addon cron triggers (e.g., codebase-index daily reindex at 3am) will never
fire.

**Fix:** In `app.py` lifespan (after addon loading, ~line 770):

1. Instantiate `TriggerDispatcher`.
2. Register each addon's triggers from manifests.
3. Start a background `asyncio.Task` that loops every 60 seconds calling
   `evaluate_cron_triggers()`.
4. For each fired trigger: resolve the handler via the addon registry,
   call it with runtime_context, emit `ServiceTriggerFired` event.
5. On shutdown: cancel the background task.

Add a `trigger_addon` Queen tool to `queen_tools.py` so the Queen can
manually fire any addon's manual trigger ("reindex the codebase now").

**Files:**
- `src/formicos/surface/app.py` -- trigger wiring in lifespan (~50 lines)
- `src/formicos/surface/queen_tools.py` -- trigger_addon tool (~40 lines)
- `config/caste_recipes.yaml` -- add trigger_addon to Queen tool list

**Tests:** 3 new (cron triggers fire on schedule, manual trigger fires via
Queen tool, shutdown cancels background task).

**Owner:** Team A. After Tracks 1-3.

---

## Track 5: Queen Autonomous Agency

**Problem:** The Queen can spawn colonies and use built-in tools, but she
lacks general-purpose project management capabilities. She cannot run
multiple checks in one operation, summarize thread history, produce
structured documents, or discover her own capabilities including addon and
MCP tools.

### 5a: `batch_command` tool

Run multiple allowlisted commands in sequence, return aggregated results.
The Queen managing a repo needs "check tests + check lint + check git
status" as one operation. Each command validated against the existing
`run_command` allowlist (`queen_tools.py`, `_handle_run_command` handler).

```
Parameters:
  commands: list[str]  -- each validated against allowlist
  stop_on_error: bool  -- default true
Returns: list of {command, exit_code, stdout, stderr}
```

Handler: iterate commands, call `_handle_run_command` for each, collect
results, short-circuit on error if `stop_on_error`.

~60 lines in `queen_tools.py`.

### 5b: `summarize_thread` tool

Produce a structured summary of a thread's entire history: planned work,
colony outcomes (success/fail/cost/rounds), knowledge extracted, total cost,
timeline. The Queen needs this for "what did we accomplish" and for
generating PR descriptions that cite colony results.

Pull data from `ThreadProjection`, `ColonyOutcome` projections, and
`BudgetSnapshot`. Format as structured text with sections.

```
Parameters:
  thread_id: str
  detail_level: str  -- "brief" | "full" (default "brief")
Returns: structured thread summary string
```

~80 lines in `queen_tools.py`.

### 5c: `draft_document` tool

Write a structured document to the workspace. Supports: changelog (prepend
to existing), release notes, generic markdown. This is `write_workspace_file`
with document-type-aware formatting and optional append/prepend modes.

```
Parameters:
  path: str
  content: str
  mode: str  -- "overwrite" | "prepend" | "append" (default "overwrite")
  workspace_id: str (optional, defaults to active workspace)
Returns: confirmation with byte count
```

~50 lines in `queen_tools.py`.

### 5d: `list_addons` tool

Return installed addons with their tools, handlers, trigger status, and
version. The Queen should answer "what can I do?" by listing her full
capability surface.

Pull from `app.state.addon_manifests` (set in `app.py:768`). Format each
addon with name, version, tool list, handler list, trigger list.

```
Parameters: none
Returns: formatted addon inventory
```

~30 lines in `queen_tools.py`.

### 5e: System prompt update for MCP-aware reasoning

Add guidance to the Queen's system prompt in `config/caste_recipes.yaml`:

```
## External Tool Chaining

When external MCP tools are available (GitHub, Slack, etc.), you can chain
them with your built-in and addon tools. Example workflow:

1. search_codebase to understand the change scope
2. spawn_parallel for implementation across providers
3. run_tests / batch_command to verify
4. git_smart_commit to commit with context-aware message
5. [GitHub MCP] create_pull_request with description from colony outcomes
6. summarize_thread for the operator

Always propose the full workflow via propose_plan before executing multi-step
sequences. When addon tools and MCP tools overlap (e.g., git operations),
prefer the addon tool for operations that benefit from FormicOS context
(smart commit messages from colony outcomes) and the MCP tool for operations
that need external service integration (PR creation, issue management).
```

### 5f: Update caste recipe tool list

Add to Queen tools in `config/caste_recipes.yaml:194`:
- `batch_command`
- `summarize_thread`
- `draft_document`
- `list_addons`
- `trigger_addon` (from Track 4)
- `edit_file` (Wave 63, missing from recipe)
- `run_tests` (Wave 63, missing from recipe)
- `delete_file` (Wave 63, missing from recipe)
- `retry_colony` (Wave 64, missing from recipe)

**Files:**
- `src/formicos/surface/queen_tools.py` -- 4 new tools (~220 lines)
- `config/caste_recipes.yaml` -- tool list update + system prompt addition

**Tests:** 6 new (batch_command runs multiple commands, batch_command
stops on error, summarize_thread returns structured output,
draft_document writes file, draft_document prepend mode, list_addons
returns inventory).

**Owner:** Team B. Independent of Team A tracks.

---

## Track 6: Proactive Intelligence Addon Polish

**Problem:** The proactive-intelligence addon was extracted (Wave 64 Track
6b) but its manifest declares `query_briefing` pointing at
`rules.py::generate_briefing` which has the wrong signature
(`(workspace_id, projections)` instead of `(inputs, workspace_id,
thread_id)`). The addon also lacks operator configurability.

**Fix:**

1. Add a `query_briefing_wrapper` function in a new `handlers.py` file
   that bridges the standard addon handler signature to
   `generate_briefing(workspace_id, projections)` using runtime_context.

2. Add `proactive_configure` Queen tool: enable/disable individual rules.
   Store per-workspace rule overrides via `WorkspaceConfigChanged` event
   (key: `proactive_disabled_rules`, value: list of rule names). The
   briefing generator already receives workspace config -- add a filter
   step.

3. Add a cron trigger to the manifest for periodic background briefing
   computation. Currently computed synchronously on every `respond()` call
   (`queen_runtime.py`), which adds latency. The cron trigger computes
   the briefing and caches it; `respond()` reads the cache instead.

**Files:**
- `src/formicos/addons/proactive_intelligence/handlers.py` -- new, wrapper
  + configure handler (~60 lines)
- `addons/proactive-intelligence/addon.yaml` -- update handler ref, add
  configure tool, add cron trigger
- `src/formicos/surface/queen_tools.py` -- proactive_configure dispatch
  (~30 lines)

**Tests:** 3 new (wrapper calls generate_briefing correctly, configure
disables rule, cron trigger handler caches briefing).

**Owner:** Team A. After Track 4 (needs trigger wiring).

---

## Track 7: Addon Development Guide + Launch Docs

**Problem:** No documentation for addon development. No updated README.
No FINDINGS.md. No CONTRIBUTING.md. No CI/CD.

### 7a: Addon development guide

Write `addons/README.md` as a comprehensive addon development guide:
- Quickstart (create an addon in 5 minutes)
- Manifest reference (every field with examples from real addons)
- Handler signatures (`async def handler(inputs, ws_id, thread_id, *,
  runtime_context=None)`)
- Runtime context (what ports are available, how to use them)
- Trigger types (cron format, event subscription, manual)
- Testing patterns (mock runtime ports, test helpers)
- Annotated walkthrough of codebase-index and git-control as examples
- Conventions (safety rules, naming, versioning)

Add `addons/TEMPLATE/` scaffold directory with commented manifest and
example handler.

### 7b: Launch documentation

- `README.md` refresh to Wave 65 state (architecture overview, quickstart,
  feature list, deployment)
- `FINDINGS.md` with the measurement story (+0.011 domain, +0.177
  operational, Syllable Counting safety story, Aider benchmark
  infrastructure ready)
- `.github/workflows/ci.yml` -- GitHub Actions (`ruff check` +
  `lint_imports` + `pytest tests/unit/` on push)
- `CONTRIBUTING.md` (how to run tests, create addons, code style, layer
  structure, ADR process)

**Files:**
- `addons/README.md` (~300 lines)
- `addons/TEMPLATE/addon.yaml` + `addons/TEMPLATE/handler.py` (~40 lines)
- `README.md` (~200 lines refresh)
- `FINDINGS.md` (~150 lines)
- `.github/workflows/ci.yml` (~40 lines)
- `CONTRIBUTING.md` (~100 lines)

**Tests:** 2 new (template addon loads without error, list_addons includes
template addon).

**Owner:** Team C. After Tracks 1-6 so documentation references real code.

---

## Team Assignment

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A (Addons) | 1, 2, 3, 4, 6 | All addon infrastructure. T1 is the shared prerequisite. T2+T3 parallel after T1. T4 after T2+T3. T6 after T4. |
| Team B (Queen) | 5 | Queen tools and system prompt. Independent of Team A. |
| Team C (Docs) | 7 | All documentation. After T1-T6 so examples are real. |

## Merge Order

```
T1 (addon runtime context)     -- unblocks T2, T3
    |
    +---> T2 (codebase index)  -- parallel
    +---> T3 (git control)     -- parallel
    |
T4 (trigger wiring)            -- after T2+T3
T5 (Queen tools)               -- independent, any time
T6 (proactive polish)          -- after T4
T7 (docs)                      -- after everything
```

## What Wave 65 Does NOT Do

- No Aider benchmark execution (infrastructure ready, operator runs when
  ready)
- No new event types (stays at 69)
- No workspace sandbox viewer (pre-launch gate, future wave)
- No retrieval correctness fixes (roadmap items 1-3, future wave)
- No quality-based auto-escalation (roadmap item 5, future wave)
- No Queen deliberation mode (pre-launch gate, future wave)
- No Queen-generated addons (needs workspace containerization)
- No hot-reload for addons (restart required)
- No GitHub MCP server installation (operator handles Docker config)
- No IDE/CLI integration
- No multi-user/auth
- No workspace_execute containerization
- No RL/self-evolution

## The MCP + Addon Composability Test

After Wave 65, if the operator adds the GitHub MCP server:

1. Operator: "Build the OAuth feature and create a PR"
2. Queen calls `propose_plan` (cloud-routed): plan with branch creation,
   colony composition, test verification, commit, PR creation
3. Operator confirms
4. Queen: `git_create_branch("feature/oauth")` (git addon)
5. Queen: `spawn_parallel(...)` across providers (built-in)
6. Colonies complete, Queen gets aggregated result (Wave 63)
7. Queen: `batch_command(["run_tests tests/", "ruff check src/"])` (built-in)
8. Queen: `git_smart_commit(...)` with real diff context (git addon)
9. Queen: `create_pull_request(...)` via GitHub MCP with description from
   colony outcomes
10. Queen: `summarize_thread(...)` reports to operator

Steps 4, 8 are addon tools. Step 9 is MCP. Steps 5-7 are built-in. The
Queen chains all of them via system prompt guidance. No special integration
code.

## Acceptance Criteria

- Every addon tool returns real results (no placeholders, no stubs)
- TriggerDispatcher runs in background, cron triggers fire
- Queen can discover and list her full tool surface (built-in + addon + MCP)
- Queen system prompt includes MCP chaining guidance
- Addon creation guide is comprehensive enough for external developers
- README, FINDINGS, CI, CONTRIBUTING all shipped
- Caste recipe updated with all Wave 63-65 tools
- 3620+ tests passing
- CI: ruff clean, imports clean

## Estimated Scope

~800 lines of new code across Tracks 1-6. ~800 lines of documentation in
Track 7. 24 new tests. No new event types. No new architectural patterns.
All tracks are policy/wiring over existing Wave 64 infrastructure.
