# Wave 20 Plan — Open + Grounded

**Wave:** 20 — "Open + Grounded"
**Theme:** The system becomes externally consumable and internally productive. External agents can discover, stream, and tool-call into FormicOS. Colonies can actually execute code. The operator sees what's real.
**Contract changes:** 0 new events. Union stays at 37. Ports frozen. State/type contracts may gain additive fields (VRAM shape, transcript response shape, protocol status).
**Estimated LOC delta:** ~400 Python, ~40 TypeScript, ~30 Docker/config

---

## Why This Wave

Waves 18-19 made the Queen capable. Wave 20 makes the *system* capable in ways that don't depend on the Queen:

- **Colonies with coders can't reliably execute code.** The full pipeline is wired — AST security → `sandbox_manager.py` → output sanitizer → `CodeExecuted` event — but the Docker image it targets (`formicos-sandbox:latest`) doesn't exist, and the app container doesn't have the Docker CLI to spawn it. Coders fall back to a restricted subprocess with `PATH=""`, which fails on anything non-trivial.
- **External agents can't call FormicOS.** The repo already has an in-process 19-tool MCP server and an Agent Card discovery surface, but there is still no mounted MCP transport and no AG-UI endpoint to stream colony activity. FormicOS is discoverable, not yet callable.
- **VRAM is still null.** Wave 17 made telemetry honest. The operator still wants the real number, especially now that the Blackwell image and 80k local context are the default stack.

This wave is compact. No new events, no new Queen tools, no architectural changes. Three independent tracks, each closing a specific gap.

---

## Tracks

### Track A — Colony Productivity: Sandbox Execution + Colony Transcript

**Goal:** The `code_execute` tool works end-to-end in a real container. Completed colonies have a clean, structured transcript.

**A1. Sandbox Docker image + container wiring.**

Three things must land together for `code_execute` to work:

1. **The sandbox image.** Build `formicos-sandbox:latest` — a minimal Python image that `sandbox_manager.py` already targets via `docker run --rm --network=none --memory=256m --cpus=0.5 --read-only formicos-sandbox:latest`. The image needs: Python 3.12 slim base, standard library only, non-root user, read-only filesystem with writable `/tmp`, no network.

2. **Docker CLI in the app container.** The current `Dockerfile` builds from `python:3.12-slim` which does **not** include the Docker CLI. `sandbox_manager._execute_docker()` shells out to `docker run` — it will fail with "command not found" even if the socket is mounted. Add Docker CLI installation to the runtime stage of the Dockerfile.

3. **Docker socket mount.** The `formicos` service in `docker-compose.yml` needs `/var/run/docker.sock:/var/run/docker.sock` so the app container can spawn sandbox sibling containers. Add a clear security note: this gives the container Docker daemon access.

Add a `SANDBOX_ENABLED` env var (default `true`). When `false`, `sandbox_manager.py` skips Docker and uses the subprocess fallback directly without attempting the socket. This lets operators who can't or won't mount the socket still run FormicOS.

Files touched:
- `docker/sandbox.Dockerfile` — new, ~15 lines
- `Dockerfile` — add Docker CLI installation to runtime stage (~5 lines)
- `docker-compose.yml` — add Docker socket mount + sandbox build note
- `src/formicos/adapters/sandbox_manager.py` — respect `SANDBOX_ENABLED` env flag
- `docs/LOCAL_FIRST_QUICKSTART.md` — document sandbox build step and security note

**A2. Colony transcript builder + endpoint.**

Add a shared transcript builder in surface layer — a function, not an endpoint-only thing:

```python
# src/formicos/surface/transcript.py
def build_transcript(colony: ColonyProjection) -> dict[str, Any]:
    """Build a structured summary of a completed colony."""
```

Returns:
```json
{
  "colony_id": "...",
  "display_name": "...",
  "original_task": "...",
  "active_goal": "...",
  "status": "completed",
  "quality_score": 0.82,
  "skills_extracted": 2,
  "cost": 0.0043,
  "rounds_completed": 6,
  "redirect_history": [...],
  "input_sources": [...],
  "team": [{"caste": "coder", "tier": "standard", "model": "llama-cpp/gpt-4"}],
  "round_summaries": [
    {
      "round": 1,
      "agents": [
        {"id": "...", "caste": "coder", "output_summary": "...", "tool_calls": ["memory_search", "code_execute"]}
      ],
      "convergence": 0.45,
      "cost": 0.0008
    }
  ],
  "final_output": "..."
}
```

