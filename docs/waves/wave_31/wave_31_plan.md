# Wave 31 Plan -- Ship Polish

**Wave:** 31 -- "Ship Polish"
**Theme:** The system becomes demonstrable. Workflow steps auto-continue. Agents gain transcript search. Knowledge gets thread-scoped retrieval in colonies (bug fix). Documentation covers the full post-30 lifecycle. Edge cases that would embarrass a demo get hardened. No new event types. No new architectural concepts. Everything that exists works reliably, looks good, and is explainable.
**Contract changes:** None. Event union stays at 48. No new models in `core/types.py`.
**Estimated LOC delta:** ~400 Python net new, ~200 TypeScript, ~300 docs. Well within 20K soft ceiling (current: 16,294 per count_loc.py non-blank metric; ~20,010 raw lines including blanks/comments).

---

## Why This Wave

After Wave 30, FormicOS has workflow threads, thread-scoped knowledge, Thompson Sampling retrieval, Bayesian confidence evolution, deterministic maintenance services, and LLM-confirmed dedup. But an outside observer cannot yet see a coherent workflow: colonies complete and the operator must manually prompt the Queen to spawn the next step. Agents cannot search past colony transcripts. Thread-scoped knowledge boosting silently never fires during colony execution due to a missing parameter. Documentation describes Wave 27 patterns. Tests cover none of the Wave 30 behaviors.

Wave 31 closes all of these. The goal is not new architecture -- it is making everything that exists work reliably, look good, and be explainable to someone who did not build it.

---

## Bug Fix (Pre-Tracks): thread_id Not Passed to Colony Knowledge Fetch

**Severity:** High. Negates the entire purpose of Wave 29's thread-scoped knowledge.

`colony_manager.py` line 374 calls `fetch_knowledge_for_colony(task=colony.task, workspace_id=colony.workspace_id, top_k=5)` without passing `thread_id`. The catalog's `_search_thread_boosted` path (which applies the 0.25 thread bonus) is never reached during colony execution. Agents in workflow threads get workspace-wide retrieval only -- thread-scoped entries get no boost.

**Fix:** Pass `thread_id=colony.thread_id` at line 374 and at line 390 (redirect re-fetch). Two-line change, massive behavioral impact.

**Ownership:** Track A touches `colony_manager.py` and owns this fix.

---

## Track A: Step Continuation + Colony Manager Hardening

### A1. Automatic step continuation prompt

After `WorkflowStepCompleted` is emitted in `_post_colony_hooks()` (line 794), detect the next pending step and inject a `QueenMessage` into the thread. This is a direct injection, not a metacognitive nudge -- step continuation is workflow-critical, not advisory. No cooldown gating.

**Implementation:**

Add `_continue_workflow_step()` to `colony_manager.py`. After the step completion block (line 794), check the thread's `workflow_steps` for the next pending step. If found, emit a `QueenMessage` event directly via `self._runtime.emit_and_broadcast()` -- the same emission pattern colony_manager uses for every other event type. Do NOT call `queen._emit_queen_message()` (that is a private method on QueenAgent). Colony_manager already emits 15+ event types directly; this follows the established pattern.

```python
from formicos.core.events import QueenMessage  # noqa: PLC0415
await self._runtime.emit_and_broadcast(
    QueenMessage(
        seq=0, timestamp=_now(),
        address=f"{ws_id}/{th_id}",
        thread_id=th_id, role="queen",
        content=continuation_text,
    ),
)
```

The continuation prompt format:

```
Step {N} completed ({status}). Artifacts produced: {types}.
Next pending step [{N+1}]: {description}
{template context if template-backed}
Consider spawning a colony for this step, or adjust the plan if needed.
```

For template-backed steps, include `template_id` and `expected_outputs` so the Queen can semi-auto-spawn with minimal reasoning.

The Queen is never bypassed. She sees the prompt as a system message and decides whether to proceed, skip, modify, or take a different approach. The automation is a prompt, not a pipeline runner.

