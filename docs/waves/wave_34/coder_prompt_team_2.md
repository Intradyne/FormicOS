# Wave 34 Team 2 — Queen Intelligence + Proactive Briefing + Knowledge Feedback

## Role

You are building the proactive intelligence system, redesigning the Queen prompt for system awareness, and adding the agent knowledge_feedback tool. B1 and B2 run immediately in parallel with Teams 1 and 3. B7 is gated on Team 1 landing.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/044-cooccurrence-scoring.md` — you don't implement co-occurrence scoring, but the Queen prompt needs to reference it.
- Read the Wave 33.5 caste prompt rewrites in `config/caste_recipes.yaml` (lines 96-230) — your Queen rewrite follows the same density-over-length style.
- **B7 (knowledge_feedback tool dispatch in runner.py) MUST NOT begin until Team 1's runner.py changes have landed and been verified.** Team 1 restructures the context formatting pipeline. knowledge_feedback hooks into that pipeline. Implement B7 last, against Team 1's landed code.
- Team 3 also modifies `surface/mcp_server.py` (sub_type filter on `formicos://knowledge` resource). You add the briefing resource and knowledge_feedback tool — different functions, no overlap. But **do not modify the existing knowledge resource handler** — Team 3 owns that.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `config/caste_recipes.yaml` | MODIFY | Queen prompt rewrite (lines 9-88), knowledge_feedback tool added to coder/reviewer/researcher tool arrays |
| `surface/proactive_intelligence.py` | CREATE | ~300 LOC: KnowledgeInsight, ProactiveBriefing, 7 insight generation rules |
| `surface/queen_runtime.py` | MODIFY | Inject top 3 insights into Queen prompt assembly |
| `surface/mcp_server.py` | MODIFY | Briefing resource (`formicos://briefing/{workspace_id}`), knowledge_feedback tool |
| `surface/routes/api.py` | MODIFY | Briefing REST endpoint |
| `engine/runner.py` | MODIFY | knowledge_feedback tool dispatch (**GATED on Team 1 landing**) |
| `tests/unit/surface/test_proactive_intelligence.py` | CREATE | Insight generation rule tests |
| `tests/unit/surface/test_knowledge_feedback.py` | CREATE | Feedback tool tests |

## DO NOT TOUCH

- `surface/knowledge_catalog.py` — Team 1 owns (tiered retrieval, co-occurrence scoring)
- `surface/knowledge_constants.py` — Team 1 owns (COMPOSITE_WEIGHTS)
- `core/types.py` — Team 3 owns (EntrySubType)
- `surface/memory_extractor.py` — Team 3 owns (sub-type classification)
- `surface/routes/knowledge_api.py` — Team 3 owns (sub_type filter)
- `frontend/*` — Team 3 owns (confidence viz, federation dashboard, briefing display)
- `docs/demos/*` — Team 3 owns
- All integration/stress test files — Validation track owns
- `CLAUDE.md`, `KNOWLEDGE_LIFECYCLE.md`, `AGENTS.md` — Validation track owns
- `pyproject.toml` — Validation track owns

## Overlap rules

- `surface/mcp_server.py`: **Team 3 also modifies this file** (adding sub_type filter to the existing knowledge resource). You own: new briefing resource function (after line 467), new knowledge_feedback tool registration. Team 3 owns: modifications to the existing `formicos://knowledge` resource handler. Do not touch the knowledge resource handler.
- `engine/runner.py`: **Team 1 owns this file for tiered search + budget assembly.** You add knowledge_feedback dispatch ONLY AFTER Team 1 has landed. Your change is ~15 lines: add to TOOL_SPECS, TOOL_CATEGORY_MAP, and dispatch case. Do NOT restructure the context assembly — Team 1 handles that.
- `config/caste_recipes.yaml`: You are the sole modifier. Team 3 does NOT touch this file.

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

## B7. Agent-level knowledge quality feedback

### Prerequisite: Team 1 must have landed before implementing B7.

Team 1 restructures the context formatting pipeline in `engine/runner.py`. B7 hooks into that pipeline. Implementing against the pre-restructured runner.py would require rewriting after Team 1 lands.

### What

Add `knowledge_feedback` tool to worker castes (coder, reviewer, researcher). Agents can explicitly report whether a retrieved entry was helpful or wrong.

### Implementation

**In engine/runner.py** — after Team 1 has landed:

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

For YAML changes: `python -c "import yaml; yaml.safe_load(open('config/caste_recipes.yaml'))"`
