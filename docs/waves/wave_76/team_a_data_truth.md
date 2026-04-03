# Wave 76 Team A: Data Truth

**Goal:** After this team's work, every surface shows the same token total,
colony lookups are O(1), and the budget reflects actual spend that survives
restart.

## Owned files

- `src/formicos/surface/projections.py` -- BudgetSnapshot fix + agent-colony index
- `src/formicos/surface/self_maintenance.py` -- reconciliation + daily spend persistence
- `src/formicos/surface/continuation.py` -- continuation estimated-cost bookkeeping + persistence hook
- `src/formicos/surface/colony_manager.py` -- reconciliation hook in `_post_colony_hooks` method body ONLY (lines 1131-1172)
- `src/formicos/surface/app.py` -- startup-time dispatcher handoff ONLY
- `frontend/src/components/budget-panel.ts` -- live token headline must include reasoning

## Do NOT touch

- `src/formicos/surface/action_queue.py` -- Team B
- `src/formicos/surface/queen_runtime.py` -- Team C
- `src/formicos/surface/routes/api.py` -- Team B
- Any frontend files other than `budget-panel.ts` -- Team B or Team C

## Before you code, read these files

1. `src/formicos/surface/projections.py` -- full file. Focus on:
   - `BudgetSnapshot` class at lines 289-310 (the `total_tokens` property at :309-310)
   - `ColonyProjection` at lines 350-400 (the `agents` dict at :368)
   - `ProjectionStore.__init__` at lines 690-704
   - `_on_agent_turn_started` -- this is where `AgentProjection` entries are created today
   - `_on_colony_completed`, `_on_colony_failed`, `_on_colony_killed` -- terminal handlers
   - `_on_tokens_consumed` at lines 1361-1389 (the O(n) scan at :1364-1373)
   - `_on_agent_turn_completed` at lines 1241-1264 (the O(n) fallback scan at :1246-1249)
2. `src/formicos/surface/self_maintenance.py` -- full file. Focus on:
   - `MaintenanceDispatcher.__init__` at lines 269-279 (`_daily_spend` at :278)
   - `_reset_daily_budget_if_needed` at lines 591-596
   - `evaluate_and_dispatch` at lines 281-388 (budget check at :302-303, spend increment at :382-385)
   - `_COST_PER_ROUND` at lines 41-45
3. `src/formicos/surface/continuation.py` -- full file. Focus on:
   - `execute_idle_continuations` at lines 179-308
   - direct `_daily_spend` increment at :281-283
   - action `estimated_cost` use at :249
4. `src/formicos/surface/colony_manager.py` -- two areas:
   - Call site at lines 977-987 (where `_post_colony_hooks` is called after `ColonyCompleted`)
   - Method body at lines 1131-1172 (`_post_colony_hooks` definition -- add reconciliation here)
5. `src/formicos/surface/app.py` around startup wiring:
   - `colony_manager = ColonyManager(runtime)` at :405
   - `_maint_dispatcher = MaintenanceDispatcher(runtime)` at :886-887
6. `docs/waves/architecture_audit_post_75.md` -- sections 1.1 (token truth), 2.3 (budget enforcement), 3.2 (O(n) token scans), 11.2 (daily budget in-memory)
7. `frontend/src/components/budget-panel.ts` -- current "Total Tokens" headline at :178-180 uses `input + output` only

---

## Track 1: Fix BudgetSnapshot.total_tokens

**The single most impactful one-line change in the wave.**

In `projections.py:309-310`, the current property:

```python
@property
def total_tokens(self) -> int:
    return self.total_input_tokens + self.total_output_tokens
```

Change to:

```python
@property
def total_tokens(self) -> int:
    return self.total_input_tokens + self.total_output_tokens + self.total_reasoning_tokens
```

**Why this works:** `total_reasoning_tokens` is already tracked correctly --
`record_token_spend()` (at :329-346) accumulates it from every `TokensConsumed`
event. The property just never included it.

**Verification required:** Search the entire codebase for every consumer of
`.total_tokens` and `total_tokens`. Confirm none will break when reasoning
tokens are included. Key consumers to check:

- `frontend/src/components/budget-panel.ts` -- renders "Total Tokens" from
  `total_input_tokens + total_output_tokens` at :178-180. This DOES need a UI
  change in this wave or the browser surface will stay wrong.
- `src/formicos/surface/metering.py` -- billing at :79-173 already includes
  reasoning. This fix makes the live projection agree with billing.
- `src/formicos/surface/mcp_server.py` -- Wave 75 receipt and billing resources
  already compute `input + output + reasoning`. Verify no double-counting.
- `src/formicos/surface/view_state.py` -- colony cards. Check if they read
  `budget_truth.total_tokens`.

Also update `frontend/src/components/budget-panel.ts` so the headline total is:

```typescript
this._fmtTokens(
  d.total_input_tokens + d.total_output_tokens + d.total_reasoning_tokens,
)
```

**Test:** Existing tests should pass unchanged. Add one test:

```python
def test_total_tokens_includes_reasoning():
    snap = BudgetSnapshot()
    snap.record_token_spend("m", 100, 50, 0.01, reasoning_tokens=25)
    assert snap.total_tokens == 175  # 100 + 50 + 25
```

