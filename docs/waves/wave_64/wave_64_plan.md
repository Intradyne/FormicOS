# Wave 64 -- The Parallel Queen, The Extensible OS

**Goal:** Make FormicOS a genuine development OS. Unlock safe multi-provider
parallel execution. Ship the addon loader and three real addons that prove
the OS metaphor. After Wave 64, the operator's daily workflow -- status
check, codebase question, architecture discussion, quick fix, full feature
build, code review, commit -- happens entirely inside FormicOS.

**Event union:** 66 -> 69. Three new events:
- `AddonLoaded` -- addon manifest parsed and registered (tracks installed
  addons for replay, enables "addon list" UI)
- `AddonUnloaded` -- addon deregistered (for hot-reload or removal)
- `ServiceTriggerFired` -- a cron/event/webhook trigger activated a service
  colony (audit trail for automated dispatches)

Requires ADR-050 (operator approval obtained). Justification: addon
lifecycle and trigger dispatch are new operational categories with no
existing event that carries these semantics.
ColonyServiceActivated (event #33) records service QUERY activation, not
cron-triggered service colony dispatch. These are fundamentally different:
one is a research delegation, the other is a scheduled daemon activation.

**Tests target:** +35 new tests minimum across all tracks.

**Pre-requisite:** Wave 63 complete (30 Queen tools, 66 events, operator
knowledge/workflow editing, project context, cross-turn tool memory).

---

## Track 1 -- Generalize Adapter Factory + Per-Provider Concurrency

**Problem:** `app.py:265-267` skips duplicate provider prefixes:
`if model.provider in llm_adapters: continue`. This means two models with
the same prefix (e.g., `llama-cpp/queen-model` and `llama-cpp/coder-model`)
cannot route to different endpoints. This blocks multi-machine setups (Mac
Mini cluster, split GPU servers) and forces awkward prefix gymnastics.

Additionally, `ModelRecord` has no `max_concurrent` field, so all providers
share the same `LLM_SLOTS` env var. A beefy cloud endpoint and a single-GPU
local server get the same concurrency limit.

**Current state:**
- `app.py:264`: `llm_adapters: dict[str, LLMPort] = {}`
- `app.py:265-267`: Provider dedup guard
- `app.py:268-301`: Provider dispatch (anthropic, gemini, OpenAI-compatible)
- `ModelRecord.endpoint` field exists (types.py:195) but only the FIRST
  endpoint per prefix is used
- `LLM_SLOTS` env var (default 2) controls OpenAI adapter semaphore
- Semaphore in llm_openai_compatible.py:133-136

**Design:**

A. **Per-endpoint adapter instances.** Change the adapter factory key from
   `provider` to `(provider, endpoint)`. When two models share a provider
   prefix but have different endpoints, each gets its own adapter instance.

   ```python
   # app.py adapter factory (revised)
   adapter_key = f"{model.provider}:{model.endpoint or 'default'}"
   if adapter_key in llm_adapters:
       continue
   ```

   The `LLMRouter` must also be updated to resolve the correct adapter
   instance. Currently `_resolve()` (runtime.py:411) splits on `/` to get
   the provider prefix. Change to look up by `(provider, endpoint)` pair,
   falling back to provider-only for backward compatibility.

B. **Unknown prefix fallback.** When a model has a provider prefix not in
   the known set (anthropic, gemini, llama-cpp, ollama, openai, deepseek),
   AND has an `endpoint` field, create an OpenAI-compatible adapter for it.
   This enables `mini1-queen/qwen3-30b` at `http://192.168.1.101:8080/v1`
   without code changes.

   ```python
   # After known provider checks:
   if model.endpoint:
       # Unknown prefix with explicit endpoint -> OpenAI-compatible
       llm_adapters[adapter_key] = OpenAICompatibleAdapter(
           base_url=model.endpoint, ...
       )
   ```

C. **`max_concurrent` on ModelRecord.** Add optional field to types.py:

   ```python
   max_concurrent: int = Field(default=0, description="Max concurrent requests. 0 = use LLM_SLOTS env var.")
   ```

   When creating an adapter, pass `max_concurrent` (or fall back to
   LLM_SLOTS). The OpenAI adapter's semaphore uses this value.

D. **Per-adapter semaphore.** Each adapter instance already has its own
   semaphore. With per-endpoint instances (Design A), each endpoint
   automatically gets independent concurrency control. If `max_concurrent`
   is set on the model, use that for the semaphore size.

**Code delta:** ~40 lines in app.py (adapter factory), ~20 lines in
runtime.py (router resolution), ~10 lines in types.py (max_concurrent),
~15 lines in llm_openai_compatible.py (semaphore from max_concurrent).

**New tests (4):**
1. `test_same_prefix_different_endpoints` -- two llama-cpp models with
   different endpoints get separate adapter instances
2. `test_unknown_prefix_with_endpoint` -- unknown prefix creates
   OpenAI-compatible adapter
3. `test_max_concurrent_overrides_slots` -- model.max_concurrent controls
   semaphore size
4. `test_backward_compat_single_prefix` -- existing single-prefix configs
   work unchanged

**Owned files:**
- `src/formicos/surface/app.py` -- adapter factory
- `src/formicos/surface/runtime.py` -- router resolution
- `src/formicos/core/types.py` -- max_concurrent field
- `src/formicos/adapters/llm_openai_compatible.py` -- semaphore config
- `tests/unit/surface/test_app.py` -- new tests

**Do not touch:** `engine/runner.py`, `core/events.py`

**Validation:**
```bash
pytest tests/unit/surface/test_app.py tests/unit/core/test_settings.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 2 -- Optimistic File Locking for Parallel Agents

**Problem:** `write_workspace_file` (runner.py:1991-2005) and `patch_file`
(runner.py:2012+) have no locking. Concurrent agents in the same execution
group writing to the same file produce undefined results. `patch_file`'s
read-modify-write pattern is the highest-risk path: agent A reads file,
agent B reads same file, both modify, both write -- one agent's changes
are silently lost.

**Current state:**
- `write_workspace_file` at runner.py:1991-2005: bare `write_text()`
- `_handle_patch_file()` at runner.py:2012+: read -> match old_text ->
  replace -> write_text
- `PRODUCTIVE_TOOLS` at runner.py:82-84 includes both
- No locks anywhere in runner.py
- asyncio.TaskGroup at runner.py:1047 runs agents concurrently within groups
- All agents share the same workspace path

**Design:**

A. **Content-hash optimistic locking for patch_file.** Before reading the
   file for patching, compute a hash of the current content. After
   constructing the new content, re-read and re-hash. If the hash changed
   between read and write, the patch fails with a retryable error:

   ```python
   async def _handle_patch_file(self, ...):
       content = path.read_text(encoding="utf-8")
       content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
       # ... apply patch ...
       # Before write:
       current = path.read_text(encoding="utf-8")
       if hashlib.sha256(current.encode()).hexdigest()[:16] != content_hash:
           return "CONFLICT: file was modified by another agent. Retry with current content."
       path.write_text(new_content, encoding="utf-8")
   ```

   The agent sees the CONFLICT error and can retry (the LLM will re-read
   the file and produce a new patch). This is safe under asyncio because
   the hash check + write is not interrupted by other coroutines (no await
   between check and write).

B. **Atomic write for write_workspace_file.** Write to a temp file, then
   rename. This prevents partial writes from being visible to concurrent
   readers:

   ```python
   tmp = path.with_suffix(path.suffix + ".tmp")
   tmp.write_text(content, encoding="utf-8")
   tmp.rename(path)  # atomic on POSIX, near-atomic on Windows
   ```

C. **Per-file write lock (optional enhancement).** If optimistic locking
   proves insufficient, add a `dict[Path, asyncio.Lock]` in RoundRunner
   that serializes writes to the same file. This is the nuclear option --
   it guarantees correctness but may slow parallel agents. Implement only
   if testing reveals the optimistic approach fails in practice.

**Code delta:** ~60 lines in runner.py (hash check in patch_file, atomic
write in write_workspace_file), ~10 lines for imports (hashlib).

**New tests (4):**
1. `test_patch_file_detects_conflict` -- concurrent modification returns
   CONFLICT error
2. `test_patch_file_succeeds_when_unchanged` -- normal patch works
3. `test_write_file_atomic` -- temp + rename pattern
4. `test_concurrent_patch_one_wins` -- integration test with two agents

**Owned files:**
- `src/formicos/engine/runner.py` -- patch_file and write_workspace_file
- `tests/unit/engine/test_runner.py` -- new tests

**Do not touch:** `surface/` layer, `core/events.py`

**Validation:**
```bash
pytest tests/unit/engine/test_runner.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 3 -- Queen Smart Fan-Out

**Problem:** `spawn_parallel` takes an explicit colony list but the Queen
has no intelligence about HOW to fan out. She doesn't know which providers
are available, what they cost, or which are fast. She can't re-dispatch a
failed colony to a different provider. After Wave 63 (failure notifications),
the Queen knows about failures -- but she can't act on them intelligently.

**Current state:**
- `spawn_parallel` in queen_tools.py creates DelegationPlan DAGs
- `propose_plan` (Wave 61) shows estimated cost per option
- `system_health` tool exposes model registry and provider status
- `outcome_stats()` (Wave 62) provides per-strategy success rates
- Per-caste model routing exists in runtime.py:908-910
- No tool for re-dispatching a failed colony

**Design:**

A. **Provider-aware planning.** Enhance `propose_plan` handler to include
   provider recommendations. When building plan options, query the model
   registry to show available providers per caste and their estimated
   costs:

   ```python
   # In _propose_plan():
   available_providers = self._runtime.get_available_providers()
   for option in options:
       option["provider_plan"] = {
           "coder": "llama-cpp/qwen3-30b ($0.00/turn, ~2s latency)",
           "reviewer": "openai/gpt-4o ($0.008/turn, ~1s latency)",
       }
   ```

   Include cost comparison: "Local-only: $0.00, ~4min. Hybrid: $0.12, ~90s."

B. **`retry_colony` Queen tool (convenience sugar).** The Queen can
   already spawn a new colony with the same task manually, and
   `redirect_colony` / `escalate_colony` handle live colonies. But for
   FAILED colonies, there's no single-action retry that copies the
   original task, adds failure context, and optionally switches provider.
   This tool is convenience sugar that makes retry-on-failure a one-step
   operation:

   ```python
   {
     "name": "retry_colony",
     "description": "Retry a failed colony with different settings.",
     "parameters": {
       "colony_id": "string -- the failed colony to retry",
       "model_override": "string -- optional model address for the retry",
       "strategy_override": "string -- optional strategy (sequential/stigmergic)",
       "additional_context": "string -- extra guidance based on failure analysis"
     }
   }
   ```

   Handler: reads the original colony's task and config from projections,
   spawns a new colony with the same task but overridden settings. Emits
   standard ColonySpawned event. The new colony's context includes a
   "Previous attempt failed: {reason}. {additional_context}" prefix.

   **Important:** The retried colony must NOT re-register into the original
   parallel plan's DelegationPlan DAG. It is a standalone colony — the
   original plan's group tracking remains unchanged (the failed colony
   stays marked as failed in the plan). This avoids corrupting plan
   completion logic in `_check_plan_completion()`.

