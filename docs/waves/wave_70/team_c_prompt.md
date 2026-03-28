# Wave 70 — Team C: Autonomy Guardrails

**Theme:** The Queen earns trust through a track record, checks her budget
before acting, and escalates high-impact work.

## Context

Read `docs/waves/wave_70/wave_70_plan.md` first. Read `CLAUDE.md` for hard
constraints.

FormicOS already has autonomy infrastructure:

- **`MaintenanceDispatcher`** (`self_maintenance.py`) with 3 levels:
  `suggest`, `auto_notify`, `autonomous`. Daily budget tracking via
  `_daily_spend` dict, reset at UTC midnight (line 243). Per-caste cost
  estimates (line 38): researcher=$0.08, archivist=$0.05, coder=$0.12/round.
- **`MaintenancePolicy`** (`core/types.py`) with `autonomy_level`,
  `auto_actions`, `max_maintenance_colonies`, `daily_maintenance_budget`.
- **`BudgetEnforcer`** (`runtime.py:1661`) with workspace hard stop at 100%,
  soft warn at 80%, downgrade at 90%.
- **`BudgetSnapshot`** (`projections.py:289`) tracking `total_cost`,
  `model_usage`, `api_cost`.
- **`ColonyOutcome`** (`projections.py:89`) with `succeeded`, `total_rounds`,
  `total_cost`, `quality_score`, `caste_composition`, `strategy`.
- **Earned autonomy rule** (`proactive_intelligence/rules.py:1237`) —
  recommendation-only: ≥5 follow-throughs + >70% rate triggers promotion
  insight, ≥3 kills + >50% negative rate triggers demotion insight.

This wave extends these foundations with three new capabilities: daily cost
caps visible to the Queen, blast radius estimation for autonomous dispatch,
and graduated autonomy scoring from outcome history.

## Your Files (exclusive ownership)

### Surface
- `src/formicos/surface/self_maintenance.py` — daily cost cap enforcement,
  blast radius estimator, autonomy scoring integration
- `src/formicos/surface/queen_tools.py` — `check_autonomy_budget` new Queen
  tool (additive to handler registry)
- `config/caste_recipes.yaml` — add `check_autonomy_budget` to Queen tool
  list

### Tests
- `tests/unit/surface/test_autonomy_guardrails.py` — **new**

## Do Not Touch

- `src/formicos/surface/queen_runtime.py` — Team B owns
- `src/formicos/surface/addon_loader.py` — Team A owns
- `src/formicos/surface/projections.py` — no projection changes
- `src/formicos/core/events.py` — no new events
- `src/formicos/core/types.py` — no type changes (extend `MaintenancePolicy`
  via workspace config, not model changes)
- `src/formicos/engine/` — any file
- `frontend/` — no frontend changes this wave
- `src/formicos/addons/proactive_intelligence/rules.py` — the earned
  autonomy rule stays recommendation-only; this wave adds a scoring
  function that the rule can reference, but the rule file itself is not
  modified

## Overlap Coordination

- Team A adds `discover_mcp_tools` to `queen_tools.py` and
  `caste_recipes.yaml`. Team B adds `propose_project_milestone` and
  `complete_milestone`. You add `check_autonomy_budget`. All additive to
  different sections. No conflict.
- All three teams touch `caste_recipes.yaml` to append tool names. The
  changes are additive. Merge last team's changes carefully.

---

## Track 7: Daily Cost Budget with Cap

### Problem

The `MaintenanceDispatcher` has a `daily_maintenance_budget` in the policy,
but the **Queen** has no visibility into how much of that budget remains.
She dispatches colonies without knowing if the workspace is approaching its
daily cost limit. The operator has no way to set a daily cap that applies
to all Queen-initiated work (not just maintenance).

### Implementation

**1. Queen tool: `check_autonomy_budget` in `queen_tools.py`.**

Add to the handler registry (around line 198):

```python
"check_autonomy_budget": lambda i, w, t: self._check_autonomy_budget(i, w, t),
```

Handler:

```python
def _check_autonomy_budget(
    self,
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """Show the Queen her remaining daily budget and autonomy status."""
    # Get maintenance policy
    import json as _json

    ws = self._runtime.projections.workspaces.get(workspace_id)
    if ws is None:
        return ("Workspace not found.", None)

    raw_policy = ws.config.get("maintenance_policy")
    policy = MaintenancePolicy()
    if raw_policy is not None:
        try:
            data = _json.loads(raw_policy) if isinstance(raw_policy, str) else raw_policy
            policy = MaintenancePolicy(**data)
        except Exception:
            pass

    # Get daily spend from MaintenanceDispatcher
    dispatcher = getattr(self._runtime, "maintenance_dispatcher", None)
    daily_spend = 0.0
    if dispatcher is not None:
        dispatcher._reset_daily_budget_if_needed()
        daily_spend = dispatcher._daily_spend.get(workspace_id, 0.0)

    budget_limit = policy.daily_maintenance_budget
    remaining = max(0.0, budget_limit - daily_spend)

    # Get workspace total budget info
    budget = ws.budget
    total_cost = budget.total_cost if budget else 0.0

    # Get active maintenance colony count
    active_maintenance = 0
    if dispatcher is not None:
        active_maintenance = dispatcher._count_active_maintenance_colonies(
            workspace_id,
        )

    lines = [
        "## Autonomy Budget Status",
        "",
        f"**Autonomy level:** {policy.autonomy_level}",
        f"**Daily budget:** ${budget_limit:.2f}",
        f"**Spent today:** ${daily_spend:.2f}",
        f"**Remaining:** ${remaining:.2f}",
        f"**Active maintenance colonies:** {active_maintenance}"
        f" / {policy.max_maintenance_colonies} max",
        "",
        f"**Workspace total cost:** ${total_cost:.2f}",
    ]

    if policy.auto_actions:
        lines.append(
            f"**Auto-dispatch categories:** {', '.join(policy.auto_actions)}"
        )
    else:
        lines.append("**Auto-dispatch categories:** none")

    if remaining <= 0:
        lines.append("")
        lines.append(
            "⚠ Daily budget exhausted. No autonomous dispatch until "
            "midnight UTC reset."
        )
    elif remaining < budget_limit * 0.2:
        lines.append("")
        lines.append(
            f"⚠ Budget running low ({remaining / budget_limit:.0%} remaining)."
        )

    return ("\n".join(lines), None)
```

Tool spec — add to `_queen_tools()` list:

```python
# Wave 70 Track 7: autonomy budget visibility
{
    "name": "check_autonomy_budget",
    "description": (
        "Check daily autonomy budget status: remaining budget, "
        "active maintenance colonies, and autonomy level."
    ),
    "parameters": {
        "type": "object",
        "properties": {},
    },
},
```

**2. Update `caste_recipes.yaml`.**

Add `"check_autonomy_budget"` to the Queen tools array (line 207).

**3. Budget-aware dispatch gate in `MaintenanceDispatcher`.**

The existing `evaluate_and_dispatch()` (self_maintenance.py:57) already
checks `budget_remaining` against `insight.suggested_colony.estimated_cost`.
This is sufficient. No changes needed to the dispatch gate itself.

The new value is that the Queen can **proactively check** her budget before
deciding to spawn colonies, rather than only discovering budget exhaustion
when a maintenance dispatch is skipped silently.

---

## Track 8: Blast Radius Estimator

### Problem

When the Queen considers dispatching work autonomously, she has no way to
estimate the impact scope. A "rename a variable" task has low blast radius;
a "refactor the auth module" task has high blast radius. The Queen should
escalate high-impact work to the operator.

### Implementation

**1. `estimate_blast_radius()` function in `self_maintenance.py`.**

A pure function that scores the estimated impact of a proposed task. No
LLM calls. Uses heuristic signals only.