**Key design decision:** Direct injection via `QueenMessage` event, not metacognitive nudge. Rationale: nudges are cooldown-gated ephemeral hints (5-minute cooldown per type). Step continuation must fire every time a step completes, must appear in the persistent conversation, and must not be suppressed by cooldown from a previous step completion. This aligns with the project knowledge: Manus found ~30% of actions wasted on planning overhead, so the continuation prompt should be minimal and actionable, not a re-planning prompt.

**Files touched:**
- `surface/colony_manager.py` -- add `_continue_workflow_step()`, call it after line 794, fix thread_id bug at lines 374/390. QueenMessage emitted directly (no queen_runtime.py changes needed).

**Non-goals for Track A:**
- Automatic spawning without Queen mediation
- Step dependency resolution (steps are sequential guidance, not a DAG)
- New events (we use existing `QueenMessage`)

### A2. Confidence fan-out batching

Colony completion with 5+ knowledge access traces emits 5+ `MemoryConfidenceUpdated` events, each triggering `sync_entry` to Qdrant. Measure whether this causes completion latency spikes. If measurable (>200ms total), batch the Qdrant syncs: collect all updated entries, issue a single batch upsert after all events are emitted.

This is a measure-first optimization. If latency is <100ms, skip the batching and document the measurement.

**Files touched:**
- `surface/colony_manager.py` -- measure timing around the confidence update loop (lines 696-746)
- `surface/memory_store.py` -- add batch `sync_entries()` if needed

### A3. Thread context truncation

A thread with 50+ colonies generates a very long `_build_thread_context()` block (line 595 of `queen_runtime.py`). Add a cap: show the last 10 colonies in detail, summarize earlier ones as a count. Same for workflow steps: show last 5 completed + all pending, summarize the rest.

**Files touched:**
- `surface/queen_runtime.py` -- modify `_build_thread_context()` (lines 595-638)

### Track A acceptance criteria

1. Colony completes a workflow step -> Queen chat shows step-continuation prompt within 5 seconds
2. Template-backed step continuation includes template_id in the prompt
3. Queen can ignore the continuation prompt and do something different (not forced)
4. Colony knowledge fetch passes thread_id (verify with structlog trace)
5. Thread context for 50+ colony thread is <2000 chars

---

## Track B: Agent Transcript Search + Test Coverage

### B1. `transcript_search` agent tool

Add a projection-based transcript search tool. No new Qdrant collection -- search colony projections directly using keyword matching on `task` + final round agent outputs. Returns pointers (colony_id + relevance snippet), not full transcripts. The agent can use `artifact_inspect` to dig deeper. This follows the pointer architecture pattern from the research: SWE-agent's constrained window outperformed full-file display by 5.3 percentage points.

**Implementation:**

1. Add `TOOL_SPECS["transcript_search"]` in `runner.py`:
   ```python
   "transcript_search": {
       "name": "transcript_search",
       "description": "Search past colony transcripts for relevant approaches and patterns. Returns colony IDs and snippets -- use artifact_inspect to see full details. Do NOT use for current colony data (use memory_search) or general knowledge queries (use knowledge_detail).",
       "parameters": {
           "type": "object",
           "properties": {
               "query": {"type": "string", "description": "Search query"},
               "top_k": {"type": "integer", "description": "Max results (1-5)", "default": 3},
           },
           "required": ["query"],
       },
   }
   ```

2. Add `TOOL_CATEGORY_MAP["transcript_search"] = ToolCategory.vector_query`

3. Add dispatch in `_execute_tool()`: call `self._transcript_search_fn(query, workspace_id, top_k)`

4. Add callback factory in `runtime.py`:
   ```python
   def make_transcript_search_fn(self) -> Callable[..., Any] | None:
       projections = self.projections
       embed_client = self.embed_client

       async def _transcript_search(query: str, workspace_id: str, top_k: int = 3) -> str:
           # Search colony projections by task + output keyword overlap
           # If embed_client available, use cosine similarity on task embeddings
           # Return formatted snippets with colony_ids
           ...
       return _transcript_search
   ```

