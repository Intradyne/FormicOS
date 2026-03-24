# Wave 31 Track C — Documentation + Edge Cases + Frontend Polish

**Track:** C
**Wave:** 31 — "Ship Polish"
**Coder:** You own this track. Read this prompt fully before writing any code.

---

## Reading Order (mandatory before any code changes)

1. `docs/decisions/040-wave-31-ship-polish.md` — All 6 decisions, especially D6 (Thompson Sampling tuning deferred)
2. `docs/waves/wave_31/wave_31_final_amendments.md` — Amendment 3 (document TS tradeoffs), Amendment 4 (document gamma-decay + archival decay tension), Amendment 5 (BM25 keyword fallback), Amendment 6 (document scoring formula)
3. `docs/waves/wave_31/wave_31_plan.md` — Track C sections (C1-C7), file ownership matrix
4. `CLAUDE.md` — hard constraints, prohibited alternatives
5. `pyproject.toml` — actual dependencies (you will need this for C2)

---

## Your Files

| File | Action |
|------|--------|
| `docs/KNOWLEDGE_LIFECYCLE.md` | **CREATE** — operator runbook |
| `CLAUDE.md` | **OWN** — rewrite to post-30 reality |
| `AGENTS.md` | **OWN** — update agent tools |
| `docs/decisions/040-wave-31-ship-polish.md` | **OWN** — already written, verify D6 is present |
| `src/formicos/surface/maintenance.py` | **OWN** — add confidence reset handler |
| `src/formicos/surface/app.py` | **OWN** — register confidence reset handler |
| `src/formicos/surface/knowledge_catalog.py` | **OWN** — BM25 keyword fallback for Qdrant-down |
| `frontend/src/components/knowledge-browser.ts` | **OWN** — empty state |
| `config/caste_recipes.yaml` | Queen system prompt only |
| `src/formicos/surface/queen_runtime.py` | first-run welcome text only (Track A owns the rest) |

## Do NOT Touch

- `surface/colony_manager.py` (Track A)
- `surface/projections.py` (Track A)
- `surface/memory_store.py` (Track A)
- `engine/runner.py` (Track B)
- `surface/runtime.py` (Track B)
- Any `tests/` files (Track B)

---

## Task 1: Knowledge Lifecycle Runbook (C1)

Create `docs/KNOWLEDGE_LIFECYCLE.md`. This is the "brilliant stranger" document — someone who didn't build FormicOS should understand the entire knowledge lifecycle after reading it.

Cover these 10 sections:

1. **Extraction:** Colony completes -> LLM extracts skills + experiences -> 4-axis security scan -> `MemoryEntryCreated` event
2. **Trust levels:** `scan_status` high/critical = rejected; safe/low/medium = candidate; source colony succeeded = verified
3. **Thread scoping:** Entries carry `thread_id`. Thread-scoped entries get 0.25 bonus in retrieval. Promote to workspace-wide via `MemoryEntryScopeChanged`
4. **Retrieval — Thompson Sampling composite scoring:**
   - Formula: `0.35*semantic + 0.25*thompson + 0.15*freshness + 0.15*status + 0.10*thread`
   - Signal ranges: semantic [0,1], thompson [0,1], freshness [0,1], status_bonus {-0.5 to 0.3} (bounded, not normalized), thread_bonus {0.0, 0.25} (bounded, not normalized)
   - Explain for operators: high-confidence entries are exploited, uncertain entries get explored, low-confidence entries fade
   - Note: status_bonus and thread_bonus are bounded but not [0,1] normalized. Formula works in practice. Normalization investigation deferred to Wave 32
5. **Confidence evolution:** Colony completes -> traces matched -> `MemoryConfidenceUpdated` emitted -> alpha/beta updated. Bayesian posterior converges with more observations
   - Prior: Beta(5.0, 5.0). Deliberately chosen to match legacy strength. Needs ~10 observations before data dominates prior
   - Monitoring: "If entries plateau at ~0.5 confidence after 20+ observations, consider reducing the prior in a future wave"
6. **Maintenance services:** Dedup (auto >= 0.98 cosine, LLM-confirmed [0.82, 0.98), dismissed pairs skipped). Stale sweep (90 days untouched). Contradiction detection (Jaccard domain overlap + opposite polarity). Scheduled daily
7. **Archival decay:**
   - Formula: `alpha *= 0.8, beta *= 1.2` with hard floor `alpha >= 1.0, beta >= 1.0`
   - **Known tension:** This formula is asymmetric — it pushes confidence downward, not just widening uncertainty. When gamma-decay ships in Wave 32, this formula must be redesigned. Document the three options: (a) symmetric decay `alpha *= 0.9, beta *= 0.9`, (b) lower-gamma variant for archived entries `gamma_archived=0.85` vs `gamma_active=0.98`, (c) subsumption into gamma-decay with hard floor
