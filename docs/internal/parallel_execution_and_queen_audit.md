# Parallel Execution and Queen Intelligence Audit

Audited 2026-03-24 against main branch (post-Wave 61).
Every line number verified by reading the source file.

---

## Parallel Execution

### Current State

**The runner already supports parallel agent execution within a round.**

`runner.py:1045-1069` uses `asyncio.TaskGroup` to run agents concurrently
within execution groups:

```python
for group in execution_groups:                     # sequential across groups
    async with asyncio.TaskGroup() as tg:
        for agent_id in group:
            tg.create_task(self._run_agent(...))    # concurrent within group
```

The grouping comes from `strategy.resolve_topology()` (line 1028):

- **SequentialStrategy** (`strategies/sequential.py:24-25`): Returns one agent
  per group -- fully serial execution. Every colony using `sequential` strategy
  runs agents one at a time.
- **StigmergicStrategy** (`strategies/stigmergic.py:49`): Returns groups from
  topological sort of pheromone-weighted adjacency. Agents in the same
  topological level run concurrently.

So parallel execution is already live for stigmergic colonies with multiple
agents at the same topological level. It has been live since stigmergic
strategy was implemented. Sequential strategy colonies are always serial.

### Round Model and Agent Parallelism

The 5-phase round model (runner.py lines 1004-1099):

| Phase | Lines | Name | Barrier? |
|-------|-------|------|----------|
| 1 | 1004-1006 | Goal | Before agents -- trivial assignment |
| 2 | 1008-1009 | Intent | Before agents -- event emission only |
| 3 | 1011-1030 | Route | Before agents -- topology + knowledge prior |
| 4 | 1032-1070 | Execute | **Contains parallelism** -- TaskGroup per group |
| 5 | 1071-1099 | Compress | After all agents -- summary + KG tuples |

Phases 1-3 run before any agent executes. Phase 4 has per-group barriers
(TaskGroup ensures all agents in a group complete before the next group
starts). Phase 5 runs only after all execution groups finish.

The compress phase (line 1071) is order-insensitive -- it joins
`outputs.items()` which preserves insertion order. No assumption about
which agent finished first.

### Shared Mutable State Between Concurrent Agents

All shared structures passed from `run_round` into concurrent `_run_agent`
calls (runner.py lines 1034-1041):

| Object | Type | Mutation | Concurrency risk |
|--------|------|----------|-----------------|
| `outputs` | `dict[str,str]` | Per-agent key write (line 1623) | Low -- unique keys per agent |
| `agent_costs` | `list[float]` | `.append()` (line 1660) | Safe under single-thread asyncio |
| `round_skill_ids` | `list[str]` | `.extend()` (line 1374) | Safe under single-thread asyncio |
| `round_knowledge_items` | `list` | `.extend()` (line 1376) | Safe under single-thread asyncio |
| `round_tool_results` | `list` | `.append()` (line 1571) | Safe under single-thread asyncio |
| `round_productive_calls` | `list[int]` | `.append()` (line 1667) | Safe under single-thread asyncio |
| `round_total_calls` | `list[int]` | `.append()` (line 1669) | Safe under single-thread asyncio |

All list mutations are safe because asyncio is cooperative single-threaded --
context switches only happen at `await` points. These would break under true
multi-threading but that is not how the system executes.

**The `outputs` dict doubles as routed context.** `assemble_context` (called at
runner.py:1360-1364) receives `routed_outputs=outputs`. Concurrent agents in
the same group see partially-populated outputs from peers. This is by design --
same-group agents are peers, not dependents.

### LLM Adapter Concurrency

All three adapters are safe for concurrent use from a shared instance:

**OpenAI-compatible** (`llm_openai_compatible.py`):
- Shared httpx client created at init (line 126-129)
- Per-call payload construction (lines 233-242) -- no shared mutable state
- Local endpoint semaphore (line 133-136): `asyncio.Semaphore(LLM_SLOTS)`,
  default 2 slots. Matches llama.cpp `-np` flag.
- Retry on 429 always, 400 for local only (lines 102-111)

**Anthropic** (`llm_anthropic.py`):
- Shared httpx client (line 68-71)
- Per-call payload (lines 137-146) -- no shared state
- No semaphore. Server-side rate limiting.

**Gemini** (`llm_gemini.py`):
- Shared httpx client (line 108)
- Per-call payload (lines 163-181) -- no shared state
- No semaphore. Server-side rate limiting.

