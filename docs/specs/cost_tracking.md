# Cost Tracking Implementation Reference

Current-state reference for FormicOS cost tracking: how costs are computed,
accumulated, enforced, and displayed. Code-anchored to Wave 60.5. Includes
reasoning/cache token accounting, analysis of the local-vs-cloud cost gap,
and specific remediation suggestions.

---

## The Problem

All cost tracking flows through a single `cost_fn` that multiplies token
counts by per-model rates from the model registry. Local models (llama.cpp
via OpenAI-compatible adapter) have `cost_per_input_token: 0.0` and
`cost_per_output_token: 0.0` in `config/formicos.yaml:47-48`. Every budget
gate, every cost display, and every proactive rule sees $0.00 for local
inference.

When the LLM router falls back to cloud providers (Anthropic, Gemini), those
calls DO have real costs — but the budget tracking mixes them into the same
`total_cost` field that was $0.00 from local calls. The result:

- **Budget gates are inert** for local-only workloads. A colony can run 50
  rounds on local GPU and never trigger warn/downgrade/hard-stop.
- **Budget display is misleading**. Agents see `[Budget: $5.00 remaining
  (100%)]` after consuming 45 minutes of GPU time.
- **Cost outlier detection is blind**. The proactive rule compares $0.00
  medians — no outliers are ever flagged for local runs.
- **Maintenance budget is fictional**. `daily_maintenance_budget: 1.0` (USD)
  never constrains maintenance colonies running on local GPU.
- **Cloud fallback costs are invisible**. Phase 1 v1 had 889 provider
  fallback events — those cloud calls had real costs but were diluted into
  a sea of $0.00 local calls.

---

## Cost Flow: End-to-End

### 1. Token counting at the adapter layer

Each LLM adapter extracts token counts from the provider response:

| Adapter | File | Token source | Notes |
|---------|------|-------------|-------|
| Anthropic | `adapters/llm_anthropic.py:174-182` | `response.usage.input_tokens`, `output_tokens`, `cache_read_input_tokens` | Accurate server-side counts; cache reads extracted |
| Gemini | `adapters/llm_gemini.py:249-256` | `usageMetadata.promptTokenCount`, `candidatesTokenCount`, `thoughtsTokenCount`, `cachedContentTokenCount` | Thinking + cache counts extracted |
| OpenAI-compatible (llama.cpp, OpenAI, DeepSeek, Groq, MiniMax, Mistral) | `adapters/llm_openai_compatible.py:273-274` | `usage.prompt_tokens`, `usage.completion_tokens`, `usage.completion_tokens_details.reasoning_tokens`, `usage.prompt_tokens_details.cached_tokens` | Reasoning + cache details extracted; llama.cpp **streaming returns 0** |

All adapters return `LLMResponse` with six integer fields:
- `input_tokens`, `output_tokens` — always present
- `reasoning_tokens` — reasoning/thinking tokens, subset of output_tokens (default 0)
- `cache_read_tokens` — input tokens served from provider cache (default 0)

The runner accumulates all four per-turn at `runner.py:1489-1493`.

### 2. Cost computation

Cost is computed at `runner.py:1649-1651` after each agent turn:

```python
estimated_cost = self._cost_fn(actual_model, total_input_tokens, total_output_tokens)
```

The `cost_fn` is built by `_build_cost_fn()` at `surface/app.py:169-183`:

```python
def cost_fn(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = rate_map.get(model, (0.0, 0.0))
    return (input_tokens * rates[0]) + (output_tokens * rates[1])
```

The `rate_map` is populated from the model registry in `config/formicos.yaml`.
Local models have rates of `(0.0, 0.0)`. Cloud models have real rates (e.g.,
Anthropic Sonnet: `$3.00/$15.00 per 1M tokens`, Gemini Flash:
`$0.80/$4.00 per 1M tokens`).

The cost function uses `response.model` (the actual serving model after
fallback), not the planned model. So when the router falls back from local
to Anthropic, the Anthropic rates ARE used — but only for that specific call.

### 3. Event emission

Two events carry cost data per agent turn:

**AgentTurnCompleted** (`core/events.py:254-267`):
- `input_tokens: int`, `output_tokens: int` — token primitives
- No cost field

**TokensConsumed** (`core/events.py:444-452`):
- `agent_id, model, input_tokens, output_tokens, cost: float`
- `reasoning_tokens: int = 0`, `cache_read_tokens: int = 0` (Wave 60.5)
- Cost in USD, emitted at `runner.py:1672-1680`

**RoundCompleted** (`core/events.py:270-282`):
- `cost: float` — sum of all agent costs in the round
- Computed at `runner.py:1067`: `cumulative_cost = sum(agent_costs)`

### 4. Accumulation

**Colony level** — `projections.py:1218`:
```python
colony.cost += e.cost  # from RoundCompleted event
```

**Workspace level** — `projections.py:1315-1320` (from TokensConsumed):
```python
budget_truth.record_token_spend(e.model, e.input_tokens, e.output_tokens, e.cost)
```

