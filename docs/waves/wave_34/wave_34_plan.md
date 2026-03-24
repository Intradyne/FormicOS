# Wave 34 Plan -- Ship Ready

**Wave:** 34 -- "Ship Ready"
**Theme:** FormicOS stops being a framework and becomes a product. The Queen gains proactive intelligence -- she knows what the knowledge system knows, what it doesn't, and what the operator should pay attention to. Retrieval becomes token-efficient via tiered auto-escalation. Co-occurrence data activates as a scoring signal. The operator gets confidence visualization, a federation dashboard, and a proactive briefing that has opinions. After Wave 34, someone who didn't build FormicOS can run it, trust it, and explain it.

**Prerequisite:** Wave 33.5 landed. Worker caste prompts rewritten with tool awareness, system awareness, and collaboration context. Retrieval results annotated with confidence tiers and federation source indicators. All 19 Wave 33 smoke test items validated. Documentation synced. Wave 33 fully operational: credential scanning, StructuredError across all surfaces, MCP resources/prompts, CRDTs, federation, trust, conflict resolution, co-occurrence collection, transcript harvest.

**Contract changes:** No new event types (union stays at 53). Co-occurrence activates as 6th scoring signal (ADR-044). `KnowledgeInsight` model added for proactive intelligence. Queen prompt major rewrite. No new dependencies.

**ADR required before coder dispatch:**
- ADR-044: Composite weight rebalancing with co-occurrence signal. Analyze collected data, determine weight, rebalance all 6 signals.

---

## Why this wave

After Wave 33.5, the agents are system-aware (they know about confidence, decay classes, and federation) and the retrieval results carry metadata. But two fundamental gaps remain:

First, the Queen is the smartest agent in the system and the least informed about it. She plans from the task and the thread context. She doesn't know the knowledge store has a contradiction about error handling conventions. She doesn't know that the peer instance's testing knowledge has been declining in trust. She doesn't know that the last 5 colonies all retrieved the same 3 entries, suggesting a knowledge bottleneck. Wave 33.5 gave the workers system awareness; Wave 34 gives the Queen system intelligence.

Second, retrieval is still expensive and undifferentiated. Every query returns full content at ~200 tokens per result. The NeuroStack analysis showed 40-50% of queries resolve at a cheap tier. At the system's operating rate, tiered retrieval saves ~50,000 tokens/day.

Third, the operator's relationship with the system is reactive. They ask, it answers. The accumulated signals (prediction errors, co-occurrence clusters, confidence trajectories, contradictions, federation trust) are numbers in a database. Nobody connects the dots. The operator should sit down and the system should say "here's what changed, here's what needs attention, and here's what I'd recommend."

---

## Track A: Retrieval Intelligence + Co-occurrence Activation

### A1. Tiered retrieval with auto-escalation

The headline efficiency feature. Start cheap, escalate when coverage is thin. Based on NeuroStack's `tiered_search()`, adapted for FormicOS.

**Three tiers:**

| Tier | Tokens/result | Content | When used |
|------|--------------|---------|-----------|
| Summary | ~15-20 | title + one-line summary + confidence tier annotation (from 33.5) | Default. Resolves ~40-50% of queries |
| Standard | ~75 | title + summary + content excerpt (200 chars) + domains + decay class | Thin coverage at summary tier |
| Full | ~200+ | full content + metadata + provenance + co-occurrence context | Insufficient at standard tier |

**Auto-escalation** in `knowledge_catalog.py`:

```python
def search_tiered(self, query, workspace_id, thread_id="", top_k=5, tier="auto"):
    results = self._search_thread_boosted(query, workspace_id, thread_id, top_k=top_k * 2)

    if tier != "auto":
        return self._format_tier(results[:top_k], tier)

    unique_sources = len(set(r.get("source_colony_id", "") for r in results))
    top_score = max((r.get("_semantic_sim", 0.0) for r in results), default=0.0)

    if unique_sources >= 2 and top_score > 0.5:
        return self._format_tier(results[:top_k], "summary")
    if unique_sources >= 1 and top_score > 0.35:
        return self._format_tier(results[:top_k], "standard")
    return self._format_tier(results[:top_k], "full")
```