**llama.cpp parallel slots are configured.** `docker-compose.yml` line 203:
`-np ${LLM_SLOTS:-2}` (default 2 parallel inference slots). The adapter's
semaphore reads the same env var (line 58), keeping client-side concurrency
matched to server-side slots.

### LLM Router

`LLMRouter` (runtime.py line 170) holds `dict[str, LLMPort]` mapping provider
prefix to adapter instance (line 187). Each `complete()` call (line 275)
resolves the provider independently via `_resolve()` (line 411) which splits
the model address on `/`. Multiple concurrent calls can hit different adapters
simultaneously with no serialization.

The routing table (runtime.py line 218, `route()` method) supports per-caste,
per-phase model assignment. Budget gating (line 234), routing table lookup
(line 239), adapter verification (line 247), and provider cooldown (line 257)
are all read-only or use simple timestamp comparisons safe under asyncio.

### Model Resolution and Per-Agent Routing

**Different agents in the same colony can route to different providers today.**

The full resolution cascade per agent (`runtime.py:875-935, build_agents()`):

1. `colony.model_assignments[caste]` -- spawn-time explicit override (line 908)
2. `recipe.tier_models[slot.tier]` -- per-caste tier model (line 909)
3. `resolve_model(caste, workspace_id)` -- workspace -> system default (line 910)

Each `AgentConfig` carries its own resolved model address (types.py line 605).
The `_route_fn` closure (colony_manager.py:582-596) calls `LLMRouter.route()`
per caste/phase, selecting the appropriate provider.

**The routing table already assigns different models per caste.** Example from
a typical config: coder -> `llama-cpp/gpt-4` (local), reviewer ->
`openai/gpt-4o` (cloud), researcher -> `openai/gpt-4o-mini` (cloud).

**Key constraint: one adapter instance per provider prefix** (app.py line 266).
Two models with the same prefix (e.g., `llama-cpp/qwen-coder` and
`llama-cpp/qwen-reviewer`) share a single adapter instance, meaning they share
the same `base_url`. You cannot route two `llama-cpp/*` models to different
servers without creating separate provider prefixes.

**ModelRecord has an `endpoint` field** (types.py line 195) -- optional URL
per model. However, adapter instantiation (app.py:261-301) creates one adapter
per provider prefix using the endpoint of the FIRST registry entry for that
provider. Subsequent entries with the same prefix but different endpoints are
silently ignored (app.py line 266: `if model.provider in llm_adapters: continue`).

### Workspace and Tool Isolation

**Tool dispatch is stateless and safe.** `TOOL_SPECS` and `TOOL_CATEGORY_MAP`
(tool_dispatch.py lines 19, 542) are module-level read-only dicts. Tool
callbacks are per-`RoundRunner` instance (runner.py line 915).

**Code sandbox is fully isolated.** Each `code_execute` gets its own disposable
Docker container with `--network=none`, `--memory=256m`, `--read-only`
(sandbox_manager.py lines 109-125).

**Workspace file operations have NO locking.**
- `write_workspace_file` (runner.py line 2001): bare `write_text()`, no lock
- `patch_file` (runner.py line 2012): read-modify-write with no atomicity
- `workspace_execute` with Docker (sandbox_manager.py line 816): destructive
  `_restore_workspace_from_archive()` (lines 373-397) deletes all files then
  copies from archive. Last-write-wins race.

All agents in a colony share the same workspace path. Concurrent agents in
the same execution group writing to the same file will race. The `patch_file`
read-modify-write pattern is the highest-risk path.

### Event Store Concurrency

`SqliteEventStore.append()` (store_sqlite.py line 95) has no application-level
lock. SQLite WAL mode (line 75) + `busy_timeout=15000` (line 77) provides
implicit write serialization. Concurrent appends are safe (no corruption,
no gaps) but ordering between concurrent agents within a round is
non-deterministic.

### Locking Mechanisms in the Codebase

Only 3 concurrency primitives exist in adapters/engine:

| Location | Primitive | Purpose |
|----------|-----------|---------|
| `egress_gateway.py:149` | `asyncio.Lock()` | Rate limiter + robots cache |
| `llm_openai_compatible.py:133` | `asyncio.Semaphore` | Local LLM slot gating |
| `telemetry_bus.py:62` | `asyncio.Queue` | Buffered telemetry |

