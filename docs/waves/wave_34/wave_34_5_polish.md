# Wave 34.5 -- Orchestrator Dispatch: B7 Landing + Validation + Wave 35 Foundations

## Context

Wave 34 Tracks A and B (B1-B6) have landed. 1,887 tests passing, CI clean.
One designed gap remains: B7 (knowledge_feedback dispatch in runner.py) was
hard-gated on Track A and is ready to implement. Track C (validation,
integration tests, documentation) has not run yet.

This polish pass has three jobs:
1. Land B7 (15 lines, closes the agent-to-knowledge feedback loop)
2. Run the Track C validation/hardening pass
3. Plant three small foundations that Wave 35 builds on directly

Wave 35's themes are: multi-colony orchestration (Queen dispatches parallel
colonies), self-maintaining knowledge (proactive insights trigger automatic
colonies), knowledge distillation (archivist colonies synthesize entry
clusters), and explainable decisions (composite score breakdowns visible to
operators and agents). Every foundation item below is < 30 lines of code
and establishes a convention or data structure that Wave 35 consumes.

Use 3 parallel coder teams. Budget: 1-2 sessions each.

## Context Documents

Read before dispatching coders:
- docs/decisions/044-cooccurrence-scoring.md (approved)
- docs/waves/wave_34/wave_34_plan.md (Track C smoke test items 1-19)
- surface/proactive_intelligence.py (KnowledgeInsight model)
- surface/knowledge_catalog.py (_composite_key, search_tiered)
- engine/runner.py (post-Track-A state, TOOL_SPECS, _execute_tool)
- config/caste_recipes.yaml (post-B1-B6 state, Queen + worker prompts)

---

## Team 1: B7 Landing + Score Breakdown Metadata

### Task 1a: Land B7 -- knowledge_feedback tool dispatch

The caste_recipes.yaml already lists knowledge_feedback in coder/reviewer/
researcher tool arrays (Team 2 added this). The runner.py dispatch is the
missing wiring.

Add to engine/runner.py (~15 lines total):

1. TOOL_SPECS entry for knowledge_feedback (after transcript_search, ~line
   1496):
```python
"knowledge_feedback": {
    "name": "knowledge_feedback",
    "description": "Report whether a retrieved knowledge entry was useful. "
                   "Positive feedback strengthens confidence. Negative feedback "
                   "signals staleness. Use when an entry was notably helpful or wrong.",
    "parameters": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "string", "description": "The knowledge entry ID"},
            "helpful": {"type": "boolean", "description": "True if useful, false if wrong/outdated"},
            "reason": {"type": "string", "description": "Brief explanation (optional)"},
        },
        "required": ["entry_id", "helpful"],
    },
}
```

2. TOOL_CATEGORY_MAP entry: `"knowledge_feedback": ToolCategory.memory`

3. Dispatch case in _execute_tool:
```python
elif tool_name == "knowledge_feedback":
    return await self._knowledge_feedback_fn(
        entry_id=arguments["entry_id"],
        helpful=arguments["helpful"],
        reason=arguments.get("reason", ""),
    )
```

4. Add _knowledge_feedback_fn to RoundRunner.__init__() callback parameters.

Add to surface/runtime.py -- make_knowledge_feedback_fn():
```python
def make_knowledge_feedback_fn(runtime, colony_id, workspace_id):
    async def _knowledge_feedback(entry_id, helpful, reason=""):
        entry = runtime.projections.memory_entries.get(entry_id)
        if not entry:
            return f"Entry {entry_id} not found"
        if helpful:
            await _emit_confidence_update(
                runtime, entry, colony_id, workspace_id,
                succeeded=True, reason="agent_feedback_positive",
            )
            return f"Positive feedback recorded for {entry_id}"
        else:
            entry["prediction_error_count"] = entry.get("prediction_error_count", 0) + 1
            await _emit_confidence_update(
                runtime, entry, colony_id, workspace_id,
                succeeded=False, reason="agent_feedback_negative",
            )
            return f"Negative feedback recorded for {entry_id}: {reason}"
    return _knowledge_feedback
```

Wire make_knowledge_feedback_fn into the callback assembly in app.py or
wherever RoundRunner callbacks are constructed (follow the pattern used by
make_transcript_search_fn).

