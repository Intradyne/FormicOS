# Wave 29 Algorithms -- Implementation Reference

**Wave:** 29 -- "Workflow Threads"
**Purpose:** Technical implementation guide grounded in current repo state.

---

## S1. Thread Lifecycle Events (Track A -- A2)

### In core/events.py

```python
class ThreadGoalSet(EventEnvelope):
    """A thread's workflow goal was set or updated (Wave 29)."""
    model_config = FrozenConfig

    type: Literal["ThreadGoalSet"] = "ThreadGoalSet"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    goal: str = Field(..., description="Workflow objective.")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Expected artifact types: code, test, document, etc.",
    )


class ThreadStatusChanged(EventEnvelope):
    """A thread's workflow status changed (Wave 29)."""
    model_config = FrozenConfig

    type: Literal["ThreadStatusChanged"] = "ThreadStatusChanged"
    workspace_id: str = Field(...)
    thread_id: str = Field(...)
    old_status: str = Field(...)
    new_status: str = Field(..., description="active | completed | archived.")
    reason: str = Field(default="", description="Why the status changed.")


class MemoryEntryScopeChanged(EventEnvelope):
    """A memory entry's thread scope changed (Wave 29)."""
    model_config = FrozenConfig

    type: Literal["MemoryEntryScopeChanged"] = "MemoryEntryScopeChanged"
    entry_id: str = Field(...)
    old_thread_id: str = Field(default="")
    new_thread_id: str = Field(default="", description="Empty = workspace-wide.")
    workspace_id: str = Field(...)


class DeterministicServiceRegistered(EventEnvelope):
    """A deterministic service handler was registered (Wave 29).

    Emitted at startup for operator visibility. Dispatch uses
    the in-memory registry on ServiceRouter, not this event.
    """
    model_config = FrozenConfig

    type: Literal["DeterministicServiceRegistered"] = "DeterministicServiceRegistered"
    service_name: str = Field(...)
    description: str = Field(default="")
    workspace_id: str = Field(default="system")
```

### Additive fields on existing ThreadCreated

```python
class ThreadCreated(EventEnvelope):
    # ... existing fields (type, workspace_id, name) ...
    goal: str = Field(default="", description="Optional workflow goal (Wave 29).")
    expected_outputs: list[str] = Field(
        default_factory=list,
        description="Optional expected artifact types (Wave 29).",
    )
```

Backward-compatible: existing serialized events without these fields get empty defaults.

### Union update

Add all four new events plus import `KnowledgeAccessItem` if not already present. The `FormicOSEvent` union grows from 41 to 45 members.

### ports.py

Add `"ThreadGoalSet"`, `"ThreadStatusChanged"`, `"MemoryEntryScopeChanged"`, `"DeterministicServiceRegistered"` to `EventTypeName` literal.

---

## S2. MemoryEntry thread_id Field (Track B -- B1)

### In core/types.py

```python
class MemoryEntry(BaseModel):
    # ... existing fields ...
    thread_id: str = Field(
        default="",
        description="Thread scope. Empty = workspace-wide (Wave 29).",
    )
```

---

## S3. Thread Projection Upgrade (Track A -- A1)

### Current state (projections.py:192)

```python
class ThreadProjection:
    id: str
    workspace_id: str
    name: str
    colonies: dict[str, ColonyProjection] = field(default_factory=dict)
    queen_messages: list[QueenMessageProjection] = field(default_factory=list)
```

### Extended state

```python
class ThreadProjection:
    id: str
    workspace_id: str
    name: str
    colonies: dict[str, ColonyProjection] = field(default_factory=dict)
    queen_messages: list[QueenMessageProjection] = field(default_factory=list)
    # Wave 29 additions:
    goal: str = ""
    expected_outputs: list[str] = field(default_factory=list)
    status: str = "active"  # active | completed | archived
    colony_count: int = 0
    completed_colony_count: int = 0
    failed_colony_count: int = 0
    artifact_types_produced: dict[str, int] = field(default_factory=dict)
```

### New handlers

