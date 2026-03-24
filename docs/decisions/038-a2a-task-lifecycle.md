# ADR-038: Inbound A2A Task Lifecycle as Colony View

**Status:** Accepted  
**Date:** 2026-03-17  
**Wave:** 23

## Decision

Add a thin A2A REST layer at `/a2a/tasks` that exposes existing colonies as externally consumable tasks.

Tasks are not a new entity. They are a view over colonies with:
- deterministic team selection
- poll-based status
- transcript-backed results
- no streaming in this version

## Context

FormicOS is already externally reachable through:
- MCP at `/mcp`
- AG-UI at `POST /ag-ui/runs`
- Agent Card at `/.well-known/agent.json`

But those surfaces are still awkward for a generic external agent:
- MCP expects knowledge of castes, tiers, strategy, and budget
- AG-UI spawns and streams a new run, but cannot attach to an existing colony
- there is no standard submit/poll/result lifecycle

External agents expect a simpler shape:
- submit task
- get handle
- poll status
- fetch result

## Design

Provide five REST endpoints:

| Method | Path | Purpose |
|---|---|---|
| POST | `/a2a/tasks` | submit task and return handle |
| GET | `/a2a/tasks` | list tasks |
| GET | `/a2a/tasks/{id}` | poll status |
| GET | `/a2a/tasks/{id}/result` | fetch result |
| DELETE | `/a2a/tasks/{id}` | cancel task |

### Key decisions

**Tasks are colonies**

- `task_id == colony_id`
- no second task store
- no new events
- no new core data model

**Team selection is deterministic**

The A2A route does not call the Queen LLM.

Selection order:
1. template match
2. simple keyword heuristics
3. safe fallback

This keeps the route predictable, cheap, and fast.

**No streaming in Wave 23**

`POST /ag-ui/runs` spawns a new colony. It cannot attach to an already-running one.

Therefore A2A does not advertise:
- `stream_url`
- attach semantics
- push notifications

If a later wave adds `GET /a2a/tasks/{id}/events`, that can build on the existing colony subscription infrastructure. It is not part of this decision.

**Results come from `build_transcript()`**

Transcript remains the single result-building path for:
- transcript HTTP
- A2A result payloads
- any future replay/result surfaces

**A2A tasks live in the normal workspace**

Use normal workspace placement with dedicated A2A-style thread naming, not a separate A2A workspace.

That preserves access to:
- workspace memory
- workspace library
- workspace settings

## Consequences

- external agents get a standard task lifecycle
- A2A stays a thin wrapper instead of becoming a fourth control plane
- operator templates improve A2A behavior automatically
- operator can still inspect A2A work in the normal UI tree
- no new event/type surface is introduced

## Rejected Alternatives

**Separate task entity**

Rejected. Colonies already hold the lifecycle state and result data A2A needs.

**Internal LLM-based team selection**

Rejected. That would make the A2A route slower, less predictable, and more expensive for little alpha-stage benefit.

**A2A streaming via AG-UI**

Rejected. AG-UI cannot attach to an existing task, so advertising streaming from A2A would be misleading.

**Dedicated A2A workspace**

Rejected. It would isolate A2A tasks from the operator's existing workspace memory and library by default.

## Implementation Note

See `docs/waves/wave_23/algorithms.md`, Section 6.