The confidence tier annotations from Wave 33.5 (HIGH/MODERATE/LOW/EXPLORATORY/STALE) are included at every tier level. The agent always knows how much to trust a result, even at the cheapest tier.

Wire into `memory_search` tool dispatch in `runner.py`. Add `detail` parameter to tool spec so agents can request specific tiers when needed.

### A2. Budget-aware context assembly

Explicit token budget allocation per knowledge scope. Prevents any single scope from dominating.

| Tier | Budget % | Content |
|------|----------|---------|
| Task-relevant knowledge | 35% | Via tiered retrieval |
| Recent observations | 20% | Colony observations from current thread |
| Structured facts | 15% | Domain tags, co-occurrence clusters, metadata |
| Round history | 15% | Compressed summaries from prior rounds |
| Scratch memory | 15% | Colony-local scratch entries |

Token estimation: 1 token per 4 characters. Early-exit when tier budget exhausted.

### A3. Co-occurrence scoring activation (requires ADR-044)

Wave 33 collected co-occurrence data silently. Wave 34 activates it as the 6th signal in `_composite_key()`.

**Estimated rebalanced weights** (subject to empirical validation from Wave 33 data):

```python
WEIGHTS = {
    "semantic": 0.38,       # was 0.40
    "thompson": 0.25,       # unchanged
    "freshness": 0.15,      # unchanged
    "status": 0.10,         # was 0.12
    "thread": 0.07,         # was 0.08
    "cooccurrence": 0.05,   # NEW
}
```

Sigmoid normalization bounds the co-occurrence boost (NeuroStack pattern). Monitor for cluster domination in production logs.

**6 validation invariants** (4 existing + 2 new):
- Invariant 5: Entries frequently co-accessed in successful colonies score higher than identical entries without co-occurrence history
- Invariant 6: Co-occurrence boost bounded -- no single cluster takes all top-5 slots more than 30% of the time

### Track A files

| File | Changes |
|------|---------|
| `surface/knowledge_catalog.py` | `search_tiered()`, `_format_tier()`, co-occurrence signal in `_composite_key()` |
| `engine/runner.py` | Wire tiered search, budget-aware assembly, `detail` param on memory_search |
| `docs/decisions/044-cooccurrence-scoring.md` | ADR (orchestrator writes before dispatch) |

---

## Track B: Proactive Intelligence + Operator Experience

This is where Wave 35's vision lands early. The accumulated signals become actionable insights.

### B1. Queen prompt redesign with system intelligence

The Queen prompt is the most important 85 lines in the codebase and the most disconnected from the system's capabilities. Wave 33.5 gave the worker castes system awareness. Wave 34 gives the Queen system intelligence -- she doesn't just know what tools she has, she knows the state of the knowledge system and can reason about it.