```python
def _on_thread_goal_set(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadGoalSet = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.goal = e.goal
            thread.expected_outputs = list(e.expected_outputs)


def _on_thread_status_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: ThreadStatusChanged = event  # type: ignore[assignment]
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.status = e.new_status


def _on_memory_entry_scope_changed(store: ProjectionStore, event: FormicOSEvent) -> None:
    e: MemoryEntryScopeChanged = event  # type: ignore[assignment]
    entry = store.memory_entries.get(e.entry_id)
    if entry is not None:
        entry["thread_id"] = e.new_thread_id
```

### Augment existing colony handlers

**_on_thread_created (projections.py:288):**

Currently:
```python
ws.threads[e.name] = ThreadProjection(
    id=e.name, workspace_id=e.workspace_id, name=e.name,
)
```

Add:
```python
ws.threads[e.name] = ThreadProjection(
    id=e.name, workspace_id=e.workspace_id, name=e.name,
    goal=getattr(e, "goal", ""),
    expected_outputs=list(getattr(e, "expected_outputs", [])),
)
```

**_on_colony_spawned:** After existing code that creates `ColonyProjection`, add:

```python
# Wave 29: track thread progress
# ColonySpawned carries thread_id and workspace_id as typed fields
# (core/events.py ColonySpawned class).  Use them directly rather
# than re-parsing the address string.
if e.thread_id:
    ws = store.workspaces.get(e.workspace_id)
    if ws is not None:
        thread = ws.threads.get(e.thread_id)
        if thread is not None:
            thread.colony_count += 1
```

Note: `ColonySpawned` carries `thread_id` and `workspace_id` as explicit Pydantic fields. The existing handler already has a typed `e: ColonySpawned` cast. Use `e.thread_id` and `e.workspace_id` directly — do not re-parse the address.

**_on_colony_completed:** After existing code, add:

```python
# Wave 29: track thread progress
colony = store.colonies.get(colony_id)
if colony is not None and colony.thread_id:
    ws = store.workspaces.get(colony.workspace_id)
    if ws is not None:
        thread = ws.threads.get(colony.thread_id)
        if thread is not None:
            thread.completed_colony_count += 1
            for art in getattr(e, "artifacts", []):
                atype = art.get("artifact_type", "generic") if isinstance(art, dict) else "generic"
                thread.artifact_types_produced[atype] = (
                    thread.artifact_types_produced.get(atype, 0) + 1
                )
```

**_on_colony_failed:** Similar pattern, increment `failed_colony_count`.

### Register in _HANDLERS (projections.py:695+)

```python
"ThreadGoalSet": _on_thread_goal_set,
"ThreadStatusChanged": _on_thread_status_changed,
"MemoryEntryScopeChanged": _on_memory_entry_scope_changed,
"DeterministicServiceRegistered": lambda store, event: None,  # no projection effect
```

---

## S4. ServiceRouter Deterministic Handler Registry (Track B -- B8, B9)

### Current ServiceRouter.__init__ (service_router.py:65)

```python
def __init__(self, inject_fn: InjectFn | None = None) -> None:
    self._registry: dict[str, str] = {}
    self._waiters: dict[str, asyncio.Event] = {}
    self._responses: dict[str, str] = {}
    self._inject_fn = inject_fn
```

### Extended __init__

```python
def __init__(self, inject_fn: InjectFn | None = None) -> None:
    self._registry: dict[str, str] = {}           # service_type -> colony_id
    self._handlers: dict[str, Callable] = {}       # service_type -> async callable (Wave 29)
    self._waiters: dict[str, asyncio.Event] = {}
    self._responses: dict[str, str] = {}
    self._inject_fn = inject_fn
    self._emit_fn: Callable | None = None          # Wave 29: event emission
```

### New registration method

```python
def register_handler(
    self,
    service_type: str,
    handler: Callable[[str, dict[str, Any]], Awaitable[str]],
) -> None:
    """Register a deterministic service handler.

    Handler signature: async (query_text: str, ctx: dict) -> str
    Takes precedence over colony-based registration for the same service_type.
    """
    self._handlers[service_type] = handler
    log.info("service_router.handler_registered", service_type=service_type)

def set_emit_fn(self, emit_fn: Callable | None) -> None:
    """Set the event emission callback. Called from app.py at startup."""
    self._emit_fn = emit_fn
```

