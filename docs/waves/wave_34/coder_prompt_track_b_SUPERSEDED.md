# Wave 34 Track B — Proactive Intelligence + Operator Experience

## Role

You are building the proactive intelligence system, redesigning the Queen prompt, adding knowledge sub-types, confidence visualization, federation dashboard, demo scenarios, and the agent knowledge_feedback tool. This is the "partner, not tool" upgrade.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/044-cooccurrence-scoring.md` — you don't implement co-occurrence scoring, but the Queen prompt needs to reference it.
- Read the Wave 33.5 caste prompt rewrites in `config/caste_recipes.yaml` (lines 96-230) — your Queen rewrite follows the same density-over-length style.
- **B7 (knowledge_feedback tool dispatch in runner.py) MUST NOT begin until Track A's runner.py changes have landed and been verified.** Track A restructures the context formatting pipeline. knowledge_feedback hooks into that pipeline. Implement B7 last, against Track A's landed code.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `config/caste_recipes.yaml` | MODIFY | Queen prompt rewrite (lines 9-88), knowledge_feedback tool added to coder/reviewer/researcher tool arrays |
| `surface/proactive_intelligence.py` | CREATE | ~300 LOC: KnowledgeInsight, ProactiveBriefing, 7 insight generation rules |
| `core/types.py` | MODIFY | EntrySubType StrEnum, sub_type field on MemoryEntry |
| `surface/memory_extractor.py` | MODIFY | Sub-type in extraction + harvest prompts |
| `surface/mcp_server.py` | MODIFY | Briefing resource, sub_type filter on knowledge resource, knowledge_feedback tool |
| `surface/queen_runtime.py` | MODIFY | Inject top 3 insights into Queen prompt assembly |
| `surface/routes/api.py` | MODIFY | Briefing REST endpoint |
| `surface/routes/knowledge_api.py` | MODIFY | sub_type filter parameter |
| `engine/runner.py` | MODIFY | knowledge_feedback tool dispatch (**GATED on Track A landing**) |
| `frontend/src/components/knowledge-browser.ts` | MODIFY | Confidence visualization |
| `frontend/src/components/federation-dashboard.ts` | CREATE | Peer trust, sync, conflicts |
| `frontend/src/components/proactive-briefing.ts` | CREATE | Insight display with severity badges |
| `docs/demos/demo-email-validator.md` | CREATE | End-to-end demo scenario 1 |
| `docs/demos/demo-federation.md` | CREATE | End-to-end demo scenario 2 |
| `docs/demos/demo-knowledge-lifecycle.md` | CREATE | End-to-end demo scenario 3 |
| `tests/unit/surface/test_proactive_intelligence.py` | CREATE | Insight generation rule tests |
| `tests/unit/surface/test_knowledge_feedback.py` | CREATE | Feedback tool tests |
| `tests/unit/surface/test_entry_subtypes.py` | CREATE | Sub-type mapping tests |

## DO NOT TOUCH

- `surface/knowledge_catalog.py` — Track A owns (tiered retrieval, co-occurrence scoring)
- `surface/knowledge_constants.py` — Track A owns (COMPOSITE_WEIGHTS)
- All integration/stress test files — Track C owns
- `CLAUDE.md`, `KNOWLEDGE_LIFECYCLE.md`, `AGENTS.md` — Track C owns (final doc pass)
- `pyproject.toml` — Track C owns (dependency pinning)

## Overlap rules

- `engine/runner.py`: Track A owns for tiered search + budget assembly. **You add knowledge_feedback dispatch ONLY AFTER Track A has landed.** Your change is ~15 lines: add to TOOL_SPECS, TOOL_CATEGORY_MAP, and dispatch case. Do NOT restructure the context assembly — Track A handles that.

---

## B1. Queen prompt redesign

### What

The Queen goes from "strategic coordinator" (80 lines, line 9-88) to "strategically informed coordinator" (~100-120 lines). She gains awareness of decay classes, co-occurrence, prediction errors, federation, contradictions, tiered retrieval, and the proactive briefing.

### Where

`config/caste_recipes.yaml` — replace the `system_prompt` block for the queen caste (lines 9-88).

### What to add (3 new sections woven into the existing prompt)

**System state awareness section** (insert before the tool list, ~15 lines):
```
## What you know about the knowledge system
- memory_search returns confidence-annotated results. HIGH = well-validated.
  EXPLORATORY = the system is testing this entry. Treat with skepticism.
