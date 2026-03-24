# Wave 20 Dispatch Prompts

Use these prompts directly. They assume the Wave 20 planning set is now the source of truth:
- `docs/waves/wave_20/plan.md`
- `docs/waves/wave_20/algorithms.md`
- `docs/waves/wave_20/planning_findings.md`
- `docs/decisions/034-mcp-streamable-http.md`
- `docs/decisions/035-agui-tier1-bridge.md`

Shared workspace. No git branches.

## Launch Order

1. Launch Stream A, Stream B, and Stream C in parallel.
2. Stream A and Stream B may both start immediately on `src/formicos/surface/app.py`, but both must reread the file before writing if the other stream has already landed changes.
3. Stream B owns the first pass on `src/formicos/surface/ws_handler.py` for colony-scoped AG-UI subscription.
4. Stream C may start probe/frontend work immediately, but must reread `src/formicos/surface/ws_handler.py` after Stream B lands before editing it.
5. Stream B owns the first pass on `frontend/src/components/settings-view.ts` for protocol-status rendering.
6. Stream C may audit `frontend/src/components/settings-view.ts`, but must reread it after Stream B lands before editing.
7. Stream A should land `src/formicos/surface/transcript.py` early if possible so Stream B can reuse it for `STATE_SNAPSHOT`; Stream B should reread it before finalizing AG-UI snapshot shape if it has landed.

---

## Stream A Prompt

```text
# Wave 20 - Stream A: Sandbox Execution + Transcript Surface

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_20/plan.md
4. docs/waves/wave_20/algorithms.md
5. docs/waves/wave_20/planning_findings.md
6. Dockerfile
7. docker-compose.yml
8. docs/LOCAL_FIRST_QUICKSTART.md
9. src/formicos/adapters/sandbox_manager.py
10. src/formicos/surface/app.py
11. src/formicos/surface/projections.py
12. src/formicos/surface/runtime.py
13. src/formicos/surface/colony_manager.py

You own:
- docker/sandbox.Dockerfile
- Dockerfile
- docker-compose.yml
- docs/LOCAL_FIRST_QUICKSTART.md
- src/formicos/adapters/sandbox_manager.py
- src/formicos/surface/transcript.py
- src/formicos/surface/app.py for the transcript route only
- tests you need for sandbox/transcript seams

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/ws_handler.py
- src/formicos/surface/view_state.py
- src/formicos/surface/mcp_server.py
- src/formicos/surface/queen_runtime.py
- frontend/*
- config/*

Mission:
Close the runtime-completion gap for coder execution and add a clean transcript surface.

Critical repo facts:
- `code_execute` is already wired conceptually: AST gate -> sandbox manager -> output sanitizer -> `CodeExecuted`
- the current blocker is runtime completion, not tool design
- `sandbox_manager._execute_docker()` shells out to `docker run`, so the app container needs both the Docker CLI and daemon access
- the current local default stack is Blackwell image + 80k context, not the older 131k assumption
- transcript logic should be a shared builder, not an internal HTTP dependency

Required outcomes:
1. `formicos-sandbox:latest` exists via `docker/sandbox.Dockerfile`
2. the app container can invoke `docker` when sandboxing is enabled
3. the formicos service has the Docker socket mount with an honest security note
4. `SANDBOX_ENABLED=false` cleanly skips Docker attempts and falls back to subprocess
5. `src/formicos/surface/transcript.py` provides a shared `build_transcript()` helper
6. `GET /api/v1/colonies/{id}/transcript` returns a clean JSON transcript and 404s for unknown IDs
7. the transcript builder works for running, completed, failed, and killed colonies

Important rules:
- Do not install any pip packages in the sandbox image. Standard library only.
- Keep the sandbox non-root and compatible with the existing `--read-only` / `--network=none` execution path.
- Reuse live projection fields; do not invent storage or event changes.
- Internal code must not call its own transcript HTTP endpoint.
- Coordinate carefully on `src/formicos/surface/app.py`: reread it before writing if Stream B has landed.

Audit allowance:
While in your owned files, fix additional low-risk sandbox/transcript issues you discover if they stay inside your ownership. Report them explicitly.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- docker compose build formicos
- docker build -f docker/sandbox.Dockerfile -t formicos-sandbox:latest .

Report back with:
- files changed
- exact sandbox image/base/runtime setup you added
- exact Docker CLI availability path in the app container
- exact Docker socket mount you added
- exact `SANDBOX_ENABLED` behavior
- exact transcript response shape
- any extra audit/polish fixes you included
- validation results
```