C. **Cost-aware auto-escalation.** Extend the Wave 62 stall-based
   escalation (colony_manager.py:1042) to include a model suggestion:

   ```
   Escalation: Colony {id} stalled after 3 rounds with 0 productive calls.
   Suggestion: retry with openai/gpt-4o (estimated $0.08, vs $0.00 local).
   ```

   The Queen sees this in the follow-up notification (Track 2 of Wave 63)
   and can use `retry_colony` to act on it.

**Code delta:** ~80 lines in queen_tools.py (retry_colony handler +
provider plan in propose_plan), ~30 lines in colony_manager.py (model
suggestion in escalation).

**New tests (4):**
1. `test_propose_plan_includes_providers` -- plan options have provider_plan
2. `test_retry_colony_spawns_new` -- retry creates new colony with task
3. `test_retry_colony_includes_failure_context` -- previous failure in context
4. `test_escalation_suggests_model` -- stall escalation includes model hint

**Owned files:**
- `src/formicos/surface/queen_tools.py` -- retry_colony + provider plan
- `src/formicos/surface/colony_manager.py` -- escalation model suggestion
- `tests/unit/surface/test_queen_tools.py` -- new tests

**Do not touch:** `engine/runner.py`, `core/events.py`

**Validation:**
```bash
pytest tests/unit/surface/test_queen_tools.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 4 -- Heuristic Cloud Routing Expansion

**Problem:** Wave 62 added cloud routing only for `propose_plan` follow-ups
(queen_runtime.py:901). Complex multi-step threads, long operator
messages, and explicit `@cloud` tags don't trigger cloud routing. The
Queen's local model (Qwen3-30B) handles everything else, including
architecture discussions where a frontier model would perform dramatically
better.

**Current state:**
- `_resolve_queen_model()` at queen_runtime.py:1070 delegates to
  `resolve_model("queen", workspace_id)`
- Cloud routing check at line 901: only fires when last assistant
  turn called `propose_plan`
- Workspace config `queen_planning_model` controls the cloud model
- No heuristic beyond the propose_plan check

**Design:**

A. **Message complexity heuristic.** Before the LLM call in `respond()`,
   estimate message complexity:

   ```python
   _last_msg = messages[-1]["content"] if messages else ""
   _thread_depth = len([m for m in messages if m["role"] == "user"])
   _msg_tokens = len(_last_msg) // 4  # rough estimate

   use_cloud = False
   # Long messages suggest complex requests
   if _msg_tokens > 500:
       use_cloud = True
   # Deep threads with many colonies suggest complex orchestration
   if _thread_depth > 10 and total_colonies > 3:
       use_cloud = True
   # Existing propose_plan check (Wave 62)
   if _last_assistant_called_propose_plan:
       use_cloud = True
   ```

B. **Explicit `@cloud` tag.** If the operator's message contains `@cloud`
   anywhere, route to the planning model regardless of heuristics. Strip
   `@cloud` from the message before sending to the LLM.

C. **Auto-escalation on parse failure.** If the local model produces a
   response that fails intent parsing AND has no tool calls AND the
   response is very short (< 50 chars), AND the operator's message was
   complex (> 200 chars or contained technical keywords like function
   names, file paths, or code blocks), retry with the cloud model. This
   catches cases where the local model is confused by complex requests.
   The message complexity guard prevents escalation on valid short
   responses to simple messages ("Sure, I'll look into that.").
   Cap at 1 retry per turn.

D. **Routing indicator in QueenMessage.** Add `model_used` to the
   QueenMessage meta so the UI can show a subtle indicator:
   "[via gemini-2.5-pro]" badge on cloud-routed responses.

E. **Awareness of context assembly.** The routing heuristic runs inside
   `respond()`, which calls `_build_messages()` (queen_runtime.py:1096).
   `_build_messages()` injects project context at position 2.7
   (queen_runtime.py:799) and cross-turn tool memory at lines 1137-1167.
   Cloud routing must account for these injected tokens when estimating
   message complexity — the operator's raw message length understates the
   actual prompt size seen by the model. If the assembled system message
   (including project context + tool memory) exceeds ~2000 tokens, that
   is itself a complexity signal favoring cloud routing.

**Code delta:** ~50 lines in queen_runtime.py (heuristics + @cloud +
retry), ~10 lines in queen-chat.ts (model badge).

**New tests (4):**
1. `test_cloud_routing_long_message` -- 500+ token message routes to cloud
2. `test_cloud_routing_at_cloud_tag` -- @cloud forces cloud routing
3. `test_cloud_routing_parse_failure_retry` -- failed parse retries on cloud
4. `test_model_used_in_meta` -- QueenMessage meta contains model_used

**Owned files:**
- `src/formicos/surface/queen_runtime.py` -- routing heuristics
- `frontend/src/components/queen-chat.ts` -- model badge
- `tests/unit/surface/test_queen_runtime.py` -- new tests

**Do not touch:** `core/events.py`, `engine/runner.py`

**Validation:**
```bash
pytest tests/unit/surface/test_queen_runtime.py -q
```

---

## Track 5 -- UI: Parallel Execution Dashboard

**Problem:** The frontend doesn't surface multi-provider parallel execution.
Colony cards don't show which provider is running. There's no cost breakdown
by provider. Parallel colony groups aren't visualized. The operator can't
see the full picture.

**Current state (queen-overview.ts, 625 lines):**
- Dashboard header at lines 159-183: active count, tokens, cost, knowledge
- Budget panel at line 198: `<fc-budget-panel>` (Wave 61)
- Health grid at lines 209-213

**Current state (colony-detail.ts, 1253 lines):**
- Agent table at lines 537-561: already shows model per agent with colored
  provider dot (lines 550-553)
- No provider-level aggregation

**Design:**

A. **Provider cost breakdown in budget panel.** Enhance `fc-budget-panel`
   to show per-provider cost:

   ```
   Total: $0.31         Local: $0.00  |  OpenAI: $0.23  |  Gemini: $0.08
   ```

   Data source: the existing budget truth in projections already tracks
   per-model costs. Aggregate by provider prefix.

B. **Parallel group visualization.** When `spawn_parallel` creates colonies,
   the queen-overview colony list should group them visually:

   - Parallel group header bar: "Parallel Plan: 3 colonies"
   - Colonies within group shown side-by-side (or in a bordered group)
   - Live status per colony: spinner (running), green check (succeeded),
     red X (failed)
   - Group-level summary: "2/3 complete, $0.15 spent"

   Data source: ParallelPlanCreated event links colonies to plans.
   Projections already store this. Frontend queries the thread timeline
   or colony list with plan_id grouping.

C. **Provider health indicators.** Add a small provider status row to
   the dashboard or settings view:

   ```
   llama-cpp: 2 slots, 1.2s avg  |  openai: healthy, 0.8s avg  |  gemini: healthy, 1.1s avg
   ```

   Data source: LLM adapters already track cooldown timestamps and error
   counts. Expose via a new `GET /api/v1/system/providers` endpoint that
   returns per-provider latency, error rate, and slot utilization.

D. **Colony card provider badge.** On each colony card in the overview,
   show a small badge: "local" / "openai" / "gemini" / "mixed" based on
   the colony's model assignments. Already partially implemented in
   colony-detail.ts (agent table) -- extend to the overview card.

**Code delta:** ~100 lines in budget-panel.ts (provider breakdown), ~150
lines in queen-overview.ts (parallel groups + provider badges), ~50 lines
in routes/api.py (provider health endpoint), ~30 lines in queen-chat.ts
(provider badge on colony cards).

**New tests (2):**
1. `test_provider_health_endpoint` -- returns provider status
2. `test_budget_by_provider` -- budget response includes per-provider split

**Owned files:**
- `frontend/src/components/budget-panel.ts` -- provider breakdown
- `frontend/src/components/queen-overview.ts` -- parallel groups
- `frontend/src/components/queen-chat.ts` -- provider badges
- `src/formicos/surface/routes/api.py` -- provider health endpoint
- `tests/integration/test_api.py` -- new tests

**Do not touch:** `core/events.py`, `engine/runner.py`

**Validation:**
```bash
pytest tests/integration/test_api.py -q
# Visual verification: docker compose up, check dashboard
```

---

## Track 6a -- Addon Loader (Core Infrastructure)

**Problem:** FormicOS has no runtime addon system. The manifest schema
exists (addons/README.md, Wave 62) and the registries are dict-based
(queen_tools.py, formicos-app.ts, Wave 62), but nothing reads manifests
or registers components at startup.

**Scope note:** This track builds ONLY the loader + a trivial test addon.
The risky proactive intelligence extraction is Track 6b (separate,
sequential). Tracks 7 and 8 can proceed once 6a lands, without waiting
for the extraction.

**Current state:**
- `addons/README.md` documents the manifest schema (Wave 62 Phase 0)
- `queen_tools.py` uses dict-based handler registry (Wave 62)
- `formicos-app.ts` uses component registry (Wave 62)
- No addon loader exists
- Service handler registration in app.py:583-616

**Design:**

A. **Manifest parser.** New module `src/formicos/surface/addon_loader.py`
   (~200 lines). Reads `addons/*/addon.yaml` files. Validates required
   fields. Returns a list of `AddonManifest` dataclasses.

B. **Registration hooks.** The loader registers addon components into
   existing registries:

   - **Tools**: registered into `queen_tools.py`'s `_handlers` dict.
     The manifest specifies handler path (`module.py::function_name`),
     the loader imports and wraps it.
   - **Event handlers**: registered via `service_router.register_handler()`.
     Same path as existing deterministic services in app.py:583-637.
   - **Colony templates**: added to the template registry.
   - **Routes**: mounted on the Starlette app as sub-routes.
   - **Panels**: registered in a frontend panel registry (metadata only --
     actual component loading is a frontend concern).

C. **Addon Python code location (Option A for v1).**

   `addons/` is at repo root, outside the Python package
   (`pyproject.toml:49` has `packages = ["src/formicos"]`). For v1, move
   addon Python code to `src/formicos/addons/{addon_name}/` so it's inside
   the package and importable normally. Keep `addons/*/addon.yaml` manifests
   at repo root for discoverability. The loader reads the manifest from
   `addons/{name}/addon.yaml` but resolves handler paths relative to
   `src/formicos/addons/`.

   When third-party addons are needed (future wave), migrate to Option C
   (`importlib.import_module()` with dynamic path resolution).

D. **Lifecycle events.** On startup, after loading each addon:

   ```python
   await event_store.append(AddonLoaded(
       addon_name="hello-world",
       version="1.0.0",
       tools=["hello"],
       handlers=[],
   ))
   ```

   On unload (shutdown or removal):
   ```python
   await event_store.append(AddonUnloaded(addon_name="hello-world"))
   ```

E. **Startup integration.** In `app.py` lifespan, after event replay and
   before service handler registration:

   ```python
   addons = load_addons(Path("addons"))
   for addon in addons:
       register_addon(addon, queen_tools, service_router, app)
       await event_store.append(AddonLoaded(...))
   ```

F. **Trivial test addon.** Create `addons/hello-world/addon.yaml` with a
   single tool `hello` that returns "Hello from addon system!" This
   validates the full loader pipeline without risking real functionality.

**New events (2 of 3 for this wave):**

```python
class AddonLoaded(BaseModel):
    """An addon manifest was loaded and its components registered."""
    addon_name: str
    version: str = ""
    tools: list[str] = Field(default_factory=list)
    handlers: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)