- Knowledge entries have decay classes: ephemeral (task-specific), stable
  (domain knowledge), permanent (verified facts).
- The system tracks co-occurrence: entries frequently used together in
  successful colonies form clusters. Results from the same cluster are
  likely complementary.
- Prediction errors accumulate when retrieved entries have low semantic
  relevance. High counts signal stale or misclassified knowledge.
- Federation peers share knowledge with trust discounting. Low trust
  means the peer's track record is unproven.
```

**Proactive planning section** (after team composition, before rules, ~10 lines):
```
## Before spawning a colony
1. Check memory_search for the task domain. Note confidence tiers.
2. If results are EXPLORATORY or STALE, warn the operator.
3. If contradictions exist (two high-confidence entries with opposite
   conclusions), flag them before proceeding.
4. If a peer instance has relevant domain coverage, consider pulling
   their knowledge first.
5. If the last N colonies all retrieved the same entries, the knowledge
   base may have a bottleneck. Consider a research colony.
```

**Tool updates** (add to existing tool guidance, ~5 lines):
```
- memory_search now supports detail="auto"|"summary"|"standard"|"full".
  Default auto starts cheap and escalates. Use detail="full" only when
  you need complete content for a specific entry.
- query_service("credential_sweep") runs retroactive credential scan.
- query_service("cooccurrence_decay") maintains co-occurrence weights.
```

### Constraints

- Stay under 120 lines total. Density over length.
- Preserve the existing prompt's tone and structure. Add to it, don't rewrite from scratch.
- Do NOT change the Queen's tool array (line 91). Tool additions happen through other mechanisms.
- YAML multi-line format: `|` (literal block scalar).

### Tests

- Queen prompt length: 80-120 lines
- Contains "decay class" or "decay_class"
- Contains "co-occurrence" or "cooccurrence"
- Contains "prediction error"
- Contains "federation" or "peer"
- Contains "contradiction"
- Contains "tiered" or "detail="
- Does NOT exceed 120 lines

---

## B2. Proactive intelligence briefing

### What

Seven deterministic insight rules that surface actionable knowledge system intelligence. No LLM needed. Injected into Queen context and exposed via MCP resource + REST endpoint.

### Where

Create `surface/proactive_intelligence.py` (~300 LOC).

### Implementation

```python
"""Proactive intelligence: deterministic insight generation from projection signals."""

from __future__ import annotations
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Any


class KnowledgeInsight(BaseModel):
    severity: str = Field(..., description="info | attention | action_required")
    category: str = Field(..., description="confidence | contradiction | federation | coverage | staleness | merge | inbound")
    title: str = Field(..., description="One-line summary")
    detail: str = Field(..., description="2-3 sentence explanation")
    affected_entries: list[str] = Field(default_factory=list)
    suggested_action: str = Field(default="")


class ProactiveBriefing(BaseModel):
    workspace_id: str
    generated_at: str
    insights: list[KnowledgeInsight]
    total_entries: int
    entries_by_status: dict[str, int]
    avg_confidence: float
    prediction_error_rate: float
    active_clusters: int
    federation_summary: dict[str, Any] = Field(default_factory=dict)


def generate_briefing(workspace_id: str, projections: Any) -> ProactiveBriefing:
    """Generate a proactive briefing from current projection state.

    All rules are deterministic. No LLM calls. Should complete in <100ms.
    """
    insights: list[KnowledgeInsight] = []
    entries = {eid: e for eid, e in projections.memory_entries.items()
               if e.get("workspace_id") == workspace_id}

    insights.extend(_rule_confidence_decline(entries))
    insights.extend(_rule_contradiction(entries))
    insights.extend(_rule_federation_trust_drop(projections))
    insights.extend(_rule_coverage_gap(entries))
    insights.extend(_rule_stale_cluster(entries, projections.cooccurrence_weights))
    insights.extend(_rule_merge_opportunity(entries))
    insights.extend(_rule_federation_inbound(entries, projections))

    # Sort by severity (action_required > attention > info)
    severity_order = {"action_required": 0, "attention": 1, "info": 2}
    insights.sort(key=lambda i: severity_order.get(i.severity, 3))

    # Compute stats
    ...

    return ProactiveBriefing(
        workspace_id=workspace_id,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        total_entries=len(entries),
        ...
    )