```python
@dataclass
class BlastRadiusEstimate:
    """Estimated scope and impact of a proposed autonomous action."""

    score: float  # 0.0 (trivial) to 1.0 (high impact)
    level: str  # "low", "medium", "high"
    factors: list[str]  # human-readable explanations
    recommendation: str  # "proceed", "notify", "escalate"


def estimate_blast_radius(
    task: str,
    caste: str = "coder",
    max_rounds: int = 3,
    strategy: str = "sequential",
    workspace_id: str = "",
    projections: ProjectionStore | None = None,
) -> BlastRadiusEstimate:
    """Estimate the blast radius of a proposed autonomous dispatch.

    Uses deterministic heuristics only. No LLM calls.
    """
    score = 0.0
    factors: list[str] = []

    # Factor 1: task length as proxy for complexity
    task_len = len(task)
    if task_len > 500:
        score += 0.2
        factors.append("Long task description (complex scope)")
    elif task_len > 200:
        score += 0.1
        factors.append("Medium-length task description")

    # Factor 2: caste risk profile
    caste_risk = {
        "coder": 0.3,  # writes files
        "reviewer": 0.1,  # read-only
        "researcher": 0.1,  # read-only
        "archivist": 0.05,  # knowledge-only
    }
    risk = caste_risk.get(caste, 0.2)
    score += risk
    if risk >= 0.3:
        factors.append(f"Caste '{caste}' can modify files")

    # Factor 3: round count as proxy for complexity
    if max_rounds > 5:
        score += 0.15
        factors.append(f"High round budget ({max_rounds} rounds)")
    elif max_rounds > 3:
        score += 0.05

    # Factor 4: strategy
    if strategy == "stigmergic":
        score += 0.1
        factors.append("Stigmergic strategy (multi-agent, harder to predict)")

    # Factor 5: keyword signals in task text
    high_risk_keywords = [
        "delete", "remove", "drop", "migrate", "refactor",
        "rename", "replace all", "database", "schema", "deploy",
        "production", "auth", "security", "permission",
    ]
    task_lower = task.lower()
    matched = [kw for kw in high_risk_keywords if kw in task_lower]
    if matched:
        score += 0.15 * min(len(matched), 3)
        factors.append(f"High-risk keywords: {', '.join(matched[:3])}")

    # Factor 6: prior outcome history for this caste/strategy
    if projections and workspace_id:
        stats = projections.outcome_stats(workspace_id)
        for stat in stats:
            if stat["strategy"] == strategy and caste in stat.get("caste_mix", ""):
                if stat["success_rate"] < 0.5 and stat["total"] >= 3:
                    score += 0.2
                    factors.append(
                        f"Low historical success rate for {strategy}/{caste}: "
                        f"{stat['success_rate']:.0%}"
                    )
                break

    # Clamp score
    score = min(1.0, max(0.0, score))

    # Determine level and recommendation
    if score >= 0.6:
        level = "high"
        recommendation = "escalate"
    elif score >= 0.3:
        level = "medium"
        recommendation = "notify"
    else:
        level = "low"
        recommendation = "proceed"

    return BlastRadiusEstimate(
        score=round(score, 2),
        level=level,
        factors=factors,
        recommendation=recommendation,
    )
```

**2. Integrate with `evaluate_and_dispatch()`.**

Before spawning a maintenance colony, call `estimate_blast_radius()` and
skip dispatch if the recommendation is `"escalate"`:

```python
# In evaluate_and_dispatch(), before _spawn_maintenance_colony():
from formicos.surface.self_maintenance import estimate_blast_radius

estimate = estimate_blast_radius(
    task=sc.task,
    caste=sc.caste,
    max_rounds=sc.max_rounds,
    strategy=sc.strategy,
    workspace_id=workspace_id,
    projections=self._runtime.projections,
)

if estimate.recommendation == "escalate":
    log.info(
        "maintenance.blast_radius_escalation",
        workspace_id=workspace_id,
        category=insight.category,
        score=estimate.score,
        factors=estimate.factors,
    )
    continue  # Skip this insight, leave for operator
```

For `auto_notify` level, also skip dispatch when recommendation is
`"notify"` — the insight is already surfaced in the briefing. For
`autonomous` level, proceed on `"notify"` but skip on `"escalate"`.

**3. Make blast radius available to `check_autonomy_budget` tool.**

When the Queen checks her budget, she can also see the blast radius
estimate for a proposed task. Add an optional `task` parameter to
`check_autonomy_budget`:

```python
# In the tool spec:
"task": {
    "type": "string",
    "description": (
        "Optional task description to estimate blast radius"
    ),
},
```

If `task` is provided, append the blast radius estimate to the output:

```python
task_text = inputs.get("task", "")
if task_text:
    estimate = estimate_blast_radius(
        task=task_text,
        workspace_id=workspace_id,
        projections=self._runtime.projections,
    )
    lines.extend([
        "",
        "## Blast Radius Estimate",
        f"**Score:** {estimate.score} ({estimate.level})",
        f"**Recommendation:** {estimate.recommendation}",
    ])
    for factor in estimate.factors:
        lines.append(f"  - {factor}")
```

---

## Track 9: Graduated Autonomy Scoring

### Problem

The earned autonomy rule in `proactive_intelligence/rules.py` uses simple
thresholds (≥5 follow-throughs, >70% rate). It generates promotion/demotion
insights but has no continuous scoring function. A graduated score would
give the Queen and operator a clearer picture of where trust stands.

### Implementation

**1. `compute_autonomy_score()` function in `self_maintenance.py`.**

A pure function that computes a 0–100 trust score from outcome history and
operator behavior. This is a **read-only computation** — it does not
change autonomy levels. The existing earned autonomy rule remains the
recommendation mechanism.

```python
@dataclass
class AutonomyScore:
    """Graduated autonomy trust score from outcome history."""

    score: int  # 0–100
    grade: str  # "A", "B", "C", "D", "F"
    components: dict[str, float]  # breakdown
    recommendation: str  # human-readable


def compute_autonomy_score(
    workspace_id: str,
    projections: ProjectionStore,
) -> AutonomyScore:
    """Compute graduated autonomy trust score from outcome history.

    Components:
    - success_rate (40%): fraction of successful colonies
    - volume (20%): log-scaled colony count (caps at 50 colonies)
    - cost_efficiency (20%): avg cost vs budget (lower is better)
    - operator_trust (20%): follow-through rate minus kill rate
    """
    components: dict[str, float] = {}

    # Success rate
    outcomes = [
        o for o in projections.colony_outcomes.values()
        if o.workspace_id == workspace_id
    ]
    if not outcomes:
        return AutonomyScore(
            score=0,
            grade="F",
            components={"success_rate": 0, "volume": 0,
                        "cost_efficiency": 0, "operator_trust": 0},
            recommendation="No outcome history. Start with supervised dispatch.",
        )

    successes = sum(1 for o in outcomes if o.succeeded)
    success_rate = successes / len(outcomes)
    components["success_rate"] = round(success_rate, 2)

    # Volume (log-scaled, caps at 50)
    import math
    volume = min(1.0, math.log(1 + len(outcomes)) / math.log(51))
    components["volume"] = round(volume, 2)

    # Cost efficiency: avg cost relative to estimated budget
    # Lower cost per colony = higher score
    avg_cost = sum(o.total_cost for o in outcomes) / len(outcomes)
    # Normalize: $0 = 1.0, $1.00 = 0.5, $5.00 = ~0.1
    cost_efficiency = 1.0 / (1.0 + avg_cost * 2)
    components["cost_efficiency"] = round(cost_efficiency, 2)

    # Operator trust: follow-through vs kills
    behavior = getattr(projections, "operator_behavior", None)
    operator_trust = 0.5  # neutral baseline
    if behavior is not None:
        total_acted = sum(behavior.suggestion_categories_acted_on.values())
        total_kills = len(behavior.kill_records)
        total_signals = total_acted + total_kills
        if total_signals > 0:
            operator_trust = total_acted / total_signals
    components["operator_trust"] = round(operator_trust, 2)

    # Weighted score
    raw = (
        success_rate * 0.40
        + volume * 0.20
        + cost_efficiency * 0.20
        + operator_trust * 0.20
    )
    score = int(round(raw * 100))
    score = max(0, min(100, score))

    # Grade
    if score >= 80:
        grade = "A"
    elif score >= 65:
        grade = "B"
    elif score >= 50:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"

    # Recommendation
    if score >= 80:
        recommendation = (
            "Strong track record. Consider promoting to autonomous level."
        )
    elif score >= 65:
        recommendation = (
            "Good track record. Auto-notify with expanded categories "
            "is appropriate."
        )
    elif score >= 50:
        recommendation = (
            "Mixed results. Auto-notify with limited categories recommended."
        )
    elif score >= 35:
        recommendation = (
            "Below average. Suggest-only mode recommended until outcomes improve."
        )
    else:
        recommendation = (
            "Poor track record. Suggest-only mode recommended. Review "
            "recent colony failures."
        )

    return AutonomyScore(
        score=score,
        grade=grade,
        components=components,
        recommendation=recommendation,
    )
```

