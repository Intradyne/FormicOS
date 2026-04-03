# Wave 76 Team B: Operational Safety

**Goal:** After this team's work, the action queue is safe, the sweep cannot
re-enter, colony completion paths honor already-visible terminal state, the
journal is complete, and the operator can see what's pending.

## Owned files

- `src/formicos/surface/action_queue.py` -- compaction + state validation
- `src/formicos/surface/app.py` -- sweep reentrancy guard + journal coverage for approved actions
- `src/formicos/surface/colony_manager.py` -- kill/completion race guard in the colony run loop ONLY (around line 968)
- `src/formicos/surface/runtime.py` -- kill path flag (if needed for race guard)
- `src/formicos/surface/routes/api.py` -- journal coverage for approve_action handler
- `src/formicos/surface/operations_coordinator.py` -- operator-idle Queen chat detection
- `frontend/src/components/operations-view.ts` -- pending count display

## Do NOT touch

- `src/formicos/surface/projections.py` -- Team A
- `src/formicos/surface/self_maintenance.py` -- Team A
- `src/formicos/surface/queen_runtime.py` -- Team C
- `src/formicos/surface/thread_plan.py` -- Team C
- `frontend/src/components/queen-chat.ts` -- Team C
- `frontend/src/components/settings-view.ts` -- Team C

## Before you code, read these files

1. `src/formicos/surface/action_queue.py` -- full file. Focus on:
   - Status constants at lines 30-44 (`_VALID_STATUSES` defined but never enforced)
   - `update_action` at lines 152-173 (no state validation, blind `act.update(updates)`)
   - `compact_action_log` at lines 249-285 (blind position-based slice, `_COMPACT_KEEP=500`)
2. `src/formicos/surface/app.py` -- lines 924-1117. Focus on:
   - `_operational_sweep_loop` at :929-944 (no reentrancy guard, 30-min default interval)
   - Approved-action processing at :1021-1095 (no journal write)