5. Wire into `RoundRunner.__init__()` via new `transcript_search_fn` parameter

6. Add to relevant castes in `caste_recipes.yaml` (coder, researcher, reviewer)

**Search strategy:** BM25 is the primary search path (see Amendment 2). Use `bm25s` with a custom code-aware tokenizer over colony projection task + final_output text. If `bm25s` is not approved as a dependency, fall back to word-overlap scoring (Jaccard on lowercased word sets). Embedding similarity is a true optional enhancement, not co-primary. Place transcript_search mid-list in TOOL_SPECS (not first, not last) to reduce ordering bias. Return top_k results formatted as:

```
[Colony {id[:8]} ({status})] Task: {task[:100]}
  Output snippet: {final_output[:200]}
  Artifacts: {artifact_count} ({artifact_types})
```

### B2. Tool-driven access tracing

Extend `KnowledgeAccessRecorded` events to cover tool-driven access. The `access_mode` field was designed for this but currently only records `"context_injection"`. Add:

- `"tool_search"` when `memory_search` is called by an agent
- `"tool_detail"` when `knowledge_detail` is called by an agent
- `"tool_transcript"` when `transcript_search` returns results that reference knowledge entries

**Implementation:** In `_handle_memory_search()` and `_execute_tool()` for `knowledge_detail`, emit `KnowledgeAccessRecorded` with the appropriate `access_mode`. The event already exists -- this is about coverage, not new events.

**Files touched:**
- `engine/runner.py` -- add transcript_search tool spec/dispatch/category + new `transcript_search_fn` parameter on `RoundRunner.__init__()` stored as `self._transcript_search_fn`
- `surface/runtime.py` -- add `make_transcript_search_fn()` callback factory
- `surface/colony_manager.py` -- wire `transcript_search_fn=self._runtime.make_transcript_search_fn()` into the RoundRunner instantiation (lines 344-358). This is one line in colony_manager, but the full wiring is 5 touch points across 3 files following the existing callback pattern (see `knowledge_detail_fn` for the exact template).
- `config/caste_recipes.yaml` -- add transcript_search to relevant castes

### B3. Test coverage for Wave 30 behaviors

Write tests for every Wave 30 behavior that currently has zero coverage. Use pytest, match existing patterns in `tests/unit/surface/`.

**Tests to write:**

| Test file | What it covers | Key assertions |
|-----------|---------------|----------------|
| `test_thompson_sampling.py` | Thompson Sampling distribution properties | Run 1000 samples from Beta(10,5), verify mean is near 0.67, verify variance is near Beta variance formula |
| `test_bayesian_confidence.py` | Confidence update end-to-end | Colony completes -> KnowledgeAccessRecorded exists -> MemoryConfidenceUpdated emitted -> alpha/beta updated correctly |
| `test_workflow_steps.py` | Workflow step lifecycle | define_steps -> spawn with step_index -> ColonySpawned sets step "running" -> ColonyCompleted -> WorkflowStepCompleted emitted -> step status "completed" |
| `test_archival_decay.py` | Thread archival confidence decay | archive_thread -> N MemoryConfidenceUpdated events emitted -> alpha *= 0.8, beta *= 1.2 per entry -> verify hard floor: alpha >= 1.0 and beta >= 1.0 after decay |
| `test_dedup_dismissal.py` | Dedup dismissed pair exclusion | Dismiss pair -> re-run dedup handler -> pair is skipped |
| `test_contradiction_detection.py` | Contradiction detector | Two entries with overlapping domains and opposite polarity -> flagged in report |
| `test_step_continuation.py` | Step continuation prompt (A1) | Colony completes workflow step -> QueenMessage emitted with step-continuation text |
| `test_transcript_search.py` | Transcript search tool (B1) | Colony exists with task and outputs -> transcript_search returns matching colony snippet |