---

## Track 2: Agent-to-colony reverse index

Add a reverse index to `ProjectionStore` so token and turn handlers don't
scan all colonies.

### Step 1: Add the index to `ProjectionStore.__init__`

After `self.colonies` (line 692):

```python
# Wave 76: agent_id -> colony_id reverse index for O(1) lookup
self._agent_colony_index: dict[str, str] = {}
```

### Step 2: Populate the index when agents are created

Populate the reverse index in `_on_agent_turn_started` (line 1217), which
is where `AgentProjection` entries are created today. After the handler
ensures `colony.agents[e.agent_id]` exists (line 1221-1224), add:

```python
store._agent_colony_index[e.agent_id] = e.colony_id
```

### Step 3: Clean up the index on terminal events

In `_on_colony_completed` (:1128), `_on_colony_failed` (:1155), and
`_on_colony_killed` (:1177) handlers, after existing processing. Each
handler already has a local `colony` variable. Append:

```python
# Wave 76: clean up reverse index
if colony is not None:
    for aid in colony.agents:
        store._agent_colony_index.pop(aid, None)
```

### Step 4: Use the index in `_on_tokens_consumed` (lines 1361-1389)

Replace the linear scan:

```python
# Before (O(n)):
matched_colony: ColonyProjection | None = None
for colony in store.colonies.values():
    agent = colony.agents.get(e.agent_id)
    if agent is not None:
        ...
        matched_colony = colony
        break

# After (O(1) with defensive fallback):
matched_colony: ColonyProjection | None = None
_indexed_cid = store._agent_colony_index.get(e.agent_id)
if _indexed_cid is not None:
    _candidate = store.colonies.get(_indexed_cid)
    if _candidate is not None:
        agent = _candidate.agents.get(e.agent_id)
        if agent is not None:
            if e.model:
                agent.model = e.model
            agent.tokens += (
                e.input_tokens + e.output_tokens + e.reasoning_tokens
            )
            matched_colony = _candidate
if matched_colony is None:
    # Defensive fallback: index miss (should not happen in normal operation)
    for colony in store.colonies.values():
        agent = colony.agents.get(e.agent_id)
        if agent is not None:
            if e.model:
                agent.model = e.model
            agent.tokens += (
                e.input_tokens + e.output_tokens + e.reasoning_tokens
            )
            matched_colony = colony
            break
```

### Step 5: Use the index in `_on_agent_turn_completed` (lines 1241-1264)

Same pattern. The current code at :1244-1249 does a primary lookup by
`colony_id` from the event address, then falls back to a scan. Change
the fallback to use the index first.

**Important:** `AgentTurnCompleted` does NOT carry a `reasoning_tokens`
field (unlike `TokensConsumed`). This handler only resolves the colony --
it does not accumulate tokens. Do not add `reasoning_tokens` here.

```python
if colony is None:
    _indexed_cid = store._agent_colony_index.get(e.agent_id)
    if _indexed_cid is not None:
        colony = store.colonies.get(_indexed_cid)
    if colony is None:
        # Final defensive fallback
        for candidate in store.colonies.values():
            if e.agent_id in candidate.agents:
                colony = candidate
                break
```

**Test:** Add a test that verifies the index is populated on spawn and
cleaned on completion/failure/kill.

---

## Track 3: Budget reconciliation from actual costs

After a colony reaches a terminal state, reconcile the daily spend with the
actual cost.

### Step 1: Track estimated costs per colony

In `MaintenanceDispatcher.__init__` (after `_last_reset` at line 279), add:

```python
self._estimated_costs: dict[str, float] = {}  # colony_id -> estimated cost at dispatch
```

### Step 2: Record the estimate at dispatch time

In `evaluate_and_dispatch`, after the colony is spawned (around line 376-386),
record the estimate:

```python
if cost > 0 and colony_id:
    self._estimated_costs[colony_id] = cost
```

Do the same in the distillation dispatch path (around line 503-510).
Note: the variable there is `estimated_cost`, not `cost`:

```python
if estimated_cost > 0 and colony_id:
    self._estimated_costs[colony_id] = estimated_cost
```

Also record the estimate in `continuation.py` after the colony spawn
at line 266. The variable is also `estimated_cost` (defined at :249):

```python
if estimated_cost > 0 and colony_id:
    dispatcher._estimated_costs[colony_id] = estimated_cost  # pyright: ignore[reportPrivateUsage]
```

### Step 3: Add `reconcile_colony_cost` method

```python
def reconcile_colony_cost(
    self, workspace_id: str, colony_id: str, actual_cost: float,
) -> None:
    """Reconcile estimated vs actual colony cost in daily spend."""
    if colony_id not in self._estimated_costs:
        return  # only reconcile colonies that this dispatcher budgeted for
    estimated = self._estimated_costs.pop(colony_id, 0.0)
    if estimated == 0.0 and actual_cost == 0.0:
        return
    adjustment = actual_cost - estimated
    if adjustment != 0.0:
        self._daily_spend[workspace_id] = max(
            0.0,
            self._daily_spend.get(workspace_id, 0.0) + adjustment,
        )
        self._persist_daily_spend(workspace_id)  # Track 4
```