3. `src/formicos/surface/colony_manager.py` -- lines 960-990. Focus on:
   - `ColonyCompleted` emission at :970-975 (no check for prior kill)
   - `_post_colony_hooks` call at :977-987 (Team A's area -- do NOT modify)
4. `src/formicos/surface/runtime.py` -- find `kill_colony` at lines 796-806
   (emits `ColonyKilled` then calls `stop_colony`)
5. `src/formicos/surface/routes/api.py` -- find approve_action handler at
   lines 1828-1938 (three execution branches, zero journal writes)
6. `src/formicos/surface/operations_coordinator.py` -- `_compute_operator_activity`
   at lines 211-257 (scans only `colony.chat_messages`, ignores Queen messages)
7. `frontend/src/components/operations-view.ts` -- line 189 (hardcoded `'0'`)
8. `docs/waves/architecture_audit_post_75.md` -- sections 2.2 (action queue),
   4.3 (pending count), 7.1 (operator-idle), 7.3 (journal gap), 9.2 (kill race),
   11.3 (compaction), 11.4 (reentrancy), 11.5 (state machine)

---

## Track 5: Action queue compaction preserves pending items

In `compact_action_log` (lines 249-285), the current logic keeps the
newest 500 entries by position. Old `pending_review` items in early
positions get archived and become invisible.

### Fix

Replace the blind position-based slice with status-aware partitioning:

```python
def compact_action_log(data_dir: str, workspace_id: str) -> bool:
    """Archive old actions, keeping all pending_review and newest completed."""
    actions = read_actions(data_dir, workspace_id)
    if len(actions) <= _COMPACT_THRESHOLD:
        return False

    # Partition: never archive pending_review items
    pending = [a for a in actions if a.get("status") == STATUS_PENDING_REVIEW]
    settled = [a for a in actions if a.get("status") != STATUS_PENDING_REVIEW]

    if len(settled) <= _COMPACT_KEEP:
        return False  # Not enough settled items to compact

    archive_entries = settled[:-_COMPACT_KEEP]
    keep_entries = pending + settled[-_COMPACT_KEEP:]

    # ... rest of archive logic unchanged (write archive_entries to gzip,
    #     rewrite active file with keep_entries) ...
```

**Verify:** The existing archive gzip path (around line 271) and the
active file rewrite (around line 280) should work unchanged with the
new `archive_entries` and `keep_entries` lists. Read the full function
to be sure.

**Test:** Write a test that:
1. Creates 1100 actions, 5 of which are `pending_review` at positions 0-4
2. Runs compaction
3. Verifies all 5 pending items survive in the active file
4. Verifies archived items do NOT include any pending_review entries

---

## Track 6: Action queue state transition validation

In `update_action` (lines 152-173), the current code does `act.update(updates)`
with no state validation. `_VALID_STATUSES` is defined at lines 37-44 but
never checked.

### Fix

Add a transition map and validation before the update:

```python
_VALID_TRANSITIONS: dict[str, set[str]] = {
    STATUS_PENDING_REVIEW: {STATUS_APPROVED, STATUS_REJECTED, STATUS_SELF_REJECTED},
    STATUS_APPROVED: {STATUS_EXECUTED, STATUS_FAILED},
    STATUS_REJECTED: set(),       # terminal
    STATUS_EXECUTED: set(),       # terminal
    STATUS_SELF_REJECTED: set(),  # terminal
    STATUS_FAILED: {STATUS_PENDING_REVIEW},  # allow retry
}
```

In `update_action`, before `act.update(updates)`:

```python
new_status = updates.get("status")
if new_status is not None:
    old_status = act.get("status", "")
    allowed = _VALID_TRANSITIONS.get(old_status, set())
    if new_status not in allowed:
        log.warning(
            "action_queue.invalid_transition",
            action_id=action_id,
            old_status=old_status,
            new_status=new_status,
        )
        raise ValueError(f"invalid transition: {old_status} -> {new_status}")
```

Important: `update_action()` returning `None` is already used by callers to
mean "action not found" (`routes/api.py:1850`) and its return value is ignored
in the sweep loop. Because Team B owns both `routes/api.py` and `app.py`,
update those call sites to handle the new `ValueError`:

- In `routes/api.py`, the `approve_action` handler at :1846 calls
  `_update_action(...)` to transition `pending_review` -> `approved`.
  Wrap in `try/except ValueError` and return a 409 Conflict response.
- In `app.py`, the sweep loop at :1078-1093 already has `except Exception`
  blocks. The `ValueError` will be caught naturally, but consider logging
  the transition error specifically so it doesn't look like a spawn failure.

**Test:** Write tests for:
- Valid transitions: `pending_review` -> `approved`, `approved` -> `executed`
- Invalid transitions: `executed` -> `pending_review`, `rejected` -> `approved`
- Retry path: `failed` -> `pending_review`

---

## Track 7: Operations dashboard real pending count

In `operations-view.ts:189`, the pending actions count is hardcoded:

```html
<div class="stat-value">${this._loading ? '-' : '0'}</div>
```

### Fix

The component already has access to operations data. Check whether the
operations summary endpoint (`GET /api/v1/workspaces/{id}/operations/summary`)
is already fetched. If so, read `pending_review_count` from the response.

If the endpoint isn't already called in this component, add a fetch in the
component's `connectedCallback` or update cycle. The endpoint exists and
returns the count -- the component just never reads it.

Replace the hardcoded `'0'` with the actual count:

```typescript
<div class="stat-value">${this._loading ? '-' : this._pendingCount}</div>
```

Where `_pendingCount` is populated from the API response or from a
property passed down from the parent.

**Verify:** Check how `operations-inbox.ts` gets its pending count. Use
the same data source to avoid a duplicate fetch.

---

## Track 8: Sweep reentrancy guard

In `app.py`, the `_operational_sweep_loop` (lines 929-944) has a 30-minute
interval with no lock. If one iteration takes longer than 30 minutes, the
next starts before the first completes.

### Fix

Add an `asyncio.Lock` before the sweep body:

```python
_sweep_lock = asyncio.Lock()

async def _operational_sweep_loop(
    interval_s: int = _ops_sweep_interval,
) -> None:
    """Consolidated operational sweep (Wave 72 Track 6)."""
    while True:
        await asyncio.sleep(interval_s)
        if _sweep_lock.locked():
            log.warning("ops_sweep.skipped_reentrant")
            continue
        async with _sweep_lock:
            # ... existing sweep body (lines 945-1117) ...
```

Define `_sweep_lock` at module scope or inside `startup()` next to the
other loop locals. Prefer the same scope as `_operational_sweep_loop`.

**Test:** This is hard to unit-test (asyncio timing). Verify by code
review that the lock wraps the entire sweep body and that the `continue`
path logs.

---

## Track 9: Colony kill/completion race guard

In `colony_manager.py`, the colony run loop emits `ColonyCompleted` at
line 970 without checking whether the colony was already killed.

### Fix

Before emitting `ColonyCompleted`, check the projection status. At both
sites, a `get_colony` call already exists immediately above -- reuse it:

**Site 1 (line 968-970):** `completion_proj` is already fetched at :968.
Add the guard between :969 and :970:

```python
completion_proj = self._runtime.projections.get_colony(colony_id)
final_artifacts = completion_proj.artifacts if completion_proj else []
# Wave 76: guard against kill/completion race
if completion_proj is not None and completion_proj.status in ("killed", "failed"):
    log.info(
        "colony.completion_after_kill",
        colony_id=colony_id,
        current_status=completion_proj.status,
    )
    return
await self._runtime.emit_and_broadcast(ColonyCompleted(...))
```

**Site 2 (line 1093-1095):** `max_proj` is already fetched at :1093.
Add the same guard between :1094 and :1095:

```python
max_proj = self._runtime.projections.get_colony(colony_id)
max_artifacts = max_proj.artifacts if max_proj else []
# Wave 76: guard against kill/completion race (max-rounds path)
if max_proj is not None and max_proj.status in ("killed", "failed"):
    log.info(
        "colony.completion_after_kill",
        colony_id=colony_id,
        current_status=max_proj.status,
    )
    return
await self._runtime.emit_and_broadcast(ColonyCompleted(...))
```

**Why this works:** `kill_colony` in `runtime.py:796-806` calls
`await self.emit_and_broadcast(ColonyKilled(...))` which updates the
projection status to `"killed"` synchronously in the event handler.
By the time the colony task checks the projection, the status is already
terminal.

**Verify:** Read `runtime.py:796-806` to confirm `emit_and_broadcast` is
awaited before `stop_colony` is called. Confirm the `ColonyKilled` handler
in projections sets `colony.status = "killed"`.

---

## Track 10: Journal coverage for API and sweep approved actions

### Fix in `routes/api.py` (approve_action handler)

Find the approve_action handler (lines 1828-1938). After each execution
branch updates the action status, add a journal entry. There are three
branches:

1. Colony spawn (around line 1855-1876)
2. Workflow template approval (around line 1879-1913)
3. Procedure suggestion approval (around line 1916-1936)

After each, add:

```python
from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415
append_journal_entry(
    data_dir_str, workspace_id,
    source="operator",
    message=f"Approved and executed: {updated.get('title', action_id)}",
)
```

**Verify:** Check that `data_dir_str` and `workspace_id` are available in
scope at each branch. The handler already uses `data_dir_str` earlier in
the function.

### Fix in `app.py` (sweep approved-action processing)

Find the approved-action processing loop (lines 1021-1095). After
successful execution (where status is updated to `STATUS_EXECUTED`,
around line 1082), add:

```python
from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415
append_journal_entry(
    data_dir_str, ws_id,
    source="sweep",
    message=f"Sweep executed approved action: {act.get('title', act.get('action_id', ''))}",
)
```

**Note:** The loop variable is `ws_id` (line 957: `for ws_id in workspace_ids:`),
not `workspace_id`. `data_dir_str` is defined at line 945.

---

## Track 11: Operator-idle includes Queen chat

In `operations_coordinator.py`, `_compute_operator_activity` (lines 211-257)
only scans `colony.chat_messages` for operator activity. It ignores Queen
thread messages entirely.

### Fix

After the colony chat scan (line 243), add a Queen message scan:

```python
    # Wave 76: also check Queen thread messages for operator activity
    if hasattr(ws, "threads"):
        for thread in ws.threads.values():
            if not hasattr(thread, "queen_messages"):
                continue
            for msg in reversed(thread.queen_messages):
                ts = getattr(msg, "timestamp", "")
                role = getattr(msg, "role", "")
                if role == "operator" and ts > latest_ts:
                    latest_ts = ts
                    break  # first operator message from the tail wins
```

Insert this between line 243 (end of colony scan) and line 245 (the
`if latest_ts:` check).

**Verified seams:**
- `ws.threads` is `dict[str, ThreadProjection]` (projections.py:547) -- always present
- `ThreadProjection.queen_messages` is `list[QueenMessageProjection]` (:522)
- `QueenMessageProjection` has `.role` (`str`) and `.timestamp` (`str`) attributes (:505-507)
- Timestamp format is ISO, same as colony chat messages (both set by `_now()`)

**Test:** Write a test that:
1. Sets up a workspace with no colony chat but recent Queen chat
2. Verifies `_compute_operator_activity` returns `operator_active=True`

---

## Validation

```bash
ruff check src/formicos/surface/action_queue.py src/formicos/surface/app.py \
  src/formicos/surface/colony_manager.py src/formicos/surface/runtime.py \
  src/formicos/surface/routes/api.py src/formicos/surface/operations_coordinator.py
pyright src/formicos/surface/action_queue.py src/formicos/surface/app.py \
  src/formicos/surface/colony_manager.py src/formicos/surface/runtime.py \
  src/formicos/surface/routes/api.py src/formicos/surface/operations_coordinator.py
pytest tests/ -x -q
```

After all tests pass, run the full CI:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

## Overlap rule

Team A also touches `colony_manager.py` but only the `_post_colony_hooks`
method body (around line 1131-1172). Team B touches the colony run loop (around line 968,
before `ColonyCompleted` emission). These are different code paths.
If you find yourself needing to modify `_post_colony_hooks`, STOP and
coordinate.