This shared builder is consumed by:
- `GET /api/v1/colonies/{id}/transcript` — the HTTP endpoint for operators and external tools
- AG-UI late-join / replay (Track B can call `build_transcript()` directly)
- Colony chaining resolution (future — `input_sources` can use the same builder instead of ad-hoc projection traversal)

Internal code never calls its own REST endpoint.

Files touched:
- `src/formicos/surface/transcript.py` — new, ~80 LOC
- `src/formicos/surface/app.py` — add transcript route (~15 LOC)

---

### Track B — External Access: MCP Transport + AG-UI Bridge + Protocol Truth

**Goal:** External MCP clients can call FormicOS tools. AG-UI clients can stream colony activity. Protocol status reflects reality.

**B1. MCP Streamable HTTP mount.**

The 19-tool MCP server exists in `mcp_server.py` but has no transport. FastMCP 3.x ships `create_streamable_http_app()` in `fastmcp.server.http` — it returns a Starlette sub-application with Streamable HTTP support (the current MCP transport standard).

```python
from fastmcp.server.http import create_streamable_http_app

mcp_http = create_streamable_http_app(
    server=mcp,
    streamable_http_path="/mcp",
    stateless_http=True,
)
```

Lifespan coordination: FastMCP's Streamable HTTP app has its own lifespan (task group for session management via `StreamableHTTPSessionManager`). When mounting as a Starlette sub-app, the nested lifespan needs to start/stop within FormicOS's existing lifespan. Smoke test this explicitly — the FastMCP docs warn about this exact issue.

After this, Claude Desktop, Cursor, VS Code Copilot, Goose, or any MCP client can connect to `http://localhost:8080/mcp` and call all 19 FormicOS tools.

Files touched:
- `src/formicos/surface/app.py` — mount MCP HTTP app (~20 LOC)

**B2. AG-UI run streaming.**

`POST /ag-ui/runs` — accepts a task, spawns a colony, streams AG-UI-formatted SSE events until completion.

Honest semantics (per orchestrator review):

| AG-UI Event | FormicOS Source | Honesty Note |
|---|---|---|
| `RUN_STARTED` | `ColonySpawned` | |
| `RUN_FINISHED` | `ColonyCompleted/Failed/Killed` | |
| `STEP_STARTED` | `RoundStarted` | |
| `STEP_FINISHED` | `RoundCompleted` | |
| `TEXT_MESSAGE_START` | `AgentTurnStarted` | |
| `TEXT_MESSAGE_CONTENT` | `AgentTurnCompleted.output_summary` | **Summary at turn end, not token streaming.** |
| `TEXT_MESSAGE_END` | After `AgentTurnCompleted` | |
| `STATE_SNAPSHOT` | Colony projection after each round | **Full snapshot, not delta.** |
| `CUSTOM` | All other FormicOS events | Passthrough with event type as name. |