Notably absent: no lock on event store writes, no lock on workspace file
operations, no lock on workspace_execute restore.

---

### Scenario A: Same-Provider Parallel Slots

**Two coder agents in a colony, both hitting llama.cpp with `-np 2`.**

**What works today:**
- Stigmergic strategy places both agents in the same topological group
- `asyncio.TaskGroup` launches both `_run_agent` concurrently
- Both LLM calls enter the OpenAI adapter concurrently
- Semaphore (default 2) allows both through simultaneously
- llama.cpp serves both requests in parallel on its 2 slots
- Both responses return, both agents execute tools, both write to `outputs`

**What breaks:**
- Workspace file races: if both agents write to the same file via
  `write_workspace_file` or `patch_file`, last-write-wins
- Workspace execute races: if both call `workspace_execute`, the
  `_restore_workspace_from_archive` path is destructive
- Non-deterministic event ordering between the two agents

**What's needed to fix:**
- File-level optimistic locking for `patch_file` (medium effort, ~100 lines
  in runner.py -- add content hash check before write)
- Per-agent workspace branches for `workspace_execute` isolation (large
  effort, ~300 lines in sandbox_manager.py -- git-based branching or
  copy-on-write overlay)
- OR: accept the limitation and keep parallel agents to
  read-different-write-different file patterns (zero effort, operational
  discipline)

**Effort to unlock:** Already works for non-overlapping file access. File
locking for overlapping access is medium (~100 lines). Full workspace
isolation is large (~300 lines).

### Scenario B: Multi-Provider Fan-Out

**Three agents: local Qwen, DeepSeek API, Gemini Flash -- all concurrent.**

**What works today:**
- Model resolution already supports per-caste routing (types.py line 605,
  runtime.py lines 908-910)
- The routing table assigns different models per caste
- `LLMRouter.complete()` resolves each to a different adapter concurrently
- No global serialization -- all three LLM calls can be in flight at once
- Each adapter has its own httpx client with connection pooling

**What breaks:**
- Same workspace file races as Scenario A
- If DeepSeek and Gemini are both `openai/*` prefix, they share one adapter
  instance and one `base_url` -- cannot route to different endpoints

**What's needed:**
- Different provider prefixes for different OpenAI-compatible endpoints:
  register DeepSeek as `deepseek/deepseek-coder` and Gemini as
  `gemini/gemini-2.5-flash` (both already have dedicated adapters or can
  use the OpenAI adapter with different prefixes)
- The `app.py:266` guard (`if provider in llm_adapters: continue`) must be
  relaxed to allow multiple adapter instances per provider with different
  endpoints. This is the key blocker for Scenario C.

**Effort:** Config-only if providers have distinct prefixes (trivial).
Adapter deduplication fix if same prefix needs different endpoints (small,
~30 lines in app.py).

### Scenario C: Mac Mini Cluster

**Four Mac Minis, each with a dedicated model via llama.cpp/MLX:**
- Mini 1: Queen model (planning-optimized)
- Mini 2: Coder model (code-optimized)
- Mini 3: Reviewer model (adversarial)
- Mini 4: Researcher model (long context)

**What works today:**
- Per-caste model assignment exists via `model_assignments`, `tier_models`,
  or the routing table
- OpenAI-compatible adapter works with any llama.cpp/MLX server exposing
  the `/v1/chat/completions` endpoint
- `ModelRecord.endpoint` field (types.py line 195) supports per-model URL
- All four LLM calls can be in flight concurrently (asyncio + httpx)

**What breaks -- the critical blocker:**

`app.py:261-301` creates one adapter per provider prefix. If all four Minis
register as `llama-cpp/*`, only the first endpoint is used. The guard at
line 266 (`if model.provider in llm_adapters: continue`) skips subsequent
endpoints.

**Fix: Multi-endpoint adapter instantiation.** Two approaches:

**Option 1: Distinct provider prefixes (zero code change, config only)**

Register each Mini as a distinct provider:
```yaml
models:
  registry:
    - address: "mini1-queen/qwen3-30b-planning"
      endpoint: "http://192.168.1.101:8080/v1"
    - address: "mini2-coder/qwen3-coder-30b"
      endpoint: "http://192.168.1.102:8080/v1"
    - address: "mini3-reviewer/qwen3-30b-adversarial"
      endpoint: "http://192.168.1.103:8080/v1"
    - address: "mini4-researcher/qwen3-30b-longctx"
      endpoint: "http://192.168.1.104:8080/v1"
```