### Step 4: Call reconciliation from colony completion hooks

In `colony_manager.py`, in the `_post_colony_hooks` method body
(definition at line 1131, last hook at line 1172), add the reconciliation
call after the existing hooks. `total_cost` is already a parameter
(line 1136), and `colony` provides `workspace_id`:

```python
# Wave 76: reconcile estimated vs actual cost for dispatcher-owned colonies
if hasattr(self, "_maintenance_dispatcher") and self._maintenance_dispatcher is not None:
    self._maintenance_dispatcher.reconcile_colony_cost(
        colony.workspace_id, colony_id, total_cost,
    )
```

The maintenance dispatcher reference is NOT currently available on runtime.
Use an explicit handoff during startup instead of reading a private local:

```python
# colony_manager.py
def set_maintenance_dispatcher(self, dispatcher: Any) -> None:
    self._maintenance_dispatcher = dispatcher
```

Then wire it once in `app.py` after both objects are created:

```python
colony_manager = ColonyManager(runtime)
_maint_dispatcher = MaintenanceDispatcher(runtime)
colony_manager.set_maintenance_dispatcher(_maint_dispatcher)
```

---

## Track 4: Daily spend persistence

Write `_daily_spend` to disk after every change.

### Step 1: Add persistence methods to `MaintenanceDispatcher`

```python
def _spend_path(self, workspace_id: str) -> Path:
    data_dir = self._runtime.settings.system.data_dir
    return (
        Path(data_dir) / ".formicos" / "operations"
        / workspace_id / "daily_spend.json"
    )

def _persist_daily_spend(self, workspace_id: str) -> None:
    """Write current daily spend to disk."""
    path = self._spend_path(workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "date": str(datetime.now(UTC).date()),
        "spend": self._daily_spend.get(workspace_id, 0.0),
        "last_updated": datetime.now(UTC).isoformat(),
    }
    path.write_text(json.dumps(data, indent=2) + "\n")

def _load_daily_spend(self, workspace_id: str) -> float:
    """Load persisted daily spend, or 0.0 if absent or stale."""
    path = self._spend_path(workspace_id)
    if not path.exists():
        return 0.0
    try:
        data = json.loads(path.read_text())
        if data.get("date") != str(datetime.now(UTC).date()):
            return 0.0  # Stale -- different day
        return float(data.get("spend", 0.0))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0.0
```

### Step 2: Load on first access

In `_reset_daily_budget_if_needed` (lines 591-596), after clearing
`_daily_spend`, reload from disk for each workspace:

```python
def _reset_daily_budget_if_needed(self) -> None:
    today = datetime.now(UTC).date()
    if self._last_reset != today:
        self._daily_spend.clear()
        self._last_reset = today
        # Wave 76: reload persisted spend for current day
        for ws_id in self._runtime.projections.workspaces:
            persisted = self._load_daily_spend(ws_id)
            if persisted > 0:
                self._daily_spend[ws_id] = persisted
```

### Step 3: Persist after every spend change

Add `self._persist_daily_spend(workspace_id)` after every line that
modifies `self._daily_spend[workspace_id]`:

- After line 385 in `self_maintenance.py` (dispatch increment)
- After line 510 in `self_maintenance.py` (distillation increment)
- In `continuation.py` after line 283 (idle continuation increment).
  The code at :281-283 accesses `dispatcher._daily_spend` directly;
  add `dispatcher._persist_daily_spend(workspace_id)` on the next line.
  You'll need the same `# pyright: ignore[reportPrivateUsage]` comment.
- After reconciliation in Track 3 (already shown in the `reconcile_colony_cost` snippet)

### Imports

You'll need `json` and `Path` in `self_maintenance.py`. Neither is
currently imported. Add `import json` and `from pathlib import Path`
to the top-level imports.

**Test:** Write a test that:
1. Dispatches work, verifies spend is persisted to disk
2. Simulates restart (new `MaintenanceDispatcher` instance), verifies
   spend is reloaded from disk
3. Verifies stale (yesterday's) spend file is ignored

---

## Validation

```bash
ruff check src/formicos/surface/projections.py src/formicos/surface/self_maintenance.py \
  src/formicos/surface/continuation.py src/formicos/surface/colony_manager.py \
  src/formicos/surface/app.py
pyright src/formicos/surface/projections.py src/formicos/surface/self_maintenance.py \
  src/formicos/surface/continuation.py src/formicos/surface/colony_manager.py \
  src/formicos/surface/app.py
pytest tests/ -x -q
```

After all tests pass, run the full CI:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Overlap rule

Team B also touches `colony_manager.py` but only the colony run loop
(around line 968, before `ColonyCompleted` emission). Team A touches
`_post_colony_hooks` method body (around line 1131-1172). These are
different methods.

`app.py` is shared with Team B, but Team A only owns the startup-time
dispatcher handoff near object construction. If you find yourself needing
to modify the operational sweep loop, STOP and coordinate.
