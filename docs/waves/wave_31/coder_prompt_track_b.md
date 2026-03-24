# Wave 31 Track B — Agent Transcript Search + Test Coverage

**Track:** B
**Wave:** 31 — "Ship Polish"
**Coder:** You own this track. Read this prompt fully before writing any code.

---

## Reading Order (mandatory before any code changes)

1. `docs/decisions/040-wave-31-ship-polish.md` — D2 (transcript_search is projection-based), D4 (no new events)
2. `docs/waves/wave_31/wave_31_final_amendments.md` — Amendment 2 (BM25 primary, code-aware tokenizer, "when NOT to use" clause), Amendment 7 (seeded deterministic + KS tests)
3. `docs/waves/wave_31/wave_31_plan.md` — Track B sections (B1, B2, B3), file ownership matrix
4. `CLAUDE.md` — hard constraints, prohibited alternatives, validation commands

---

## Your Files

| File | Action |
|------|--------|
| `src/formicos/engine/runner.py` | **OWN** — add transcript_search tool spec, dispatch, category, init param |
| `src/formicos/surface/runtime.py` | **OWN** — add `make_transcript_search_fn()` callback factory |
| `src/formicos/surface/colony_manager.py` | wire callback — **one line only** in RoundRunner() call (lines 344-358) |
| `config/caste_recipes.yaml` | **OWN** — add transcript_search to relevant castes |
| `tests/unit/surface/test_thompson_sampling.py` | **CREATE** |
| `tests/unit/surface/test_bayesian_confidence.py` | **CREATE** |
| `tests/unit/surface/test_workflow_steps.py` | **CREATE** |
| `tests/unit/surface/test_archival_decay.py` | **CREATE** |
| `tests/unit/surface/test_dedup_dismissal.py` | **CREATE** |
| `tests/unit/surface/test_contradiction_detection.py` | **CREATE** |
| `tests/unit/surface/test_step_continuation.py` | **CREATE** |
| `tests/unit/surface/test_transcript_search.py` | **CREATE** |

## Do NOT Touch

- `surface/colony_manager.py` beyond the one wiring line (Track A owns this file)
- `surface/queen_runtime.py` (Track A)
- `surface/projections.py` (Track A)
- `surface/knowledge_catalog.py` (Track C)
- `surface/maintenance.py` (Track C)
- `surface/app.py` (Track C)
- Any `docs/` files (Track C)
- `CLAUDE.md`, `AGENTS.md` (Track C)

---

## Task 1: transcript_search Agent Tool (B1)

This is a new agent tool that searches past colony transcripts. It is projection-based (no Qdrant collection). Follow the existing `knowledge_detail` pattern exactly — it has 5 touch points across 3 files.

### Touch 1: Tool spec in `runner.py`

Add to `TOOL_SPECS` dict (line 50). Place it mid-list — after `knowledge_detail`, before `artifact_inspect` — to reduce ordering bias.

```python
"transcript_search": {
    "name": "transcript_search",
    "description": (
        "Search past colony transcripts for relevant approaches and patterns. "
        "Returns colony IDs and snippets -- use artifact_inspect to see full details. "
        "Do NOT use this tool for the current colony's data (use memory_search instead) "
        "or for general knowledge queries (use knowledge_detail instead)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query (keywords work best)",
            },
            "top_k": {
                "type": "integer",
                "description": "Max results (1-5)",
                "default": 3,
            },
        },
        "required": ["query"],
    },
},
```

Note the "when NOT to use" clause in the description — this is intentional per Amendment 2 to prevent tool overuse.

### Touch 2: Category mapping in `runner.py`

Add to `TOOL_CATEGORY_MAP` (line 255):

```python
"transcript_search": ToolCategory.vector_query,
```

### Touch 3: Init parameter on `RoundRunner.__init__()` (line 663)

Add after `artifact_inspect_fn` (line 679):

```python
transcript_search_fn: Callable[..., Any] | None = None,
```

Store it:
```python
self._transcript_search_fn = transcript_search_fn
```

### Touch 4: Dispatch in `_execute_tool()`

Find the dispatch block for tools (search for `knowledge_detail` dispatch as your template). Add:

```python
if name == "transcript_search":
    if self._transcript_search_fn is None:
        return "Error: transcript search not available"
    query = args.get("query", "")
    top_k = min(int(args.get("top_k", 3)), 5)
    workspace_id = context.workspace_id if context else ""
    return await self._transcript_search_fn(query, workspace_id, top_k)
```

### Touch 5: Callback factory in `runtime.py`