### Task 1b: Attach composite score breakdown to search results

This is the Wave 35 explainability foundation. When _composite_key() scores
an entry, the per-signal breakdown is computed but discarded -- only the
final composite float survives. Preserving it as metadata costs ~25 lines
and enables click-to-explain without any UI work.

**Confirmed: the intermediate signal values are NOT stored on the item dict.**
They are computed inside `_keyfn` (knowledge_catalog.py lines 409-429) and
discarded after the sort returns the composite float. The coder must add
~10 lines inside `_keyfn` to write the values back onto the item dict before
returning the composite.

**Step 1: Store signals inside _keyfn (knowledge_catalog.py:409-429)**

Inside the `_keyfn` closure (or whatever the composite scoring function is
named post-Wave-34), after computing each signal value and before returning
the composite, write the intermediate values onto the item dict:

```python
def _keyfn(item):
    # ... existing signal computations ...
    # (semantic, thompson, freshness, status_bonus, thread_bonus, cooc
    #  are all local variables computed above)

    composite = -(
        W["semantic"] * semantic
        + W["thompson"] * thompson
        + W["freshness"] * freshness
        + W["status"] * status_bonus
        + W["thread"] * thread_bonus
        + W["cooccurrence"] * cooc
    )

    # Store intermediate values for score breakdown (Wave 34.5 addition)
    item["_semantic_sim"] = semantic
    item["_thompson_draw"] = thompson
    item["_freshness"] = freshness
    item["_status_bonus"] = status_bonus
    item["_thread_bonus"] = thread_bonus
    item["_cooccurrence"] = cooc
    item["_composite"] = -composite  # store as positive value

    return composite
```

**Step 2: Assemble _score_breakdown after sorting**

After the sort at line 365 (or equivalent post-Wave-34), annotate top_k
results:

```python
for item in merged[:top_k]:
    item["_score_breakdown"] = {
        "semantic": item.get("_semantic_sim", 0.0),
        "thompson": item.get("_thompson_draw", 0.0),
        "freshness": item.get("_freshness", 0.0),
        "status": item.get("_status_bonus", 0.0),
        "thread": item.get("_thread_bonus", 0.0),
        "cooccurrence": item.get("_cooccurrence", 0.0),
        "composite": item.get("_composite", 0.0),
        "weights": dict(COMPOSITE_WEIGHTS),
    }
```

The _score_breakdown dict flows through to:
- The agent's memory_search results (at standard and full tiers)
- The MCP formicos://knowledge/{id} resource
- The AG-UI KNOWLEDGE_ACCESSED event
- The frontend knowledge-browser hover panel (Wave 35 will render it)

For now, include _score_breakdown in the "full" tier format only (don't
bloat summary tier). In _format_tier(), add to the full tier:
```python
if tier == "full":
    item["score_breakdown"] = r.get("_score_breakdown", {})
```

### Acceptance criteria:
- knowledge_feedback tool callable by coder/reviewer/researcher agents
- helpful=true -> MemoryConfidenceUpdated with reason="agent_feedback_positive"
- helpful=false -> prediction_error_count incremented + confidence update
- Full-tier search results include score_breakdown with all 6 signal values
  and the weight configuration
- _keyfn stores all intermediate signal values on the item dict
- pytest clean, pyright clean

---

## Team 2: Proactive Intelligence Hardening + Self-Maintenance Foundation

### Task 2a: Add suggested_colony to KnowledgeInsight model

Wave 35's self-maintaining knowledge connects proactive insights to
automatic colony dispatch. The KnowledgeInsight model currently has
suggested_action as a plain string. Adding a structured suggested_colony
field establishes the convention that insights can recommend specific
colony configurations.

In surface/proactive_intelligence.py, extend KnowledgeInsight:

```python
class SuggestedColony(BaseModel):
    """Colony configuration that could resolve this insight.
    Wave 35 will add auto-dispatch. Wave 34.5 just structures the data."""
    task: str
    caste: str           # "researcher" | "archivist" | "coder"
    strategy: str        # "sequential" | "stigmergic"
    max_rounds: int = 5
    rationale: str = ""

class KnowledgeInsight(BaseModel):
    severity: str
    category: str
    title: str
    detail: str
    affected_entries: list[str]
    suggested_action: str
    suggested_colony: SuggestedColony | None = None  # NEW
```

