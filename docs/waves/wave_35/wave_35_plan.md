# Wave 35 Plan -- The Self-Maintaining Colony

**Wave:** 35 -- "The Self-Maintaining Colony"
**Theme:** The system uses its own capabilities on itself. The Queen gains a parallel planner for multi-colony orchestration. Proactive insights trigger automatic maintenance colonies. Knowledge clusters get distilled into higher-order syntheses. Decisions become explainable. The operator gains mid-colony steering. After Wave 35, FormicOS doesn't just execute tasks -- it maintains its own knowledge quality, explains its reasoning, and responds to operator direction mid-flight.

**Prerequisite:** Wave 34.5 landed. Score breakdown metadata stored on search results (`_score_breakdown` dict on full-tier items). SuggestedColony model on KnowledgeInsight (3/7 rules populated). distillation_candidates computed in maintenance loop. knowledge_feedback tool operational. Mastery-restoration evaluation completed (expected finding: 43.4% gap at stable decay class, restoration bonus recommended). All 19 Wave 34 smoke tests passing. Documentation synced.

**Contract changes:** 2 new event types: `ParallelPlanCreated` and `KnowledgeDistilled` (ADR-045, union 53 to 55). `OperatorDirective` model added. Per-workspace composite weights via WorkspaceConfigChanged (ADR-044 D4 activation). Mastery-restoration bonus in confidence pipeline.

**ADRs required before coder dispatch:**
- ADR-045: Event union expansion 53 to 55. ParallelPlanCreated (Queen planning audit trail). KnowledgeDistilled (distillation provenance).
- ADR-046: Autonomy levels for self-maintenance (suggest / auto-with-notify / autonomous).

---

## Why this wave

