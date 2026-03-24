# Wave 24 Planning Findings

This document records the repo-grounded findings that shaped Wave 24.

---

## 1. Wave 23 solved protocol honesty, not surface trust

Wave 23 left the system in a good place structurally:

- A2A is live and honest
- AG-UI is live and honest
- protocol truth is aligned across the Agent Card, snapshot, and UI

But manual operator use exposed a second class of alpha issues: the product still presents some truthful internals in misleading or incomplete ways.

Wave 24 exists to close that gap.

---

## 2. Colony display names already exist, but the tree does not send them

Confirmed in the live repo:

- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py) already stores `display_name`
- [helpers.ts](/c:/Users/User/FormicOSa/frontend/src/helpers.ts) already prefers `displayName`
- [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py) still builds colony tree nodes from raw ids

This is a small, high-leverage fix:

- send `displayName`
- prefer `display_name or id` in the tree node

The frontend is already prepared to benefit from it.

---

## 3. Local model identity is mostly a display-policy issue

The live repo already derives a human-readable local model name in [view_state.py](/c:/Users/User/FormicOSa/src/formicos/surface/view_state.py).

The inconsistency the operator sees is not primarily a missing backend probe. It is that different surfaces emphasize different identifiers:

- one surface emphasizes the human model name
- another emphasizes the routing alias or address

Wave 24 therefore treats this as a presentation reconciliation problem, not a model-discovery project.

---

## 4. Tree collapse must be treated as a live-behavior bug

Static reading of [tree-nav.ts](/c:/Users/User/FormicOSa/frontend/src/components/tree-nav.ts) does not reveal an obvious logic error:

- toggle state is local
- event propagation is already being stopped
- the render branch looks correct

But the operator reports that the control still does not collapse the tree in practice.

Conclusion:

- this ticket must be accepted by live browser verification
- not by static code inspection alone

---

## 5. Context reduction is real, but the UI explanation is not good enough

The product is already showing a difference between configured and effective context.

What is missing is the explanation:

- why the reduction happened
- whether it is expected
- what the operator can do about it

The stale `131k` comment in [formicos.yaml](/c:/Users/User/FormicOSa/config/formicos.yaml) reinforces the confusion and should be cleaned up in the same wave.

---

## 6. VRAM units are not normalized cleanly across probe paths

The live repo mixes source units:

- Prometheus path reads bytes
- health path may return bytes or already-normalized values
- `nvidia-smi` path returns MiB

This is the most plausible explanation for the absurd VRAM numbers seen in manual use.

Wave 24 should:

- normalize backend values to MiB
- keep field names stable
- render in a human-readable unit on the frontend

---

## 7. Aggregate budget is mathematically true but product-misleading

The top-level budget denominator is currently the sum of per-colony budget caps.

That is not a fake calculation, but it behaves like a fake product concept:

- it looks like a global budget
- it grows every time a colony is spawned
- the operator cannot meaningfully adjust it from that surface

Conclusion:

- aggregate surfaces should show session cost only
- per-colony budget should stay in colony detail

This affects more than one UI surface and must be fixed consistently.

---

## 8. A2A is honest but still missing attach

After Wave 23:

- A2A supports submit, poll, result, cancel
- AG-UI supports spawn-and-stream

What is still missing is the external story:

"I submitted work. Now let me watch it."

The cleanest next step is still attach under A2A, not AG-UI expansion.

---

## 9. Multi-subscriber fan-out is the technical hinge for attach

The current colony subscription shape in [ws_handler.py](/c:/Users/User/FormicOSa/src/formicos/surface/ws_handler.py) is still effectively one queue per colony id.

That is sufficient for the current AG-UI path.
It is not sufficient for:

- attach-to-existing task streams
- multiple listeners
- replay-plus-live-tail flows

Before attach can be trustworthy, colony fan-out must support more than one subscriber per colony.

---

## 10. Event translation must not fork

[agui_endpoint.py](/c:/Users/User/FormicOSa/src/formicos/surface/agui_endpoint.py) still contains the live translation logic from FormicOS events into AG-UI-shaped SSE messages.

If A2A attach adds a second streaming path, duplicating that logic would create immediate drift risk.

Conclusion:

- extract one shared translator
- keep AG-UI behavior equivalent
- reuse the same translation for A2A attach

---

## 11. Failure metadata exists on events, but is dropped in projections

Confirmed in the live repo:

- [events.py](/c:/Users/User/FormicOSa/src/formicos/core/events.py) carries:
  - `ColonyFailed.reason`
  - `ColonyKilled.killed_by`
- [projections.py](/c:/Users/User/FormicOSa/src/formicos/surface/projections.py) currently stores only terminal status, not the related metadata
- [transcript.py](/c:/Users/User/FormicOSa/src/formicos/surface/transcript.py) therefore cannot expose conservative failure context today

This means Wave 24 can support:

- `failure_reason`
- `killed_by`
- failed/killed round context

But it should not claim richer governance metadata that the repo does not persist.

---

## 12. No new ADR is necessary for Wave 24

The wave is making implementation refinements inside the shape already established by:

- [034-mcp-streamable-http.md](/c:/Users/User/FormicOSa/docs/decisions/034-mcp-streamable-http.md)
- [035-agui-tier1-bridge.md](/c:/Users/User/FormicOSa/docs/decisions/035-agui-tier1-bridge.md)
- [038-a2a-task-lifecycle.md](/c:/Users/User/FormicOSa/docs/decisions/038-a2a-task-lifecycle.md)

Wave 24 does not introduce a new protocol or a new domain entity.
It completes attach under the accepted A2A lifecycle and improves surface truth.

---

## Conclusion

Wave 24 is the right next step because it combines two things the product now needs at the same time:

- operator trust in what the UI is saying
- a complete external "submit then attach" story

That is why the wave is scoped as "Trust the Surfaces" rather than as a pure interoperability wave or a generic polish wave.