Then update the 7 insight generation rules to populate suggested_colony
where applicable:

- _rule_contradiction: suggested_colony with caste="researcher", task=
  "Investigate contradiction between Entry A and Entry B. Determine which
  is correct based on current evidence."
- _rule_coverage_gap: suggested_colony with caste="researcher", task=
  "Research {domain} to fill knowledge gap. Current queries return only
  unvalidated results."
- _rule_stale_cluster: suggested_colony with caste="researcher", task=
  "Re-validate the {domain} knowledge cluster. Recent retrievals show low
  semantic relevance."
- _rule_merge_opportunity: No colony needed (deterministic merge).
  suggested_colony = None.
- _rule_confidence_decline: No colony needed (observational).
  suggested_colony = None.
- _rule_federation_trust_drop: No colony needed (operator decision).
  suggested_colony = None.
- _rule_federation_inbound: No colony needed (operator review).
  suggested_colony = None.

3 of 7 rules get suggested_colony. The data is available in the MCP
briefing resource and REST endpoint immediately. Wave 35 adds the
auto-dispatch mechanism.

### Task 2b: Add distillation_candidate flag to co-occurrence clusters

Wave 35's knowledge distillation triggers when a co-occurrence cluster
reaches density thresholds. The maintenance loop already decays
co-occurrence weights. Add a lightweight check that flags clusters
ready for distillation.

In surface/maintenance.py, in the co-occurrence decay pass (the
make_cooccurrence_decay_handler function), after decay and pruning,
add a cluster density scan:

```python
# After pruning, identify distillation candidates
# A cluster is a connected component of entries with co-occurrence weight > 2.0
# A cluster is a distillation candidate when:
#   - It has >= 5 entries
#   - Average weight > 3.0
#   - No entry in the cluster is already a distillation product
clusters = _find_cooccurrence_clusters(
    runtime.projections.cooccurrence_weights, min_weight=2.0,
)
candidates = [
    c for c in clusters
    if len(c) >= 5 and _avg_cluster_weight(c, runtime.projections) > 3.0
]
runtime.projections.distillation_candidates = candidates
```

Add `distillation_candidates: list[list[str]]` to ProjectionStore (list
of entry ID lists). This is a projection-only derived field -- ephemeral,
rebuilt on every maintenance pass.

Surface the count in the ProactiveBriefing stats:
```python
distillation_candidates: int  # count of clusters ready for synthesis
```

This is ~20 lines of code. Wave 35 adds the archivist colony dispatch
that consumes these candidates.

### Acceptance criteria:
- 3 of 7 insight rules include suggested_colony with caste + task + strategy
- 4 of 7 have suggested_colony = None (correct -- not every insight needs a colony)
- Briefing MCP resource includes suggested_colony data
- distillation_candidates populated after maintenance loop
- ProactiveBriefing includes distillation_candidates count
- pytest clean, pyright clean

---

## Team 3: Wave 34 Validation + Documentation Pass

This is the Track C work from the wave_34_plan.md. Run the full validation
suite and final documentation pass.

**Gating note:** Smoke test items 1-4 and 6-19 can run immediately. Item 5
(knowledge_feedback tool verification) requires Team 1's B7 dispatch to have
landed. Start with everything else; verify item 5 after Team 1 completes.

### Task 3a: Run all 19 smoke test items from wave_34_plan.md

Execute each smoke test item from the plan. Document results as pass/fail/
fixed. Fix any failures in place.

Key validation areas:
1. Tiered retrieval: verify auto-escalation thresholds produce summary-tier
   resolution for typical queries. Log tier distribution.
2. Co-occurrence scoring: verify invariants 5 and 6 from ADR-044 D3. Run
   the 6-invariant test suite.
3. Queen proactive intelligence: give the Queen a task in a domain with a
   known contradiction. Verify she mentions the conflict before spawning.
4. Proactive briefing: generate briefing for a workspace with 50+ entries.
   Verify <100ms, no LLM calls, insights sorted by severity.
5. knowledge_feedback tool (AFTER Team 1 B7 lands): agent calls with
   helpful=false, verify prediction_error_count increments and confidence
   update emits with reason="agent_feedback_negative".