`BudgetSnapshot` (`projections.py:293-320`) maintains:
- `total_cost: float` — USD total across all models
- `total_input_tokens: int` — aggregate input tokens
- `total_output_tokens: int` — aggregate output tokens
- `total_reasoning_tokens: int` — aggregate reasoning/thinking tokens (Wave 60.5)
- `total_cache_read_tokens: int` — aggregate cache read tokens (Wave 60.5)
- `model_usage: dict[str, dict]` — per-model breakdown of cost, input_tokens,
  output_tokens, reasoning_tokens, cache_read_tokens

The per-model breakdown is the key asset — it already separates local from
cloud usage. The aggregation into `total_cost` is where the signal is lost.

**Colony outcome** — `projections.py:1047-1053`:
- `ColonyOutcome.total_cost = colony.cost`
- `ColonyOutcome.pre_escalation_cost` — cost before compute tier escalation
- Used by proactive intelligence for cost outlier detection

### 5. Budget enforcement

`BudgetEnforcer` at `surface/runtime.py:1619-1718` uses three thresholds:

| Threshold | Utilization | Action | Code |
|-----------|-------------|--------|------|
| WARN | 80% | Log info-level warning | `runtime.py:1664-1669` |
| DOWNGRADE | 90% | Route to cheapest model | `runtime.py:1672-1694` |
| HARD_STOP | 100% | Block spawns, stop colonies | `runtime.py:1696-1718` |

Utilization is: `ws.budget.total_cost / ws.budget_limit`

Colony-level enforcement in `colony_manager.py:673-676` — checks workspace
hard stop at each round start.

**Budget injection into agent context** — `engine/context.py:339-375`:
```
[Budget: $4.50 remaining (90%) — comfortable]
[Iteration 2/7 · Round 3/25]
```

Agent sees remaining USD and regime classification (comfortable / tightening /
critical / exhausted). When local models produce $0.00 cost, agents always
see "comfortable" regardless of actual resource consumption.

### 6. Maintenance budget

`daily_maintenance_budget` in `MaintenancePolicy` (`core/types.py:849`)
defaults to `$1.00`. The `MaintenanceDispatcher` at
`surface/self_maintenance.py:72-77` computes:

```python
budget_remaining = policy.daily_maintenance_budget - self._daily_spend.get(workspace_id, 0.0)
```

`_daily_spend` accumulates colony costs. With local models at $0.00,
maintenance colonies never consume budget — the dispatcher can spawn
unlimited maintenance work.

### 7. Proactive cost outlier rule

`_rule_cost_outlier()` at `surface/proactive_intelligence.py:652-684`:

- Requires ≥5 colonies with non-zero costs
- Flags colonies at >2.5× median cost
- With local models, all costs are $0.00 → fewer than 5 non-zero colonies
  → rule never fires

### 8. Queen cost display

**Follow-up summary** (`queen_runtime.py:384-404`):
```
Colony **csv-parser** completed well after 8 round(s). Quality: 61%. Cost: $0.0000.
```

**Colony info** (`queen_tools.py:1519-1521`):
```
Cost: $0.0000 / $5.00
```

**Outcomes endpoint** (`routes/api.py:462`):
```python
total_cost = sum(o.total_cost for o, _ in ws_outcomes)
```

All display paths show $0.00 for local-only workloads.

---

## What Already Works

The per-model breakdown in `BudgetSnapshot.model_usage` already separates
local from cloud. A workspace that ran 100 local calls and 5 Anthropic
fallback calls has:

```python
model_usage = {
    "llama-cpp/qwen3-30b": {"cost": 0.0, "input_tokens": 450000, "output_tokens": 80000},
    "anthropic/claude-sonnet": {"cost": 0.23, "input_tokens": 15000, "output_tokens": 3000},
}
```

The data is there. The problem is that `total_cost` sums both, and all gates
use `total_cost`.

---

## Suggestions

### S1: Split cost into `api_cost` and `local_tokens`

Add two derived properties to `BudgetSnapshot`:

```python
@property
def api_cost(self) -> float:
    """Real USD cost from cloud providers only."""
    return sum(
        v.get("cost", 0.0) for k, v in self.model_usage.items()
        if v.get("cost", 0.0) > 0
    )

@property
def local_tokens(self) -> int:
    """Total tokens processed by local models (cost == 0)."""
    return sum(
        int(v.get("input_tokens", 0) + v.get("output_tokens", 0))
        for k, v in self.model_usage.items()
        if v.get("cost", 0.0) == 0
    )
```

This is purely additive — no schema changes, no event changes. The existing
`total_cost` stays for backward compatibility.

**Touch points**: `projections.py` (BudgetSnapshot class, ~10 lines).

### S2: Budget enforcement gates on `api_cost`

Change `BudgetEnforcer` to use `ws.budget.api_cost` instead of
`ws.budget.total_cost` for utilization computation. The warn/downgrade/
hard-stop thresholds then gate on real money spent, not fictional local costs.

