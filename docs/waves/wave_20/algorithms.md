# Wave 20 Algorithms — Implementation Reference

**Wave:** 20 — "Open + Grounded"
**Purpose:** Technical implementation guide for all three tracks. Coder teams should read the section for their track before writing code.

---

## §1. Sandbox Execution Pipeline (Track A)

### Existing Wiring (Do Not Modify)

The full sandbox pipeline is already wired across four files:

```
colony_manager.py::_build_code_execute_handler()
  → ast_security.py::check_ast_safety(code)      # Gate 1: AST screening
  → sandbox_manager.py::execute_sandboxed(code)   # Gate 2: Container execution
  → output_sanitizer.py::sanitize_output(stdout)  # Gate 3: Output cleaning
  → emit CodeExecuted event                        # Telemetry
```

`runner.py::_execute_tool()` dispatches `code_execute` to `self._code_execute_handler`, which is injected by `colony_manager.py` at colony start. The engine never imports adapters directly.

### What's Missing

Three things prevent this pipeline from working with real containers:

1. **No sandbox image.** `sandbox_manager._execute_docker()` targets `formicos-sandbox:latest`. That image doesn't exist.
2. **No Docker CLI.** The `Dockerfile` builds from `python:3.12-slim`, which has no `docker` binary. `asyncio.create_subprocess_exec("docker", "run", ...)` fails with "command not found".
3. **No Docker socket.** The `formicos` service in `docker-compose.yml` has no volume mount for `/var/run/docker.sock`. Even with the CLI, `docker run` can't reach the daemon.

### Sandbox Dockerfile

```dockerfile
# docker/sandbox.Dockerfile
FROM python:3.12-slim

# Non-root execution
RUN useradd -m -s /bin/bash sandbox
USER sandbox
WORKDIR /code

# No pip installs — standard library only
# Container runs with: --read-only --network=none --memory=256m --cpus=0.5
# Writable /tmp via: --tmpfs /tmp:size=10m

ENTRYPOINT ["python"]
```

Build: `docker build -f docker/sandbox.Dockerfile -t formicos-sandbox:latest .`

### Docker CLI in App Container

Add to the runtime stage of `Dockerfile`:

```dockerfile
# Install Docker CLI for sandbox container spawning
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
```

This copies the static Docker CLI binary from the official Docker image. No daemon, no compose, no buildx — just the CLI binary needed for `docker run`.

### Docker Socket Mount

In `docker-compose.yml`, add to the `formicos` service:

```yaml
formicos:
  # ... existing config ...
  volumes:
    - ./data:/data
    - /var/run/docker.sock:/var/run/docker.sock  # Sandbox container spawning
```

### SANDBOX_ENABLED Flag

In `sandbox_manager.py`, gate Docker execution:

```python
import os

SANDBOX_ENABLED = os.environ.get("SANDBOX_ENABLED", "true").lower() in ("true", "1", "yes")

async def execute_sandboxed(code: str, timeout_s: int = DEFAULT_TIMEOUT_S) -> SandboxExecutionResult:
    timeout_s = min(timeout_s, MAX_TIMEOUT_S)

    if SANDBOX_ENABLED:
        try:
            return await _execute_docker(code, timeout_s)
        except Exception:
            log.debug("sandbox.docker_unavailable", fallback="subprocess")

    return await _execute_subprocess(code, timeout_s)
```

When `SANDBOX_ENABLED=false`, skip the Docker attempt entirely. Useful for development without Docker socket access.

---

## §2. Transcript Builder (Track A)

### Shared Builder Pattern

`transcript.py` is a pure function that reads from `ColonyProjection` — no I/O, no HTTP calls, no event store queries.