**2. Include autonomy score in `check_autonomy_budget` output.**

At the end of the `_check_autonomy_budget` handler, add:

```python
# Autonomy score
from formicos.surface.self_maintenance import compute_autonomy_score

auto_score = compute_autonomy_score(
    workspace_id, self._runtime.projections,
)
lines.extend([
    "",
    "## Autonomy Score",
    f"**Score:** {auto_score.score}/100 (Grade: {auto_score.grade})",
    f"**Recommendation:** {auto_score.recommendation}",
])
for component, value in auto_score.components.items():
    lines.append(f"  - {component}: {value}")
```

This gives the Queen a single tool call that shows budget status, blast
radius estimate (if task provided), and autonomy score — everything she
needs to decide whether to act autonomously or escalate.

---

## Tests

Create `tests/unit/surface/test_autonomy_guardrails.py`:

1. `test_estimate_blast_radius_low` — simple task, researcher caste, 2
   rounds → score < 0.3, level "low", recommendation "proceed".

2. `test_estimate_blast_radius_high` — long task with "delete" + "database"
   keywords, coder caste, 8 rounds, stigmergic → score ≥ 0.6, level "high",
   recommendation "escalate".

3. `test_estimate_blast_radius_medium` — moderate task, coder caste, 3
   rounds → score between 0.3 and 0.6, level "medium".

4. `test_estimate_blast_radius_uses_outcome_history` — mock projections
   with low success rate for coder/sequential, assert score increases.

5. `test_compute_autonomy_score_no_outcomes` — empty outcomes → score 0,
   grade "F".

6. `test_compute_autonomy_score_perfect` — all successes, high volume, low
   cost, positive operator trust → score ≥ 80, grade "A".

7. `test_compute_autonomy_score_mixed` — 50% success, moderate volume →
   score in C/D range.

8. `test_check_autonomy_budget_tool_returns_status` — mock runtime with
   policy and dispatcher, call handler, assert output includes budget
   remaining and autonomy level.

9. `test_blast_radius_blocks_dispatch` — mock MaintenanceDispatcher with
   a high-risk insight, assert colony is NOT spawned when blast radius
   recommends escalation.

10. `test_daily_budget_exhausted_message` — set daily_spend equal to
    budget, call `check_autonomy_budget`, assert "exhausted" message.

**Test setup pattern:** Mock `Runtime` with projections containing
`ColonyOutcome` entries and operator behavior records. Follow existing
patterns in `tests/unit/surface/` for runtime mocking.

---

## Acceptance Gates

- [ ] `check_autonomy_budget` Queen tool returns daily budget status
- [ ] Budget output includes remaining amount, active colonies, autonomy level
- [ ] Budget exhaustion shown clearly when daily limit reached
- [ ] `estimate_blast_radius()` returns scored estimate without LLM calls
- [ ] Blast radius uses 6 heuristic factors (task length, caste risk,
      rounds, strategy, keywords, outcome history)
- [ ] High blast radius blocks autonomous dispatch in `evaluate_and_dispatch()`
- [ ] `compute_autonomy_score()` returns 0–100 score from outcome history
- [ ] Score includes 4 weighted components (success, volume, efficiency, trust)
- [ ] Autonomy score included in `check_autonomy_budget` output
- [ ] No changes to earned autonomy rule in proactive_intelligence
- [ ] No new event types
- [ ] No projection changes
- [ ] No type changes to `MaintenancePolicy`
- [ ] No frontend changes
- [ ] All tests pass

## Validation

```bash
pytest tests/unit/surface/test_autonomy_guardrails.py -v
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