**What the Queen currently lacks awareness of:**
- Decay classes (she doesn't know some knowledge is permanent vs ephemeral)
- Co-occurrence clusters (she doesn't know which knowledge travels together)
- Prediction errors (she doesn't know which knowledge is drifting)
- Federation (she doesn't know about peer instances or trust scores)
- Confidence trajectories (she doesn't know what's gaining or losing trust)
- Contradictions (she doesn't know when knowledge conflicts exist)
- The transcript harvest (she doesn't know that colonies extract more than she sees)
- Tiered retrieval (she doesn't know to request different detail levels)
- StructuredError (she doesn't know error responses carry recovery hints)

**The redesigned prompt should add:**

System state awareness section (brief, before the tool list):
```
## What you know about the knowledge system
Before planning any task, consider:
- memory_search returns confidence-annotated results. HIGH means well-validated.
  EXPLORATORY means the system is testing this entry -- treat with skepticism.
- Knowledge entries have decay classes: ephemeral (task-specific), stable
  (domain knowledge), permanent (verified facts). You can ask the archivist to
  classify entries.
- The system tracks co-occurrence -- entries frequently used together in
  successful colonies form clusters. memory_search results from the same cluster
  are likely complementary.
- Prediction errors accumulate when retrieved entries have low semantic relevance.
  High prediction error counts signal stale or misclassified knowledge.
- Federation peers share knowledge with trust discounting. Entries from peers
  carry a trust score. Low trust means the peer's track record is unproven.
```

Proactive planning section (after team composition, before rules):
```
## Before spawning a colony
1. Call memory_search for the task domain. Check confidence tiers on results.
2. If results are EXPLORATORY or STALE, warn the operator: "Our knowledge
   on X is limited/outdated. This colony may need more rounds."
3. If contradictions exist in the knowledge base (two high-confidence entries
   with opposite conclusions), flag them: "Knowledge conflict detected on X.
   Recommend resolving before proceeding."
4. If a peer instance has relevant domain coverage (check the Agent Card),
   consider whether their knowledge should be pulled first.
5. If the last N colonies in this thread all retrieved the same entries,
   the knowledge base may have a bottleneck. Consider a research colony
   to expand coverage.
```

Updated tool guidance for new capabilities:
```
## Tool updates
- memory_search now returns tiered results with confidence annotations.
  Default is auto-tier. Use detail="full" when you need complete content.
- query_service("credential_sweep") runs a retroactive credential scan.
- query_service("cooccurrence_decay") maintains co-occurrence weights.
```

The Queen prompt should stay under 120 lines. Density over length. Every sentence should change behavior.

### B2. Proactive intelligence briefing

The colony brief from the original Wave 34 plan, evolved from a static summary into an opinionated system briefing. This is the "partner, not tool" upgrade.

```python
class KnowledgeInsight(BaseModel):
    """A single proactive insight for the operator or Queen."""
    severity: str          # "info" | "attention" | "action_required"
    category: str          # "confidence" | "contradiction" | "federation" | "coverage" | "staleness"
    title: str             # one-line summary
    detail: str            # 2-3 sentence explanation
    affected_entries: list[str]  # entry IDs
    suggested_action: str  # what to do about it

class ProactiveBriefing(BaseModel):
    """System intelligence briefing, assembled from projection signals."""
    workspace_id: str
    generated_at: str
    insights: list[KnowledgeInsight]

    # Stats (from original colony brief)
    total_entries: int
    entries_by_status: dict[str, int]
    avg_confidence: float
    prediction_error_rate: float
    active_clusters: int
    federation_summary: dict[str, Any]
```

**Insight generation rules** (deterministic, no LLM needed):

| Signal | Condition | Insight |
|--------|-----------|---------|
| Confidence decline | Entry alpha dropped >20% in 7 days | "Entry X confidence declining -- 4 recent colonies found it unhelpful" |
| Contradiction | Two verified entries, opposite polarity, domain overlap >0.3 | "Knowledge conflict: Entry A says X, Entry B says not-X. Both high-confidence." |
| Federation trust drop | Peer trust score dropped below 0.5 | "Peer Y's reliability declining -- last 5 entries used from them had mixed outcomes" |
| Coverage gap | memory_search returns only EXPLORATORY results for a query seen 3+ times | "Repeated queries about X return only unvalidated knowledge. Consider a research colony." |
| Stale cluster | Co-occurrence cluster where all entries have prediction_error_count > 3 | "The {domain} knowledge cluster is drifting. Entries are being retrieved but aren't semantically relevant." |
| Merge opportunity | 2+ entries with cosine > 0.85 that the dedup handler hasn't caught (below 0.98 threshold) | "Entries A and B are similar (87% overlap) but not auto-merged. Review for manual merge." |
| Federation inbound | New entries received from peer in domain with no local coverage | "Peer Z sent 8 entries about {domain} -- you have no local knowledge here. Review?" |

**Surfaced at four levels:**
- MCP resource: `formicos://briefing/{workspace_id}` -- external agents consume it
- REST endpoint: `GET /api/v1/workspaces/{id}/briefing`
- WebSocket: included in initial state snapshot, refreshed hourly
- Queen context: injected into the Queen's prompt assembly when she's responding. She sees the top 3 insights (by severity) before planning any colony.

**Queen integration is the key differentiator.** The briefing isn't just for the operator to read -- the Queen reads it too. When the operator says "build me a REST API" and the briefing says "knowledge conflict on error handling conventions," the Queen says "I noticed a conflict in our knowledge about error handling -- Entry A recommends X, Entry B recommends Y. Which approach should I follow?" This is the proactive intelligence vision realized.

### B3. Knowledge entry sub-types

Enrich skill/experience taxonomy for better filtering. Based on NeuroStack's entity types.

```python
class EntrySubType(StrEnum):
    # Under "skill"
    technique = "technique"
    pattern = "pattern"
    anti_pattern = "anti_pattern"
    # Under "experience"
    decision = "decision"
    convention = "convention"
    learning = "learning"
    bug = "bug"
```

The transcript harvest (Wave 33) already classifies as bug/decision/convention/learning -- map to sub_types. Structured extraction prompt updated to assign sub_types. Filterable across all surfaces.

### B4. Confidence visualization

The Wave 31 stretch goal, now with mature data to visualize.

**Default view:** Gradient-opacity confidence bar (opaque at posterior mean, fading at 90% credible interval edges). Color-coded tier badge (gray/red/yellow/green). Natural-language summary: "High confidence (72%) -- 47 observations, stable decay class."

**Hover view:** Numeric mean +/- credible interval, observation count, decay class, federation source, co-occurrence cluster membership, prediction error count.

**Power user panel:** Raw alpha/beta, sparkline history, merged_from provenance, peak_alpha tracking.

### B5. Federation dashboard

Peer trust table, sync status, conflict log, knowledge flow metrics. All from projections -- PeerConnection state, conflict resolution results, federation event counts.

### B6. End-to-end demo scenarios

Three complete walkthroughs (documented + integration tested):

**Scenario 1: "Build me an email validator with tests"** -- full loop from operator goal through knowledge extraction, tiered retrieval in future colonies, proactive briefing showing confidence growth.

**Scenario 2: "Federation knowledge sharing"** -- two instances, trust evolution, validation feedback, proactive insight when trust drops.

**Scenario 3: "Knowledge lifecycle"** -- entry creation through decay classes, merge, archival burst, recovery, prediction errors, stale sweep. The proactive briefing surfaces each transition.

### B7. Agent-level knowledge quality feedback

The 33.5 enriched results give agents confidence annotations. Wave 34 closes the feedback loop: agents can explicitly report whether retrieved entries were useful.

Add a lightweight `knowledge_feedback` tool to worker castes (coder, reviewer, researcher):

```python
"knowledge_feedback": {
    "name": "knowledge_feedback",
    "description": "Report whether a retrieved knowledge entry was useful. Positive feedback strengthens the entry. Negative feedback signals staleness. Use when an entry was notably helpful or notably wrong.",
    "parameters": {
        "entry_id": {"type": "string"},
        "helpful": {"type": "boolean"},
        "reason": {"type": "string", "description": "Brief explanation (optional)"}
    }
}
```

Implementation: `helpful=true` emits a `MemoryConfidenceUpdated` with reason="agent_feedback_positive". `helpful=false` increments the entry's prediction_error_count and emits a confidence update with reason="agent_feedback_negative". This is a stronger signal than colony success/failure because it's entry-specific.

The caste prompts (already updated in 33.5) tell agents to use this when entries are notably helpful or wrong. The Queen's proactive briefing can surface entries with consistently negative feedback: "Entry X received negative feedback from 3 agents this week -- review for accuracy."

Add to worker caste tool lists in caste_recipes.yaml. NOT added to the Queen (she doesn't consume knowledge entries directly).

### Track B files

| File | Changes |
|------|---------|
| `config/caste_recipes.yaml` | Queen prompt rewrite, knowledge_feedback tool added to worker castes |
| `surface/proactive_intelligence.py` | NEW (~300 LOC): KnowledgeInsight, ProactiveBriefing, insight generation rules |
| `surface/colony_brief.py` | NEW or absorbed into proactive_intelligence.py |
| `core/types.py` | EntrySubType StrEnum, sub_type field on MemoryEntry |
| `surface/memory_extractor.py` | Sub-type in extraction + harvest prompts |
| `surface/mcp_server.py` | Briefing resource, sub_type filter, knowledge_feedback tool |
| `engine/runner.py` | knowledge_feedback tool dispatch |
| `surface/routes/api.py` | Briefing REST endpoint |
| `surface/routes/knowledge_api.py` | sub_type filter parameter |
| `surface/queen_runtime.py` | Inject top insights into Queen prompt assembly |
| `frontend/src/components/knowledge-browser.ts` | Confidence visualization |
| `frontend/src/components/federation-dashboard.ts` | NEW: peer trust, sync, conflicts |
| `frontend/src/components/proactive-briefing.ts` | NEW: insight display with severity badges |
| `docs/demos/demo-email-validator.md` | NEW |
| `docs/demos/demo-federation.md` | NEW |
| `docs/demos/demo-knowledge-lifecycle.md` | NEW |

---

## Track C: Hardening for Handoff

### C1. Federation integration test (two-instance round-trip)

Full federation round-trip with real projections: create on A, replicate to B, B uses in colony, validation feedback to A, trust evolution verified. Include proactive insight generation: after trust drops below 0.5, verify the briefing surfaces "Peer Y's reliability declining."

### C2. Co-occurrence + Thompson interaction stress test

100 queries against entries with co-occurrence clusters. Verify no single cluster dominates top-5 more than 30% of the time. Verify the sigmoid normalization bounds the co-occurrence contribution.

### C3. Replay idempotency with 53-event union

All 53 event types including CRDT and MemoryEntryMerged. Double-apply test verifies CRDT merge idempotency.

### C4. Tiered retrieval threshold validation

Run 100 representative queries from actual colony transcripts. Measure:
- What percentage resolve at summary tier (target: 40-50%)
- What percentage need escalation to standard
- What percentage need full
- Token savings vs always-full baseline

If summary resolution is below 30%, adjust thresholds. This is empirical validation of the NeuroStack-derived thresholds against FormicOS's actual query distribution.

### C5. Proactive intelligence accuracy test

Generate a projection state with known signals (contradictions, declining confidence, stale clusters, federation trust drop). Run the insight generation. Verify each rule fires at the correct conditions and produces actionable insights. Verify false positive rate (insights generated when no action is needed) is below 10%.

### C6. Mastery-restoration evaluation

The open research question from the implementation unknowns research. With decay classes now live (33.5 validated), evaluate whether they're sufficient:

1. Identify entries where decay_class="stable" has alpha > 20 historically but current alpha < 10 (decayed)
2. Simulate single re-observation
3. Compare: does the stable gamma (0.995) preserve enough signal, or does the entry effectively restart?
4. If the gap is > 20%, recommend the restoration bonus for Wave 35

If decay classes solve the problem, document the finding and close the research question.

### C7. Dependency audit and pinning

Pin all remaining loosely-pinned dependencies to `>=current,<next_major`.

### C8. Final documentation pass

Every document reflects the post-Wave-34 codebase including proactive intelligence, tiered retrieval, co-occurrence scoring, Queen redesign, knowledge_feedback tool, sub-types, and confidence visualization.

**CLAUDE.md**, **KNOWLEDGE_LIFECYCLE.md**, **AGENTS.md**, **OPERATORS_GUIDE.md** (new or major update) -- all accurate and complete.

### Track C files

| File | Changes |
|------|---------|
| `tests/integration/test_federation_roundtrip.py` | NEW |
| `tests/integration/test_cooccurrence_thompson.py` | NEW |
| `tests/integration/test_tiered_retrieval.py` | NEW |
| `tests/integration/test_proactive_intelligence.py` | NEW |
| `tests/unit/test_replay_idempotency_53.py` | Extend |
| `tests/unit/surface/test_mastery_restoration.py` | NEW (evaluation) |
| `pyproject.toml` | Dependency pinning |
| `CLAUDE.md` | Full rewrite |
| `AGENTS.md` | Update for knowledge_feedback + sub-types |
| `docs/KNOWLEDGE_LIFECYCLE.md` | Major update |
| `docs/OPERATORS_GUIDE.md` | NEW |

---

## File Ownership Matrix

| File | Track A | Track B | Track C |
|------|---------|---------|---------|
| `surface/knowledge_catalog.py` | **OWN** | -- | -- |
| `engine/runner.py` | **OWN** (tiered + budget) | knowledge_feedback dispatch | -- |
| `config/caste_recipes.yaml` | -- | **OWN** (Queen + feedback tool) | -- |
| `surface/proactive_intelligence.py` | -- | **CREATE** | -- |
| `surface/queen_runtime.py` | -- | **MODIFY** (insight injection) | -- |
| `core/types.py` | -- | **MODIFY** (EntrySubType) | -- |
| `surface/mcp_server.py` | -- | **MODIFY** | -- |
| `frontend/src/components/*` | -- | **OWN** (3 components) | -- |
| `docs/demos/*` | -- | **CREATE** (3 scenarios) | -- |
| `docs/decisions/044-*.md` | -- | -- | -- |
| All test files | -- | -- | **OWN** |
| All documentation | -- | -- | **OWN** |

**Overlap:** `engine/runner.py` is owned by Track A (tiered search wiring + budget assembly) but Track B adds knowledge_feedback dispatch. Different functions, same file. Track B's change is a ~15-line tool dispatch addition. Track A should land first since budget assembly restructures the context path.

---

## Sequencing

**Track A starts immediately.** Tiered retrieval and budget assembly are independent. A3 (co-occurrence) waits for ADR-044.

**Track B starts immediately.** Queen prompt rewrite and proactive intelligence are independent of retrieval changes. B7 (knowledge_feedback) is a small addition that pairs with the Queen redesign.

**Track C starts when A and B have draft implementations.** Integration tests verify the full system, including tiered retrieval thresholds and proactive insight accuracy. The documentation pass is last.

Can split subagent teams within tracks:
- Track B: one for Queen prompt + proactive intelligence (B1+B2), one for sub-types + visualization (B3+B4), one for federation dashboard + demos (B5+B6), one for knowledge_feedback (B7)
- Track C: one for integration tests (C1-C5), one for evaluation + deps + docs (C6-C8)

---

## What Wave 34 Does NOT Include

- **No multi-hop federation.** Still two-instance.
- **No knowledge distillation.** Synthesizing higher-order patterns from multiple entries across instances.
- **No visual workflow composition.** The canvas-based spatial workflow editor. Wave 35 candidate.
- **No operator behavior learning.** Implicitly adapting to operator preferences. Wave 35 candidate.
- **No token-level AG-UI streaming.** Still summary-at-turn-end.
- **No Docker MCP Gateway.**
- **No automatic sub-type classification on existing entries.** New entries get sub-types, existing default to None.
- **No mastery-restoration implementation unless C6 evaluation proves necessary.**

---

## ADR-044 Outline

**Title:** Composite Scoring with Co-occurrence -- Weight Rebalancing

**D1:** Co-occurrence activates at ~0.05 weight. Sigmoid normalization bounds contribution.

**D2:** Rebalanced weights (empirically adjusted from Wave 33 data): semantic 0.38, thompson 0.25, freshness 0.15, status 0.10, thread 0.07, cooccurrence 0.05. Sum: 1.00.

**D3:** 6 invariants. Existing 4 preserved. New: co-occurrence boosts co-accessed entries; sigmoid prevents cluster domination.

**D4:** Weights tunable per workspace via WorkspaceConfigChanged. Default values in knowledge_constants.py. First time weights become operator-configurable.

---

## Smoke Test (Post-Integration)

1. `memory_search("async Python testing")` resolves at summary tier. Structlog shows tier=summary. Result includes confidence annotations from 33.5.
2. Same query with `detail="full"` returns full content at tier=full.
3. Context assembly for colony with 4000-token budget: no scope exceeds its 35% allocation.
4. Co-occurrence entries rank higher than non-co-occurring equivalents. Invariant 5 passes.
5. Queen receives task in domain with known contradiction. She says "I noticed a conflict in our knowledge about X -- Entry A says Y, Entry B says not-Y."
6. Proactive briefing for workspace with 50+ entries returns in <100ms. Includes insights sorted by severity. No LLM calls.
7. `formicos://briefing/{workspace_id}` MCP resource returns structured insights.
8. Agent calls `knowledge_feedback(entry_id, helpful=false, reason="outdated")`. Entry's prediction_error_count increments. Confidence update emitted.
9. Knowledge browser shows gradient-opacity confidence bars. Green badge on verified entries. Hover shows decay class and federation source.
10. Federation dashboard shows peer trust, sync status, conflict log.
11. Entry sub-type filter: `/api/v1/knowledge?sub_type=bug` returns only bug entries.
12. Federation round-trip integration test passes. Proactive insight fires when trust drops.
13. Tiered retrieval validation: 100 queries, >35% resolve at summary tier.
14. Proactive intelligence accuracy: all rules fire correctly, false positive rate <10%.
15. Replay idempotency with 53 events including double-apply CRDT idempotency.
16. Co-occurrence + Thompson stress: no cluster dominates top-5 >30% of the time.
17. Demo scenario 1 (email validator): end-to-end with proactive briefing.
18. All docs accurate for post-34 codebase.
19. `pytest` all pass. `pyright src/` 0 errors. `lint_imports.py` 0 violations.

---

## Priority Stack (if scope must be cut)

| Priority | Item | Track | Rationale |
|----------|------|-------|-----------|
| 1 | A1: Tiered retrieval | A | 3-4x token cost reduction |
| 2 | B1: Queen prompt redesign | B | Highest behavioral impact per line changed |
| 3 | B2: Proactive intelligence | B | The "partner not tool" upgrade |
| 4 | A3: Co-occurrence activation | A | Wave 33 data collection wasted without this |
| 5 | C1: Federation integration test | C | Federation shipped in 33 without e2e testing |
| 6 | C8: Final documentation pass | C | "Ship ready" means someone else understands it |
| 7 | B4: Confidence visualization | B | Operator trust requires visual understanding |
| 8 | A2: Budget-aware context assembly | A | Pairs with tiered retrieval |
| 9 | B7: Agent knowledge_feedback tool | B | Closes the agent-to-knowledge feedback loop |
| 10 | B6: End-to-end demos | B | Product validation |
| 11 | B3: Entry sub-types | B | Taxonomy enrichment |
| 12 | B5: Federation dashboard | B | Visualization, not blocking |
| 13 | C4: Tiered retrieval threshold validation | C | Empirical calibration |
| 14 | C5: Proactive intelligence accuracy test | C | Quality assurance |
| 15 | C2: Co-occurrence + Thompson stress | C | Degenerate pattern detection |
| 16 | C3: Replay idempotency 53 | C | Fundamental invariant |
| 17 | C6: Mastery-restoration evaluation | C | Research question, may defer |
| 18 | C7: Dependency audit | C | Hygiene |

---

## After Wave 34

The system has: intelligent knowledge extraction (transcript harvest, inline dedup, credential scanning), self-improving retrieval (co-occurrence, prediction errors, Thompson exploration, tiered auto-escalation, budget-aware assembly), proactive intelligence (the Queen and the operator both see system-generated insights about knowledge health, contradictions, trust, and coverage gaps), agent-level knowledge feedback (agents explicitly report entry quality), secure knowledge management (credential scanning, redaction), federated learning (two instances with trust discounting and conflict resolution), self-guiding API surfaces (structured errors, MCP resources, next_actions), and visual operator tools (confidence bars, federation dashboard, proactive briefing).

The Queen doesn't just plan from the task -- she plans from what the system knows about itself. The operator doesn't just see numbers -- they see opinions about what needs attention. The agents don't just consume knowledge -- they report on its quality.

An operator can run it. An external agent can operate it. A peer instance can federate with it. A new developer can understand it.

That is ship ready.