### Modified query() method

The critical change. Insert handler check BEFORE the colony lookup:

```python
async def query(
    self, service_type: str, query_text: str, *,
    sender_colony_id: str | None = None,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    inject_fn: Any = None,
) -> str:
    # --- Wave 29: deterministic handler bypass ---
    if service_type in self._handlers:
        handler = self._handlers[service_type]
        # NOTE: _make_request_id(colony_id) uses colony_id[-8:] for the ID
        # suffix.  For handlers we pass service_type — the last 8 chars of
        # e.g. "service:consolidation:dedup" produce "up:dedup".  Functional
        # and distinguishable from colony-based IDs ("svc-<hex>-<ts>").
        request_id = self._make_request_id(service_type)
        t0 = _time_mod.perf_counter()

        # Emit ServiceQuerySent
        await self._emit_service_query_sent(
            request_id=request_id,
            service_type=service_type,
            target_id=service_type,  # handler name, not colony_id
            sender_colony_id=sender_colony_id,
            query_preview=query_text[:200],
        )

        result = await handler(query_text, {
            "sender_colony_id": sender_colony_id,
        })
        latency_ms = (_time_mod.perf_counter() - t0) * 1000

        # Emit ServiceQueryResolved
        await self._emit_service_query_resolved(
            request_id=request_id,
            service_type=service_type,
            source_id=service_type,
            response_preview=result[:200],
            latency_ms=latency_ms,
        )

        log.info(
            "service_router.deterministic_resolved",
            request_id=request_id,
            service_type=service_type,
            latency_ms=round(latency_ms, 2),
        )
        return result

    # --- Existing colony-based dispatch (unchanged except event emission) ---
    colony_id = self._registry.get(service_type)
    if colony_id is None:
        msg = f"No {service_type} colony is running"
        raise ValueError(msg)

    request_id = self._make_request_id(colony_id)
    event = asyncio.Event()
    self._waiters[request_id] = event
    formatted = self.format_query(request_id, query_text)

    # Emit ServiceQuerySent (Wave 29: was never emitted before)
    await self._emit_service_query_sent(
        request_id=request_id,
        service_type=service_type,
        target_id=colony_id,
        sender_colony_id=sender_colony_id,
        query_preview=query_text[:200],
    )

    effective_inject_fn = inject_fn or self._inject_fn
    if effective_inject_fn is None:
        msg = "Service router has no colony injection function configured"
        raise RuntimeError(msg)
    await effective_inject_fn(colony_id, formatted)

    t0 = _time_mod.perf_counter()
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout_s)
    except TimeoutError:
        self._cleanup_request(request_id)
        log.warning("service_router.query_timeout", ...)
        raise TimeoutError(...) from None

    latency_ms = (_time_mod.perf_counter() - t0) * 1000
    response = self._responses.pop(request_id, "")
    self._cleanup_request(request_id)

    # Emit ServiceQueryResolved (Wave 29: was never emitted before)
    await self._emit_service_query_resolved(
        request_id=request_id,
        service_type=service_type,
        source_id=colony_id,
        response_preview=response[:200],
        latency_ms=latency_ms,
    )

    log.info("service_router.query_resolved", ...)
    return response
```

### Event emission helpers

```python
async def _emit_service_query_sent(
    self, *, request_id: str, service_type: str,
    target_id: str, sender_colony_id: str | None,
    query_preview: str,
) -> None:
    if self._emit_fn is None:
        return
    from formicos.core.events import ServiceQuerySent
    await self._emit_fn(ServiceQuerySent(
        seq=0,
        timestamp=datetime.now(UTC),
        address=f"service/{service_type}",
        request_id=request_id,
        service_type=service_type,
        target_colony_id=target_id,
        sender_colony_id=sender_colony_id,
        query_preview=query_preview,
    ))

async def _emit_service_query_resolved(
    self, *, request_id: str, service_type: str,
    source_id: str, response_preview: str,
    latency_ms: float,
) -> None:
    if self._emit_fn is None:
        return
    from formicos.core.events import ServiceQueryResolved
    await self._emit_fn(ServiceQueryResolved(
        seq=0,
        timestamp=datetime.now(UTC),
        address=f"service/{service_type}",
        request_id=request_id,
        service_type=service_type,
        source_colony_id=source_id,
        response_preview=response_preview,
        latency_ms=latency_ms,
        artifact_count=0,
    ))
```

