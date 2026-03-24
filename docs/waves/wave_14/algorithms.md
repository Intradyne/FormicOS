# Wave 14 Algorithms and Implementation Reference

**Audience:** Offline coders implementing Wave 14 without internet access.  
**Repo reality:** Use the actual module seams in this repo, not conceptual ones.

---

## 1. Repo module map

- `src/formicos/core/types.py`
  - repo-native value objects and config models use `pydantic.BaseModel`, `ConfigDict`, `Field`
- `src/formicos/core/events.py`
  - event union and event payload models
- `src/formicos/engine/context.py`
  - context assembly and prompt shaping
- `src/formicos/engine/runner.py`
  - round execution loop
- `src/formicos/engine/service_router.py`
  - new in Wave 14
- `src/formicos/surface/runtime.py`
  - `Runtime.build_agents()`, spawn/build logic, `LLMRouter`
- `src/formicos/surface/commands.py`
  - WS mutation commands
- `src/formicos/surface/app.py`
  - HTTP routes
- `src/formicos/surface/mcp_server.py`
  - MCP tool registration
- `src/formicos/surface/colony_manager.py`
  - lifecycle/status tracking; new service/chat methods land here in Wave 14
- `src/formicos/surface/projections.py`
  - projections and new event handlers
- `src/formicos/surface/view_state.py`
  - materialized views including colony chat
- `src/formicos/surface/template_manager.py`
  - exists from Wave 11; Wave 14 migrates it from `caste_names` to `CasteSlot`

Important correction:
- `build_agents()` is in `surface/runtime.py`, not `engine/runner.py`
- spawn flow crosses `commands.py` and `runtime.py`; there is no single `colony_manager.spawn()`

---

## 2. Core type additions

Match the repo's existing Pydantic style.

```python
from enum import StrEnum

from pydantic import BaseModel, Field

FrozenConfig = ConfigDict(frozen=True, extra="forbid")


class SubcasteTier(StrEnum):
    light = "light"
    standard = "standard"
    heavy = "heavy"
    flash = "flash"


class ChatSender(StrEnum):
    operator = "operator"
    queen = "queen"
    system = "system"
    agent = "agent"
    service = "service"


class ToolCategory(StrEnum):
    read_fs = "read_fs"
    write_fs = "write_fs"
    exec_code = "exec_code"
    search_web = "search_web"
    vector_query = "vector_query"
    llm_call = "llm_call"
    shell_cmd = "shell_cmd"
    network_out = "network_out"
    delegate = "delegate"


class CasteSlot(BaseModel):
    model_config = FrozenConfig

    caste: str = Field(..., description="Caste name.")
    tier: SubcasteTier = Field(
        default=SubcasteTier.standard, description="Routing tier override."
    )
    count: int = Field(default=1, description="Number of agents to spawn.")


class CasteToolPolicy(BaseModel):
    model_config = FrozenConfig

    caste: str
    allowed_categories: frozenset[ToolCategory]
    denied_tools: frozenset[str] = frozenset()
    max_tool_calls_per_iteration: int = 10
```

Do not introduce `msgspec.Struct` here unless the repo is deliberately changing type systems. That is not the current design.

---

## 3. Budget regime injection

**Owner:** Stream B  
**File:** `src/formicos/engine/context.py`

Inject a budget block into the system prompt before each LLM call.

```python
def _budget_regime_block(
    budget_total: float,
    cost_accumulated: float,
    iteration: int,
    max_iterations: int,
    round_num: int,
    max_rounds: int,
) -> str:
    remaining = max(budget_total - cost_accumulated, 0.0)
    pct = remaining / budget_total if budget_total > 0 else 0.0

    if pct >= 0.70:
        advice = "You have room for detailed exploration. Use multiple tool calls if helpful."
    elif pct >= 0.30:
        advice = "Be focused. Prioritize the most promising approach."
    elif pct >= 0.10:
        advice = "Budget is low. Wrap up your current approach."
    else:
        advice = "Budget nearly exhausted. Answer with what you have."

    return (
        "[Budget Status]\n"
        f"Budget remaining: ${remaining:.2f} ({pct:.0%})\n"
        f"Iterations: {iteration}/{max_iterations}\n"
        f"Round: {round_num}/{max_rounds}\n"
        f"Advice: {advice}"
    )
```