---

## Stream B Prompt

```text
# Wave 20 - Stream B: MCP Transport + AG-UI Bridge + Protocol Truth

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_20/plan.md
4. docs/waves/wave_20/algorithms.md
5. docs/waves/wave_20/planning_findings.md
6. docs/decisions/034-mcp-streamable-http.md
7. docs/decisions/035-agui-tier1-bridge.md
8. src/formicos/surface/app.py
9. src/formicos/surface/mcp_server.py
10. src/formicos/surface/ws_handler.py
11. src/formicos/surface/view_state.py
12. src/formicos/surface/runtime.py
13. src/formicos/surface/projections.py
14. frontend/src/components/settings-view.ts

If Stream A has already landed `src/formicos/surface/transcript.py`, read that before finalizing `STATE_SNAPSHOT`.
If Stream A has already changed `src/formicos/surface/app.py`, reread it before editing.

You own:
- src/formicos/surface/app.py for MCP mount, AG-UI route, and Agent Card update
- src/formicos/surface/agui_endpoint.py
- src/formicos/surface/ws_handler.py for colony-scoped subscription only
- src/formicos/surface/view_state.py for protocol-status truth only
- frontend/src/components/settings-view.ts for protocol-status rendering only
- docs/AG-UI-EVENTS.md
- tests you need for MCP/AG-UI/protocol seams

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/colony_manager.py
- src/formicos/surface/projections.py
- src/formicos/surface/mcp_server.py tool definitions
- Dockerfile
- docker-compose.yml
- config/*
- frontend components outside protocol-status rendering

Mission:
Make FormicOS actually callable and streamable through standard external protocols, and make the operator-facing protocol surface truthful.

Critical repo facts:
- the repo already has an in-process FastMCP server, but no mounted HTTP transport
- the Agent Card already exists and is discovery-only today
- AG-UI Tier 1 must stay honest: summary-at-turn-end, no fake token stream, no fake tool-call start/end, no synthetic JSON-patch deltas
- `AgentTurnCompleted` carries `output_summary`, not a token stream and not `round_number`
- `view_state.py` currently reports MCP active and AG-UI inactive regardless of transport reality

Required outcomes:
1. `/mcp` is mounted via FastMCP Streamable HTTP
2. MCP startup/lifespan works cleanly under the parent Starlette app
3. `POST /ag-ui/runs` spawns a colony and streams honest AG-UI SSE events
4. AG-UI emits only the supported Tier 1 event set
5. `TEXT_MESSAGE_CONTENT` is explicitly summary content
6. colony-scoped event subscription exists in `WebSocketManager`
7. protocol status in the snapshot/UI reflects live MCP + AG-UI + inactive A2A truthfully
8. Agent Card advertises the live MCP and AG-UI endpoints once they exist
9. `docs/AG-UI-EVENTS.md` documents CUSTOM passthrough names and payload guidance

Important rules:
- Start with a normal FastMCP mount. Only add manual lifespan wiring if mount-only startup proves insufficient.
- Use `stateless_http=True`.
- `messageId` must derive round number from tracked `RoundStarted` state, not from `AgentTurnCompleted`.
- Do not emit `TOOL_CALL_START`, `TOOL_CALL_END`, or `STATE_DELTA` in Tier 1.
- Keep AG-UI read-only: spawn + observe, no steering.
- On `src/formicos/surface/app.py`, coordinate carefully with Stream A and reread before writing.
- On `src/formicos/surface/ws_handler.py`, keep your changes scoped to colony subscription so Stream C can reread and land probe work after you.

Audit allowance:
While in your owned files, fix additional low-risk protocol-truth issues you discover if they stay inside your ownership. Report them explicitly.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build
- smoke the MCP endpoint with a JSON-RPC tools/list request
- smoke the AG-UI endpoint with a spawned run and verify event ordering

Report back with:
- files changed
- exact MCP mount pattern used
- whether mount-only lifespan worked or required explicit wiring
- exact AG-UI event set emitted
- exact `TEXT_MESSAGE_CONTENT` payload semantics
- exact colony-subscription path added to `WebSocketManager`
- exact protocol-status shape now exposed
- exact Agent Card protocol fields you added
- any extra audit/polish fixes you included
- validation results
```