**Note on layer discipline:** These helpers import `ServiceQuerySent`/`ServiceQueryResolved` from `core.events` (core import -- layer-safe for engine code). The `emit_fn` is a callback injected from the surface layer. The engine never imports surface code.

---

## S5. Queen Thread Context (Track A -- A3)

### In queen_runtime.py -- new method

```python
def _build_thread_context(self, thread_id: str, workspace_id: str) -> str:
    """Build thread workflow context for Queen pre-spawn injection."""
    ws = self._runtime.projections.workspaces.get(workspace_id)
    if ws is None:
        return ""
    thread = ws.threads.get(thread_id)
    if thread is None or not thread.goal:
        return ""

    lines = [f'[Thread: "{thread.name}"]']
    lines.append(f"Goal: {thread.goal}")
    lines.append(f"Status: {thread.status}")

    if thread.expected_outputs:
        parts = []
        for out_type in thread.expected_outputs:
            count = thread.artifact_types_produced.get(out_type, 0)
            mark = "done" if count > 0 else "missing"
            parts.append(f"{out_type}: {count} ({mark})")
        lines.append(f"Progress: {', '.join(parts)}")

    lines.append(
        f"Colonies: {thread.completed_colony_count} completed, "
        f"{thread.failed_colony_count} failed, "
        f"{thread.colony_count} total"
    )

    missing = [t for t in thread.expected_outputs
               if thread.artifact_types_produced.get(t, 0) == 0]
    if missing:
        lines.append(f"Still needed: {', '.join(missing)}")

    return "\n".join(lines)
```

Inject in `respond()` after system prompt, before conversation history:

```python
thread_ctx = self._build_thread_context(thread_id, workspace_id)
if thread_ctx:
    messages.insert(insert_pos, {"role": "system", "content": thread_ctx})
    insert_pos += 1
```

---

## S6. Queen Thread + Service Tools (Track A -- A4, A5)

### Tool specs (added to _queen_tools return list)

```python
{
    "name": "set_thread_goal",
    "description": "Set or update the workflow goal and expected outputs for the current thread.",
    "parameters": {
        "type": "object",
        "properties": {
            "goal": {"type": "string", "description": "Workflow objective."},
            "expected_outputs": {
                "type": "array", "items": {"type": "string"},
                "description": "Expected artifact types: code, test, document, schema, report.",
            },
        },
        "required": ["goal"],
    },
},
{
    "name": "complete_thread",
    "description": "Mark the current thread's workflow as completed.",
    "parameters": {
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why the workflow is complete."},
        },
        "required": ["reason"],
    },
},
{
    "name": "query_service",
    "description": (
        "Query an active service (LLM service colony or deterministic maintenance service). "
        "Available services include consolidation:dedup and consolidation:stale_sweep."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "service_type": {"type": "string", "description": "Service name to query."},
            "query": {"type": "string", "description": "Query text or command."},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default 30)."},
        },
        "required": ["service_type", "query"],
    },
},
```

### Tool dispatch (in _execute_tool_call)