class AddonUnloaded(BaseModel):
    """An addon was deregistered."""
    addon_name: str
    reason: str = ""  # "shutdown" | "removed" | "error"
```

**Code delta:** ~200 lines addon_loader.py, ~20 lines hello-world addon,
~30 lines app.py integration, ~30 lines events.py (2 events + union update).

**New tests (4):**
1. `test_addon_loader_parses_manifest` -- valid manifest returns AddonManifest
2. `test_addon_loader_registers_tool` -- tool appears in queen_tools._handlers
3. `test_addon_loader_registers_handler` -- handler in service_router
4. `test_addon_loaded_event_emitted` -- AddonLoaded in event store

**Owned files:**
- `src/formicos/surface/addon_loader.py` (NEW)
- `src/formicos/core/events.py` -- 2 new events (#67, #68)
- `src/formicos/surface/app.py` -- addon loading in lifespan
- `addons/hello-world/` (NEW trivial test addon)
- `src/formicos/addons/__init__.py` (NEW package init)
- `src/formicos/addons/hello_world/` (NEW Python code for test addon)
- `tests/unit/surface/test_addon_loader.py` (NEW)

**Do not touch:** `engine/runner.py`, `core/types.py`, `queen_runtime.py`,
`proactive_intelligence.py`

**Validation:**
```bash
pytest tests/unit/surface/test_addon_loader.py -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 6b -- Proactive Intelligence Extraction