Then set the routing table:
```yaml
defaults:
  queen: "mini1-queen/qwen3-30b-planning"
  coder: "mini2-coder/qwen3-coder-30b"
  reviewer: "mini3-reviewer/qwen3-30b-adversarial"
  researcher: "mini4-researcher/qwen3-30b-longctx"
```

Each prefix gets its own adapter instance in `app.py`. The routing table
routes each caste to its Mini. All four LLM calls happen concurrently.

This works TODAY with zero code changes. The only requirement is that
`app.py`'s adapter factory recognizes each prefix as OpenAI-compatible.
Currently (lines 261-301), it checks specific prefixes: `llama-cpp`,
`ollama`, `openai`, `deepseek`. Unknown prefixes are skipped.

**Fix needed:** Generalize the adapter factory to treat any prefix with an
`endpoint` field as OpenAI-compatible if no dedicated adapter exists.
~15 lines in `app.py`.

**Option 2: Per-model adapter instances (more robust, ~50 lines)**

Change `app.py` to create one adapter per unique `(provider, endpoint)`
pair instead of per provider. This allows `llama-cpp/queen-model` at
`http://mini1:8080` and `llama-cpp/coder-model` at `http://mini2:8080`
to coexist.

**Recommended: Option 1 for immediate use, Option 2 as a follow-up.**

**Embedding server:** Keep shared. Run the embedding sidecar on one Mini
(or the FormicOS host) and point all agents at it. Embedding calls are
lightweight (~5ms per query) and infrequent compared to LLM calls. Network
latency between Minis (~0.5ms LAN) is negligible vs inference time
(~500ms-2s per completion).

**Network topology:**

```
[FormicOS Host] --- LAN switch --- [Mini 1: Queen]
                                   [Mini 2: Coder]
                                   [Mini 3: Reviewer]
                                   [Mini 4: Researcher]
                                   [Qdrant on Host or Mini]
                                   [Embedding sidecar on Host]
```

The FormicOS container runs on the host. Each Mini runs llama-cpp-server
(or MLX-server) exposing `/v1/chat/completions`. Qdrant and the embedding
sidecar stay on the host. All communication is HTTP over LAN.

**Per-Mini semaphore:** Each Mini's adapter instance should have its own
semaphore matching its slot count. With Option 1 (distinct prefixes), this
happens automatically -- each adapter gets `LLM_SLOTS` from env. To set
different slot counts per Mini, use per-prefix env vars or add a
`max_concurrent` field to `ModelRecord`.

**Effort:** Option 1 is trivial (config + ~15 lines in app.py). Option 2
is small (~50 lines in app.py). Everything else works today.

### Blocking Issues

Ordered by severity:

1. **Workspace file write races** (high severity, medium effort)
   `write_workspace_file` and `patch_file` have no locking. Concurrent
   agents writing the same file produce undefined results. Affects any
   multi-agent colony where agents might touch overlapping files.
   Files: `runner.py` (~100 lines for optimistic locking)

2. **Single adapter per provider prefix** (medium severity, small effort)
   `app.py:266` skips duplicate providers. Blocks Scenario C (Mac Mini
   cluster) when using same prefix for different endpoints.
   Files: `app.py` (~15-50 lines depending on approach)

3. **workspace_execute restore race** (medium severity, large effort)
   `_restore_workspace_from_archive()` is destructive and unprotected.
   Two concurrent `workspace_execute` calls on the same workspace will
   corrupt each other's results.
   Files: `sandbox_manager.py` (~300 lines for proper isolation)

4. **Non-deterministic event ordering** (low severity, no fix needed)
   Concurrent agents produce events in arbitrary order. Not harmful --
   sequence numbers are still monotonic, just non-deterministic between
   concurrent agents. Acceptable trade-off.

### Enabling Changes

Ordered by effort (smallest first):

| Change | Effort | Unlocks |
|--------|--------|---------|
| Generalize adapter factory for unknown prefixes | Trivial (~15 lines in app.py) | Mac Mini cluster with distinct prefixes |
| Increase `LLM_SLOTS` env var | Trivial (config) | More concurrent local inference slots |
| Per-model adapter instances | Small (~50 lines in app.py) | Same prefix, different endpoints |
| Optimistic locking for `patch_file` | Medium (~100 lines in runner.py) | Safe concurrent file edits |
| Per-agent workspace overlay | Large (~300 lines in sandbox_manager.py) | Full workspace isolation for parallel agents |
| `max_concurrent` field on ModelRecord | Small (~20 lines in types.py + app.py) | Per-Mini slot counts |

