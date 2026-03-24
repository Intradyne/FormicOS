# Wave 34 Track C — Hardening for Handoff

## Role

You are the quality gate. You write integration tests, stress tests, and evaluation scripts that prove the system works end-to-end. You also perform the final documentation pass that makes FormicOS understandable to someone who didn't build it. You run AFTER Teams 1, 2, and 3 have all landed (including Team 2's B7 follow-up).

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- **Wait for all 3 teams to land before starting integration tests.** Team 1 = tiered retrieval + co-occurrence scoring. Team 2 = Queen intelligence + proactive briefing + knowledge_feedback (B7). Team 3 = sub-types + frontend + demos. Your tests verify the full post-34 system.
- Read all ADRs (041-044) before writing tests. The invariants in ADR-044 D3 are your test specifications.
- You may touch any source file to fix validation failures, but document every fix.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `tests/integration/test_federation_roundtrip.py` | CREATE | Full two-instance federation test |
| `tests/integration/test_cooccurrence_thompson.py` | CREATE | Co-occurrence + Thompson stress test |
| `tests/integration/test_tiered_retrieval.py` | CREATE | Tiered retrieval threshold validation |
| `tests/integration/test_proactive_intelligence.py` | CREATE | Insight generation accuracy test |
| `tests/unit/test_replay_idempotency_53.py` | MODIFY | Extend for 53-event union + CRDT idempotency |
| `tests/unit/surface/test_mastery_restoration.py` | CREATE | Decay class evaluation |
| `pyproject.toml` | MODIFY | Pin remaining loose dependencies |
| `CLAUDE.md` | MODIFY | Full update for post-34 codebase |
| `AGENTS.md` | MODIFY | knowledge_feedback tool + sub-types + federation |
| `docs/KNOWLEDGE_LIFECYCLE.md` | MODIFY | Major update for all Wave 34 additions |
| `docs/OPERATORS_GUIDE.md` | CREATE | Operator field manual |

## Gating

Teams 1, 2, and 3 run in parallel. Team 2's B7 is a small follow-up after Team 1 lands. You run after ALL of them have landed and passed CI. Do not begin until confirmed.

## DO NOT TOUCH (unless fixing a validation failure)

- `surface/knowledge_catalog.py` — Team 1 owns
- `surface/knowledge_constants.py` — Team 1 owns
- `engine/runner.py` — Team 1 + Team 2 own
- `config/caste_recipes.yaml` — Team 2 owns
- `surface/proactive_intelligence.py` — Team 2 owns
- `surface/queen_runtime.py` — Team 2 owns
- `core/types.py` — Team 3 owns
- `surface/memory_extractor.py` — Team 3 owns
- `frontend/*` — Team 3 owns

---

## C1. Federation integration test (two-instance round-trip)

### What

Full federation round-trip with real projections. Not a unit test with mocks — instantiate two ProjectionStores, two FederationManagers with a mock transport, and verify the complete flow.

### Implementation

```python
async def test_federation_full_roundtrip():
    """Instance A creates entry, replicates to B, B uses in colony, sends feedback, A's trust updates."""

    # Setup: two instances with separate projection stores
    store_a = ProjectionStore()
    store_b = ProjectionStore()
    transport = MockFederationTransport()
    fed_a = FederationManager("inst-a", store_a, transport)
    fed_b = FederationManager("inst-b", store_b, transport)

    # Step 1: Instance A creates a knowledge entry
    # (emit MemoryEntryCreated, apply to store_a)

    # Step 2: A pushes to B
    pushed = await fed_a.push_to_peer("inst-b")
    assert pushed == 1

    # Step 3: B receives and applies
    pulled = await fed_b.pull_from_peer("inst-a")
    assert pulled == 1
    assert "entry-001" in store_b.memory_entries

    # Step 4: B uses entry in a colony (simulate)
    # (emit KnowledgeAccessRecorded for entry-001)

    # Step 5: B sends validation feedback to A
    await fed_b.send_validation_feedback("inst-a", "entry-001", success=True)

    # Step 6: A's trust in B is updated
    peer_b = fed_a._peers["inst-b"]
    assert peer_b.trust.alpha > 1.0  # success recorded

    # Step 7: Proactive insight generation
    # After trust drops below 0.5, verify briefing surfaces it
    for _ in range(20):
        peer_b.trust.record_failure()
    briefing = generate_briefing("ws-1", store_a)
    trust_insights = [i for i in briefing.insights if i.category == "federation"]
    assert len(trust_insights) > 0
    assert "declining" in trust_insights[0].title.lower() or "reliability" in trust_insights[0].detail.lower()

    # Step 8: Cycle prevention
    # A's own events should not be re-replicated back
    pushed_back = await fed_b.push_to_peer("inst-a")
    # Should not push A's own events back to A
```

---