**DEPENDS ON Track 6a** (needs the addon loader).

**Problem:** proactive_intelligence.py is 1980 lines. self_maintenance.py
is 464 lines. Both are fully self-contained -- they read projections,
produce insights, dispatch maintenance. They touch the kernel only through
the event bus. This is the ideal first real extraction to validate the
addon architecture.

**Current state:**
- `proactive_intelligence.py`: 17 rules, 1980 lines, imports only from core
- `self_maintenance.py`: 464 lines, MaintenanceDispatcher class
- Addon loader from Track 6a is functional

**Design:**

A. **Move rule implementations.** Create addon structure:

   Manifest at `addons/proactive-intelligence/addon.yaml`.
   Python code at `src/formicos/addons/proactive_intelligence/`:

   ```
   src/formicos/addons/proactive_intelligence/
     __init__.py
     rules/
       __init__.py
       knowledge_health.py    # 7 rules (~700 lines)
       performance.py         # 4 rules (~400 lines)
       system_health.py       # 6 rules (~800 lines)
     dispatch.py              # MaintenanceDispatcher (~464 lines)
   ```

B. **Manifest:**

   ```yaml
   name: proactive-intelligence
   version: "1.0.0"
   description: "17 deterministic briefing rules + maintenance dispatch"
   author: "formicos-core"

   tools:
     - name: query_briefing
       description: "Query proactive intelligence briefing for a workspace"
       handler: rules/__init__.py::handle_query_briefing
       parameters:
         type: object
         properties:
           workspace_id: { type: string }
           categories: { type: array, items: { type: string } }

   handlers:
     - event: ColonyCompleted
       handler: dispatch.py::on_colony_completed
     - event: MemoryConfidenceUpdated
       handler: dispatch.py::on_confidence_updated
   ```