Each test uses mocked projections and AsyncMock for emit_and_broadcast. No live LLM or Qdrant calls. Property-based assertions where appropriate (Thompson Sampling distribution tests).

**Files created:**
- `tests/unit/surface/test_thompson_sampling.py`
- `tests/unit/surface/test_bayesian_confidence.py`
- `tests/unit/surface/test_workflow_steps.py`
- `tests/unit/surface/test_archival_decay.py`
- `tests/unit/surface/test_dedup_dismissal.py`
- `tests/unit/surface/test_contradiction_detection.py`
- `tests/unit/surface/test_step_continuation.py`
- `tests/unit/surface/test_transcript_search.py`

### Track B acceptance criteria

1. `transcript_search` tool returns relevant colony snippets for a keyword query
2. `KnowledgeAccessRecorded` events fire with correct `access_mode` for tool-driven access
3. All 8 new test files pass
4. Thompson Sampling test verifies distribution properties over 1000+ samples
5. Existing tests still pass (`pytest` clean)

---

## Track C: Documentation + Edge Cases + Frontend Polish

### C1. Operator runbook: knowledge lifecycle

Write `docs/KNOWLEDGE_LIFECYCLE.md` covering the full post-30 knowledge lifecycle:

1. **Extraction:** Colony completes -> LLM extracts skills + experiences -> 4-axis security scan -> MemoryEntryCreated
2. **Trust:** scan_status high/critical = rejected; safe/low/medium = candidate; source colony succeeded = verified
3. **Thread scoping:** Entries carry thread_id. Thread-scoped entries get 0.25 bonus in retrieval. Promote to workspace-wide via `MemoryEntryScopeChanged`.
4. **Retrieval:** Thompson Sampling composite scoring (0.35 semantic + 0.25 thompson + 0.15 freshness + 0.15 status + 0.10 thread). Explain what Thompson Sampling means for operators: high-confidence entries are exploited, uncertain entries get explored, low-confidence entries fade.
5. **Confidence evolution:** Colony completes -> traces matched -> alpha/beta updated. Bayesian posterior converges with more data.
6. **Maintenance:** Dedup (auto >= 0.98 cosine, LLM-confirmed [0.82, 0.98), dismissed pairs skipped). Stale sweep (90 days untouched). Contradiction detection (Jaccard domain overlap + opposite polarity). Scheduled daily.
7. **Archival decay:** Thread archived -> unpromoted entries get alpha *= 0.8, beta *= 1.2 (with hard floor: alpha >= 1.0, beta >= 1.0). **Known tension:** This formula is asymmetric -- it biases confidence downward, not just widening uncertainty. When gamma-decay ships in Wave 32, this formula must be redesigned. Document the three options: symmetric decay, lower-gamma variant for archived entries, or subsumption into gamma-decay.
8. **How to trigger maintenance manually:** Queen tool `query_service(service_type="service:consolidation:dedup")`, etc.
9. **How to read confidence:** Beta posterior mean = alpha/(alpha+beta). Uncertainty width = high beta total means more data, narrower band. Explain the UI confidence bars.
10. **How to promote entries:** From thread-scoped to workspace-wide.

### C2. Updated CLAUDE.md

Rewrite CLAUDE.md to reflect post-30 reality:

- **Verify tech stack against actual imports and pyproject.toml before documenting.** Do NOT assume things were removed -- check. Specifically: FastMCP is still active (mcp_server.py, app.py), sentence-transformers is still a dependency (pyproject.toml, app.py fallback path) alongside the Qwen3-embedding sidecar. Both coexist. Qdrant replaced LanceDB (confirmed). Lit Web Components confirmed.
- Add knowledge system to architecture section
- Reference 48 events (not just "closed union")
- Add workflow threads and steps to workflow cadence
- Add Thompson Sampling and confidence to hard constraints context
- Update key paths table with knowledge catalog, maintenance, transcript files
- Add the "adding a Queen tool" and "adding an agent tool" patterns from the briefing

### C3. Updated AGENTS.md