NOT included:
- True token streaming (runner doesn't produce per-token events)
- Real-time `TOOL_CALL_START/END` (tool calls are recorded post-hoc as name lists on `AgentTurnCompleted.tool_calls`)
- JSON-patch `STATE_DELTA` (no native delta source)

`TEXT_MESSAGE_CONTENT` should label itself as summary content. AG-UI clients should not expect streaming tokens.

Implementation requires a colony-scoped event subscription (~20 LOC in `ws_handler.py`), the SSE endpoint + event translator (~200 LOC in new `agui_endpoint.py`), and route wiring (~5 LOC in `app.py`).

Files touched:
- `src/formicos/surface/agui_endpoint.py` — new, ~200 LOC
- `src/formicos/surface/ws_handler.py` — add colony-scoped subscription queue (~20 LOC)
- `src/formicos/surface/app.py` — add route (~5 LOC)

**B3. Protocol status truth.**

`view_state.py` currently hardcodes AG-UI as `"inactive"` and MCP as `"active"` with a tool count. After B1 and B2 land, update protocol status to reflect reality:

- MCP: `"active"`, tools: 19, transport: `"streamable_http"`, endpoint: `"/mcp"`
- AG-UI: `"active"`, events: (count of supported AG-UI event types), endpoint: `"/ag-ui/runs"`
- A2A: `"inactive"` (Agent Card is discovery-only, no task handling)

This makes the protocol status section of the UI truthful — the operator sees which protocols are live and which aren't.

Files touched:
- `src/formicos/surface/view_state.py` — update `_build_protocol_status()` (~15 LOC)
- `frontend/src/components/settings-view.ts` — render transport/endpoint details if present (~10 LOC)

**B4. Update Agent Card.**

`/.well-known/agent.json` should now advertise:
- `capabilities.streaming: true` (AG-UI endpoint exists)
- A `protocols` object listing `mcp: "/mcp"` and `agui: "/ag-ui/runs"`

Files touched:
- `src/formicos/surface/app.py` — update `agent_card()` response (~10 LOC)

**B5. AG-UI event glossary.**

Document which `CUSTOM` event names FormicOS emits, with payload shapes and rendering guidance. External AG-UI clients need this to decide what to render vs. ignore.

Files touched:
- `docs/AG-UI-EVENTS.md` — new reference doc

---

### Track C — Runtime Observability Polish

**Goal:** VRAM is real. Slot probes are cleaned up. Accumulated UX debt is cleared.

**C1. VRAM monitoring (core).**

With the Blackwell image default (Wave 18), the LLM container has GPU access. Three probe options in order of preference:

- **Option A:** llama.cpp `/metrics` Prometheus endpoint — if available, exposes `llama_kv_cache_usage_bytes` and GPU memory gauges. Cleanest: HTTP scrape, no Docker socket dependency.
- **Option B:** llama.cpp `/health` on newer builds — some versions include VRAM in the health response. Check the Blackwell build.
- **Option C:** `docker exec formicos-llm nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits` — requires Docker socket (which Track A adds). Last resort.

Pick the option that works on the live stack. Surface `vram` as `{usedMb: number, totalMb: number} | null` on the `LocalModel` snapshot. Frontend renders a VRAM utilization bar alongside the existing slot utilization bar.

Files touched:
- `src/formicos/surface/ws_handler.py` — add VRAM probe to `_probe_local_endpoints()` (~30 LOC)
- `src/formicos/surface/view_state.py` — populate `vram` from probe data (~5 LOC)
- `frontend/src/types.ts` — update `vram` type to `{usedMb: number, totalMb: number} | null`
- `frontend/src/components/model-registry.ts` — render VRAM bar (~20 LOC)

**C2. Slot probe cleanup (core).**

`ws_handler._probe_local_endpoints()` currently probes `/health` twice (once without params, once with `?include_slots`). The llama.cpp API has evolved — newer builds may have changed the slot response format. While touching the probe for VRAM, clean up:

- Consolidate to a single `/health?include_slots` call (it returns everything the plain `/health` returns plus slot details)
- Read `total_slots` from `/props` if not already present in health response
- Remove any dead-letter probe paths that no longer match llama.cpp output

Files touched:
- `src/formicos/surface/ws_handler.py` — refactor probe logic (~net -10 LOC, cleaner)

**C3. Dead control audit (polish allowance).**

Walk every interactive element in all 25 Lit components post-Wave 19. Verify each button, toggle, and input dispatches a command that reaches a handler that produces a visible effect. Fix or remove anything dead.

Specific targets:
- Colony export button edge cases (empty colonies, no Archivist, no workspace files)
- Template editor save → verify round-trip persistence
- Caste editor save → verify round-trip persistence
- Model policy edit → verify YAML persistence survives restart
- Redirect/escalation UI elements from Wave 19 wired to live data
- Protocol status display accuracy after B3 lands

Files touched:
- Various frontend components — fixes only, no new features
- Documented in wave summary

**C4. Skill bank hit-rate visibility (stretch).**

Track whether retrieved skills correlate with successful colony outcomes. Extend the skill confidence update path in `colony_manager.py` to compute a simple `hit_rate = successful_retrievals / total_retrievals`. Surface `hitRate` alongside `avgConfidence` in the skill bank stats snapshot.

This is stretch because: it's easy to compute something noisy, harder to make it meaningfully actionable. If the wave runs long, this drops first.

Files touched (if stretch lands):
- `src/formicos/surface/colony_manager.py` — extend skill confidence update (~20 LOC)
- `src/formicos/surface/skill_lifecycle.py` — add hit_rate to summary (~10 LOC)
- `src/formicos/surface/view_state.py` — include hitRate in skillBankStats (~5 LOC)
- `frontend/src/components/skill-browser.ts` — render hit rate (~10 LOC)

---

## Execution Shape for 3 Parallel Coder Teams

| Team | Track | First Lands On | Dependencies |
|------|-------|-----------------|--------------|
| **Coder 1** | A (Sandbox + Transcript) | `Dockerfile`, `docker-compose.yml`, `sandbox_manager.py`, `transcript.py`, `app.py` | None — starts immediately |
| **Coder 2** | B (MCP + AG-UI + Protocol) | `agui_endpoint.py`, `app.py`, `ws_handler.py`, `view_state.py` | Coordinates with Coder 1 on `app.py` route additions |
| **Coder 3** | C (Observability) | `ws_handler.py`, `view_state.py`, frontend | Coordinates with Coder 2 on `ws_handler.py`; may use Docker socket from Track A for VRAM probe Option C |

### Serialization Rules

- **Coder 1 and Coder 2 both add routes to `app.py`** — non-overlapping additions (transcript route vs MCP mount + AG-UI route + Agent Card update). Safe to parallel if both read before writing.
- **Coder 2 and Coder 3 both touch `ws_handler.py`** — Coder 2 adds colony-scoped subscription. Coder 3 refactors probe logic + adds VRAM probe. Different methods. Coder 3 rereads after Coder 2.
- **Coder 2 and Coder 3 both touch `view_state.py`** — Coder 2 updates protocol status. Coder 3 updates VRAM. Different functions. Safe to parallel.

### Overlap-Prone Files

| File | Teams | Resolution |
|------|-------|------------|
| `app.py` | 1 + 2 | Both add routes. Non-overlapping sections. |
| `ws_handler.py` | 2 + 3 | Coder 2 adds subscription. Coder 3 refactors probes. Coder 3 rereads after Coder 2. |
| `view_state.py` | 2 + 3 | Coder 2 updates protocol status. Coder 3 updates VRAM. Different functions. |
| `docker-compose.yml` | 1 only | Sandbox image + Docker socket. |
| `Dockerfile` | 1 only | Docker CLI install. |
| Frontend | 3 only | VRAM bar + dead control fixes. |

---

## Acceptance Criteria

Wave 20 is complete when:

1. **Sandbox executes real code.** `code_execute` tool in a coder agent runs Python inside `formicos-sandbox:latest`. `CodeExecuted` event emitted with stdout/stderr/exit_code. AST security blocks dangerous patterns.
2. **Docker CLI works in app container.** `docker run --rm formicos-sandbox:latest python -c "print('hello')"` succeeds from inside the formicos container.
3. **Colony transcript returns clean summary.** `GET /api/v1/colonies/{id}/transcript` returns structured JSON for completed colonies. `build_transcript()` is importable from surface layer.
4. **MCP transport is live.** An MCP client connects to `http://localhost:8080/mcp` and successfully calls `list_workspaces`.
5. **AG-UI streams colony activity.** `POST /ag-ui/runs` spawns a colony and streams AG-UI events over SSE. Events arrive in correct lifecycle order.
6. **Agent Card advertises live protocols.** `/.well-known/agent.json` lists MCP and AG-UI endpoints with `streaming: true`.
7. **Protocol status is truthful.** Settings view shows MCP as active with transport type, AG-UI as active with endpoint, A2A as inactive.
8. **VRAM is real.** Model registry shows actual GPU VRAM utilization from a concrete probe source.
9. **Slot probes are clean.** Single consolidated probe path, no dead-letter reads.
10. **No dead controls.** Every button dispatches, connects, and produces visible effect — or is removed.
11. **All CI gates green.**

### Smoke Traces

1. **Sandbox execution trace:** Spawn colony with coder → coder calls `code_execute` with `print(2+2)` → sandbox container runs → `stdout: "4"` → `CodeExecuted` event with `exit_code: 0`
2. **Sandbox security trace:** Coder calls `code_execute` with `import os; os.system("rm -rf /")` → AST security blocks → `CodeExecuted` event with `blocked: true`
3. **Sandbox disabled trace:** Set `SANDBOX_ENABLED=false` → `code_execute` falls back to subprocess → restricted execution works
4. **Transcript trace:** Colony completes → `GET /api/v1/colonies/{id}/transcript` → structured JSON with rounds, team, quality, redirects
5. **MCP trace:** Connect MCP client to `/mcp` → call `list_workspaces` → receive workspace list
6. **AG-UI trace:** POST to `/ag-ui/runs` with task → SSE stream → `RUN_STARTED` → rounds stream → `RUN_FINISHED`
7. **Protocol discovery trace:** `GET /.well-known/agent.json` → verify MCP and AG-UI endpoints listed → `GET /health` → `settings-view` shows protocols truthfully
8. **VRAM trace:** Stack running → model registry shows VRAM used/total → values are non-null and plausible

---

## Not In Wave 20

| Item | Reason | When |
|------|--------|------|
| AG-UI bidirectional steering | Read-only stream is sufficient for Tier 1 | Post-alpha |
| AG-UI token streaming | Runner doesn't produce per-token events | Requires runner instrumentation |
| A2UI generative dashboards | Needs Lit vs React resolution | Post-alpha |
| Full A2A task handling | Agent Card + MCP is sufficient | Post-alpha |
| MCP OAuth 2.1 auth | Single-operator, no auth needed yet | Post-alpha |
| New Queen tools | Wave 18-19 tools are sufficient | If needed |
| Event union expansion | No new events needed | — |
| Self-evolution / experimentation engine | Needs more data from config changes | Post-alpha |
| Skill hit-rate (if stretch doesn't land) | Noisy metric, not operator-obvious | Wave 21 |

---

## Frozen Files

| File | Reason |
|---|---|
| `src/formicos/core/events.py` | No event changes. |
| `src/formicos/core/ports.py` | Ports frozen. |
| `src/formicos/core/types.py` | No type changes (InputSource, CasteSlot stable). |
| `src/formicos/engine/runner.py` | Stable. Code execute handler is injected, not modified here. |
| `src/formicos/surface/queen_runtime.py` | No new Queen tools. |
| `src/formicos/surface/colony_manager.py` | Stable (unless stretch C4 lands). |
| `src/formicos/surface/mcp_server.py` | Tools unchanged — transport added via mount, not tool modification. |
| `src/formicos/surface/config_validator.py` | Stable. |
| `config/formicos.yaml` | No config changes. |
| `config/caste_recipes.yaml` | No caste changes. |

---

## Open Questions

1. **Docker socket security.** Mounting `/var/run/docker.sock` is standard for CI/CD and container-spawning patterns. For a single-operator local-first system this is acceptable. The `SANDBOX_ENABLED=false` flag provides an opt-out. E2B/Daytona are future alternatives that avoid the socket but add external dependencies. Recommend: proceed with socket mount + flag + documentation.

2. **VRAM probe method.** Depends on what the Blackwell llama.cpp build exposes. Test in order: `/metrics` endpoint → `/health` response → `docker exec nvidia-smi`. Pick the first that works. Coder 3 should test on the live stack before committing to an approach.

3. **MCP lifespan coordination.** FastMCP's `StreamableHTTPSessionManager` needs its task group started. The `create_streamable_http_app()` returns a `StarletteWithLifespan` that exposes a `.lifespan` property. When mounting as a sub-app under FormicOS's Starlette, verify the nested lifespan starts/stops correctly. Smoke test: connect, call a tool, disconnect, verify no leaked tasks.

4. **AG-UI `STATE_SNAPSHOT` frequency.** After every round is the natural FormicOS shape — it aligns with `RoundCompleted` events and doesn't require inventing a polling cadence. Recommend: one `STATE_SNAPSHOT` per `STEP_FINISHED`.