```python
# src/formicos/surface/transcript.py

from __future__ import annotations

from typing import Any

from formicos.core.types import ColonyProjection


def build_transcript(colony: ColonyProjection) -> dict[str, Any]:
    """Build a structured summary of a colony.

    Consumed by:
    - GET /api/v1/colonies/{id}/transcript (HTTP endpoint)
    - AG-UI late-join replay (agui_endpoint.py)
    - Colony chaining resolution (future)

    Reads only from the projection. No I/O.
    """
    round_summaries = []
    for rec in colony.round_records:
        agents = []
        for agent_id, output in rec.agent_outputs.items():
            agents.append({
                "id": agent_id,
                "caste": rec.agent_castes.get(agent_id, "unknown"),
                "output_summary": output[:500],
                "tool_calls": rec.agent_tool_calls.get(agent_id, []),
            })
        round_summaries.append({
            "round": rec.round_number,
            "agents": agents,
            "convergence": rec.convergence_score,
            "cost": rec.round_cost,
        })

    # Final output: last round's combined agent outputs
    final_output = ""
    if colony.round_records:
        last = colony.round_records[-1]
        final_output = "\n\n".join(
            f"[{aid}] {out[:1000]}"
            for aid, out in last.agent_outputs.items()
        )

    return {
        "colony_id": colony.id,
        "display_name": getattr(colony, "display_name", None) or colony.id,
        "original_task": getattr(colony, "original_task", colony.task),
        "active_goal": getattr(colony, "active_goal", colony.task),
        "status": colony.status,
        "quality_score": colony.quality_score,
        "skills_extracted": colony.skills_extracted,
        "cost": colony.cost,
        "rounds_completed": colony.round_number,
        "redirect_history": getattr(colony, "redirect_history", []),
        "input_sources": getattr(colony, "input_sources", []),
        "team": _format_team(colony),
        "round_summaries": round_summaries,
        "final_output": final_output,
    }
```

**Important:** The exact field names on `ColonyProjection` may vary from this pseudocode. Read the live projection class before implementing. Use `getattr()` with defaults for fields that may not exist on older colonies (e.g., `redirect_history`, `input_sources` from Wave 19).

### HTTP Endpoint

In `app.py`:

```python
from formicos.surface.transcript import build_transcript

async def get_transcript(request: Request) -> JSONResponse:
    colony_id = request.path_params["colony_id"]
    colony = projections.get_colony(colony_id)
    if colony is None:
        return JSONResponse({"error": "colony not found"}, status_code=404)
    return JSONResponse(build_transcript(colony))

# In routes list:
Route("/api/v1/colonies/{colony_id:str}/transcript", get_transcript, methods=["GET"]),
```

---

## §3. MCP Streamable HTTP Mount (Track B)

### The Mount

FastMCP 3.x provides `create_streamable_http_app()` in `fastmcp.server.http`. It returns a `StarletteWithLifespan` — a Starlette sub-app with its own lifespan for session management.

```python
from fastmcp.server.http import create_streamable_http_app

# After creating the MCP server:
mcp_http = create_streamable_http_app(
    server=mcp,
    streamable_http_path="/mcp",
    stateless_http=True,  # No session state needed for tool calls
)
```

### Lifespan Coordination

This is the tricky part. `StreamableHTTPSessionManager` requires a running task group. When mounting as a Starlette sub-app, the sub-app's lifespan must be started by the parent app.

Two options:

**Option A: Mount as route (simpler).**
Mount the MCP app as a sub-application. Starlette handles nested lifespans for mounted apps.

```python
routes.append(Mount("/mcp", app=mcp_http))
```

**Option B: Wire lifespan manually (if Option A fails).**
Start the MCP session manager in the parent lifespan:

```python
@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncGenerator[None]:
    # ... existing startup ...
    
    # Start MCP session manager
    async with mcp_http.lifespan(mcp_http):
        yield
    
    # ... existing shutdown ...
```

**Try Option A first.** It's the documented pattern. Option B is the fallback if the nested lifespan doesn't auto-start.

### Smoke Test

After mounting, verify with any MCP client:

```bash
# Using curl to test the Streamable HTTP endpoint
curl -X POST http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
```

Expected: JSON-RPC response listing all 19 FormicOS tools.

---

## §4. AG-UI Run Streaming (Track B)