```python
if name == "set_thread_goal":
    goal = inputs.get("goal", "")
    expected = inputs.get("expected_outputs", [])
    if not goal:
        return ("Error: goal is required.", None)
    await self._runtime.emit_and_broadcast(ThreadGoalSet(
        seq=0, timestamp=_now(),
        address=f"{workspace_id}/{thread_id}",
        workspace_id=workspace_id, thread_id=thread_id,
        goal=goal, expected_outputs=expected,
    ))
    return (f"Thread goal set: {goal}", None)

if name == "complete_thread":
    reason = inputs.get("reason", "")
    ws = self._runtime.projections.workspaces.get(workspace_id)
    old_status = "active"
    if ws is not None:
        thread = ws.threads.get(thread_id)
        if thread is not None:
            old_status = thread.status
    await self._runtime.emit_and_broadcast(ThreadStatusChanged(
        seq=0, timestamp=_now(),
        address=f"{workspace_id}/{thread_id}",
        workspace_id=workspace_id, thread_id=thread_id,
        old_status=old_status, new_status="completed", reason=reason,
    ))
    return (f"Thread completed: {reason}", None)

if name == "query_service":
    stype = inputs.get("service_type", "")
    query_text = inputs.get("query", "")
    timeout = min(inputs.get("timeout", 30), 60)
    if not stype or not query_text:
        return ("Error: service_type and query are required.", None)
    # ServiceRouter lives on ColonyManager (colony_manager.py:225).
    # Access via runtime.colony_manager.service_router.
    cm = self._runtime.colony_manager
    if cm is None:
        return ("Error: service routing not available.", None)
    router = cm.service_router
    try:
        result = await router.query(
            service_type=stype, query_text=query_text,
            sender_colony_id=None, timeout_s=float(timeout),
        )
        return (result, None)
    except ValueError as exc:
        return (f"Error: {exc}", None)
    except TimeoutError as exc:
        return (f"Error: {exc}", None)
```

---

## S7. Thread-Aware Knowledge Catalog (Track B -- B4)

### In knowledge_catalog.py -- search method

```python
async def search(
    self, query: str, *,
    source_system: str = "",
    canonical_type: str = "",
    workspace_id: str = "",
    thread_id: str = "",         # Wave 29
    top_k: int = 10,
) -> list[dict[str, Any]]:
```

When `thread_id` is provided:

```python
_THREAD_BONUS = 0.25

if thread_id:
    # Phase 1: thread-scoped entries (boost score)
    thread_items = await self._search_institutional(
        query, workspace_id=workspace_id,
        thread_id=thread_id, top_k=top_k,
    )
    for item in thread_items:
        item["score"] = float(item.get("score", 0.0)) + _THREAD_BONUS

    # Phase 2: workspace-wide entries
    ws_items = await self._search_institutional(
        query, workspace_id=workspace_id,
        thread_id="", top_k=top_k,
    )

    # Merge + deduplicate (thread-boosted version wins)
    seen: set[str] = set()
    merged = []
    for item in thread_items + ws_items:
        item_id = item.get("id", "")
        if item_id not in seen:
            seen.add(item_id)
            merged.append(item)

    # Add legacy (no thread concept)
    legacy = await self._search_legacy(query, top_k=top_k) if self._vector else []
    for item in legacy:
        if item.get("id", "") not in seen:
            seen.add(item.get("id", ""))
            merged.append(item)

    merged.sort(key=lambda x: -float(x.get("score", 0.0)))
    return merged[:top_k]
```

---

## S8. Maintenance Handlers (Track B -- B10)

### In surface/maintenance.py