Update AGENTS.md to reflect post-30 agent capabilities:

- 8 agent tools (9 with transcript_search after B1)
- Knowledge detail and artifact inspect descriptions
- Thread-scoped knowledge retrieval (after the bug fix)
- Workflow step context in agent prompts
- Confidence evolution impact on retrieval

### C4. ADR-040: Wave 31 decisions

Record the key decisions:

- D1: Step continuation is direct QueenMessage injection, not metacognitive nudge. Rationale: workflow-critical vs advisory; cooldown gating inappropriate for step transitions.
- D2: transcript_search is projection-based, not Qdrant-backed. Rationale: no new collection needed; colony projections already hold task + outputs; embed-based similarity optional enhancement.
- D3: thread_id bug fix is a two-line change, not a new feature. Rationale: thread-scoped knowledge was the purpose of Wave 29; not passing thread_id negates it.
- D4: No new events in Wave 31. Rationale: step continuation uses existing QueenMessage; access tracing uses existing KnowledgeAccessRecorded; all new behavior composes from the existing 48-event vocabulary.
- D5: Dedup pagination deferred to post-31 unless store exceeds 500 entries. Rationale: O(n^2) scan is acceptable for alpha-scale stores; Qdrant-based candidate pair search is the correct fix but adds complexity.

### C5. Edge case hardening

**Concurrent dedup + active extraction (maintenance.py):**
VERIFIED: Already handled. Lines 103-106 use `.get()` (returns None, no KeyError) with `if ea is None or eb is None: continue`. No fix needed.

**Qdrant unavailability fallback (knowledge_catalog.py):**
If Qdrant is down during context assembly, both the catalog search and legacy fallback fail (both use Qdrant). Add a projection-based emergency fallback: if catalog search raises, fall back to returning the 5 most recent verified `memory_entries` from projections, sorted by `created_at`. No vector similarity, but agents get *something* instead of empty context.

**Confidence divergence reset:**
An entry with alpha=50, beta=50 (confidence ~0.5 with very narrow uncertainty) will almost never be surfaced by Thompson Sampling and almost never go stale. Add a "confidence reset" option to the maintenance toolkit: if an entry's total observations (alpha + beta - 10, accounting for the 5.0/5.0 prior) exceed a threshold (e.g., 50) and its posterior mean is between 0.35 and 0.65, allow the operator to reset it to the prior (5.0/5.0) via a new maintenance service handler.

**IMPORTANT: The confidence reset handler must be registered in `app.py` (lines 493-541) following the existing pattern** -- `make_confidence_reset_handler` imported alongside the other handlers, registered via `service_router.register_handler("service:consolidation:confidence_reset", ...)`, and a `DeterministicServiceRegistered` event emitted. Without this registration, the handler is dead code.

**Step definition after existing colonies:**
Document in the runbook that defining workflow steps after colonies have already completed will not retroactively bind completed colonies to steps. This is expected behavior -- steps are Queen scaffolding for future work, not a retrospective classification tool.

**Files touched:**
- `surface/maintenance.py` -- confidence reset handler factory
- `surface/app.py` -- register confidence reset handler (lines 493-541 pattern)
- `surface/knowledge_catalog.py` -- projection-based emergency fallback
- `docs/KNOWLEDGE_LIFECYCLE.md` -- new file
- `CLAUDE.md` -- rewrite
- `AGENTS.md` -- update
- `docs/decisions/040-wave-31-ship-polish.md` -- new ADR

### C6. Knowledge browser empty state

Update `frontend/src/components/knowledge-browser.ts` to show a helpful empty state when no entries exist:

```
No knowledge entries yet.
Knowledge is extracted automatically when colonies complete.
Try running a colony, then come back here to see what was learned.
```

Include a subtle link/hint to trigger maintenance if entries exist but none are verified.