```

**Seven insight rules:**

1. **Confidence decline** (`_rule_confidence_decline`): Entry alpha dropped >20% in 7 days. Severity: attention. Check `last_confidence_update` and compare `conf_alpha` trajectory.

2. **Contradiction** (`_rule_contradiction`): Two verified entries with opposite polarity and domain overlap >0.3 (using Jaccard on domains lists). Severity: action_required.

3. **Federation trust drop** (`_rule_federation_trust_drop`): Any peer's trust score dropped below 0.5. Check `PeerConnection` trust scores in projections. Severity: attention.

4. **Coverage gap** (`_rule_coverage_gap`): memory_search returns only EXPLORATORY results for a pattern seen 3+ times in recent prediction_error_queries. Severity: info (first occurrence), attention (3+ occurrences).

5. **Stale cluster** (`_rule_stale_cluster`): Co-occurrence cluster where all entries have `prediction_error_count > 3`. Use cooccurrence_weights to identify clusters (connected components with weight > 0.5). Severity: attention.

6. **Merge opportunity** (`_rule_merge_opportunity`): 2+ entries with similar titles/domains that the dedup handler hasn't merged (cosine between 0.82-0.98). Heuristic: entries in the same domain with similar word overlap in titles. Severity: info.

7. **Federation inbound** (`_rule_federation_inbound`): New entries from peer in domain where local coverage is zero or all EXPLORATORY. Check entries with foreign observation sources. Severity: info.

### Queen integration

In `surface/queen_runtime.py` — at the prompt assembly point (lines 282-303), inject top 3 insights:

```python
briefing = generate_briefing(workspace_id, self._runtime.projections)
top_insights = briefing.insights[:3]
if top_insights:
    insight_text = "\n".join(
        f"[{i.severity.upper()}] {i.title}: {i.detail}" for i in top_insights
    )
    # Inject into Queen's context before her planning
    messages.insert(context_position, {
        "role": "system",
        "content": f"## System Intelligence Briefing\n{insight_text}",
    })
```

### Surface exposure

- **MCP resource:** `formicos://briefing/{workspace_id}` in mcp_server.py (after existing resources, line 467+)
- **REST endpoint:** `GET /api/v1/workspaces/{workspace_id}/briefing` in routes/api.py (line 273+)

### Tests

- Workspace with declining-confidence entry → "confidence" insight generated
- Workspace with two contradictory verified entries → "contradiction" insight, severity=action_required
- Workspace with no contradictions → no contradiction insight (false positive check)
- Briefing generation completes in <100ms for 500 entries
- Insights sorted by severity (action_required first)
- Queen context includes top 3 insights when briefing has them
- MCP resource returns valid ProactiveBriefing JSON
- REST endpoint returns 200 with structured briefing

---

## B3. Knowledge entry sub-types

### Where

`core/types.py` — add `EntrySubType` StrEnum near existing enums (line 315-336 area). Add `sub_type` field to `MemoryEntry` (line 339+).

### Implementation

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

Add to MemoryEntry:
```python
sub_type: EntrySubType | None = Field(default=None, description="Granular sub-type within skill/experience.")
```

**In memory_extractor.py** — update `build_extraction_prompt()` (line 30) and `build_harvest_prompt()` (line 172) to classify sub_type. The harvest already classifies as bug/decision/convention/learning (HARVEST_TYPES at line 164) — map to EntrySubType.

**Filter support:** Add `sub_type` parameter to `routes/knowledge_api.py` and the MCP `formicos://knowledge` resource filter.

### Tests

- Extraction prompt includes sub_type classification instruction
- Harvest types map correctly: bug→bug, decision→decision, convention→convention, learning→learning
- Knowledge API filters by sub_type
- Default sub_type is None (existing entries unaffected)

---

## B4. Confidence visualization

### Where

`frontend/src/components/knowledge-browser.ts` — enhance existing knowledge entry display.

### Implementation

**Default view:** Gradient-opacity confidence bar. Color-coded tier badge:
- Gray: STALE
- Red: EXPLORATORY
- Yellow: LOW/MODERATE
- Green: HIGH

Natural-language summary: "High confidence (72%) — 47 observations, stable decay class."

**Hover view:** Numeric mean ± credible interval, observation count, decay class, federation source indicator, co-occurrence cluster membership, prediction error count.

**Power user panel** (expandable): Raw alpha/beta, merged_from provenance list.

Use the same `_confidence_tier()` classification logic from engine/runner.py (lines 388-423) — reimplement in TypeScript for the frontend.

---

## B5. Federation dashboard

### Where