Add `make_transcript_search_fn()` following the `make_knowledge_detail_fn()` pattern (line 1054). This is the core search logic.

**Search strategy (Amendment 2):** BM25 via `bm25s` is the primary path. If `bm25s` is not available (dependency not approved), fall back to word-overlap scoring.

```python
def make_transcript_search_fn(self) -> Callable[..., Any] | None:
    """Create a callback for the transcript_search agent tool."""
    projections = self.projections

    async def _transcript_search(
        query: str, workspace_id: str, top_k: int = 3,
    ) -> str:
        # Collect completed colonies for this workspace
        colonies = [
            c for c in projections.colonies.values()
            if getattr(c, "workspace_id", "") == workspace_id
            and getattr(c, "status", "") in ("completed", "failed")
        ]
        if not colonies:
            return "No completed colonies found in this workspace."

        # Build search corpus: task + last round output
        def _last_output(colony: Any) -> str:
            rounds = getattr(colony, "rounds", [])
            if not rounds:
                return ""
            last = rounds[-1] if isinstance(rounds, list) else None
            if last is None:
                return ""
            agents = getattr(last, "agents", [])
            if not agents:
                return ""
            # Get last agent's output
            last_agent = agents[-1] if isinstance(agents, list) else None
            if last_agent is None:
                return ""
            return str(getattr(last_agent, "output", "") or "")[:500]

        corpus_texts = [
            f"{getattr(c, 'task', '')} {_last_output(c)}"
            for c in colonies
        ]

        # Try BM25 search first, fall back to word overlap
        scored: list[tuple[float, Any]] = []
        try:
            import bm25s  # noqa: PLC0415
            import re as _re  # noqa: PLC0415

            def _code_tokenizer(texts: list[str]) -> list[list[str]]:
                result = []
                for text in texts:
                    text = _re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
                    text = _re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', text)
                    tokens = _re.findall(r'\w+', text.lower())
                    result.append([t for t in tokens if len(t) > 1])
                return result

            corpus_tokens = _code_tokenizer(corpus_texts)
            query_tokens = _code_tokenizer([query])
            retriever = bm25s.BM25()
            retriever.index(corpus_tokens)
            results, scores = retriever.retrieve(query_tokens, k=min(top_k, len(colonies)))
            for i in range(len(results[0])):
                idx = int(results[0][i])
                scored.append((float(scores[0][i]), colonies[idx]))
        except ImportError:
            # Fallback: word-overlap scoring (no dependency)
            query_words = set(query.lower().split())
            for i, text in enumerate(corpus_texts):
                entry_words = set(text.lower().split())
                overlap = len(query_words & entry_words)
                if overlap > 0:
                    scored.append((float(overlap), colonies[i]))
            scored.sort(key=lambda x: -x[0])
            scored = scored[:top_k]

        if not scored:
            return f"No matching colonies found for query: {query}"

        # Format results as pointers (not full transcripts)
        lines = []
        for _score, colony in scored:
            cid = getattr(colony, "id", "?")
            status = getattr(colony, "status", "?")
            task = str(getattr(colony, "task", ""))[:100]
            output_snippet = _last_output(colony)[:200]
            artifacts = getattr(colony, "artifacts", [])
            art_count = len(artifacts) if artifacts else 0
            art_types = set()
            for art in (artifacts or []):
                atype = art.get("artifact_type", "generic") if isinstance(art, dict) else "generic"
                art_types.add(atype)

            lines.append(
                f"[Colony {cid[:8]} ({status})] Task: {task}\n"
                f"  Output snippet: {output_snippet}\n"
                f"  Artifacts: {art_count} ({', '.join(sorted(art_types)) if art_types else 'none'})"
            )
        return "\n\n".join(lines)

    return _transcript_search
```

### Touch 5b: Wire into colony_manager.py

**Track A owns this file.** You add ONE line to the `RoundRunner(...)` call at lines 344-358. Reread this block after Track A lands — they may have reordered things.

```python
runner = RoundRunner(
    # ... existing params ...
    artifact_inspect_fn=self._runtime.make_artifact_inspect_fn(),
    transcript_search_fn=self._runtime.make_transcript_search_fn(),  # NEW
)
```

### Touch 6: caste_recipes.yaml

Add `transcript_search` to the tool lists of: `coder`, `researcher`, `reviewer`. Do NOT add to `queen` (Queen has her own tools).

---

## Task 2: Tool-Driven Access Tracing (B2)