---

## Stream C Prompt

```text
# Wave 20 - Stream C: VRAM Truth + Slot Probe Cleanup + Dead Control Audit

Working directory: C:\Users\User\FormicOSa

Read first, in order:
1. CLAUDE.md
2. AGENTS.md
3. docs/waves/wave_20/plan.md
4. docs/waves/wave_20/algorithms.md
5. docs/waves/wave_20/planning_findings.md
6. src/formicos/surface/ws_handler.py
7. src/formicos/surface/view_state.py
8. frontend/src/types.ts
9. frontend/src/components/model-registry.ts
10. frontend/src/components/settings-view.ts
11. frontend/src/components/colony-detail.ts
12. frontend/src/components/template-editor.ts
13. frontend/src/components/caste-editor.ts
14. frontend/src/components/skill-browser.ts

Important reread rules:
- Stream B owns the first pass on `src/formicos/surface/ws_handler.py` for colony-scoped subscription. Reread that file after Stream B lands before editing it.
- Stream B owns the first pass on `frontend/src/components/settings-view.ts` for protocol-status rendering. Reread it after Stream B lands before editing it.
- If Stream B updates `src/formicos/surface/view_state.py`, reread before editing so your VRAM changes compose cleanly with protocol-status truth.

You own:
- src/formicos/surface/ws_handler.py for VRAM probe + slot probe cleanup
- src/formicos/surface/view_state.py for VRAM/hit-rate snapshot fields only
- frontend/src/types.ts for VRAM and optional hit-rate types
- frontend/src/components/model-registry.ts
- frontend/src/components/colony-detail.ts for dead-control fixes only
- frontend/src/components/template-editor.ts for dead-control fixes only
- frontend/src/components/caste-editor.ts for dead-control fixes only
- frontend/src/components/settings-view.ts after rereading Stream B's version
- frontend/src/components/skill-browser.ts only if stretch hit-rate lands
- tests you need for probe/view/frontend seams

Do NOT touch:
- src/formicos/core/*
- src/formicos/engine/*
- src/formicos/surface/app.py
- src/formicos/surface/mcp_server.py
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/projections.py
- Dockerfile
- docker-compose.yml
- config/*

Mission:
Make the operator-facing local-runtime status real and clean up the most obvious dead-control debt without drifting into unrelated feature work.

Critical repo facts:
- `view_state.py` currently reports local model `vram` as `None`
- `ws_handler.py` already probes local llama.cpp health and slot state, but the probe path is a little stale and redundant
- the current local default stack is the Blackwell image with 80k context
- the repo values honest nulls over invented telemetry
- dead-control audit is explicit polish allowance, not a blank check to redesign the frontend

Required outcomes:
1. VRAM probe works from a real source on the live stack
2. if VRAM cannot be probed, the UI still reports `null`, not fake numbers
3. slot probing is consolidated to a single clean path
4. `frontend/src/types.ts` reflects the new VRAM object shape
5. model registry renders a truthful VRAM utilization surface
6. protocol-status rendering still works after Stream B lands
7. dead controls found in your owned frontend files are fixed or removed
8. stretch skill hit-rate lands only if A/B are green and C1-C3 are complete

Important rules:
- Probe in this order: `/metrics`, then `/health`, then `docker exec nvidia-smi` if necessary.
- Prefer the cleanest live source that actually works on the running stack.
- Do not invent VRAM estimates.
- Keep `src/formicos/surface/view_state.py` changes scoped so they compose cleanly with Stream B's protocol-status changes.
- Document every dead-control finding you fix.
- Treat skill hit-rate as stretch. Drop it first if the wave gets noisy.

Audit allowance:
You explicitly have dead-control audit allowance inside your owned frontend files. Keep fixes narrow, operator-visible, and reported.

Validation:
- python scripts/lint_imports.py
- python -m pytest -q
- cd frontend && npm run build
- live probe verification on the running local stack if available

Report back with:
- files changed
- exact VRAM probe source that worked
- exact fallback order you implemented
- exact slot-probe cleanup you made
- exact frontend VRAM rendering behavior
- exact dead controls you found/fixed/removed
- whether stretch hit-rate landed or was deferred
- validation results
```