### Event Flow

```
Client: POST /ag-ui/runs {task, castes, ...}
Server: Spawns colony → subscribes to colony events → streams AG-UI SSE

FormicOS Event          → AG-UI Event
─────────────────────────────────────────────
ColonySpawned           → RUN_STARTED
RoundStarted            → STEP_STARTED
AgentTurnStarted        → TEXT_MESSAGE_START
AgentTurnCompleted      → TEXT_MESSAGE_CONTENT (output_summary)
                        → TEXT_MESSAGE_END
RoundCompleted          → STEP_FINISHED
                        → STATE_SNAPSHOT
ColonyCompleted/Failed  → RUN_FINISHED
All other events        → CUSTOM {type: event_type_name, data: {...}}
```

### Colony-Scoped Event Subscription

Add to `WebSocketManager`:

```python
async def subscribe_colony(self, colony_id: str) -> asyncio.Queue[FormicOSEvent]:
    """Subscribe to events for a single colony. Returns a queue.

    Caller must call unsubscribe_colony() when done.
    """
    queue: asyncio.Queue[FormicOSEvent] = asyncio.Queue(maxsize=1000)
    self._colony_subscribers[colony_id] = queue
    return queue

def unsubscribe_colony(self, colony_id: str) -> None:
    """Remove a colony-scoped subscription."""
    self._colony_subscribers.pop(colony_id, None)
```

In the existing `broadcast()` method that fans events to WebSocket clients, also check `_colony_subscribers` and put matching events into the queue:

```python
# In broadcast():
for cid, queue in self._colony_subscribers.items():
    if cid in event.address:  # address is "workspace/thread/colony"
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            log.warning("agui.queue_full", colony_id=cid)
```

### SSE Endpoint

```python
# src/formicos/surface/agui_endpoint.py

from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request

async def handle_run(request: Request) -> EventSourceResponse:
    body = await request.json()
    task = body["task"]
    castes = body.get("castes", [])
    # ... validate, build CasteSlots ...

    # Spawn colony via runtime
    runtime = request.app.state.runtime
    colony_id = await runtime.spawn_colony(...)

    # Start colony execution
    if runtime.colony_manager:
        asyncio.create_task(runtime.colony_manager.start_colony(colony_id))

    # Subscribe to colony events
    ws_manager = request.app.state.ws_manager
    queue = await ws_manager.subscribe_colony(colony_id)

    async def event_generator():
        try:
            # RUN_STARTED
            yield {"event": "RUN_STARTED", "data": json.dumps({
                "type": "RUN_STARTED",
                "runId": colony_id,
                "timestamp": _now_iso(),
            })}

            current_round = 0
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=300)

                if isinstance(event, RoundStarted):
                    current_round = event.round_number
                    yield _step_started(colony_id, current_round)

                elif isinstance(event, AgentTurnStarted):
                    yield _text_message_start(colony_id, event)

                elif isinstance(event, AgentTurnCompleted):
                    yield _text_message_content(colony_id, event, current_round)
                    yield _text_message_end(colony_id, event, current_round)

                elif isinstance(event, RoundCompleted):
                    yield _step_finished(colony_id, current_round)
                    # STATE_SNAPSHOT after each round
                    colony = runtime.projections.get_colony(colony_id)
                    if colony:
                        yield _state_snapshot(colony_id, colony)

                elif isinstance(event, (ColonyCompleted, ColonyFailed, ColonyKilled)):
                    yield _run_finished(colony_id, event)
                    break

                else:
                    # CUSTOM passthrough
                    yield _custom_event(colony_id, event)

        except asyncio.TimeoutError:
            yield _run_finished_timeout(colony_id)
        finally:
            ws_manager.unsubscribe_colony(colony_id)

    return EventSourceResponse(event_generator())
```

### Honest Semantics — Critical Details

**TEXT_MESSAGE_CONTENT carries `output_summary`, not `output`.**