Append this to the system prompt in the existing context assembly path. Do not create a second prompt store.

---

## 4. Tool permission enforcement

**Owner:** Stream B  
**Files:** `src/formicos/core/types.py`, `src/formicos/engine/runner.py`

Policy is hardcoded in `core/types.py` for Wave 14.

```python
CASTE_TOOL_POLICIES: dict[str, CasteToolPolicy] = {
    "manager": CasteToolPolicy(
        caste="manager",
        allowed_categories=frozenset({
            ToolCategory.read_fs,
            ToolCategory.vector_query,
            ToolCategory.llm_call,
            ToolCategory.delegate,
        }),
        max_tool_calls_per_iteration=5,
    ),
    "coder": CasteToolPolicy(
        caste="coder",
        allowed_categories=frozenset({
            ToolCategory.read_fs,
            ToolCategory.write_fs,
            ToolCategory.exec_code,
            ToolCategory.vector_query,
        }),
        denied_tools=frozenset({"rm", "chmod", "chown", "sudo"}),
        max_tool_calls_per_iteration=15,
    ),
}
```

Enforcement happens before tool dispatch in `engine/runner.py`.

```python
def check_tool_permission(
    tool_name: str,
    caste: str,
    iteration_tool_count: int,
) -> tuple[bool, str]:
    policy = CASTE_TOOL_POLICIES.get(caste)
    if policy is None:
        return False, f"Unknown caste '{caste}'"

    category = TOOL_CATEGORIES.get(tool_name)
    if category is None:
        return False, f"Tool '{tool_name}' has no category mapping"

    if tool_name in policy.denied_tools:
        return False, f"Tool '{tool_name}' is denied for caste '{caste}'"

    if category not in policy.allowed_categories:
        return False, f"Category '{category.value}' not permitted for caste '{caste}'"

    if iteration_tool_count >= policy.max_tool_calls_per_iteration:
        return False, "Tool call limit reached for this iteration"

    return True, ""
```

Unknown tools must fail closed.

---

## 5. Provider cooldown cache

**Owner:** Stream B  
**File:** `src/formicos/surface/runtime.py`

This extends `LLMRouter`. It does not replace the existing routing table.

```python
class _ProviderCooldown:
    def __init__(self, window_s: float = 60.0, max_failures: int = 3):
        self.window_s = window_s
        self.max_failures = max_failures
        self._failures: list[float] = []
        self.cooldown_until: float = 0.0

    def record_failure(self, now: float, duration_s: float) -> None:
        self._failures = [t for t in self._failures if now - t < self.window_s]
        self._failures.append(now)
        if len(self._failures) >= self.max_failures:
            self.cooldown_until = now + duration_s
            self._failures.clear()

    def is_active(self, now: float) -> bool:
        return now < self.cooldown_until
```

Important distinction:
- Gemini safety/recitation block is a per-request fallback case
- it does not increment the provider cooldown counter

Tier routing order in `LLMRouter.route()`:
1. apply tier override
2. check whether the chosen provider is cooled down
3. use routing-table fallback if needed
4. if all cloud providers are unavailable, fall back to local

---

## 6. Per-caste iteration caps and timeouts

**Owner:** Stream B  
**Files:** `config/caste_recipes.yaml`, `src/formicos/engine/runner.py`

Add:
- `max_iterations`
- `max_execution_time_s`

When an agent hits a limit:
- preserve the latest partial output
- emit a `ColonyChatMessage` with sender `system`
- continue the round rather than failing the whole colony

This logic belongs in the runner's agent-turn loop, not in `runtime.py`.

---

## 7. Service router

**Owner:** Stream C  
**File:** `src/formicos/engine/service_router.py`

The service router tracks active service colonies and manages request/response matching.

Message convention:

```text
[Service Query: svc-col-abc-1710441060000]
What JWT libraries work with async Python?
```