8. **How to trigger maintenance manually:** Queen tool `query_service(service_type="service:consolidation:dedup")`, etc.
9. **How to read confidence:** Beta posterior mean = `alpha/(alpha+beta)`. Uncertainty width = high alpha+beta means more data, narrower band. Explain the UI confidence bars
10. **How to promote entries:** From thread-scoped to workspace-wide via `MemoryEntryScopeChanged`

---

## Task 2: Updated CLAUDE.md (C2)

Rewrite CLAUDE.md to reflect post-30 reality.

**CRITICAL: Verify tech stack against actual imports and `pyproject.toml` before documenting.** The previous plan draft incorrectly claimed FastMCP was removed and sentence-transformers was replaced. Both are FALSE:
- FastMCP is still active (`mcp_server.py`, `app.py`)
- sentence-transformers is still a dependency (`pyproject.toml`, `app.py` fallback path) alongside the Qwen3-embedding sidecar
- Qdrant replaced LanceDB (confirmed)
- Lit Web Components confirmed

Run these checks yourself before writing the tech stack section:
```bash
grep -r "fastmcp\|FastMCP" src/ --include="*.py" -l
grep "sentence.transformers" pyproject.toml
grep "lancedb\|LanceDB" pyproject.toml src/ --include="*.py" -l
```

Changes to CLAUDE.md:
- Update tech stack to reflect actual dependencies
- Add knowledge system to architecture section
- Reference 48 events (not just "closed union")
- Add workflow threads and steps to workflow cadence
- Add Thompson Sampling and confidence to hard constraints context
- Update key paths table: add knowledge_catalog, maintenance, transcript search
- Add the "adding a Queen tool" pattern (define in `_queen_tools()` in queen_runtime.py, handle in `_handle_queen_tool_call()`)
- Add the "adding an agent tool" pattern (5 touch points: TOOL_SPECS in runner.py, TOOL_CATEGORY_MAP, RoundRunner.__init__, _execute_tool dispatch, callback factory in runtime.py, caste_recipes.yaml)

---

## Task 3: Updated AGENTS.md (C3)

Update AGENTS.md to reflect post-30 agent capabilities:
- List all agent tools: memory_search, memory_write, code_execute, query_service, spawn_colony, get_status, kill_colony, search_web, http_fetch, file_read, file_write, knowledge_detail, artifact_inspect, transcript_search (after Track B lands)
- Knowledge detail and artifact inspect descriptions
- Thread-scoped knowledge retrieval (after bug fix)
- Workflow step context in agent prompts
- Confidence evolution impact on retrieval

---

## Task 4: ADR-040 Verification (C4)

`docs/decisions/040-wave-31-ship-polish.md` is already written with D1-D6. Verify D6 is present and includes:
- Beta(5.0, 5.0) prior unchanged
- Gamma-decay deferred, gamma ~0.98 (not 0.95)
- Archival decay tension documented
- RRF deprioritized
- Wave 32 scope list

If D6 is complete, this task is done. Do not rewrite the existing decisions.

---

## Task 5: Edge Case Hardening (C5)

### C5a: Qdrant unavailability fallback (knowledge_catalog.py)

When Qdrant is down during knowledge search, the catalog raises. Add a projection-based keyword fallback. **Use word-overlap scoring, NOT raw recency** (Amendment 5).

```python
def _projection_keyword_fallback(
    self, query: str, workspace_id: str, top_k: int = 5,
) -> list[dict[str, Any]]:
    """BM25 keyword fallback when Qdrant is unavailable."""
    entries = [
        e for e in self._projections.memory_entries.values()
        if e.get("workspace_id") == workspace_id
        and e.get("status") in ("verified", "active", "candidate")
    ]
    if not entries:
        return []
    query_words = set(query.lower().split())
    scored = []
    for e in entries:
        text = f"{e.get('title', '')} {e.get('content', '')} {' '.join(e.get('domains', []))}".lower()
        entry_words = set(text.split())
        overlap = len(query_words & entry_words)
        if overlap > 0:
            scored.append((overlap, e))
    scored.sort(key=lambda x: -x[0])
    return [self._normalize_result(e, score=0.0, source="keyword_fallback") for _, e in scored[:top_k]]
```

Adapt `_normalize_result` to whatever the existing normalization function is. The key points:
- Tag results with `source: "keyword_fallback"` so agents know they're getting degraded results
- No new dependency — word-overlap only
- Only search verified/active/candidate entries

Wrap the existing Qdrant search call in a try/except that falls through to this fallback.

### C5b: Confidence reset handler (maintenance.py + app.py)

Add `make_confidence_reset_handler` to `maintenance.py`:

```python
def make_confidence_reset_handler(runtime: Runtime):  # noqa: ANN201
    """Factory: confidence reset for stuck entries."""

    async def _handle_confidence_reset(query_text: str, ctx: dict[str, Any]) -> str:
        from formicos.core.events import MemoryConfidenceUpdated  # noqa: PLC0415

        projections = runtime.projections
        threshold = 50  # total observations above prior
        reset_count = 0

        for entry_id, entry in projections.memory_entries.items():
            alpha = float(entry.get("conf_alpha", 5.0))
            beta = float(entry.get("conf_beta", 5.0))
            total_obs = (alpha + beta) - 10.0  # subtract prior (5.0 + 5.0)
            mean = alpha / (alpha + beta)

            if total_obs >= threshold and 0.35 <= mean <= 0.65:
                ws_id = entry.get("workspace_id", "")
                th_id = entry.get("thread_id", "")
                await runtime.emit_and_broadcast(
                    MemoryConfidenceUpdated(
                        seq=0,
                        timestamp=datetime.now(UTC),
                        address=f"{ws_id}/{th_id}" if ws_id else "system",
                        entry_id=entry_id,
                        colony_id="",
                        colony_succeeded=True,
                        old_alpha=alpha,
                        old_beta=beta,
                        new_alpha=5.0,
                        new_beta=5.0,
                        new_confidence=0.5,
                        workspace_id=ws_id,
                        thread_id=th_id,
                        reason="manual_reset",
                    ),
                )
                reset_count += 1

        return f"Reset {reset_count} entries to prior (5.0/5.0)"

    return _handle_confidence_reset
```

**Register in app.py** (lines 493-541 pattern). This is critical — without registration the handler is dead code:

1. Add to the import block (line 494):
```python
from formicos.surface.maintenance import (
    make_confidence_reset_handler,  # NEW
    make_contradiction_handler,
    make_dedup_handler,
    make_stale_handler,
)
```

2. Add registration (after line 513):
```python
service_router.register_handler(
    "service:consolidation:confidence_reset",
    make_confidence_reset_handler(runtime),
)
```

3. Add to the registration events loop (line 521):
```python
(
    "service:consolidation:confidence_reset",
    "Reset stuck entries to prior confidence",
),
```

4. Add to the maintenance loop services list (line 555) — **NO, do NOT add to the maintenance loop.** Confidence reset is manual-only, not scheduled. The operator triggers it via `query_service(service_type="service:consolidation:confidence_reset")`.

### C5c: Concurrent dedup + active extraction

VERIFIED: Already handled. Lines 103-106 of maintenance.py use `.get()` with None check. No fix needed. Document this in your completion report.

---

## Task 6: Knowledge Browser Empty State (C6)

Update `frontend/src/components/knowledge-browser.ts`. When no entries exist, show:

```
No knowledge entries yet.
Knowledge is extracted automatically when colonies complete.
Try running a colony, then come back here to see what was learned.
```

Include a subtle hint to trigger maintenance if entries exist but none are verified.

**Stretch goal (if time permits):** Gradient-opacity confidence bars — opaque at posterior mean, fading at 90% credible interval edges. Color-coded tier badge: gray (insufficient data, alpha+beta < 15), red (low, CI > 30%), yellow (moderate, 15-30%), green (high, CI < 15% and alpha+beta > 30). Natural-language hover: "High confidence (72%) -- based on 47 observations."

---

## Task 7: First-Run Queen Welcome (C7)

Update the Queen's first-run welcome message. Check both:
- `config/caste_recipes.yaml` (Queen system prompt section)
- `surface/queen_runtime.py` (if first-run text is hardcoded)

Add mentions of:
- Threads and goals: "Try setting a thread goal to organize your work"
- Workflow steps: "I can define workflow steps to break down complex projects"
- Knowledge: "I learn from each colony -- check the Knowledge tab after your first task completes"

**Track A owns queen_runtime.py for follow_up_colony, gate relaxation, and thread context truncation.** Your changes are limited to first-run welcome text. Non-overlapping section — but coordinate if in doubt.

---

## Acceptance Criteria

1. `docs/KNOWLEDGE_LIFECYCLE.md` exists, covers all 10 sections, passes "brilliant stranger" test
2. `CLAUDE.md` references 48 events, Qdrant, Thompson Sampling, workflow threads — **tech stack verified against pyproject.toml and actual imports**
3. `AGENTS.md` lists all agent tools including transcript_search
4. ADR-040 D6 is present and correct
5. Knowledge browser shows helpful empty state on fresh workspace
6. Confidence reset handler registered in app.py and callable via `query_service(service_type="service:consolidation:confidence_reset")`
7. Qdrant-down scenario returns keyword-fallback results (not empty), tagged with `source: "keyword_fallback"`
8. Concurrent dedup scenario verified as already handled (document in completion report)

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Run this before declaring done. All must pass.

## Overlap Rules

- **Track A owns `queen_runtime.py`** for follow_up_colony changes, gate relaxation, thread context truncation, and archival decay hard-floor. You touch it ONLY for first-run welcome text.
- **Track B touches `caste_recipes.yaml`** for agent tool lists. You touch it for Queen system prompt. Non-overlapping YAML sections. Reread before committing.
- **Track A owns `projections.py`.** Do not touch.
- **Track B will add transcript_search to AGENTS.md's tool count.** Coordinate: you write the base update, they adjust the count after their tool lands.