C. **Shim in surface layer.** `proactive_intelligence.py` becomes a thin
   shim (~50 lines) that imports from the addon package and re-exports the
   `generate_briefing()` function. This preserves backward compatibility
   for existing callers (queen_runtime.py:835 calls `generate_briefing()`
   directly). The shim is transitional -- once all callers go through the
   addon registry, the shim is deleted.

   ```python
   # proactive_intelligence.py (post-extraction shim)
   """Shim -- delegates to formicos.addons.proactive_intelligence."""
   from formicos.addons.proactive_intelligence.rules import generate_briefing
   from formicos.addons.proactive_intelligence.rules import KnowledgeInsight, SuggestedColony
   __all__ = ["generate_briefing", "KnowledgeInsight", "SuggestedColony"]
   ```

**Code delta:** ~100 lines addon.yaml + restructured rules (mostly moved,
not new), ~50 lines proactive_intelligence.py shim, ~20 lines
self_maintenance.py import updates.

**Success criterion:** `proactive_intelligence.py` shrinks from 1980 to
~50 lines. The 17 proactive rules still fire. `generate_briefing()` returns
identical results. All existing tests pass. `self_maintenance.py` either
stays in surface (calling into the addon) or moves entirely into the addon.

**New tests (1):**
1. `test_proactive_addon_generates_briefing` -- extracted rules produce
   same output as pre-extraction

**Owned files:**
- `addons/proactive-intelligence/addon.yaml` (NEW manifest)
- `src/formicos/addons/proactive_intelligence/` (NEW Python code)
- `src/formicos/surface/proactive_intelligence.py` -- shim
- `src/formicos/surface/self_maintenance.py` -- updated imports