```text
[Service Response: svc-col-abc-1710441060000]
python-jose and PyJWT are the most likely fits...
```

Minimal shape:

```python
class ServiceRouter:
    def __init__(self):
        self._registry: dict[str, str] = {}
        self._waiters: dict[str, asyncio.Event] = {}
        self._responses: dict[str, str] = {}

    def register(self, service_type: str, colony_id: str) -> None: ...
    def unregister(self, service_type: str) -> None: ...
    async def query(...) -> str: ...
    def resolve_response(self, request_id: str, response_text: str) -> None: ...
```

Important repo note:
- `colony_manager.inject_message()` does not exist yet
- Stream C creates it in `src/formicos/surface/colony_manager.py`

Service-response detection belongs in `engine/runner.py` after agent output is captured.

---

## 8. Colony chat selection rules

**Owner:** Stream C  
**Files:** `src/formicos/engine/runner.py`, `src/formicos/surface/projections.py`, `src/formicos/surface/view_state.py`

The table below is the rule set for what becomes a `ColonyChatMessage`.

| Content | In chat | Emitted by |
|---|---|---|
| Round start | Yes | `engine/runner.py` |
| Phase transition | Yes | `engine/runner.py` |
| Governance warning | Yes | `engine/runner.py` |
| Iteration/time limit hit | Yes | `engine/runner.py` |
| Tool permission denied | Yes | `engine/runner.py` |
| Code execution result summary | Yes | `engine/runner.py` |
| Colony complete/failed | Yes | `engine/runner.py` |
| Approval request | Yes | `engine/runner.py` |
| Operator colony message | Yes | `surface/commands.py` |
| Service query sent/received summary | Yes | `engine/service_router.py` |
| Agent token streams | No | keep in detailed output panels |
| DyTopo weights | No | topology/diagnostics only |
| Individual tool-call transcripts | No | detailed output panels only |
| Per-call token counts | No | diagnostics/cost views only |

Materialization belongs in `ColonyChatViewRegistry` in `surface/view_state.py`.

---

## 9. Template YAML schema

**Owner:** Stream A for schema/manager, Stream C for Save As flow  
**Files:** `src/formicos/surface/template_manager.py`, `config/templates/*.yaml`

```yaml
name: full-stack
version: 1
description: Balanced team for implementation tasks
tags: [coding, implementation, refactoring]

castes:
  - caste: manager
    tier: heavy
    count: 1
  - caste: coder
    tier: standard
    count: 2
  - caste: reviewer
    tier: light
    count: 1
  - caste: archivist
    tier: light
    count: 1

governance:
  max_rounds: 12
  budget_usd: 5.0
```

`save_from_colony()` should serialize the current colony shape into this schema, not the old `caste_names` layout.

---

## 10. CasteSlot migration sequence

**Owner:** Stream A

Ordered file sequence:

1. `core/types.py`
2. `core/events.py`
3. `surface/runtime.py`
4. `surface/commands.py`
5. `surface/mcp_server.py`
6. `surface/colony_manager.py`
7. `surface/projections.py`
8. `surface/view_state.py`
9. `surface/template_manager.py` (edit — already exists from Wave 11)
10. `config/templates/*.yaml`
11. `frontend/src/types.ts`
12. `docs/contracts/events.py`
13. `docs/contracts/types.ts`
14. tests still referencing `caste_names`

Validation:

```bash
rg -n "caste_names" src frontend tests docs/contracts
pytest
cd frontend && npm run build
```

---

## 11. Sandbox integration notes

**Owner:** Stream B  
**Files:** `src/formicos/surface/mcp_server.py`, `src/formicos/engine/runner.py`

`code_execute` integration requirements:
- AST pre-check first
- sandbox manager executes code
- output sanitizer runs before result leaves the sandbox path
- emit `CodeExecuted`
- also emit a one-line `ColonyChatMessage` summary for operator visibility

The detailed sandbox implementation is owned by Stream B; the Wave 14 requirement is that it integrates with the event and chat model cleanly.