## C2. Co-occurrence + Thompson interaction stress test

### What

100 queries against entries with co-occurrence clusters. Verify no cluster domination.

### Implementation

```python
async def test_cooccurrence_thompson_no_cluster_domination():
    """No single co-occurrence cluster takes all top-5 >30% of the time."""

    # Setup: 50 entries in 5 clusters of 10
    # Each cluster has strong internal co-occurrence (weight 5.0-8.0)
    # Between clusters: no co-occurrence

    # Run 100 queries with varying semantic relevance across clusters
    cluster_domination_count = {i: 0 for i in range(5)}

    for query_idx in range(100):
        results = await catalog.search_tiered(
            query=f"test query {query_idx}",
            workspace_id="ws-test",
            top_k=5,
            tier="full",
        )
        # Check if all 5 results are from the same cluster
        clusters_in_results = set(entry_to_cluster[r["id"]] for r in results)
        if len(clusters_in_results) == 1:
            cluster_domination_count[clusters_in_results.pop()] += 1

    # No cluster should dominate >30% of queries
    for cluster_id, count in cluster_domination_count.items():
        assert count <= 30, f"Cluster {cluster_id} dominated {count}/100 queries"
```

---

## C3. Replay idempotency with 53-event union

### What

Extend existing replay tests to cover all 53 event types. Double-apply CRDT events to verify idempotency.

### Key checks

- All 53 event types deserialize and apply to projections without error
- Applying the same CRDT event twice produces the same projection state (idempotency)
- G-Counter merge after double-apply: pairwise max is idempotent
- MemoryEntryMerged double-apply: target entry updated once, source rejected once

---

## C4. Tiered retrieval threshold validation

### What

Run 100 representative queries from actual colony transcripts. Measure tier distribution.

### Implementation

```python
async def test_tiered_retrieval_distribution():
    """Validate that tiered retrieval thresholds match expected distribution."""

    # Use queries extracted from recent colony tasks
    queries = _extract_representative_queries(projections, n=100)

    tier_counts = {"summary": 0, "standard": 0, "full": 0}
    total_tokens_tiered = 0
    total_tokens_full = 0

    for query in queries:
        results_tiered = await catalog.search_tiered(query, workspace_id="ws-test", tier="auto")
        results_full = await catalog.search_tiered(query, workspace_id="ws-test", tier="full")

        tier_used = results_tiered[0]["tier"] if results_tiered else "full"
        tier_counts[tier_used] += 1

        total_tokens_tiered += sum(_estimate_tokens(str(r)) for r in results_tiered)
        total_tokens_full += sum(_estimate_tokens(str(r)) for r in results_full)

    # Target: >35% resolve at summary tier
    summary_pct = tier_counts["summary"] / 100
    assert summary_pct > 0.35, f"Only {summary_pct:.0%} resolved at summary (target: >35%)"

    # Verify token savings
    savings = 1 - (total_tokens_tiered / max(total_tokens_full, 1))
    assert savings > 0.20, f"Only {savings:.0%} token savings (target: >20%)"
```

If summary resolution is below 35%, adjust the escalation thresholds in `search_tiered()` and re-run.

---

## C5. Proactive intelligence accuracy test

### What

Generate a projection state with known signals. Verify each rule fires correctly. Verify false positive rate <10%.

### Implementation

```python
def test_proactive_intelligence_accuracy():
    """All 7 rules fire at correct conditions. False positive rate <10%."""

    # Scenario 1: declining confidence
    store = _build_store_with_declining_entry()
    briefing = generate_briefing("ws-test", store)
    assert any(i.category == "confidence" for i in briefing.insights)

    # Scenario 2: contradiction
    store = _build_store_with_contradiction()
    briefing = generate_briefing("ws-test", store)
    contradictions = [i for i in briefing.insights if i.category == "contradiction"]
    assert len(contradictions) == 1
    assert contradictions[0].severity == "action_required"

    # Scenario 3: clean state (no issues)
    store = _build_clean_store()
    briefing = generate_briefing("ws-test", store)
    assert len(briefing.insights) == 0  # No false positives

    # ... (test all 7 rules)

    # False positive rate: run against 100 random clean states
    false_positives = 0
    for _ in range(100):
        store = _build_random_clean_store()
        briefing = generate_briefing("ws-test", store)
        if len(briefing.insights) > 0:
            false_positives += 1
    assert false_positives < 10, f"False positive rate: {false_positives}%"
```

---

## C6. Mastery-restoration evaluation

### What

The open research question: do decay classes solve the "permanent knowledge decays after 6 months" problem?

### Implementation