```python
def _text_message_content(colony_id, event: AgentTurnCompleted, round_num: int):
    return {"event": "TEXT_MESSAGE_CONTENT", "data": json.dumps({
        "type": "TEXT_MESSAGE_CONTENT",
        "messageId": f"{colony_id}-{event.agent_id}-r{round_num}",
        "content": event.output_summary,  # NOT event.output — that field doesn't exist
        "contentType": "summary",  # Explicit: this is summary, not streaming
    })}
```

**`messageId` derives round number from tracked state, not from the event.**
`AgentTurnCompleted` does NOT carry `round_number`. Track `current_round` from `RoundStarted` events in the generator loop.

**`STATE_SNAPSHOT` is a full colony projection snapshot.**
Use `build_transcript()` from `transcript.py` for the snapshot payload. This gives a consistent shape whether the client is watching live or replaying later.

```python
def _state_snapshot(colony_id, colony):
    from formicos.surface.transcript import build_transcript
    return {"event": "STATE_SNAPSHOT", "data": json.dumps({
        "type": "STATE_SNAPSHOT",
        "snapshot": build_transcript(colony),
    })}
```

### What Is NOT Emitted

- `TOOL_CALL_START` / `TOOL_CALL_END` — tool calls are post-hoc name lists on `AgentTurnCompleted.tool_calls`, not real-time events
- `STATE_DELTA` — no native JSON-patch delta source exists
- Token streaming — the runner does not produce per-token events

---

## §5. Agent Card Update (Track B)

Update the existing `agent_card()` function in `app.py`:

```python
card = {
    "name": "FormicOS",
    "description": "Stigmergic multi-agent colony framework. ...",
    "url": str(request.base_url).rstrip("/"),
    "version": "0.20.0",
    "capabilities": {
        "streaming": True,        # AG-UI endpoint exists
        "pushNotifications": False,
    },
    "protocols": {
        "mcp": "/mcp",
        "agui": "/ag-ui/runs",
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": skills,
}
```

---

## §6. VRAM Monitoring (Track C)

### Probe Strategy

Try in order. Use the first that works on the live stack.

**Option A: llama.cpp `/metrics` Prometheus endpoint.**

If `--metrics` is passed in compose (check), llama.cpp exposes Prometheus metrics at port 8008:

```
# Request
GET http://formicos-llm:8008/metrics

# Look for
llama_kv_cache_usage_bytes
llama_gpu_memory_used_bytes
llama_gpu_memory_total_bytes
```

Parse with simple regex or string splitting. No Prometheus client needed.

```python
async def _probe_vram_metrics(endpoint: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{endpoint}/metrics")
            text = resp.text
            used = _parse_prometheus_gauge(text, "llama_gpu_memory_used_bytes")
            total = _parse_prometheus_gauge(text, "llama_gpu_memory_total_bytes")
            if used is not None and total is not None:
                return {"usedMb": round(used / 1e6), "totalMb": round(total / 1e6)}
    except Exception:
        pass
    return None
```

**Option B: `/health` response.**

Newer llama.cpp builds may include VRAM in the health response. Check:

```python
async def _probe_vram_health(endpoint: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{endpoint}/health")
            data = resp.json()
            if "vram_used" in data and "vram_total" in data:
                return {"usedMb": data["vram_used"], "totalMb": data["vram_total"]}
    except Exception:
        pass
    return None
```

**Option C: Docker exec nvidia-smi (last resort).**

Requires Docker socket (which Track A adds):

```python
async def _probe_vram_nvidia_smi() -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "exec", "formicos-llm",
            "nvidia-smi", "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        parts = stdout.decode().strip().split(",")
        if len(parts) == 2:
            return {"usedMb": int(parts[0].strip()), "totalMb": int(parts[1].strip())}
    except Exception:
        pass
    return None
```

### Integration

In `_probe_local_endpoints()`, after existing health/slot probes:

```python
# VRAM probe (try methods in order of preference)
vram = await _probe_vram_metrics(endpoint)
if vram is None:
    vram = await _probe_vram_health(endpoint)
if vram is None:
    vram = await _probe_vram_nvidia_smi()
# vram is None if all methods fail — frontend handles null honestly
```