---

## Queen Intelligence

### Current Context Model

The Queen has no single context assembly function. Context is built across
two locations:

**`_build_messages()` (queen_runtime.py line 801)** -- base context:
1. System prompt from `caste_recipes.yaml` queen section (~120 lines)
2. Queen notes (thread-scoped persistent memory, lines 816-838)
3. Metacognitive nudges (memory_available, prior_failures, lines 841-851)
4. Conversation history (token-budgeted at 6000 tokens, lines 846-848)

**`respond()` (queen_runtime.py line 498)** -- dynamic injections:
5. Knowledge retrieval (up to 5 entries relevant to last message, lines 517-539)
6. Thread workflow context (goal, status, colony counts, step timeline, lines 541-552)
7. Proactive intelligence briefing (top insights across 7 categories, lines 554-621)

The Queen does NOT need to call tools to see colony status, knowledge state,
or budget -- these are injected automatically. However, the injected data is
summarized. For detailed inspection she uses tools (`inspect_colony`,
`query_outcomes`, `query_briefing`).

**Static vs dynamic split:** Only the system prompt (item 1) is truly static.
Everything else is computed fresh per `respond()` call.

### Session Memory

**Conversation history persists across turns** via `QueenMessage` events stored
in projections. Each operator message and Queen response is emitted as an event
(line 473) and replayed into the LLM context on the next call.

**Tool results do NOT persist across turns.** Within a single `respond()` call,
tool results accumulate in the `messages` list (lines 698-707) through up to 7
tool iterations (`_MAX_TOOL_ITERATIONS`, line 51). But only the final reply text
is emitted as a `QueenMessage` event (line 763). On the next operator message,
the Queen sees prior conversation text but not the tool outputs from previous
turns.

**Workaround:** The `queen_note` tool lets the Queen explicitly save persistent
notes. These are injected into every future turn (lines 816-838). This is
the only mechanism for the Queen to carry structured findings across turns.

**Compaction:** When thread history exceeds `_THREAD_TOKEN_BUDGET = 6000`
tokens (line 143), older messages are collapsed into a structured summary.
The 10 most recent messages are always kept raw (line 145). Pinned messages
(unresolved asks, active preview cards) survive compaction (lines 153-164).

### Colony Feedback Loop

Colony results are **pushed** to the Queen via `follow_up_colony()`
(queen_runtime.py line 334), called from `colony_manager._post_colony_hooks()`
(line 1101) -> `_hook_follow_up()` (line 1221) as a fire-and-forget asyncio
task.

The follow-up builds a quality-aware summary (lines 402-422), checks contract
satisfaction (lines 424-438), appends step continuation text if present
(lines 440-442), and emits a `QueenMessage` with `render="result_card"` and
structured metadata (lines 444-466).

**Gate conditions** (lines 349-366):
- Thread must exist
- Thread must have operator activity within last 30 minutes OR step continuation
- Colony must have succeeded (`colony_manager.py:1231`)

**Gap: Failed colonies do NOT trigger follow-up** (line 1231 checks
`succeeded=True`). The Queen learns about failures only if the operator asks.
This means stalled or failed colonies are invisible unless the operator
proactively checks.

**For parallel colonies** (spawned via `spawn_parallel`): Each colony
completes independently and triggers its own `follow_up_colony()` call. The
Queen sees them as sequential messages in the thread. There is no aggregated
"all 3 colonies completed" summary -- each arrives individually.

### Proactive Behavior

Proactive insights reach the Queen through two channels:

1. **Automatic injection** (lines 554-621): Top insights from
   `generate_briefing()` are computed fresh on every `respond()` call and
   injected as a system message. Categories: knowledge-health (top 3),
   performance (top 2), learning-loop (top 2), evaporation recommendations
   (up to 3), configuration recommendations (up to 4).

2. **On-demand via `query_briefing` tool** (queen_tools.py line 963):
   The Queen can call this for filtered, detailed briefing data with
   suggested colony configurations.