**Do not touch:** `engine/runner.py`, `core/types.py`, `queen_runtime.py`
(it still calls `generate_briefing()` via the shim -- no change needed),
`addon_loader.py` (Track 6a, already merged)

**Validation:**
```bash
pytest tests/unit/surface/test_proactive_intelligence.py -q  # existing tests still pass
pytest tests/unit/surface/test_addon_loader.py -q  # loader still works
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 7 -- Codebase Semantic Index Addon

**Problem:** `search_codebase` (Wave 62) does grep. It finds exact text
matches. It cannot find "all functions that handle authentication" or
"where is error handling implemented" -- these require semantic search
over code. The codebase needs a persistent semantic index.

**Current state:**
- `search_codebase` in queen_tools.py: grep + pathlib fallback
- Qdrant instance running for knowledge entries
- Embedding sidecar (Qwen3-Embedding-0.6B) running
- No code-specific collection in Qdrant
- `ColonyServiceActivated` event exists for service queries

**Design -- Service Colony Infrastructure:**

A. **ServiceTriggerFired event** (event #69):

   ```python
   class ServiceTriggerFired(BaseModel):
       """A scheduled trigger activated a service colony."""
       addon_name: str
       trigger_type: str = ""  # "cron" | "event" | "webhook" | "manual"
       workspace_id: str = ""
       details: str = ""
   ```

B. **Cron trigger dispatcher.** Add to addon_loader.py or a new
   `trigger_dispatch.py` module (~100 lines):

   ```python
   class TriggerDispatcher:
       """Evaluates addon triggers on a schedule."""
       async def evaluate_cron_triggers(self) -> list[str]:
           """Check all addon cron triggers. Returns list of fired trigger names."""
           now = datetime.utcnow()
           for addon in self._addons:
               for trigger in addon.triggers:
                   if trigger.type == "cron" and trigger.is_due(now):
                       await self._fire_trigger(addon, trigger)
   ```

   Cron parsing: use a simple minute/hour/day matcher (no external dep).
   Or parse crontab format with a ~30-line parser. Don't add croniter
   as a dependency.

C. **Service colony lifecycle.** Service colonies differ from task colonies:
   - They run repeatedly (triggered, not one-shot)
   - They have persistent state between activations (checkpoint)
   - They restart on failure

   For v1, keep it simple: each trigger activation spawns a new colony
   with the service addon's task. State between activations is passed
   via a checkpoint file in the workspace (`.formicos/service_state/
   {addon_name}.json`). No daemon mode -- each activation is a fresh
   colony that reads the checkpoint, does work, writes updated checkpoint.

**Design -- Codebase Index Addon:**

D. **Addon manifest:**

   ```yaml
   name: codebase-index
   version: "1.0.0"
   description: "Semantic code search via embedding index"
   author: "formicos-core"

   tools:
     - name: semantic_search_code
       description: "Search codebase by meaning, not just text"
       handler: search.py::handle_semantic_search
       parameters:
         type: object
         properties:
           query: { type: string }
           top_k: { type: integer, default: 10 }
           file_pattern: { type: string }

   triggers:
     - type: cron
       schedule: "0 3 * * *"  # daily at 3am
       handler: indexer.py::full_reindex
     - type: manual
       handler: indexer.py::incremental_reindex
   ```

E. **Indexer implementation** (~200 lines):

   **Collection creation:** The indexer uses `create-if-not-exists` on
   first run. The Qdrant adapter's `ensure_collection()` method (used by
   the knowledge system at startup) is reused here with a different
   collection name (`code_index`). The indexer calls
   `vector_port.ensure_collection("code_index", vector_size=...)` before
   the first upsert. This is idempotent -- subsequent runs are no-ops.

   ```python
   async def full_reindex(workspace_path: Path, embed_fn, vector_port):
       """Walk workspace, chunk files, embed, upsert to Qdrant."""
       collection = "code_index"
       await vector_port.ensure_collection(collection, vector_size=1024)
       for path in workspace_path.rglob("*"):
           if _is_code_file(path):
               content = path.read_text(encoding="utf-8", errors="ignore")
               chunks = _chunk_code(content, path, chunk_size=500)
               for chunk in chunks:
                   embedding = await embed_fn(chunk.text)
                   await vector_port.upsert(
                       collection=collection,
                       id=chunk.id,
                       vector=embedding,
                       payload={"path": str(path), "line_start": chunk.line_start,
                                "content": chunk.text},
                   )
   ```

   Chunking strategy: split on function/class boundaries where detectable
   (simple regex for def/class in Python, function/class in JS/TS),
   fall back to 500-char sliding window with 100-char overlap.

F. **Search handler** (~50 lines):

   ```python
   async def handle_semantic_search(inputs, workspace_id, thread_id):
       query_embedding = await embed_fn(inputs["query"])
       results = await vector_port.search(
           collection="code_index",
           query_vector=query_embedding,
           limit=inputs.get("top_k", 10),
       )
       return format_search_results(results)
   ```

**Code delta:** ~100 lines trigger infrastructure, ~200 lines indexer,
~50 lines search handler, ~30 lines addon.yaml + init. Total ~380 lines
across the addon.

**New tests (4):**
1. `test_cron_trigger_fires` -- TriggerDispatcher fires due trigger
2. `test_semantic_search_returns_results` -- search handler formats output
3. `test_code_chunking` -- chunker splits on function boundaries
4. `test_incremental_reindex` -- only changed files are re-embedded

**Owned files:**
- `src/formicos/surface/trigger_dispatch.py` (NEW, ~100 lines)
- `src/formicos/core/events.py` -- ServiceTriggerFired event (#69)
- `addons/codebase-index/` (NEW directory)
- `tests/unit/surface/test_trigger_dispatch.py` (NEW)
- `tests/unit/addons/test_codebase_index.py` (NEW)

**Do not touch:** `engine/runner.py`, `queen_tools.py` (tool registered
via addon loader, not hardcoded)

**Validation:**
```bash
pytest tests/unit/surface/test_trigger_dispatch.py tests/unit/addons/ -q
ruff check src/ && python scripts/lint_imports.py
```

---

## Track 8 -- Git Control Center Addon

**Problem:** The operator commits, branches, and analyzes git state outside
FormicOS. The Queen has `run_command` (Wave 62) with `git status/diff/log`
in the allowlist, but no structured git intelligence. Generating good
commit messages, analyzing branch divergence, and auto-staging colony
output are all manual.

**Design:**

A. **Addon manifest:**

   ```yaml
   name: git-control
   version: "1.0.0"
   description: "Git intelligence for the Queen"
   author: "formicos-core"

   tools:
     - name: git_smart_commit
       description: "Generate commit message from staged changes and commit"
       handler: tools.py::handle_smart_commit
       parameters:
         type: object
         properties:
           message_hint: { type: string }
           amend: { type: boolean, default: false }

     - name: git_branch_analysis
       description: "Analyze branch divergence and suggest merge strategy"
       handler: tools.py::handle_branch_analysis
       parameters:
         type: object
         properties:
           branch: { type: string }
           base: { type: string, default: "main" }

   handlers:
     - event: ColonyCompleted
       handler: handlers.py::on_colony_completed_auto_stage
   ```

B. **`git_smart_commit` handler** (~80 lines):

   1. Run `git diff --cached --stat` to get staged changes
   2. Run `git diff --cached` to get full diff (truncate to 3000 chars)
   3. Run `git log --oneline -5` to get recent commit style
   4. Build a prompt for the Queen: "Generate a commit message for these
      changes, matching the style of recent commits."
   5. The Queen generates the message in her response (not a separate LLM
      call -- the tool returns the diff context and the Queen writes the
      message in her reply)
   6. On confirmation: `git commit -m "{message}"`

   Safety: never force-push. Never amend without explicit `amend: true`.
   Only commit staged changes (never `git add -A`).

C. **`git_branch_analysis` handler** (~60 lines):

   1. `git merge-base {base} {branch}` to find divergence point
   2. `git log --oneline {merge_base}..{branch}` for branch commits
   3. `git log --oneline {merge_base}..{base}` for base commits since diverge
   4. `git diff --stat {merge_base}..{branch}` for file change summary
   5. Return structured analysis: commits ahead/behind, conflicting files,
      suggested strategy (fast-forward / merge / rebase)

D. **Auto-stage handler** (~40 lines):

   On ColonyCompleted, if the colony modified workspace files:
   1. Check if workspace is a git repo
   2. Run `git diff --name-only` to see unstaged changes
   3. Filter to files that the colony's agents actually wrote to (from
      agent turn events)
   4. `git add` those specific files (never `git add -A`)
   5. Log the action but don't commit (staging only, commit is explicit)

   This is opt-in via workspace config: `git_auto_stage: true`.

**Code delta:** ~200 lines total across the addon (tools.py ~140,
handlers.py ~60).

**New tests (4):**
1. `test_smart_commit_returns_diff_context` -- handler returns staged diff
2. `test_branch_analysis_ahead_behind` -- correct commit counts
3. `test_auto_stage_only_colony_files` -- only modified files staged
4. `test_auto_stage_respects_config` -- disabled when config is false

**Owned files:**
- `addons/git-control/` (NEW directory)
- `tests/unit/addons/test_git_control.py` (NEW)

**Do not touch:** `engine/runner.py`, `core/events.py`, `queen_tools.py`
(tool registered via addon loader)

**Validation:**
```bash
pytest tests/unit/addons/test_git_control.py -q
```

---

## Dependency Graph

```
Track 1 (adapter factory)  -- independent
Track 2 (file locking)     -- independent
Track 3 (smart fan-out)    -- independent (benefits from Track 1 at runtime)
Track 4 (cloud routing)    -- independent
Track 5 (UI dashboard)     -- DEPENDS ON Track 1 (provider data), Track 3 (plan data)
Track 6a (addon loader)    -- independent (MUST merge first -- 6b, 7, 8 depend on it)
Track 6b (proactive extraction) -- DEPENDS ON Track 6a
Track 7 (codebase index)   -- DEPENDS ON Track 6a (addon loader + trigger dispatch)
Track 8 (git control)      -- DEPENDS ON Track 6a (addon loader)
```

## Team Assignment (3 coder teams)

| Team | Tracks | Rationale |
|------|--------|-----------|
| Team A (Parallelism) | 1, 2, 4 | Backend infrastructure: adapter factory, file locking, cloud routing. Independent tracks, can execute in parallel. Team A owns runner.py and app.py. |
| Team B (Addon System) | 6a, 6b, 7, 8 | Addon loader first (Track 6a), then extraction (6b) + two addons. Sequential: 6a -> then 6b, 7, 8 can parallel. Team B owns events.py changes and addons/ directory. |
| Team C (Queen + Frontend) | 3, 5 | Queen intelligence (smart fan-out) and UI dashboard. Track 3 first (provides data), then Track 5 (displays it). Team C owns queen_tools.py and frontend. |

## File Overlap Matrix

| File | Tracks | Resolution |
|------|--------|------------|
| events.py | 6 (AddonLoaded, AddonUnloaded), 7 (ServiceTriggerFired) | Team B owns exclusively. Add all 3 events in Track 6 merge. |
| app.py | 1, 6 | Track 1 (adapter factory) and Track 6 (addon loading in lifespan) touch different sections. Team A merges Track 1 first, Team B merges Track 6 after. |
| queen_tools.py | 3 | Team C only (retry_colony + provider plan). Addons register via loader, not direct queen_tools.py edits. |
| routes/api.py | 5 | Team C only (provider health endpoint). |
| queen_runtime.py | 4 | Team A only (cloud routing heuristics). |
| runner.py | 2 | Team A only (file locking). |
| types.ts | 5 | Team C only. |

## Merge Order

1. Team B: Track 6a -- addon loader + events (FIRST -- unblocks 6b, 7, 8)
2. Team A: Track 1 -- adapter factory (independent)
3. Team A: Track 2 -- file locking (independent)
4. Team A: Track 4 -- cloud routing (independent)
5. Team C: Track 3 -- smart fan-out
6. Team B: Track 6b -- proactive intelligence extraction (needs Track 6a)
7. Team B: Track 7 -- codebase index addon (needs Track 6a)
8. Team B: Track 8 -- git control addon (needs Track 6a)
9. Team C: Track 5 -- UI dashboard (last -- needs all data sources)

## Acceptance Criteria

After Wave 64:
- [ ] Multiple providers with same prefix but different endpoints work
- [ ] Unknown provider prefixes with endpoints auto-create OpenAI adapters
- [ ] Per-model max_concurrent controls adapter semaphore
- [ ] patch_file detects concurrent modification and returns CONFLICT
- [ ] write_workspace_file uses atomic temp+rename
- [ ] Queen proposes provider-specific plans with cost estimates
- [ ] retry_colony spawns new colony with failure context
- [ ] @cloud tag forces cloud routing
- [ ] Long messages and deep threads auto-route to cloud
- [ ] Parse failure triggers one cloud retry
- [ ] Budget panel shows per-provider cost breakdown
- [ ] Parallel colony groups displayed as visual groups
- [ ] Provider health visible in dashboard
- [ ] Addon loader reads addons/*/addon.yaml and registers components
- [ ] AddonLoaded/AddonUnloaded events emitted on startup/shutdown
- [ ] Proactive intelligence extracted to addon, 1980-line file -> 50-line shim
- [ ] 17 proactive rules still fire identically
- [ ] Codebase semantic index addon: daily reindex + semantic_search_code tool
- [ ] Git control addon: smart_commit + branch_analysis + auto-stage
- [ ] 69 event types total
- [ ] 32+ Queen tools (30 from Wave 63 + retry_colony + addon-registered tools)
- [ ] 3535+ tests passing

## Does NOT Do

- No hot-reload of addons (restart required for now)
- No addon dependency resolution (addons are independent for v1)
- No addon marketplace or remote installation
- No Queen-generated addons (future wave)
- No true daemon service colonies (each trigger activation is a fresh colony)
- No multi-threading (asyncio only -- file locking is cooperative)
- No workspace_execute isolation (the large ~300 line sandbox fix is deferred)
- No drag-and-drop in workflow editor (up/down buttons from Wave 63)
- No streaming test output in run_tests
- No changes to the 7-signal retrieval weights
- No new knowledge events (addon events only)

---

## The "Replace OpenClaw" Test

After Wave 64, the operator's daily workflow:

| Activity | FormicOS tool | Status |
|----------|--------------|--------|
| Morning status | Queen: get_status + query_briefing + cross-turn memory | Wave 63 |
| Quick codebase question | Queen: search_codebase + semantic_search_code | Wave 62 + 64 |
| Architecture discussion | Queen: cloud-routed propose_plan with project context | Wave 63 + 64 |
| Quick fix | Queen: edit_file with diff preview + operator confirmation | Wave 63 |
| Full feature build | Queen: spawn_parallel across providers + retry_colony | Wave 62 + 64 |
| Code review | Queen: run_tests + inspect_colony | Wave 62 + 63 |
| End of day | Queen: git_smart_commit + workflow step update | Wave 63 + 64 |

**Gaps remaining after Wave 64:**
- No IDE integration (must use web UI or API)
- No inline code completion (that's the model's job, not FormicOS's)
- No persistent service colonies that watch for file changes (v1 is
  trigger-activated, not continuous)
- No multi-user collaboration (single operator)

## The "OS" Test

After Wave 64, the OS metaphor:

| OS concept | FormicOS equivalent | Status |
|-----------|---------------------|--------|
| Kernel | Event store + replay | Shipped (Wave 1) |
| Shell | Queen (32+ tools) | Wave 64 |
| Filesystem | Workspace + knowledge store | Shipped + Wave 63 (editing) |
| Processes | Task colonies | Shipped |
| Daemons | Service colonies (trigger-activated) | Wave 64 |
| Apps | Addons (3 installed) | Wave 64 |
| Package manifest | addon.yaml | Wave 64 |
| Package manager | Drop directory + restart | Wave 64 (primitive) |
| User preferences | Workspace config + project_context.md | Wave 63 |
| Task manager | Colony overview + parallel dashboard | Wave 64 |

**What's missing from a real OS:**
- Hot-reload (requires restart for new addons)
- Dependency management between addons
- Permission model for addons (all addons are trusted)
- Self-extending (Queen building her own addons)
- Multi-user / multi-tenant

These are future waves. The foundation is in place after 64.