### Slot Probe Consolidation

Current: two calls to `/health` (with and without `?include_slots`).
Target: one call to `/health?include_slots`.

```python
# Before (two calls):
health_resp = await client.get(f"{endpoint}/health")
slots_resp = await client.get(f"{endpoint}/health?include_slots")

# After (one call):
resp = await client.get(f"{endpoint}/health?include_slots")
data = resp.json()
# data contains both health status AND slot details
status = data.get("status", "unknown")
slots = data.get("slots", [])
total_slots = len(slots)  # or from /props if needed
```

---

## §7. Protocol Status Truth (Track B)

Update `_build_protocol_status()` in `view_state.py`:

```python
def _build_protocol_status() -> dict:
    return {
        "mcp": {
            "status": "active",
            "tools": 19,
            "transport": "streamable_http",
            "endpoint": "/mcp",
        },
        "agui": {
            "status": "active",
            "events": 9,  # RUN_STARTED, RUN_FINISHED, STEP_*, TEXT_MESSAGE_*, STATE_SNAPSHOT, CUSTOM
            "endpoint": "/ag-ui/runs",
            "semantics": "summary-at-turn-end",
        },
        "a2a": {
            "status": "inactive",
            "note": "Agent Card at /.well-known/agent.json (discovery only)",
        },
    }
```

Frontend `settings-view.ts` renders transport/endpoint details for active protocols.

---

## §8. Files Changed Summary

### Track A (Coder 1)
| File | Action |
|------|--------|
| `docker/sandbox.Dockerfile` | New — minimal Python 3.12 sandbox image |
| `Dockerfile` | Add Docker CLI binary from `docker:27-cli` |
| `docker-compose.yml` | Add Docker socket mount to formicos service |
| `src/formicos/adapters/sandbox_manager.py` | Add `SANDBOX_ENABLED` env flag gate |
| `src/formicos/surface/transcript.py` | New — shared `build_transcript()` builder |
| `src/formicos/surface/app.py` | Add `GET /api/v1/colonies/{id}/transcript` route |
| `docs/LOCAL_FIRST_QUICKSTART.md` | Document sandbox build step + security note |

### Track B (Coder 2)
| File | Action |
|------|--------|
| `src/formicos/surface/app.py` | Mount MCP HTTP sub-app at `/mcp`. Add AG-UI route. Update Agent Card. Wire MCP lifespan. |
| `src/formicos/surface/agui_endpoint.py` | New — AG-UI SSE run streaming endpoint |
| `src/formicos/surface/ws_handler.py` | Add `subscribe_colony()` / `unsubscribe_colony()` + fan-out integration |
| `src/formicos/surface/view_state.py` | Update `_build_protocol_status()` with transport/endpoint details |
| `frontend/src/components/settings-view.ts` | Render transport type + endpoint for active protocols |
| `docs/AG-UI-EVENTS.md` | New — event glossary for external AG-UI clients |

### Track C (Coder 3)
| File | Action |
|------|--------|
| `src/formicos/surface/ws_handler.py` | Add VRAM probe. Consolidate slot probes. **(Reread after Coder 2)** |
| `src/formicos/surface/view_state.py` | Populate `vram` from probe data |
| `frontend/src/types.ts` | Update `vram` type to `{usedMb, totalMb} | null` |
| `frontend/src/components/model-registry.ts` | Render VRAM utilization bar |
| Various frontend components | Dead control audit fixes |

### Track C Stretch (Coder 3, if time)
| File | Action |
|------|--------|
| `src/formicos/surface/colony_manager.py` | Extend skill confidence update with hit counts |
| `src/formicos/surface/skill_lifecycle.py` | Add `hit_rate` to skill bank summary |
| `src/formicos/surface/view_state.py` | Include `hitRate` in skillBankStats |
| `frontend/src/components/skill-browser.ts` | Render hit rate |