**Stretch goal (if time permits):** Upgrade the existing confidence bars to gradient-opacity encoding -- opaque at the posterior mean, fading to transparent at the 90% credible interval edges. Add a color-coded tier badge: gray (insufficient data, alpha+beta < 15), red (low confidence, CI width > 30%), yellow (moderate, 15-30%), green (high, CI width < 15% and alpha+beta > 30). Add natural-language summary on hover: "High confidence (72%) -- based on 47 observations."

### C7. First-run Queen welcome update

Update the Queen's first-run welcome message (in `queen_runtime.py` or the caste recipe system prompt) to mention:

- Threads and goals ("Try setting a thread goal to organize your work")
- Workflow steps ("I can define workflow steps to break down complex projects")
- Knowledge ("I learn from each colony -- check the Knowledge tab after your first task completes")

**Files touched:**
- `frontend/src/components/knowledge-browser.ts` -- empty state
- `config/caste_recipes.yaml` -- Queen system prompt update (if first-run text is there)
- `surface/queen_runtime.py` -- if first-run welcome is hardcoded

### Track C acceptance criteria

1. `docs/KNOWLEDGE_LIFECYCLE.md` exists and passes the "brilliant stranger" test
2. `CLAUDE.md` references 48 events, Qdrant, Thompson Sampling, workflow threads -- tech stack verified against pyproject.toml and actual imports
3. `AGENTS.md` lists all agent tools including transcript_search
4. ADR-040 exists with all 5 decisions documented
5. Knowledge browser shows helpful empty state on fresh workspace
6. Confidence reset handler registered in app.py and callable via `query_service(service_type="service:consolidation:confidence_reset")`
7. Qdrant-down scenario returns projection-based fallback (not empty)

---

## File Ownership Matrix

| File | Track A | Track B | Track C | Notes |
|------|---------|---------|---------|-------|
| `surface/colony_manager.py` | **OWN** | wire callback | -- | A owns; B adds one line to RoundRunner() call |
| `surface/queen_runtime.py` | **OWN** | -- | first-run text | A: extend follow_up_colony, relax 30-min gate, thread context truncation, archival decay hard-floor (lines 1282-1283: clamp new_alpha >= 1.0, new_beta >= 1.0) |
| `engine/runner.py` | -- | **OWN** | -- | B adds tool spec/dispatch/category/init param |
| `surface/runtime.py` | -- | **OWN** | -- | B adds transcript_search callback factory |
| `surface/knowledge_catalog.py` | -- | -- | **OWN** | C adds Qdrant-down fallback |
| `surface/maintenance.py` | -- | -- | **OWN** | C adds confidence reset handler |
| `surface/app.py` | -- | -- | **OWN** | C registers confidence reset handler (lines 493-541 pattern) |
| `surface/memory_store.py` | measure only | -- | -- | A measures sync_entry latency |
| `surface/projections.py` | **OWN** | read only | -- | A: add continuation_depth to ThreadProjection, increment in _on_workflow_step_completed |
| `config/caste_recipes.yaml` | -- | **OWN** | Queen prompt | B adds transcript_search to castes; C updates Queen prompt |
| `tests/unit/surface/test_*.py` | -- | **OWN** | -- | B writes all 8 test files |
| `CLAUDE.md` | -- | -- | **OWN** | C rewrites |
| `AGENTS.md` | -- | -- | **OWN** | C updates |
| `docs/KNOWLEDGE_LIFECYCLE.md` | -- | -- | **OWN** | C creates |
| `docs/decisions/040-*.md` | -- | -- | **OWN** | C creates |
| `frontend/src/components/knowledge-browser.ts` | -- | -- | **OWN** | C adds empty state |

**Overlap rule:** Track A owns `colony_manager.py`. Track B adds one line to the RoundRunner instantiation in that file (wiring `transcript_search_fn`) but the full wiring spans runner.py + runtime.py + colony_manager.py (5 touch points total -- follow the `knowledge_detail_fn` pattern exactly). Track B must reread lines 340-358 after Track A's changes land and adjust accordingly. Track C touches `caste_recipes.yaml` for the Queen prompt; Track B touches it for tool lists. They are non-overlapping sections -- no conflict expected, but both should reread before committing.