For local-only workloads (api_cost == 0), the enforcer would never fire
budget gates — which is correct since there's no money being spent. A
separate complexity budget (S4) handles the resource concern.

**Touch points**: `runtime.py` (BudgetEnforcer, ~5 line changes).

### S3: Budget display shows both dimensions

Change the agent-facing budget block at `context.py:339-375` to:

```
[API Budget: $4.50 remaining (90%) — comfortable]
[Local: 45K tokens processed]
[Iteration 2/7 · Round 3/25]
```

And Queen-facing displays at `queen_runtime.py:384` and `queen_tools.py:1519`:

```
Cost: $0.23 API / 450K local tokens / $5.00 budget
```

**Touch points**: `context.py:359-362` (budget block format), `queen_runtime.py:384-404`
(follow-up), `queen_tools.py:1519-1521` (colony info).

### S4: Local complexity budget (time-based)

Add a `time_budget_seconds` field to colony configuration alongside
`budget_limit`. The runner already tracks elapsed time at `runner.py:1430-1442`
(the time guard). Extend it to check against a configurable time budget:

- Default: 600s (10 minutes) per colony
- Warn at 80% (8 minutes)
- Hard stop at 100% (10 minutes)

This gives local-only workloads meaningful resource gating without
pretending GPU time has a dollar cost.

For the budget block, show time remaining alongside API cost:

```
[API Budget: $5.00 remaining (100%)]
[Time: 7:30 remaining of 10:00 — comfortable]
```

**Touch points**: `core/types.py` (add time_budget_seconds to colony config),
`runner.py:1430-1442` (extend time guard to use configurable budget),
`context.py:339-375` (budget block format), `queen_tools.py:975` (spawn
parameter).

### S5: Cost outlier rule uses `api_cost`

Change `_rule_cost_outlier()` at `proactive_intelligence.py:652-684` to use
`api_cost` from colony outcomes. For local-only workloads, add a parallel
`_rule_time_outlier()` that flags colonies exceeding 2.5× median wall time.

**Touch points**: `proactive_intelligence.py` (~30 lines), `projections.py`
(ColonyOutcome needs `api_cost` and `duration_ms` — `duration_ms` already
exists).

### S6: Maintenance budget uses `api_cost`

Change `MaintenanceDispatcher._daily_spend` to track only cloud API costs.
Local-only maintenance colonies don't decrement the budget. When a
maintenance colony uses cloud fallback, its API cost is tracked.

**Touch points**: `self_maintenance.py:72-77` (~3 lines).

---

## Suggested Implementation Order

| Phase | Suggestions | Effort | Value |
|-------|------------|--------|-------|
| **1** | S1 + S2 + S6 | ~20 lines | Budget enforcement and maintenance gating become meaningful |
| **2** | S3 | ~15 lines | Operator and agent see accurate cost information |
| **3** | S5 | ~30 lines | Proactive intelligence works for local workloads |
| **4** | S4 | ~40 lines | Time-based gating for local inference (new concept) |

Phase 1 is the highest leverage: 20 lines that make every existing budget
gate work correctly. Phase 4 is the biggest change (introduces a new budget
dimension) and can be deferred until local-only workloads need gating.

---

## Key Source Files

| File | Cost Role |
|------|-----------|
| `config/formicos.yaml:36-85` | Model registry with per-model cost rates |
| `surface/app.py:169-183` | `_build_cost_fn()` — rate lookup closure |
| `engine/runner.py:1649-1680` | Per-turn cost computation + event emission |
| `surface/projections.py:293-320` | `BudgetSnapshot` — accumulation with per-model breakdown |
| `surface/projections.py:1218` | Colony cost accumulation from RoundCompleted |
| `surface/projections.py:1315-1320` | Workspace cost accumulation from TokensConsumed |
| `surface/runtime.py:1619-1718` | `BudgetEnforcer` — warn/downgrade/hard-stop gates |
| `engine/context.py:339-375` | `build_budget_block()` — agent-facing budget display |
| `surface/queen_runtime.py:384-404` | Queen follow-up cost display |
| `surface/queen_tools.py:975,1519-1521` | Colony spawn budget_limit, colony info display |
| `surface/proactive_intelligence.py:652-684` | Cost outlier detection rule |
| `surface/self_maintenance.py:72-77` | Maintenance daily budget enforcement |
| `core/events.py:444-452` | TokensConsumed event (model, tokens, cost, reasoning, cache) |
| `core/events.py:270-282` | RoundCompleted event (round cost) |
| `core/types.py:849` | `daily_maintenance_budget` in MaintenancePolicy |
| `adapters/llm_anthropic.py:174-182` | Anthropic token extraction |
| `adapters/llm_gemini.py:249-256` | Gemini token extraction |
| `adapters/llm_openai_compatible.py:273-274` | OpenAI/llama.cpp token extraction |
| `adapters/telemetry_otel.py:119-137` | OTel metrics: tokens, cost, duration per call |