```python
"""Deterministic maintenance service handlers (Wave 29).

Each handler is a plain async function registered on ServiceRouter.
Receives query_text and a context dict. Returns response text.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def make_dedup_handler(runtime: Runtime):
    """Factory: returns an async callable for dedup consolidation."""

    async def _handle_dedup(query_text: str, ctx: dict[str, Any]) -> str:
        projections = runtime.projections
        memory_store = getattr(runtime, "memory_store", None)
        if memory_store is None:
            return "Error: memory store not available"

        verified = [
            e for e in projections.memory_entries.values()
            if e.get("status") == "verified"
        ]
        verified.sort(key=lambda e: e.get("created_at", ""))

        merged_count = 0
        flagged: list[dict[str, Any]] = []

        for i, entry_a in enumerate(verified):
            for entry_b in verified[i + 1:]:
                # Use embedding similarity via memory_store
                try:
                    sim = await _compute_similarity(
                        memory_store, entry_a, entry_b,
                    )
                except Exception:
                    continue

                if sim >= 0.98:
                    # Auto-merge: reject the lower-confidence entry
                    survivor, absorbed = (
                        (entry_a, entry_b)
                        if entry_a.get("confidence", 0) >= entry_b.get("confidence", 0)
                        else (entry_b, entry_a)
                    )
                    from formicos.core.events import MemoryEntryStatusChanged
                    await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                        seq=0, timestamp=datetime.now(UTC),
                        address=f"{absorbed.get('workspace_id', '')}",
                        entry_id=absorbed.get("id", ""),
                        old_status=absorbed.get("status", "verified"),
                        new_status="rejected",
                        reason=f"dedup:auto_merge (similarity {sim:.3f}, kept {survivor.get('id', '')})",
                    ))
                    merged_count += 1
                elif sim >= 0.82:
                    flagged.append({
                        "entry_a": entry_a.get("id"),
                        "entry_b": entry_b.get("id"),
                        "similarity": round(sim, 3),
                    })

        report = {
            "merged": merged_count,
            "flagged_for_review": len(flagged),
            "flagged_pairs": flagged,
        }
        return (
            f"Dedup complete: {merged_count} auto-merged, "
            f"{len(flagged)} flagged for review.\n"
            f"{json.dumps(report, indent=2)}"
        )

    return _handle_dedup


def make_stale_handler(runtime: Runtime):
    """Factory: returns an async callable for stale sweep."""

    async def _handle_stale(query_text: str, ctx: dict[str, Any]) -> str:
        projections = runtime.projections
        now = datetime.now(UTC)
        stale_days = 90

        # Build set of recently-accessed entry IDs from KnowledgeAccessRecorded
        accessed_ids: set[str] = set()
        for colony in projections.colonies.values():
            for trace in getattr(colony, "knowledge_accesses", []):
                for item in trace.get("items", []):
                    accessed_ids.add(item.get("id", ""))

        stale_count = 0

        for entry_id, entry in projections.memory_entries.items():
            if entry.get("status") in ("rejected", "stale"):
                continue
            try:
                created = datetime.fromisoformat(entry.get("created_at", ""))
            except (ValueError, TypeError):
                continue
            age = now - created

            if entry_id not in accessed_ids and age > timedelta(days=stale_days):
                from formicos.core.events import MemoryEntryStatusChanged
                await runtime.emit_and_broadcast(MemoryEntryStatusChanged(
                    seq=0, timestamp=now,
                    address=entry.get("workspace_id", ""),
                    entry_id=entry_id,
                    old_status=entry.get("status", "verified"),
                    new_status="stale",
                    reason=f"stale_sweep: not accessed in {age.days} days",
                ))
                stale_count += 1

        # NOTE: Confidence decay (gradual penalty for aging entries) is
        # deferred to Wave 30 where Bayesian confidence (Beta distribution)
        # replaces the current scalar field.  Decaying confidence here
        # would mutate projection state without an event (hard constraint #7).

        return f"Stale sweep: {stale_count} entries transitioned to stale"

    return _handle_stale


async def _compute_similarity(memory_store, entry_a, entry_b):
    """Compute cosine similarity between two entries via vector search.

    memory_store.search() returns Qdrant hit.score which is cosine
    *similarity* (higher = more similar), NOT distance.  Use directly.
    """
    content_a = entry_a.get("content_preview", "") or entry_a.get("summary", "")
    if not content_a:
        return 0.0
    results = await memory_store.search(
        query=content_a, top_k=10,
        workspace_id=entry_a.get("workspace_id", ""),
    )
    for hit in results:
        if hit.get("id") == entry_b.get("id"):
            return float(hit.get("score", 0.0))  # cosine similarity, higher = more similar
    return 0.0
```

---

## S9. Startup Registration (Track B -- B11)

### In app.py lifespan

```python
# Wave 29: register deterministic service handlers
from formicos.surface.maintenance import make_dedup_handler, make_stale_handler

if service_router is not None:
    service_router.register_handler(
        "service:consolidation:dedup",
        make_dedup_handler(runtime),
    )
    service_router.register_handler(
        "service:consolidation:stale_sweep",
        make_stale_handler(runtime),
    )
    service_router.set_emit_fn(runtime.emit_and_broadcast)

    # Emit registration events for operator visibility
    from formicos.core.events import DeterministicServiceRegistered
    for svc_name, svc_desc in [
        ("service:consolidation:dedup", "Auto-merge near-duplicate knowledge entries"),
        ("service:consolidation:stale_sweep", "Transition stale entries and decay confidence"),
    ]:
        await runtime.emit_and_broadcast(DeterministicServiceRegistered(
            seq=0, timestamp=datetime.now(UTC),
            address="system",
            service_name=svc_name,
            description=svc_desc,
        ))
```

