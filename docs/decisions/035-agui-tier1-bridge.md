# ADR-035: AG-UI Tier 1 Bridge with Honest Summary Semantics

**Status:** Accepted
**Date:** 2026-03-15
**Wave:** 20

## Decision

Add a read-only AG-UI SSE endpoint at `POST /ag-ui/runs` that spawns a colony and streams its lifecycle as AG-UI-formatted events. Use honest summary-at-turn-end semantics — do not synthesize granularity the runner does not produce.

## Context

AG-UI is an event transport protocol (not a UI framework) that defines standard events for agent-to-UI communication: `RUN_STARTED`, `RUN_FINISHED`, `STEP_*`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `STATE_SNAPSHOT`, `STATE_DELTA`, `CUSTOM`.

FormicOS already has rich internal events streamed over WebSocket, but in a proprietary format. Providing an AG-UI-shaped view of colony activity makes FormicOS consumable by any AG-UI-compatible client without reverse-engineering the FormicOS event schema.

However, the FormicOS runner does not produce all the granularity AG-UI defines. Specifically:

- Agent output is available as `output_summary` (200 chars) at turn completion, not as per-token streaming
- Tool calls are recorded as a post-hoc name list on `AgentTurnCompleted.tool_calls`, not as real-time start/end events with arguments and results
- No RFC 6902-style JSON patches exist for state deltas

Inventing synthetic events would be dishonest and mislead AG-UI clients into expecting capabilities that don't exist.

## Emitted Events

| AG-UI Event | FormicOS Source | Notes |
|---|---|---|
| `RUN_STARTED` | `ColonySpawned` | |
| `RUN_FINISHED` | `ColonyCompleted/Failed/Killed` | |
| `STEP_STARTED` | `RoundStarted` | |
| `STEP_FINISHED` | `RoundCompleted` | |
| `TEXT_MESSAGE_START` | `AgentTurnStarted` | |
| `TEXT_MESSAGE_CONTENT` | `AgentTurnCompleted.output_summary` | Summary content, explicitly labeled |
| `TEXT_MESSAGE_END` | After `AgentTurnCompleted` | |
| `STATE_SNAPSHOT` | Colony projection after `RoundCompleted` | One per round |
| `CUSTOM` | All other FormicOS events | Event type name as custom event name |

## NOT Emitted

| AG-UI Event | Reason |
|---|---|
| `TOOL_CALL_START` | Runner does not emit per-tool-call start events |
| `TOOL_CALL_END` | Tool results are not available as discrete events |
| `STATE_DELTA` | No native JSON-patch delta source |
| Token streaming | Runner does not produce per-token events |

These can be added later if runner instrumentation is extended.

## Consequences

- External AG-UI clients can stream colony lifecycle events
- `TEXT_MESSAGE_CONTENT` is explicitly labeled as summary content via `contentType: "summary"` — clients should not render it as streaming tokens
- `STATE_SNAPSHOT` after each round uses the shared `build_transcript()` builder, giving a consistent shape for both live streaming and late-join replay
- `CUSTOM` events pass through all FormicOS-specific events (e.g., `ColonyRedirected`, `CodeExecuted`, `SkillConfidenceUpdated`) — external clients can choose what to render
- Colony-scoped event subscription added to `WebSocketManager` — reusable for future per-colony filtering
- No bidirectional steering — the AG-UI endpoint is read-only, spawn-and-observe
- ~200 LOC in new `agui_endpoint.py`

## Rejected Alternatives

**Full AG-UI compliance with synthetic events**
Rejected. Synthesizing `TOOL_CALL_START/END` from post-hoc name lists or `STATE_DELTA` from full snapshots would be dishonest. Clients would make incorrect assumptions about real-time granularity.

**Bidirectional AG-UI steering (Tier 2)**
Rejected for this wave. Read-only streaming is sufficient for external observability. Bidirectional control introduces complex state synchronization between AG-UI clients and the existing WebSocket UI.

**AG-UI as frontend replacement (Tier 3 / A2UI)**
Rejected. Queen-as-UI-composer requires resolving the Lit vs React question and introduces generative layout complexity. This is post-alpha scope.

**Token streaming via response chunking**
Rejected. The runner calls `llm_port.complete()` which returns a complete response, not a stream. Adding streaming would require changes to `LLMPort`, all three LLM adapters, and the runner's tool-call loop. Out of scope for a Tier 1 bridge.

## Implementation Note

See `docs/waves/wave_20/algorithms.md`, §4.
