# Wave 10 Planning Findings

**Date:** 2026-03-14
**Input:** Wave 9 validated (579 tests, 24 hard gates + 1 advisory, exit 0)
**Evaluator:** Opus planning session against orchestrator prompt

---

## 1. Findings

### What Wave 9 completion changes about Wave 10 planning

- **Model routing is now a live control surface.** `AgentTurnStarted.model` reflects the routed model. structlog captures every decision with reason codes. The routing table in `formicos.yaml` has commented Gemini entries. Adding a third provider is a fill-in-the-blank exercise — the slot exists.

- **Skills are live reusable assets with lifecycle.** Composite retrieval (semantic 0.50 + confidence 0.25 + freshness 0.25), quality gates (cosine dedup + source quality), confidence evolution (±0.1), and colony observation hooks all work. The skill bank is real — but it's sitting on LanceDB, which can't do payload-filtered search, doesn't support tenant indexing, and lacks the collection management needed for scaling past 100 entries.

- **Observation hooks produce data exhaust.** `colony_observation` structlog entries capture task, castes, strategy, rounds, quality, cost, skills retrieved/extracted, governance warnings, stall count. This is the data the experimentation engine will eventually consume — but the experimentation engine is premature until this data has actually accumulated over real production runs.

- **The frontend shows routing and skills — but is thin.** Routing badges, model column in colony detail, skill bank stats line. No skill browser, no detailed routing visualization, no colony creation flow improvement. The deferred T3 UI work from W9 is real debt.

- **Colony-scoped agent IDs prevent cross-contamination.** This was a W9 hardening win that removes a class of bugs for parallel colony execution.

- **Queen tool-calling on local models is advisory, not reliable.** W9 smoke treats Queen spawn as advisory. This is a model limitation, not a code limitation. Wave 10 should not try to "fix" this — it should work around it (Gemini Flash as a Queen fallback is the natural answer).

- **The VectorPort contract takes `query: str`, not a vector.** The adapter must embed internally. The Qdrant adapter needs an `embed_fn` injected at construction, same pattern as the existing LanceDB adapter. This is a critical implementation detail.

- **LanceDB is the weakest link in the stack.** Qdrant is already running in docker-compose, already healthy, already consuming resources — but the app doesn't use it. The skill lifecycle functions (confidence update, dedup gate, ingestion validation) all work through `VectorPort.search()` and `VectorPort.upsert()`. Swapping the adapter is the highest-leverage infrastructure change available.

- **`skillBankStats` is pre-fetched for snapshots, not projected state.** This is fine. It's recomputed from the vector store on each snapshot build. No event-sourcing purity issue to fix.

- **Skill confidence exists without opening the event contract.** Confidence is mutable metadata on vector store documents, updated by `skill_lifecycle.py`. This is the right design for alpha — it's derived, best-effort, and doesn't need event-sourced replay guarantees. Formalizing it as events would be premature.

---

## 2. Wave 10 Recommendation

### Theme: "Real Infrastructure"

**Why:** Wave 8 closed the loop. Wave 9 made routing and skills operational. Wave 10 replaces placeholder infrastructure with production infrastructure and catches the frontend up to the backend.

The system is currently paying the cost of running Qdrant (container memory, startup time, healthcheck) while using LanceDB (no filtering, no tenant indexing, embedded-only). It has commented Gemini entries in the routing table with no adapter to activate them. And the frontend is one wave behind the backend's capabilities.

These three things — Qdrant migration, Gemini adapter, and UI catch-up — are independent, low-risk, high-value, and directly build on Wave 9's validated foundation.

**Why NOT the experimentation engine:** The experimentation engine needs production routing data and a real skill bank to experiment on. This wave generates that data. Building the experiment framework before the data pipeline is real would produce an engine with nothing to measure. Ship Qdrant + Gemini, run real colonies for a sprint, then build experiments on top of actual data in Wave 11.

**Why NOT colony templates:** Templates require opening the 22-event union (new event types). The contract has been frozen since Phase 2 and every wave has respected that. Opening it for one feature is high risk for moderate value. Wait until Wave 11 when templates + experiment events can open the contract together.

---

## 3. Revised Wave 10 Plan

See `docs/waves/wave_10/plan.md` for the full dispatch document.

### Summary

Three terminals, strict file ownership, zero overlap:

| Terminal | Scope | Key deliverable |
|----------|-------|-----------------|
| T1 — Qdrant Migration | `adapters/vector_qdrant.py`, migration script, config flag | VectorPort backed by Qdrant with payload-filtered search |
| T2 — Gemini + Output Hardening | `adapters/llm_gemini.py`, `adapters/parse_defensive.py`, routing table | Third LLM provider + defensive tool-call parsing for all adapters |
| T3 — Skill Browser + Frontend Polish | `frontend/src/components/skill-browser.ts`, colony detail enhancements, REST endpoint | Operator can browse/filter skills, see 3-provider routing, auto-navigate on colony creation |