Create `frontend/src/components/federation-dashboard.ts`.

### Implementation

- Peer trust table: instance_id, trust score, success/failure counts, last sync
- Sync status: last_sync_clock per peer, events pending push/pull
- Conflict log: recent ConflictResult entries with resolution method
- Knowledge flow: entries sent/received per peer, domains exchanged

All data from projections — PeerConnection state, conflict resolution history, federation event counts.

---

## B6. End-to-end demo scenarios

### What

Three complete walkthroughs documented as markdown + integration tests.

Create in `docs/demos/`:

**demo-email-validator.md:** Operator says "build me an email validator with tests." System decomposes via Queen, executes colony, extracts knowledge, tiered retrieval in future colonies uses the extracted knowledge, proactive briefing shows confidence growing.

**demo-federation.md:** Two instances. Instance A builds testing knowledge. Replicates to B. B uses in colony. Validation feedback. Trust evolves. Proactive insight fires when trust changes.

**demo-knowledge-lifecycle.md:** Entry creation with sub-type classification, decay class assignment, confidence evolution through colony outcomes, merge via dedup, archival burst, recovery on re-access, prediction errors, stale sweep. Proactive briefing surfaces each transition.

---

## B7. Agent-level knowledge quality feedback

### Prerequisite: Track A must have landed before implementing B7.

Track A restructures the context formatting pipeline in `engine/runner.py`. B7 hooks into that pipeline. Implementing against the pre-restructured runner.py would require rewriting after Track A lands.

### What

Add `knowledge_feedback` tool to worker castes (coder, reviewer, researcher). Agents can explicitly report whether a retrieved entry was helpful or wrong.

### Implementation

**In engine/runner.py** — after Track A has landed:

1. Add to `TOOL_SPECS` (line 53 area):
```python
"knowledge_feedback": {
    "name": "knowledge_feedback",
    "description": "Report whether a retrieved knowledge entry was useful. Positive feedback strengthens confidence. Negative feedback signals staleness.",
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

2. Add to `TOOL_CATEGORY_MAP` (line 282):
```python
"knowledge_feedback": ToolCategory.memory,
```

3. Add dispatch in `_execute_tool()`:
```python
elif tool_name == "knowledge_feedback":
    return await self._knowledge_feedback_fn(
        entry_id=arguments["entry_id"],
        helpful=arguments["helpful"],
        reason=arguments.get("reason", ""),
    )
```

4. Add callback parameter to `RoundRunner.__init__()` or `RunnerCallbacks`.

**In surface/runtime.py** — add `make_knowledge_feedback_fn()`:
```python
def make_knowledge_feedback_fn(runtime: Runtime, colony_id: str, workspace_id: str):
    async def _knowledge_feedback(entry_id: str, helpful: bool, reason: str = "") -> str:
        entry = runtime.projections.memory_entries.get(entry_id)
        if not entry:
            return f"Entry {entry_id} not found"

        if helpful:
            # Positive: emit confidence update with reward=1.0
            await _emit_confidence_update(runtime, entry, colony_id, workspace_id,
                                          succeeded=True, reason="agent_feedback_positive")
            return f"Positive feedback recorded for {entry_id}"
        else:
            # Negative: increment prediction_error_count + confidence update with reward=0.0
            entry["prediction_error_count"] = entry.get("prediction_error_count", 0) + 1
            await _emit_confidence_update(runtime, entry, colony_id, workspace_id,
                                          succeeded=False, reason="agent_feedback_negative")
            return f"Negative feedback recorded for {entry_id}: {reason}"
    return _knowledge_feedback
```

**In caste_recipes.yaml** — add `"knowledge_feedback"` to tool arrays:
- Coder tools (line 127): append `"knowledge_feedback"`
- Reviewer tools (line 159): append `"knowledge_feedback"`
- Researcher tools (line 193): append `"knowledge_feedback"`
- Archivist: do NOT add (archivist creates knowledge, doesn't consume it in colonies)

### Tests

- helpful=true → MemoryConfidenceUpdated emitted with reason="agent_feedback_positive"
- helpful=false → prediction_error_count incremented + confidence update with reason="agent_feedback_negative"
- Invalid entry_id → graceful error message
- Tool appears in coder/reviewer/researcher specs, not archivist

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

For frontend changes: verify Lit components compile and render correctly.
For YAML changes: `python -c "import yaml; yaml.safe_load(open('config/caste_recipes.yaml'))"`