---

## Sequencing

All three tracks can start in parallel. No blocking dependencies between them.

**Track A** is the headline feature. Expected 1-2 sessions.
**Track B** is the largest track (new tool + 8 test files). Expected 2-3 sessions. Can call subagent teams in parallel: one team for tool implementation (runner.py + runtime.py + colony_manager.py wiring), one team for tests.
**Track C** is the broadest track (docs + edge cases + frontend). Expected 2-3 sessions. Can call subagent teams in parallel: one for docs (CLAUDE.md + AGENTS.md + runbook + ADR), one for code hardening (maintenance.py + knowledge_catalog.py + frontend).

**Integration pass** after all three land: verify thread_id flows end-to-end, verify transcript_search works with the step continuation flow, verify docs match the code.

---

## What Wave 31 Does NOT Include

- **No new events.** 48 is the vocabulary. Everything composes from existing types.
- **No automatic step execution without Queen mediation.** The Queen always decides.
- **No RLM-style recursive context decomposition.** One new tool (transcript_search) is enough for this wave.
- **No dedup pagination.** O(n^2) scan is acceptable at alpha scale (<500 entries). If stores grow larger, this becomes a Wave 32 item. The correct fix (Qdrant-based candidate pair search) is documented in ADR-040 as deferred.
- **No composable dashboards.** The Agent Composable UI Reference is aspirational. Ship static views first.
- **No performance optimization without measurement.** A2 measures first, optimizes only if latency exceeds 200ms.
- **No queen_runtime.py refactor.** At 2,316 lines it deserves splitting, but this is a polish wave, not a refactor wave. Elegance improvements stay cosmetic (thread context truncation, first-run text). Structural extraction of tool handlers into `queen_tools.py` is a Wave 32 candidate.

---

## Questions Resolved

**Q1. Step continuation: nudge or direct injection?**
Direct injection via QueenMessage. Nudges are cooldown-gated advisory hints; step continuation is workflow-critical. See ADR-040 D1.

**Q2. transcript_search scope: thread or workspace?**
Workspace-wide. Thread-scoped search misses cross-workflow patterns. The tool searches all colonies in the workspace, with a `thread_id` filter parameter available for future narrowing.

**Q3. Performance budget for retrieval?**
Measure first. If Thompson Sampling + two-phase thread search stays under 200ms, no optimization. If it exceeds 200ms, batch the Qdrant calls. The fan-out concern (A2) is measure-then-act.

**Q4. Documentation format?**
Markdown in `docs/`. Operator-facing docs may eventually be accessible from the UI, but for Wave 31, markdown in the repo is correct.

**Q5. Test strategy?**
Unit tests per feature with mocked projections and AsyncMock. No integration tests requiring live Qdrant or LLM. Property-based assertions for Thompson Sampling. Existing pytest patterns. 8 new test files.

---

## Smoke Test (Post-Integration)

After all three tracks land and the integration pass completes, run this sequence on a fresh event store:

1. Create workspace, create thread, set goal
2. Define 3 workflow steps (via Queen chat)
3. Spawn colony for step 1 with step_index=0
4. Colony completes -> verify: step 1 marked "completed", step-continuation prompt appears in Queen chat
5. Queen spawns colony for step 2 -> verify: step 2 marked "running"
6. Step 2 colony completes -> verify: step-continuation prompt for step 3 appears
7. Check Knowledge tab -> verify: entries extracted, confidence bars visible
8. In a new colony, use `memory_search` -> verify: `KnowledgeAccessRecorded` with `access_mode` includes tool traces
9. Use `transcript_search` -> verify: returns snippets from completed colonies
10. Archive the thread -> verify: confidence decay events emitted
11. Visit Knowledge browser on a fresh workspace -> verify: empty state message shows

Record whether the smoke tests code-as-written or code-as-deployed. If Docker was not rebuilt, say so.
