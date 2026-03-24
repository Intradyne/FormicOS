# Wave 20 Planning Findings - Open + Grounded

**Date:** 2026-03-16  
**Scope:** Planning audit after Wave 19 close

---

## 1. The Biggest Remaining Gaps Are Openness and Actual Productivity

Waves 18-19 made the Queen materially more capable:
- she can inspect
- she can redirect
- she can chain work forward
- she can complete approval-backed config changes
- she can escalate a colony

What still feels unfinished is not Queen power. It is system usefulness:
- coder colonies still do not have a reliable real sandbox path
- external clients still cannot call or observe FormicOS through standard transports
- operator telemetry is truthful but still missing the VRAM number people actually want

That makes Wave 20 a good "open + grounded" wave instead of another autonomy wave.

---

## 2. Sandbox Execution Is the Highest-Value Backend Completion Item

The code execution path is already conceptually correct:
- AST safety gate
- sandbox manager
- output sanitizer
- `CodeExecuted` event

The missing part is runtime completion, not design:
- the sandbox image does not exist
- the app container does not include the Docker CLI
- the app container cannot reach the Docker daemon without the socket mount

Those three pieces should be treated as one unit. Shipping only one or two of them would still leave `code_execute` effectively broken.

An operator opt-out flag is also worth carrying in the plan. A small `SANDBOX_ENABLED=false` escape hatch keeps local development workable for people who do not want Docker socket access.

---

## 3. Transcript Should Be a Shared Builder, Not an Internal HTTP Dependency

A colony transcript surface is a strong fit for this wave, but the clean seam is a shared builder function rather than an endpoint-first design.

That builder can serve three consumers cleanly:
- the operator-facing transcript endpoint
- AG-UI late-join or replay flows
- future chaining helpers

The important planning constraint is to avoid internal code depending on its own REST surface.

---

## 4. MCP Transport Is the Right First "Open" Move

The repo already has an in-process MCP server and Wave 19 already added Agent Card discovery. What is missing is a transport that lets external clients actually connect.

Mounting FastMCP Streamable HTTP is the smallest credible step because it:
- reuses the existing tool surface
- follows the current MCP transport standard
- avoids inventing a parallel bespoke API

The only meaningful implementation risk here is lifespan coordination. The plan should keep that explicit and treat smoke coverage as part of the feature, not an afterthought.

---

## 5. AG-UI Tier 1 Must Stay Honest

The AG-UI bridge is a good fit as long as it describes the runner truthfully.

The current runner gives us:
- run lifecycle
- round lifecycle
- agent turn start
- turn-end summaries
- full state snapshots
- rich FormicOS events for passthrough

It does **not** give us:
- token streaming
- real-time tool call start/end events
- native JSON-patch state deltas

That means the right first bridge is "summary + snapshot semantics," not protocol completeness theater.

---

## 6. Protocol Truth Should Ship With the Bridge

If Wave 20 lands MCP and AG-UI, the operator-facing protocol status and Agent Card should be updated in the same slice.

That pairing matters because the repo is already trying to be honest about local/cloud/runtime state. Leaving protocol status stale after adding live transports would repeat the exact class of truth gap Wave 17 worked to remove.

The natural pairing is:
- MCP transport mount
- AG-UI endpoint
- protocol status truth in the snapshot/UI
- Agent Card protocol advertisement
- AG-UI custom-event glossary

---

## 7. Observability Should Stay Narrow and Concrete

VRAM monitoring is a good Wave 20 core item. It is concrete, operator-visible, and directly tied to the now-stable Blackwell local stack.

The rest of Track C should stay disciplined:
- VRAM probe: core
- slot probe cleanup: core
- dead-control audit: polish allowance
- skill-bank hit rate: stretch only

That keeps the wave grounded in visible operator value instead of drifting into metrics that are easy to compute but hard to trust.

---

## 8. Wave 20 Should Reflect the Current 80k Local Default

The repo no longer uses the earlier 100k/131k default assumptions as the normal local baseline. The current local-default stack is:
- Blackwell-native llama.cpp image
- `LLM_CONTEXT_SIZE=80000`
- `context.total_budget_tokens=32000`

Wave 20 planning should treat that as the baseline reality when discussing VRAM headroom and local observability. The wave does not need to reopen the context-size debate in order to deliver openness, sandbox completion, or telemetry truth.

---

## 9. Recommended Wave Shape

The cleanest shape for the wave is:

- Track A: sandbox execution completion + transcript surface
- Track B: MCP transport + AG-UI bridge + protocol truth
- Track C: VRAM monitoring + slot probe cleanup, with audit polish and skill hit-rate only if time remains

That keeps the wave small, useful, and easy to explain:
- FormicOS can do real coder work
- external tools can discover and talk to it
- the operator sees what is actually happening