Proactive insights are NOT pushed asynchronously. They are computed
synchronously on each `respond()` call. The `MaintenanceDispatcher`
(`self_maintenance.py`) can auto-dispatch colonies based on insights, but
does not notify the Queen directly about what it dispatched.

**The Queen cannot initiate conversation.** She only responds when the
operator sends a message. Colony follow-up messages appear in the thread
but require the operator to open the conversation to see them.

### Cloud Routing Seams

**Current mechanism:** `_resolve_queen_model()` (line 775) delegates to
`resolve_model("queen", workspace_id)` (runtime.py line 862). The cascade:
workspace config `queen_model` -> system defaults -> fallback to coder default.

**Planning-specific routing** (lines 625-636, Wave 62 addition): If workspace
has `queen_planning_model` configured AND the last assistant message contained
a `propose_plan` tool call, the model switches to the planning model. This
routes the Queen's follow-up reasoning after a plan proposal to cloud.

**Upgrade path for broader cloud routing:**

The seam is at `respond()` line 627, between model resolution and the LLM
call at line 628. Any heuristic can be inserted here:

```python
queen_model = self._resolve_queen_model(workspace_id)
# Heuristic routing examples:
# - Message length > N tokens -> cloud
# - Operator explicitly tagged @cloud -> cloud
# - propose_plan in recent tool calls -> cloud (already implemented)
# - Complex multi-step thread with >5 colonies -> cloud
```

The architecture supports this cleanly because model resolution happens once
per `respond()` call (line 510) and the result is passed to all subsequent
LLM calls in the tool loop. Changing the model at line 510 routes the
entire conversation turn to a different provider.

### Upgrade Path

Ordered by impact and effort:

| # | Change | Effort | Impact |
|---|--------|--------|--------|
| 1 | Persist tool results in QueenMessage events | Small (~40 lines in queen_runtime.py) | Queen retains tool findings across turns -- biggest intelligence gap |
| 2 | Push failed colony notifications | Small (~20 lines in colony_manager.py) | Queen learns about failures without operator asking |
| 3 | Aggregate parallel colony summaries | Medium (~80 lines in queen_runtime.py) | "All 3 colonies completed: 2 succeeded, 1 failed" instead of 3 separate messages |
| 4 | Heuristic cloud routing for Queen | Small (~30 lines in queen_runtime.py) | Route complex planning turns to cloud, keep simple turns local |
| 5 | Structured Queen working memory | Medium (~150 lines) | Replace queen_note plaintext with typed key-value store |
| 6 | Asynchronous proactive notifications | Medium (~100 lines) | Queen can initiate "Colony X just finished" without waiting for operator message |
| 7 | Cross-turn tool result compaction | Medium (~100 lines) | Instead of persisting all tool results, persist a compacted summary |

---

## Summary Table

| Capability | Status | Effort to ship | Depends on |
|------------|--------|---------------|------------|
| Parallel agents within round (stigmergic) | **Works today** | None | Stigmergic strategy selection |
| Concurrent LLM calls to same provider | **Works today** | None | LLM_SLOTS env var >= 2 |
| Concurrent LLM calls to different providers | **Works today** | None | Per-caste routing table |
| Per-caste model assignment | **Works today** | None | model_assignments or routing table |
| Mac Mini cluster (distinct prefixes) | **Partially built** | Trivial (~15 lines) | Generalize adapter factory |
| Mac Mini cluster (same prefix, different endpoints) | Not built | Small (~50 lines) | Per-model adapter instances |
| Safe concurrent file writes | Not built | Medium (~100 lines) | Optimistic locking in runner.py |
| Workspace isolation for parallel agents | Not built | Large (~300 lines) | Per-agent overlay in sandbox_manager.py |
| Per-Mini concurrent slot limits | Not built | Small (~20 lines) | max_concurrent on ModelRecord |
| Queen cross-turn tool memory | Not built | Small (~40 lines) | Persist tool results in events |
| Queen failure notifications | Not built | Small (~20 lines) | Remove succeeded gate in colony_manager |
| Queen parallel colony aggregation | Not built | Medium (~80 lines) | Batch follow_up messages |
| Queen heuristic cloud routing | Partially built | Small (~30 lines) | Expand propose_plan routing |
| Queen structured working memory | Not built | Medium (~150 lines) | New projection or note schema |
| Queen proactive push notifications | Not built | Medium (~100 lines) | Async message injection |
| Non-deterministic event ordering | Accepted | None (by design) | -- |