Extend `KnowledgeAccessRecorded` events to cover tool-driven access. The `access_mode` field (in `core/events.py`, line 724) already exists but currently only records `"context_injection"`.

In `runner.py`, when handling `memory_search` results, emit `KnowledgeAccessRecorded` with `access_mode="tool_search"`.

When handling `knowledge_detail`, emit with `access_mode="tool_detail"`.

When `transcript_search` returns results that reference knowledge entries, emit with `access_mode="tool_transcript"`.

Follow the existing emission pattern — use `self._emit(KnowledgeAccessRecorded(...))`. The event already exists in the union; this is coverage expansion, not a new event.

---

## Task 3: Test Coverage (B3)

Write 8 test files. Use pytest, match existing patterns in `tests/unit/surface/`. All tests use mocked projections and `AsyncMock` for `emit_and_broadcast`. No live LLM or Qdrant calls.

### Test techniques (Amendment 7):

- **Seeded deterministic tests:** Use `random.seed(42)` in Thompson Sampling tests for reproducibility
- **KS test for distribution:** Run 10,000+ samples, verify Beta distribution via `scipy.stats.kstest` (if scipy available; skip gracefully if not)
- **Given/When/Then pattern** for projection tests (matches BDD style in `docs/specs/`)

### Test files:

| File | What it covers | Key assertions |
|------|---------------|----------------|
| `test_thompson_sampling.py` | Thompson Sampling distribution | 1000+ samples from Beta(10,5), mean ~0.67, variance matches formula. Seeded deterministic ranking test. |
| `test_bayesian_confidence.py` | Confidence update E2E | Colony completes -> access trace exists -> MemoryConfidenceUpdated emitted -> alpha/beta correct |
| `test_workflow_steps.py` | Step lifecycle | define -> spawn with step_index -> running -> completed -> WorkflowStepCompleted emitted |
| `test_archival_decay.py` | Archival confidence decay | archive_thread -> MemoryConfidenceUpdated per entry -> alpha *= 0.8, beta *= 1.2 -> **verify hard floor: alpha >= 1.0, beta >= 1.0** |
| `test_dedup_dismissal.py` | Dismissed pair exclusion | Dismiss pair -> re-run dedup -> pair skipped |
| `test_contradiction_detection.py` | Contradiction detector | Two entries, overlapping domains, opposite polarity -> flagged |
| `test_step_continuation.py` | Step continuation (A1) | Colony completes workflow step -> follow_up_colony called with step_continuation text. Verify: text appended to summary, 30-min gate relaxed, depth >= 20 produces safety message |
| `test_transcript_search.py` | Transcript search (B1) | Colony with task/outputs exists -> transcript_search returns matching snippet. Test word-overlap fallback path. |

### Notes on test_step_continuation.py:

This tests Track A's code but that's fine — tests document contracts. Mock `queen.follow_up_colony` and verify it receives `step_continuation` parameter. Also verify:
- When `step_continuation` is truthy, the 30-min gate is skipped
- When `continuation_depth >= 20`, text is the safety message
- Template-backed steps include template_id in the text

### Notes on test_archival_decay.py:

Track A is adding the hard-floor clamp (`max(new_alpha, 1.0)`). Your test should verify that:
- After decay: alpha >= 1.0 and beta >= 1.0 (hard floor holds)
- Entry with alpha=1.0 before decay: alpha stays at 1.0 after decay (not 0.8)

---

## Acceptance Criteria

1. `transcript_search` tool returns relevant colony snippets for a keyword query
2. Tool description includes "when NOT to use" clause
3. `transcript_search` placed mid-list in TOOL_SPECS (not first, not last)
4. `KnowledgeAccessRecorded` events fire with correct `access_mode` for tool searches
5. All 8 new test files pass
6. Thompson Sampling test verifies distribution properties over 1000+ samples with seeded reproducibility
7. Existing tests still pass (`pytest` clean)
8. BM25 code-aware tokenizer splits camelCase (e.g., `getAgentStatus` -> `get`, `agent`, `status`)

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Run this before declaring done. All must pass.

## Overlap Rules

- **Track A owns `colony_manager.py`.** You add ONE line to the RoundRunner instantiation. Reread lines 344-358 after Track A lands. If Track A reordered things, adjust your line placement accordingly.
- **Track C touches `caste_recipes.yaml`** for the Queen system prompt. You touch it for tool lists. These are non-overlapping YAML sections. Both should reread before committing.
- **`bm25s` is a new dependency.** This requires operator approval per CLAUDE.md. If denied, the word-overlap fallback path must work correctly. Make sure both paths are tested.