```python
def test_mastery_restoration_evaluation():
    """Evaluate whether decay classes prevent knowledge loss for long-lived entries."""

    # Entry with decay_class="stable", historically alpha=25
    # Simulate 180 days without observation
    gamma = GAMMA_RATES["stable"]  # 0.995
    elapsed = 180.0
    gamma_eff = gamma ** min(elapsed, MAX_ELAPSED_DAYS)

    decayed_alpha = gamma_eff * 25.0 + (1 - gamma_eff) * PRIOR_ALPHA
    # At stable: 0.995^180 ≈ 0.407, alpha ≈ 0.407*25 + 0.593*5 ≈ 13.14

    # Simulate single re-observation (success) — immediate, so elapsed=0
    # gamma_eff for re-observation is 1.0 (no time has passed since re-access)
    restored_alpha = decayed_alpha + 1.0
    # After re-obs: 13.14 + 1.0 = 14.14

    # Compare: gap between original (25) and restored
    gap_pct = (25.0 - restored_alpha) / 25.0

    # If gap < 20%, decay classes are sufficient
    if gap_pct < 0.20:
        # FINDING: decay classes solve the problem
        # Document: stable gamma preserves enough signal
        pass
    else:
        # FINDING: restoration bonus needed for Wave 35
        # Document: how much bonus would close the gap
        restoration_bonus_needed = 25.0 - restored_alpha
        pass

    # Report finding
    # Expected values:
    # decayed_alpha ≈ 13.14, restored_alpha ≈ 14.14, gap ≈ 43.4%
    # Verdict: restoration bonus recommended for Wave 35
    print(f"Stable decay after 180 days: alpha {25.0} → {decayed_alpha:.2f}")
    print(f"After re-observation: {restored_alpha:.2f}")
    print(f"Gap: {gap_pct:.1%}")
    print(f"Verdict: {'Decay classes sufficient' if gap_pct < 0.20 else 'Restoration bonus recommended'}")
```

---

## C7. Dependency audit and pinning

### What

Pin all remaining loosely-pinned dependencies to `>=current,<next_major`.

### Implementation

1. Run `uv pip list` to get current resolved versions
2. Check `pyproject.toml` for any unpinned or loosely-pinned deps
3. Pin each to `>=resolved_version,<next_major`
4. Run `uv sync` to verify resolution
5. Run full test suite to verify compatibility

---

## C8. Final documentation pass

### CLAUDE.md

Update for the complete post-34 codebase:
- Event union: 53 (ADR-gated)
- Knowledge system: add tiered retrieval, co-occurrence scoring (6 signals), budget-aware assembly, knowledge_feedback tool, entry sub-types
- Proactive intelligence: 7 deterministic rules, Queen integration, MCP resource, REST endpoint
- Queen: system-intelligent prompt with briefing injection
- Composite weights: 0.38/0.25/0.15/0.10/0.07/0.05 (ADR-044)
- Key paths: add proactive_intelligence.py
- Common patterns: add "Tiered retrieval usage" and "Proactive intelligence rules"

### KNOWLEDGE_LIFECYCLE.md

Major update:
- Tiered retrieval: auto-escalation logic, tier definitions, token budgets
- Co-occurrence scoring: activation, sigmoid normalization, weight 0.05
- Budget-aware context assembly: scope percentages, early-exit
- knowledge_feedback tool: agent-level quality signals
- Entry sub-types: classification, filtering
- Proactive intelligence: 7 rules with conditions and actions

### AGENTS.md

- Add knowledge_feedback to coder/reviewer/researcher tool lists
- Add sub-type classification guidance
- Update Queen section for system intelligence capabilities

### OPERATORS_GUIDE.md (NEW)

Create a comprehensive operator field manual:
- Getting started: workspace creation, thread setup, colony lifecycle
- Knowledge system: how entries are created, scored, decayed, merged, federated
- Proactive briefing: what each insight means and what to do about it
- Federation: adding peers, trust evolution, replication filters
- Troubleshooting: common issues, diagnostic queries, maintenance handlers
- Configuration: model assignments, budget limits, workspace config

---

## Validation

After all tests and docs:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Produce a final summary following the Wave 33.5 Team 3 format:
```
Wave 34 Smoke Test Results:
  Pass: X/19
  Fixed: Y/19
  Known issues: Z

Integration Tests:
  Federation round-trip: pass/fail
  Co-occurrence stress: pass/fail (cluster domination rate)
  Tiered retrieval: pass/fail (summary tier %, token savings %)
  Proactive intelligence: pass/fail (false positive rate)
  Replay idempotency: pass/fail

Evaluation:
  Mastery restoration: decay classes sufficient / restoration bonus needed

Documentation:
  CLAUDE.md: sections updated
  KNOWLEDGE_LIFECYCLE.md: sections added
  AGENTS.md: changes
  OPERATORS_GUIDE.md: created (estimated pages)

Final CI:
  ruff: pass/fail
  pyright: X errors
  lint_imports: X violations
  pytest: X passed, Y failed
```