**Merge order: T1 → T2 → T3.** T1 first because the Qdrant adapter validates the VectorPort contract that everything depends on. T2 independent of T1 but merges second for sequencing discipline. T3 last because it surfaces data produced by T1 and T2.

**ADR prerequisites:** ADR-013 (Qdrant Migration) and ADR-014 (Gemini Provider) must be written before coding starts.

**New dependencies (justified):** `qdrant-client>=1.16` (T1), `json-repair>=0.30` (T2). Both earn their place against the 15K LOC budget.

**Contract status: FROZEN.** No event union changes. No port interface changes.

---

## 4. What Changed Because Wave 9 Is Real

| Earlier W10 draft assumption | Reality after W9 validation | Change |
|-----|-----|-----|
| Experimentation engine is the flywheel core | No production data exists to experiment on yet | Deferred to W11 — this wave generates the data |
| Colony templates via ContextUpdated events | Templates need first-class events (contract change) | Deferred to W11 when contract opens for multiple features |
| Skill dedup as meta-synthesis with HDBSCAN | < 50 skills exist; cosine > 0.92 gate is sufficient | Deferred batch dedup to W11+ when bank reaches 100+ |
| Bayesian confidence (Beta distribution) | ±0.1 clamped to [0.1, 1.0] works at current scale | Keep current model; upgrade when bank grows |
| `skillBankStats` needs event sourcing | Pre-fetched recomputation is fine | Lean into current approach |
| Routing table needs ML-based learning | Static heuristic + budget gate is working | Keep static; add Gemini as a third tier |
| Frontend is close enough | Skill browser was explicitly deferred; colony creation flow is broken | T3 catches up the frontend |

---

## 5. What Should Wait

| Deferred | Why | Earliest |
|----------|-----|----------|
| Colony templates | Requires event union opening. Need 3+ real patterns first. | Wave 11 |
| Experimentation engine | Needs production data from routing + skill systems this wave builds. | Wave 11 |
| `SkillConfidenceTierChanged` event | Requires contract change. Bundle with templates. | Wave 11 |
| Bayesian confidence (Beta distribution) | ±0.1 is sufficient at < 100 skills. | Wave 11 |
| LLM-gated dedup (Mem0 pattern) | Need 50+ skills and observed duplicate patterns. | Wave 11 |
| Meta-skill synthesis | Need clusters of 3+ related skills. Too few exist. | Wave 11+ |
| Qdrant hybrid search (BM25 + dense) | Overkill at < 1K entries. Dense-only sufficient. | Wave 12+ |
| Knowledge graph (SQLite adjacency) | No consumer yet. Flat skill bank covers alpha. | Wave 12+ |
| SGLang inference server | Multi-week infra swap, orthogonal. | Wave 12+ |
| Dashboard composition (Queen-composed layouts) | Needs more components, A2UI work, frontend maturity. | Wave 13+ |
| Qwen3-Embedding-0.6B upgrade | +18.7% MTEB over BGE-M3, but not blocking at < 1K entries. | Opportunistic |

---

## 6. Open Risks

1. **VectorPort `search()` takes `query: str`, not a vector.** The Qdrant adapter must embed the query text internally before calling `query_points()`. If the embedding endpoint (BGE-M3 on port 8009) is slow or down, search degrades. The LanceDB adapter has the same dependency via `embed_fn`. Mitigation: graceful degradation (return empty on failure).

2. **Qdrant v1.16+ API change.** The `search()` method was removed. All new code must use `query_points()`. If a coder reads old Qdrant docs or the research doc's earlier examples, they'll write broken code. Mitigation: ADR-013 explicitly calls this out.

3. **Gemini RECITATION blocks on code content.** Cannot be disabled via safety settings. Code-heavy agent workloads may trigger false positives. Mitigation: fallback chain (Gemini → local → Claude). structlog tracks `fallback_triggered`.

4. **`json-repair` is a new dependency.** It's well-maintained (1.3K stars, active releases) but adds to the dependency surface. Mitigation: the alternative is hand-rolled regex parsing, which is worse.

5. **Embedding model mismatch.** The current config says `Snowflake/snowflake-arctic-embed-s` (384-dim) but the docker-compose runs BGE-M3 (1024-dim). The Qdrant collection must be configured for whichever model is actually producing embeddings. Mitigation: ADR-013 specifies the adapter reads dimensions from config; the smoke test validates search works end-to-end.

6. **Two vector backends in pyproject.toml.** LanceDB stays as a fallback behind a feature flag this wave. This means two vector store dependencies in the lock file. Mitigation: remove LanceDB in Wave 11 after production validation.

7. **Frontend has no unit test framework.** T3 validation is `npm run build` + manual browser verification. Mitigation: acceptable for alpha; add Vitest in a future wave.