After Wave 34.5, FormicOS has proactive intelligence (it knows what's wrong with its knowledge), score breakdowns (it knows why it ranked things), suggested colonies on insights (it knows what would fix problems), and distillation candidates (it knows which clusters are ready for synthesis). But it doesn't act on any of this. The proactive briefing surfaces problems; the operator resolves them manually. The Queen plans sequentially; parallelizable work waits in line.

Wave 35 connects insight to action. Three capabilities, all built on the same foundation: the system spawning colonies to operate on itself.

Multi-colony orchestration is the prerequisite for the other two. Self-maintaining knowledge needs the Queen to spawn a research colony to resolve a contradiction while other work continues. Knowledge distillation needs the Queen to spawn an archivist colony to synthesize a cluster without blocking task colonies. Both require the Queen to manage multiple concurrent colonies -- which she currently cannot do.

---

## Track A: Multi-Colony Orchestration + Explainable Decisions

### A1. Queen parallel planner (DelegationPlan with DAG)

The Queen currently plans one colony, watches it complete, plans the next. For complex goals that decompose into independent subtasks, this serializes work that could run in parallel. The LLMCompiler pattern (Kim et al. 2023) shows 3.6x speed improvement from DAG-based parallel execution. The project's own prompt engineering reference documents the exact model needed:

```python
class ColonyTask(BaseModel):
    task_id: str
    task: str
    caste: str
    strategy: str
    max_rounds: int
    budget_limit: float
    depends_on: list[str] = []     # task_ids that must complete first
    input_from: list[str] = []     # colony_ids to chain output from

class DelegationPlan(BaseModel):
    reasoning: str                  # free-form planning rationale
    tasks: list[ColonyTask]
    parallel_groups: list[list[str]]  # task_ids that can run simultaneously
    estimated_total_cost: float
    knowledge_gaps: list[str]       # domains where briefing flagged issues
```

The Queen generates a DelegationPlan in her planning phase (before any spawn_colony calls). The plan is:
1. Validated: no circular dependencies, all depends_on references exist
2. Emitted as a `ParallelPlanCreated` event (audit trail + operator visibility)
3. Executed: parallel groups dispatched simultaneously via asyncio.gather on spawn_colony calls
4. Monitored: Queen polls all active colonies, re-plans if any fail

**Implementation in queen_runtime.py:**

The Queen's tool-calling loop already iterates: receive message -> reason -> emit tool calls -> observe results -> repeat. Multi-colony orchestration changes the tool-calling pattern, not the loop structure. Instead of one spawn_colony per iteration, the Queen can emit multiple spawn_colony calls in a single iteration (parallel group). The existing asyncio.create_task infrastructure handles concurrent colony execution.

The key change is in the Queen's prompt: teach her to generate DelegationPlan before spawning, and to emit parallel spawn_colony calls for independent tasks.

**Convergence check between parallel groups:**

After a parallel group completes, the Queen reviews all results (via read_colony_output for each) before spawning the next group. This is the existing pattern (spawn -> wait -> review -> spawn) applied at the group level instead of the colony level.

**AG-UI representation:** Parallel colonies in the same group share a visual row in the workflow view. The operator sees the DAG structure: "Group 1: [research-auth, research-db] -> Group 2: [implement-api] -> Group 3: [test-suite]."

### A2. ParallelPlanCreated event

```python
class ParallelPlanCreated(EventEnvelope):
    type: Literal["ParallelPlanCreated"] = "ParallelPlanCreated"
    thread_id: str
    workspace_id: str
    plan: dict[str, Any]         # serialized DelegationPlan
    parallel_groups: list[list[str]]  # colony task_ids per group
    reasoning: str
    knowledge_gaps: list[str]
    estimated_cost: float
```

Projection handler stores the plan on the thread projection. The AG-UI stream emits a PARALLEL_PLAN custom event so the frontend can render the DAG.

### A3. Explainable retrieval (score breakdown rendering)

Wave 34.5 stored `_score_breakdown` on full-tier search results. Wave 35 renders it.

**Agent-facing:** When memory_search returns results at standard or full tier, include a human-readable explanation line:

```
[Entry abc123] Python async testing patterns
  Confidence: HIGH (verified, 47 observations, stable decay)
  Ranking: semantic 0.72 (dominant), thompson 0.81 (exploring), freshness 0.95,
           status 1.0 (verified), thread +0.07, cooccurrence +0.04 with Entry xyz789
  Content: Use @pytest.mark.asyncio for async test functions...
```

This is a formatting change in `_format_tier()` -- the data already exists.

**Operator-facing:** In the knowledge-browser frontend, the hover panel (Wave 34 B4) renders the score breakdown as a horizontal stacked bar chart. Each signal is a colored segment proportional to its weighted contribution. Clicking a segment shows the raw value, the weight, and a one-line explanation ("thompson drew 0.81 -- high uncertainty, system is exploring this entry").

**Queen-facing:** When the proactive briefing injects insights, include score breakdown context: "Entry X has been declining because semantic relevance is dropping (was 0.72, now 0.45) while thompson keeps exploring it (high uncertainty). The entry may need re-validation."

### A4. Queen decision explanations

The Queen already produces one-line "Why" rationale when spawning colonies. Wave 35 enriches this with system-grounded reasoning that references the proactive briefing and score breakdowns.

**In the Queen prompt** (extending the Wave 34 B1 redesign):

```
## Explaining your decisions
When you spawn a colony or make a strategic choice, explain WHY using
system evidence:
- "Chose coder+reviewer because memory_search returned 3 HIGH entries
  for Python API patterns (no knowledge gap). Template python-api
  matched at 85%."
- "Spawning research colony first because the briefing flagged a
  contradiction on error handling. Resolving before implementation
  prevents wasted work."
- "Running research and schema colonies in parallel -- they have no
  data dependency. Research results will feed into the implementation
  colony (Group 2, input_from=research)."
```

The explanation is stored in the DelegationPlan's `reasoning` field and emitted in the ParallelPlanCreated event. The operator sees the full reasoning in the AG-UI stream and the workflow view.

### Track A files

| File | Changes |
|------|---------|
| `core/types.py` | DelegationPlan, ColonyTask, OperatorDirective models |
| `core/events.py` | ParallelPlanCreated event (union 53 to 54) |
| `surface/queen_runtime.py` | Parallel plan generation, concurrent spawn dispatch, convergence check |
| `config/caste_recipes.yaml` | Queen prompt: parallel planning, decision explanation sections |
| `surface/knowledge_catalog.py` | Score breakdown rendering in `_format_tier()` at standard + full tiers |
| `surface/event_translator.py` | PARALLEL_PLAN AG-UI event promotion |
| `frontend/src/components/knowledge-browser.ts` | Score breakdown stacked bar in hover panel |
| `frontend/src/components/workflow-view.ts` | DAG visualization for parallel groups |

---

## Track B: Self-Maintaining Knowledge + Knowledge Distillation

Both features are "the system using colonies on itself." Both consume the multi-colony orchestration from Track A. Both build on Wave 34.5 foundations (SuggestedColony, distillation_candidates).

### B1. Autonomy levels for self-maintenance (requires ADR-046)

Before the system can spawn colonies automatically, the operator must control how much autonomy it has. Three levels per workspace:

```python
class AutonomyLevel(StrEnum):
    suggest = "suggest"         # insights shown, no auto-action
    auto_notify = "auto_notify" # routine maintenance runs, operator notified
    autonomous = "autonomous"   # full self-maintenance, operator sees results

# Per workspace, stored via WorkspaceConfigChanged
class MaintenancePolicy(BaseModel):
    autonomy_level: AutonomyLevel = AutonomyLevel.suggest  # safe default
    auto_actions: list[str] = []  # which insight categories auto-dispatch
    max_maintenance_colonies: int = 2  # concurrent maintenance colony cap
    daily_maintenance_budget: float = 1.0  # $ limit for auto-spawned colonies
```

At `suggest` (default): the briefing shows SuggestedColony data. The operator spawns manually. This is current behavior.

At `auto_notify`: the system auto-spawns colonies for insight categories listed in `auto_actions`. Each spawn emits a notification via AG-UI (MAINTENANCE_COLONY_SPAWNED custom event). The operator can kill any maintenance colony. Daily budget cap prevents runaway costs.

At `autonomous`: same as auto_notify but without requiring explicit category opt-in. All 3 SuggestedColony-eligible insights (contradiction, coverage_gap, stale_cluster) can auto-dispatch. The operator sees results in the briefing.

### B2. Self-maintenance dispatch engine

Create `surface/self_maintenance.py` (~250 LOC). This is the bridge between proactive intelligence (Wave 34 B2) and colony execution.

```python
class MaintenanceDispatcher:
    """Connects proactive insights to automatic colony dispatch."""

    async def evaluate_and_dispatch(
        self, workspace_id: str, briefing: ProactiveBriefing
    ) -> list[str]:
        """Check insights against autonomy policy. Dispatch eligible colonies."""
        policy = self._get_policy(workspace_id)
        if policy.autonomy_level == AutonomyLevel.suggest:
            return []  # operator-only mode

        dispatched = []
        active = self._count_active_maintenance_colonies(workspace_id)
        budget_remaining = self._daily_budget_remaining(workspace_id)

        for insight in briefing.insights:
            if not insight.suggested_colony:
                continue
            if active >= policy.max_maintenance_colonies:
                break
            if budget_remaining <= 0:
                break
            if policy.autonomy_level == AutonomyLevel.auto_notify:
                if insight.category not in policy.auto_actions:
                    continue

            colony_id = await self._spawn_maintenance_colony(
                workspace_id, insight
            )
            dispatched.append(colony_id)
            active += 1
            budget_remaining -= insight.suggested_colony.estimated_cost

        return dispatched
```

**Integration:** The maintenance dispatcher runs after `generate_briefing()` in the maintenance loop. When insights with SuggestedColony are found and the autonomy policy allows, colonies are spawned. Each maintenance colony is tagged with `maintenance_source: str` (the insight category) so outcomes feed back into the proactive intelligence system.

**Feedback loop:** When a maintenance colony completes:
- If it resolved a contradiction: the losing entry's confidence is updated, the insight clears from the next briefing
- If it filled a coverage gap: new entries appear, the coverage_gap insight clears
- If it re-validated a stale cluster: entries either get confidence boosts (still relevant) or prediction error increments (confirmed stale)

### B3. Knowledge distillation via archivist colonies

When a co-occurrence cluster reaches the density thresholds identified in Wave 34.5 (>= 5 entries, average weight > 3.0), the system can spawn an archivist colony to synthesize a distilled entry.

```python
async def _spawn_distillation_colony(
    self, workspace_id: str, cluster: list[str]
) -> str:
    """Spawn archivist colony to synthesize a knowledge cluster."""
    entries = [self._projections.memory_entries[eid] for eid in cluster]
    entry_summaries = "\n".join(
        f"- [{e['id']}] ({e.get('sub_type', 'unknown')}): {e.get('title', '')}\n"
        f"  Content: {e.get('content', '')[:300]}\n"
        f"  Confidence: {_confidence_tier(e)}, Observations: {e.get('conf_alpha',5)+e.get('conf_beta',5)-10:.0f}"
        for e in entries
    )

    task = (
        f"Synthesize these {len(cluster)} related knowledge entries into a single "
        f"comprehensive entry. Preserve all key insights. Resolve any contradictions "
        f"by noting the strongest evidence. The synthesis should be more useful than "
        f"any individual entry.\n\n{entry_summaries}"
    )

    return await self._spawn_colony(
        workspace_id=workspace_id,
        task=task,
        caste="archivist",
        strategy="sequential",
        max_rounds=3,
        tags=["distillation"],
    )
```

**KnowledgeDistilled event:**

```python
class KnowledgeDistilled(EventEnvelope):
    type: Literal["KnowledgeDistilled"] = "KnowledgeDistilled"
    distilled_entry_id: str
    source_entry_ids: list[str]
    workspace_id: str
    cluster_avg_weight: float
    distillation_strategy: str  # "archivist_synthesis"
```

The projection handler:
1. Creates the distilled entry with `decay_class="stable"` and elevated initial confidence (alpha = sum of source alphas / 2, capped at 30)
2. Marks source entries with `distilled_into: str` pointing to the new entry
3. Does NOT reject source entries -- they remain searchable but the distilled entry ranks higher due to higher confidence

**Distillation is NOT automatic by default.** It requires `autonomy_level >= auto_notify` AND `"distillation"` in the maintenance policy's `auto_actions` list. At `suggest` level, the briefing shows "Cluster X is ready for distillation" with the SuggestedColony data.

### Track B files

| File | Changes |
|------|---------|
| `core/types.py` | AutonomyLevel StrEnum, MaintenancePolicy model |
| `core/events.py` | KnowledgeDistilled event (union 54 to 55) |
| `surface/self_maintenance.py` | NEW (~250 LOC): MaintenanceDispatcher |
| `surface/proactive_intelligence.py` | Wire dispatcher into briefing pipeline |
| `surface/maintenance.py` | Trigger distillation check, dispatch integration |
| `surface/projections.py` | KnowledgeDistilled handler, distilled_into field |
| `surface/mcp_server.py` | Maintenance policy tools (set_autonomy, get_policy) |
| `surface/event_translator.py` | MAINTENANCE_COLONY_SPAWNED, KNOWLEDGE_DISTILLED AG-UI events |

---

## Track C: Interactive Steering + Remaining Hardening

### C1. Operator directives for mid-colony steering

The operator currently has two options during a colony: kill it or approve/deny a request. Wave 35 adds typed directives that the colony's context assembly treats differently from regular chat.

```python
class DirectiveType(StrEnum):
    context_update = "context_update"     # new information the colony doesn't have
    priority_shift = "priority_shift"     # change what the colony focuses on
    constraint_add = "constraint_add"     # add a hard requirement
    strategy_change = "strategy_change"   # change the approach

class OperatorDirective(BaseModel):
    directive_type: DirectiveType
    content: str
    priority: str = "normal"  # "normal" | "urgent"
    applies_to: str = "all"   # "all" | specific agent_id
```

**Delivery mechanism:** Extend `chat_colony` MCP tool to accept an optional `directive_type` parameter. When present, the message is tagged as a directive instead of regular chat.

**Context assembly handling:** In the round's Phase 1 (Goal), directives are injected with special framing:

```
## Operator Directives (prioritize these)
[CONTEXT_UPDATE] The API endpoint changed last week. New base URL: https://api.v2.example.com
[CONSTRAINT_ADD] Do not use subprocess.run -- use the code_execute sandbox.
```

`URGENT` directives are injected at the top of the context, before the task description. Normal directives go after the task but before round history.

**AG-UI integration:** The frontend shows a "Send Directive" panel with directive type selector and content field. The panel is visible whenever colonies are running. Directives appear in the AG-UI stream as `OPERATOR_DIRECTIVE` custom events.

### C2. Per-workspace composite weights (ADR-044 D4 activation)

The deferred feature from Wave 34. With score breakdown visualization now live (Track A3), operators can see which signals dominate before tuning.

**Implementation:**
- `_composite_key()` receives weights as a parameter (default: COMPOSITE_WEIGHTS from knowledge_constants.py)
- WorkspaceConfigChanged events can include a `composite_weights` override
- Workspace projection stores the override
- Search functions thread workspace_id through to scoring

**New MCP tool:**
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
    """Adjust composite scoring weights for this workspace. Weights must sum to 1.0."""
```

Validation: weights must sum to 1.0 +/- 0.001. All weights must be >= 0.0 and <= 0.5. The tool returns the effective weights after the change.

### C3. Mastery-restoration bonus

The Wave 34.5 evaluation found a 43.4% gap for stable entries after 180 days (alpha 25 decays to 13.14, re-observation only recovers to 14.14). The restoration bonus closes part of this gap for entries with a history of high confidence.

**Implementation in the confidence update hook:**

```python
# Track peak alpha as a derived projection field
peak_alpha = entry.get("peak_alpha", entry.get("conf_alpha", PRIOR_ALPHA))
if new_alpha > peak_alpha:
    entry["peak_alpha"] = new_alpha

# Restoration bonus on re-observation after long gap
current_alpha = query_alpha(now)
if current_alpha < peak_alpha * 0.5 and succeeded:
    gap = peak_alpha - current_alpha
    restoration = gap * 0.2  # recover 20% of the gap
    new_alpha += restoration
```

The bonus is conservative (20% of the gap) and only fires when:
1. Current alpha is less than half the historical peak
2. The observation is a success (not failure)
3. The entry has decay_class "stable" or "permanent" (ephemeral entries are expected to decay fully)

At the 43.4% gap example: gap = 25 - 13.14 = 11.86, bonus = 2.37, restored alpha = 14.14 + 2.37 = 16.51. Gap drops from 43.4% to 34.0%. With 3 successive observations: alpha approaches ~22, gap ~12%. The restoration is gradual, not instant -- multiple successful re-observations required to fully recover.

### C4. Integration tests

**Parallel planning test:** Queen receives complex task. Generates DelegationPlan with 2 parallel groups. Group 1 runs simultaneously. After completion, Group 2 starts with input_from dependencies. Total time < 2x single-group time (vs 3x sequential).

**Self-maintenance test:** Create workspace with known contradiction. Set autonomy_level to auto_notify with `auto_actions=["contradiction"]`. Run maintenance. Verify research colony spawns. Verify operator notification. Verify contradiction insight clears after resolution.

**Distillation test:** Create 6 entries with strong co-occurrence (weight > 3.0). Run maintenance. Verify distillation_candidate flagged. Set autonomy to allow distillation. Verify archivist colony spawns. Verify KnowledgeDistilled event. Verify distilled entry has elevated confidence and stable decay class.

**Operator directive test:** Spawn colony. Send CONTEXT_UPDATE directive. Verify directive appears in next round's context with special framing. Send URGENT CONSTRAINT_ADD. Verify it appears before the task description.

**Mastery-restoration test:** Entry with peak_alpha=25, current_alpha=13.14 (after 180 days stable decay). Successful observation. Verify restoration bonus of ~2.37. Verify bonus only applies to stable/permanent entries, not ephemeral.

**Per-workspace weights test:** Set workspace weights to semantic=0.50, cooccurrence=0.0 (other defaults). Verify invariants 1-4 still pass. Verify invariant 5 (co-occurrence boost) does NOT pass (cooccurrence weight is 0). Verify retrieval uses workspace weights, not global defaults.

### C5. Final documentation pass

**CLAUDE.md:** Multi-colony orchestration (DelegationPlan, parallel groups). Self-maintenance (autonomy levels, dispatcher). Knowledge distillation (cluster synthesis). Operator directives. Per-workspace weights. Mastery restoration. Event union at 55.

**KNOWLEDGE_LIFECYCLE.md:** Self-maintenance loop (insight -> suggested colony -> dispatch -> outcome -> feedback). Distillation pipeline (cluster detection -> archivist synthesis -> elevated entry). Mastery restoration formula.

**AGENTS.md:** Queen parallel planning capabilities. Operator directive types. configure_scoring tool.

**OPERATORS_GUIDE.md:** Autonomy level configuration. Maintenance policy tuning. Directive usage guide. Per-workspace weight tuning with score breakdown visualization.

### Track C files

| File | Changes |
|------|---------|
| `surface/colony_manager.py` | Mastery-restoration bonus in confidence update, peak_alpha tracking |
| `surface/mcp_server.py` | configure_scoring tool, directive_type param on chat_colony |
| `surface/knowledge_constants.py` | Per-workspace weight lookup function |
| `surface/knowledge_catalog.py` | Weights-as-parameter in _composite_key(), workspace threading |
| `engine/runner.py` | Directive injection in context assembly |
| `surface/projections.py` | peak_alpha field, per-workspace weight storage |
| `surface/event_translator.py` | OPERATOR_DIRECTIVE AG-UI event |
| `frontend/src/components/directive-panel.ts` | NEW: directive type selector + content field |
| Tests, docs (see C4, C5) | |

---

## File Ownership Matrix

| File | Track A | Track B | Track C |
|------|---------|---------|---------|
| `core/types.py` | DelegationPlan, ColonyTask | AutonomyLevel, MaintenancePolicy | OperatorDirective, DirectiveType |
| `core/events.py` | ParallelPlanCreated | KnowledgeDistilled | -- |
| `surface/queen_runtime.py` | **OWN** (parallel planning) | -- | -- |
| `config/caste_recipes.yaml` | **OWN** (Queen prompt) | -- | -- |
| `surface/self_maintenance.py` | -- | **CREATE** | -- |
| `surface/proactive_intelligence.py` | -- | **MODIFY** | -- |
| `surface/knowledge_catalog.py` | Score breakdown rendering | -- | Per-workspace weights |
| `surface/colony_manager.py` | -- | -- | Mastery restoration |
| `surface/mcp_server.py` | -- | Maintenance policy tools | configure_scoring, directive param |
| `engine/runner.py` | -- | -- | Directive injection |
| Frontend components | Score breakdown, workflow DAG | -- | Directive panel |

**Overlap in core/types.py:** Three tracks add models. Different classes, no conflict. Coordinate via the same pattern used in Wave 33.

**Overlap in surface/mcp_server.py:** Track B adds maintenance tools, Track C adds configure_scoring and directive param. Different tool registrations, same file. Track B's tools are independent of Track C's.

---

## Sequencing

**Track A starts immediately.** Parallel planning and explainability have no dependencies on B or C.

**Track B starts after A's parallel planner is functional** (not necessarily fully landed -- B needs the concurrent spawn_colony capability). B1 (autonomy levels) and the dispatcher can be built in parallel with A, but B2 (dispatch engine) needs to actually spawn colonies, which requires A1.

**Track C starts when A is stable.** Directives hook into the context assembly. Per-workspace weights modify `_composite_key()`. Mastery restoration is independent and can start immediately.

Can split subagent teams:
- Track A: one for Queen parallel planning (A1+A2), one for explainability (A3+A4)
- Track B: one for autonomy model + dispatcher (B1+B2), one for distillation (B3)
- Track C: one for directives + weights (C1+C2), one for mastery + tests + docs (C3+C4+C5)

---

## What Wave 35 Does NOT Include

- **No Experimentation Engine.** Controlled A/B testing on colony configuration (caste recipes, DyTopo thresholds, model assignments) is the Self-Evolving Colony Architecture's next phase. Wave 36 candidate.
- **No Research Colony as persistent service.** Autonomous arxiv monitoring, trend tracking, and skill bank updates. Wave 36 candidate.
- **No operator behavior learning.** Tracking operator patterns (which entries they promote, which overrides they make, which threads they archive early) and adapting system behavior. Wave 36 data collection, Wave 37 activation.
- **No visual workflow composition.** Canvas-based spatial workflow editor where the operator drags nodes and draws edges. Wave 36+ candidate.
- **No federated distillation.** Two instances collaboratively producing a synthesis that neither could make alone. Wave 36+ after single-instance distillation is proven.
- **No three-tier autonomy with graduated trust building.** The autonomy levels are operator-set, not earned. Earned autonomy (system proves itself over time and gains more independence) is a future refinement.

---

## ADR-045 Outline

**Title:** Event Union Expansion 53 to 55 -- Parallel Planning and Distillation

**D1:** ParallelPlanCreated event. Captures the Queen's delegation plan as a first-class event for audit trail, replay, and operator visibility. Contains the full DelegationPlan with parallel groups, reasoning, and knowledge gaps.

**D2:** KnowledgeDistilled event. Captures the synthesis of a knowledge cluster into a higher-order entry. Contains source entry IDs, cluster statistics, and distillation strategy. Projection handler creates the distilled entry with elevated confidence and stable decay class.

## ADR-046 Outline

**Title:** Autonomy Levels for Self-Maintenance Colonies

**D1:** Three levels: suggest (default, current behavior), auto_notify (auto-dispatch with notification), autonomous (full self-maintenance). Per-workspace via WorkspaceConfigChanged.

**D2:** MaintenancePolicy model: autonomy_level, auto_actions (which insight categories), max_maintenance_colonies (concurrent cap), daily_maintenance_budget (cost cap). Safe defaults: suggest level, 2 max colonies, $1.00 daily budget.

**D3:** Only SuggestedColony-eligible insights can auto-dispatch (contradiction, coverage_gap, stale_cluster). Other insight types (confidence_decline, federation_trust_drop, merge_opportunity, federation_inbound) are informational only and always require operator action.

---

## Smoke Test (Post-Integration)

1. Queen receives "build a REST API with auth and tests." Generates DelegationPlan with research + implementation in parallel, then testing. ParallelPlanCreated event emitted. AG-UI shows DAG.
2. Two parallel colonies run simultaneously. Total wall time < 2x single colony time.
3. Queen explains her decision: "Spawning research and schema in parallel because they have no data dependency."
4. memory_search at full tier returns score_breakdown with stacked bar visualization in knowledge browser.
5. Workspace with contradiction at autonomy=auto_notify, auto_actions=["contradiction"]. Research colony spawns automatically. Operator notified. Contradiction resolves.
6. Workspace with dense co-occurrence cluster at autonomy=auto_notify, auto_actions=["distillation"]. Archivist colony spawns. KnowledgeDistilled event emitted. Distilled entry has stable decay class and elevated confidence.
7. Maintenance colonies respect daily budget cap. Third colony blocked when budget exhausted.
8. Operator sends CONTEXT_UPDATE directive to running colony. Next round includes directive with special framing.
9. Operator sends URGENT CONSTRAINT_ADD. Appears before task description in next round.
10. configure_scoring sets cooccurrence=0.0 for workspace. Retrieval uses custom weights. Invariants 1-4 pass, invariant 5 does not (correct -- co-occurrence disabled).
11. Entry with peak_alpha=25 after 180-day stable decay (current alpha ~13.14). Successful observation applies restoration bonus (~2.37). Ephemeral entry gets no bonus.
12. Autonomy at suggest level: briefing shows SuggestedColony but no colony spawns.
13. Replay with 55 event types including ParallelPlanCreated and KnowledgeDistilled. Projections identical.
14. All documentation accurate for post-35 codebase.
15. `pytest` all pass. `pyright src/` 0 errors. `lint_imports.py` 0 violations.

---

## Priority Stack (if scope must be cut)

| Priority | Item | Track | Rationale |
|----------|------|-------|-----------|
| 1 | A1: Queen parallel planner | A | Foundation for B1-B3, headline capability, 3.6x speed for complex tasks |
| 2 | B1: Autonomy levels | B | Gate for all self-maintenance, safe defaults |
| 3 | B2: Self-maintenance dispatch | B | Connects insight to action, the "self-maintaining" promise |
| 4 | A3: Explainable retrieval | A | Score breakdown rendering, data already exists |
| 5 | C3: Mastery-restoration bonus | C | Research-identified gap, formula is simple |
| 6 | B3: Knowledge distillation | B | Cluster synthesis, builds on 34.5 candidates |
| 7 | A4: Queen decision explanations | A | Trust-building for parallel planning |
| 8 | C1: Operator directives | C | Mid-colony steering, pairs with parallel planning |
| 9 | C2: Per-workspace weights | C | ADR-044 D4, explainability makes it safe |
| 10 | A2: ParallelPlanCreated event | A | Audit trail, can defer if parallel planning works without it |
| 11 | C4+C5: Tests + docs | C | Quality gate |

---

## After Wave 35

The system maintains its own knowledge quality. The Queen plans and executes parallel workflows. Decisions are explainable. The operator can steer mid-colony. Knowledge clusters get synthesized into higher-order entries. The mastery of long-lived knowledge is preserved through restoration bonuses.

Wave 36 picks up the Self-Evolving Colony Architecture vision: the Experimentation Engine (controlled A/B testing on colony configuration), the Research Colony as a persistent service (autonomous trend tracking), and federated distillation (two instances collaboratively synthesizing knowledge). The system doesn't just maintain itself -- it improves itself.