6. Confidence visualization: verify gradient bars render with correct tier
   badges. Hover shows decay class and federation source.
7. Federation dashboard: verify peer trust table populates from projections.
8. Entry sub-types: verify filter works on API and MCP resource.

### Task 3b: Integration tests

Write and run:
- Federation round-trip (two-instance, mock transport, real CRDT merge,
  trust evolution, proactive insight fires on trust drop)
- Co-occurrence + Thompson stress test (100 queries, no cluster domination
  >30%)
- Replay idempotency with 53 events (double-apply CRDT idempotency)
- Tiered retrieval threshold validation (100 queries, >35% summary, >20%
  token savings)
- Proactive intelligence accuracy (all 7 rules fire correctly, false
  positive rate <10% on clean states)

### Task 3c: Mastery-restoration evaluation

Run the evaluation from the plan. Determine whether decay classes are
sufficient or whether a restoration bonus is needed for Wave 35.

Corrected math (re-observation is immediate, elapsed=0, gamma_eff=1.0):

For stable (gamma=0.995) entry with alpha=25 after 180 days:
  gamma_eff = 0.995^180 = 0.407
  decayed_alpha = 0.407 * 25 + 0.593 * 5 = 13.14
  re-observation (elapsed=0, gamma_eff=1.0): 13.14 + 1.0 = 14.14
  gap: (25 - 14.14) / 25 = 43.4%

This gap is > 20%, so the recommendation will likely be "restoration bonus
needed for Wave 35." Document the finding with the exact computation.

### Task 3d: Dependency audit

Pin all remaining loose dependencies to >=current,<next_major.

### Task 3e: Final documentation pass

Update all docs for the complete post-34.5 codebase:

**CLAUDE.md:**
- 6 scoring signals with ADR-044 weights
- Tiered retrieval (auto/summary/standard/full)
- Budget-aware context assembly (scope percentages)
- Proactive intelligence (7 rules, Queen integration, suggested_colony)
- knowledge_feedback tool on worker castes
- Entry sub-types
- Score breakdown metadata on full-tier results
- distillation_candidates in projections (foundation for Wave 35)

**KNOWLEDGE_LIFECYCLE.md:**
- Tiered retrieval with auto-escalation
- Co-occurrence scoring activation (sigmoid, 0.05 weight)
- Budget-aware assembly with scope budgets
- knowledge_feedback as agent-level quality signal
- Proactive intelligence rules with suggested_colony
- Distillation candidate identification

**AGENTS.md:**
- knowledge_feedback tool on coder/reviewer/researcher (not archivist)
- Score breakdown in full-tier results
- Sub-type classification
- Queen system intelligence capabilities

**OPERATORS_GUIDE.md** (create if doesn't exist):
- Getting started walkthrough
- Knowledge system explanation (creation, scoring, decay, merge, federation)
- Proactive briefing interpretation (what each insight means, what to do)
- Federation setup and monitoring
- Troubleshooting common issues
- Configuration reference

### Acceptance criteria:
- All 19 smoke test items verified (pass/fail/fixed count documented)
- All integration tests pass
- Mastery-restoration evaluation documented with exact computation
- Dependencies pinned
- All docs accurate for post-34.5 codebase
- pytest clean, pyright clean, lint_imports clean

---

## Integration check (after all 3 teams)

- Run full pytest (target: >1900 tests)
- Run pyright src/ (0 errors)
- Run lint_imports.py (0 violations)
- Verify knowledge_feedback round-trip: agent calls -> confidence update
  emitted -> projection updated -> proactive briefing reflects change
- Verify score_breakdown present in full-tier memory_search results
  (all 6 signal values + weights dict)
- Verify _keyfn stores intermediate values on item dict (inspect a
  search result dict for _semantic_sim, _thompson_draw, etc.)
- Verify suggested_colony present in briefing insights for contradiction/
  coverage_gap/stale_cluster rules
- Verify distillation_candidates populated after maintenance loop
- Verify documentation consistency: CLAUDE.md event count matches events.py,
  AGENTS.md tool lists match caste_recipes.yaml, KNOWLEDGE_LIFECYCLE.md
  weights match knowledge_constants.py, ADR-044 weights match code
