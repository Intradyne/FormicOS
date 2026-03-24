# Wave 35 Team 3 — Explainability + Directives + Per-Workspace Weights + Mastery Restoration

## Role

You are building four independent features: score breakdown rendering (the data already exists from Wave 34.5), operator directives for mid-colony steering, per-workspace composite weight configuration (ADR-044 D4 activation), and the mastery-restoration bonus. All four are independent of each other and of Teams 1 and 2.

## Coordination rules

- `CLAUDE.md` defines the evergreen repo rules. This prompt overrides root `AGENTS.md` for this dispatch.
- Read `docs/decisions/044-cooccurrence-scoring.md` (ADR-044 D4) for the per-workspace weights design. You are activating the deferred feature.
- Read `docs/decisions/045-event-union-parallel-distillation.md` (ADR-045 D3) — operator directives use existing `ColonyChatMessage` with a `directive_type` field, NOT a new event type.
- The Wave 34.5 mastery-restoration evaluation found a 43.4% gap for stable entries. Your restoration bonus addresses this.
- You run in parallel with Teams 1 and 2. No dependencies between teams.

## File ownership

| File | Status | Changes |
|------|--------|---------|
| `core/types.py` | MODIFY | DirectiveType StrEnum, OperatorDirective model (add after Team 2's models, before `__all__`) |
| `surface/knowledge_catalog.py` | MODIFY | Score breakdown rendering in `_format_tier()`, weights-as-parameter in `_composite_key()` and `_keyfn` |
| `surface/knowledge_constants.py` | MODIFY | Per-workspace weight lookup function |
| `engine/runner.py` | MODIFY | Directive injection in context assembly |
| `surface/colony_manager.py` | MODIFY | Mastery-restoration bonus in confidence update, peak_alpha tracking |
| `surface/projections.py` | MODIFY | peak_alpha field, per-workspace composite weight storage |
| `surface/mcp_server.py` | MODIFY | configure_scoring tool, directive_type param on chat_colony |
| `surface/event_translator.py` | MODIFY | OPERATOR_DIRECTIVE AG-UI event |
| `frontend/src/components/knowledge-browser.ts` | MODIFY | Score breakdown stacked bar in hover panel |
| `frontend/src/components/directive-panel.ts` | CREATE | Directive type selector + content field |
| `tests/unit/surface/test_score_rendering.py` | CREATE | Score breakdown format tests |
| `tests/unit/surface/test_directives.py` | CREATE | Directive injection tests |
| `tests/unit/surface/test_workspace_weights.py` | CREATE | Per-workspace weight tests |
| `tests/unit/surface/test_mastery_restoration.py` | MODIFY | Extend for restoration bonus |

## DO NOT TOUCH

- `surface/queen_runtime.py` — Team 1 owns (parallel planning)
- `config/caste_recipes.yaml` — Team 1 owns (Queen prompt)
- `surface/self_maintenance.py` — Team 2 creates
- `surface/proactive_intelligence.py` — Team 2 modifies
- `surface/maintenance.py` — Team 2 modifies
- All integration test files — Validation track owns
- All documentation — Validation track owns

## Overlap rules

- `core/types.py`: Teams 1 and 2 also add models. You add DirectiveType StrEnum and OperatorDirective. Team 1 adds DelegationPlan/ColonyTask. Team 2 adds AutonomyLevel/MaintenancePolicy. All independent — add yours after Team 2's models, before `__all__`.
- `surface/mcp_server.py`: Team 2 also modifies (maintenance policy tools). You add configure_scoring tool and directive_type param on chat_colony. Different tool registrations, no overlap. Do not add maintenance policy tools.
- `surface/projections.py`: Team 2 also modifies (KnowledgeDistilled handler, maintenance policy storage). You add peak_alpha field and per-workspace weight storage. Different projection fields, no overlap.
- `surface/event_translator.py`: Teams 1 and 2 also modify (PARALLEL_PLAN, MAINTENANCE_COLONY_SPAWNED, KNOWLEDGE_DISTILLED). You add OPERATOR_DIRECTIVE. Different event promotions, no overlap.

---

## A3. Score breakdown rendering

### What

Wave 34.5 stored `_score_breakdown` on full-tier search results. Wave 35 renders it for agents and operators.

### Agent-facing (in knowledge_catalog.py `_format_tier()`)

At standard and full tiers, include a human-readable explanation line from the score breakdown:

```python
if tier in ("standard", "full") and "_score_breakdown" in r:
    sb = r["_score_breakdown"]
    # Find dominant signal (highest weighted contribution)
    contributions = {k: sb.get(k, 0.0) * sb.get("weights", {}).get(k, 0.0)
                     for k in ["semantic", "thompson", "freshness", "status", "thread", "cooccurrence"]}
    dominant = max(contributions, key=contributions.get)
    item["ranking_explanation"] = (
        f"semantic {sb.get('semantic', 0):.2f}, thompson {sb.get('thompson', 0):.2f}, "
        f"freshness {sb.get('freshness', 0):.2f}, status {sb.get('status', 0):.2f}, "
        f"thread {sb.get('thread', 0):.2f}, cooccurrence {sb.get('cooccurrence', 0):.2f} "
        f"(dominant: {dominant})"
    )
```

At full tier, include the complete score_breakdown dict (already done in 34.5). At standard tier, include only the ranking_explanation string.

### Operator-facing (in knowledge-browser.ts)

In the hover panel (Wave 34 B4), render the score breakdown as a horizontal stacked bar chart:
- Each signal is a colored segment proportional to its weighted contribution
- Colors: semantic=blue, thompson=purple, freshness=green, status=gold, thread=cyan, cooccurrence=orange
- Clicking a segment shows: raw value, weight, weighted contribution, one-line explanation

### Tests

- Full tier results include score_breakdown dict
- Standard tier results include ranking_explanation string
- Summary tier results do NOT include score data
- ranking_explanation identifies correct dominant signal

---

## C1. Operator directives for mid-colony steering

### Models (in core/types.py)

```python
class DirectiveType(StrEnum):
    context_update = "context_update"     # new information
    priority_shift = "priority_shift"     # change focus
    constraint_add = "constraint_add"     # add hard requirement
    strategy_change = "strategy_change"   # change approach

class OperatorDirective(BaseModel):
    directive_type: DirectiveType
    content: str
    priority: str = "normal"  # "normal" | "urgent"
    applies_to: str = "all"   # "all" | specific agent_id
```

### Delivery (in mcp_server.py)

Extend `chat_colony` MCP tool to accept an optional `directive_type` parameter. When present, the message payload includes the directive metadata:
```python
@mcp.tool()
async def chat_colony(
    colony_id: str,
    message: str,
    directive_type: str | None = None,  # NEW
    directive_priority: str = "normal",  # NEW
) -> dict:
```

When `directive_type` is provided, the ColonyChatMessage event payload includes `{"directive_type": directive_type, "directive_priority": directive_priority}`. This follows ADR-045 D3 (no new event type).

### Context assembly (in engine/runner.py)

In the round's context assembly, detect directive-tagged messages and inject with special framing:

```python
# Extract directives from recent messages
directives = [msg for msg in messages if msg.get("directive_type")]

if directives:
    urgent = [d for d in directives if d.get("directive_priority") == "urgent"]
    normal = [d for d in directives if d.get("directive_priority") != "urgent"]

    if urgent:
        # Inject BEFORE task description
        urgent_text = "\n".join(
            f"[{d['directive_type'].upper()}] {d['content']}" for d in urgent
        )
        context.insert(0, f"## URGENT Operator Directives\n{urgent_text}")

    if normal:
        # Inject AFTER task, BEFORE round history
        normal_text = "\n".join(
            f"[{d['directive_type'].upper()}] {d['content']}" for d in normal
        )
        context.insert(task_end_pos, f"## Operator Directives\n{normal_text}")
```

### AG-UI event (in event_translator.py)

Emit OPERATOR_DIRECTIVE custom event when a directive-tagged chat message is sent.

### Frontend (directive-panel.ts)

Create a "Send Directive" panel visible whenever colonies are running:
- Dropdown: directive type selector (Context Update, Priority Shift, Constraint, Strategy Change)
- Toggle: normal / urgent priority
- Text field: directive content
- Send button

### Tests

- Directive sent → ColonyChatMessage event includes directive_type in payload
- Urgent directive → appears before task description in context
- Normal directive → appears after task, before round history
- No directive_type → standard chat message behavior (no framing)
- AG-UI event emitted for directive messages

---

## C2. Per-workspace composite weights (ADR-044 D4 activation)

### What

The deferred feature from Wave 34. Score breakdown visualization (A3) makes the impact visible before operators tune weights.

### Implementation

**In knowledge_constants.py:**
```python
def get_workspace_weights(workspace_id: str, projections) -> dict[str, float]:
    """Return composite weights for a workspace. Falls back to defaults."""
    ws = projections.workspaces.get(workspace_id, {})
    override = ws.get("composite_weights")
    if override and isinstance(override, dict):
        return override
    return dict(COMPOSITE_WEIGHTS)
```

**In knowledge_catalog.py:**
- `_composite_key()` and `_keyfn` receive weights as a parameter instead of reading the module constant
- The search functions (`search_tiered`, `_search_thread_boosted`) accept an optional `weights` parameter
- Callers pass workspace-specific weights from `get_workspace_weights()`

**In projections.py:**
Store workspace weight overrides from WorkspaceConfigChanged:
```python
if "composite_weights" in event.config:
    ws["composite_weights"] = event.config["composite_weights"]
```

**MCP tool (in mcp_server.py):**
```python
@mcp.tool()
async def configure_scoring(
    workspace_id: str,
    semantic: float | None = None,
    thompson: float | None = None,
    freshness: float | None = None,
    status: float | None = None,
    thread: float | None = None,
    cooccurrence: float | None = None,
) -> dict:
    """Adjust composite scoring weights for this workspace.

    Weights must sum to 1.0 (+/- 0.001). All values must be >= 0.0 and <= 0.5.
    Omitted values keep their current setting.
    """
```

Validation: weights sum to 1.0 +/- 0.001. All >= 0.0 and <= 0.5. Emit WorkspaceConfigChanged with `composite_weights` in config.

### Tests

- Default workspace: uses COMPOSITE_WEIGHTS from knowledge_constants
- Custom weights: workspace uses overrides
- Custom weights with cooccurrence=0.0 (e.g., semantic=0.43, thompson=0.25, freshness=0.15, status=0.10, thread=0.07, cooccurrence=0.0 = 1.00): invariant 5 (co-occurrence boost) does NOT apply
- Custom weights: invariants 1-4 still pass
- Weights that don't sum to 1.0 → StructuredError
- Weight > 0.5 → StructuredError
- configure_scoring round-trip: set, retrieve, verify

---

## C3. Mastery-restoration bonus

### What

The Wave 34.5 evaluation found a 43.4% gap for stable entries after 180 days (alpha 25 decays to 13.14, re-observation recovers only to 14.14). The restoration bonus closes part of this gap.

### Implementation (in colony_manager.py confidence update)

```python
# Track peak alpha as a projection field
peak_alpha = entry.get("peak_alpha", entry.get("conf_alpha", PRIOR_ALPHA))
if new_alpha > peak_alpha:
    entry["peak_alpha"] = new_alpha

# Restoration bonus on re-observation after long dormancy
current_alpha = entry.get("conf_alpha", PRIOR_ALPHA)
if (current_alpha < peak_alpha * 0.5
    and succeeded
    and entry.get("decay_class", "ephemeral") in ("stable", "permanent")):
    gap = peak_alpha - current_alpha
    restoration = gap * 0.2  # recover 20% of the gap per successful observation
    new_alpha += restoration
```

**Conditions (all must be true):**
1. Current alpha is less than half the historical peak
2. The observation is a success (not failure)
3. The entry has decay_class "stable" or "permanent" (ephemeral entries are expected to decay fully)

**Expected behavior at the 43.4% gap example:**
- gap = 25 - 13.14 = 11.86, bonus = 2.37, restored alpha = 14.14 + 2.37 = 16.51
- Gap drops from 43.4% to 34.0%
- After 3 successive successful observations: alpha approaches ~22, gap ~12%
- Restoration is gradual, not instant — multiple successful re-observations required

### peak_alpha projection field (in projections.py)

Add `peak_alpha` to memory entry projection. Updated whenever conf_alpha increases:
```python
# In _on_memory_confidence_updated
current_peak = entry.get("peak_alpha", entry.get("conf_alpha", 5.0))
if new_alpha > current_peak:
    entry["peak_alpha"] = new_alpha
```

### Tests

- Stable entry at peak_alpha=25, current=13.14 → bonus of ~2.37 on success
- Ephemeral entry at same gap → NO bonus (decay_class filter)
- Entry with current > peak*0.5 → NO bonus (threshold not met)
- Failed observation → NO bonus (succeeded=False)
- peak_alpha tracked correctly across multiple confidence updates
- 3 successive successful observations → alpha approaches ~22

---

## Validation

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

For frontend changes: verify Lit components compile and render correctly.