---

## S10. Extraction Tags thread_id (Track B -- B2)

### In colony_manager.py -- _extract_institutional_memory

The colony's thread_id is available from the colony projection:

```python
colony_proj = self._runtime.projections.get_colony(colony_id)
thread_id = colony_proj.thread_id if colony_proj else ""
```

After `build_memory_entries()` returns, tag each entry:

```python
for entry in entries:
    entry["thread_id"] = thread_id  # Wave 29
    # ... existing scan + emit logic unchanged ...
```

---

## S11. Promote Endpoint (Track C -- C3)

### In routes/knowledge_api.py

```python
async def promote_entry(request: Request) -> JSONResponse:
    """Promote a thread-scoped knowledge entry to workspace-wide."""
    item_id = request.path_params["item_id"]
    entry = projections.memory_entries.get(item_id)
    if entry is None:
        return JSONResponse({"error": "not found"}, status_code=404)

    old_thread = entry.get("thread_id", "")
    if not old_thread:
        return JSONResponse({"error": "already workspace-wide"}, status_code=400)

    from formicos.core.events import MemoryEntryScopeChanged
    await runtime.emit_and_broadcast(MemoryEntryScopeChanged(
        seq=0, timestamp=datetime.now(UTC),
        address=f"{entry.get('workspace_id', '')}/{old_thread}",
        entry_id=item_id,
        old_thread_id=old_thread,
        new_thread_id="",
        workspace_id=entry.get("workspace_id", ""),
    ))
    return JSONResponse({"promoted": True, "entry_id": item_id})
```

Route: `Route("/api/v1/knowledge/{item_id:str}/promote", promote_entry, methods=["POST"])`

---

## S12. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `src/formicos/core/events.py` | 4 events, additive ThreadCreated fields, union 41->45 (~40 LOC) |
| `src/formicos/core/ports.py` | 4 event names (~4 LOC) |
| `src/formicos/surface/projections.py` | thread progress fields, 3 new handlers, augment 3 colony handlers (~70 LOC) |
| `src/formicos/surface/queen_runtime.py` | thread context builder, 3 new tools + dispatch (~100 LOC) |
| `src/formicos/surface/runtime.py` | create_thread with goal (~5 LOC) |
| `config/caste_recipes.yaml` | query_service in Queen tools + update prompt (~10 lines) |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/core/types.py` | thread_id on MemoryEntry (~2 LOC) |
| `src/formicos/surface/colony_manager.py` | tag entries with thread_id, thread_id in knowledge fetch (~10 LOC) |
| `src/formicos/surface/knowledge_catalog.py` | thread-aware search (~40 LOC) |
| `src/formicos/surface/memory_store.py` | thread-aware Qdrant queries (~20 LOC) |
| `src/formicos/surface/runtime.py` | thread_id in fetch + callbacks (~10 LOC) |
| `src/formicos/surface/projections.py` | scope-change handler (~5 LOC) |
| `src/formicos/surface/routes/knowledge_api.py` | thread filter (~10 LOC) |
| `src/formicos/engine/service_router.py` | handler registry, pre-dispatch bypass, emit helpers (~60 LOC) |
| `src/formicos/surface/maintenance.py` | new: dedup + stale handlers (~120 LOC) |
| `src/formicos/surface/app.py` | register handlers, set emit_fn (~15 LOC) |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `frontend/src/components/thread-view.ts` | workflow progress display (~80 LOC) |
| `frontend/src/components/knowledge-browser.ts` | thread filter + promote + maintenance trigger (~60 LOC) |
| `frontend/src/types.ts` | thread + service types (~20 LOC) |
| `src/formicos/surface/routes/knowledge_api.py` | promote + maintenance endpoints (~30 LOC) |
