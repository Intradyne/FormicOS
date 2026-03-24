# Wave 19 Planning Findings - The Queen Steers

**Date:** 2026-03-15  
**Scope:** Planning audit after Wave 18 docs landed

---

## 1. The Highest-Value Gap Is Mid-Run Steering

Wave 18 gave the Queen much better visibility:
- template inspection
- colony inspection
- skill inspection
- workspace file inspection
- safe config proposals

But she is still mostly fire-and-forget. Once a colony is running, the only real steering tools are operator kill or passive waiting. That is the biggest remaining gap between "the system works" and "the system feels intelligent."

The most valuable Wave 19 intervention is therefore not broader autonomy. It is narrow, auditable strategic steering.

---

## 2. Redirect Is the Right First Adaptive Capability

The cleanest first intervention is redirecting a colony's goal while preserving the team and topology.

Key design choices:
- preserve the original task
- add `active_goal`
- keep an append-only `redirect_history`
- reset convergence and stall windows
- preserve pheromone weights

This gives the Queen a meaningful strategic action without forcing a larger redesign of the round loop or team model.

---

## 3. Governance Alerts Should Stay Explicit

The planning pass favors direct Queen notification from the governance path over hidden mutable projection flags.

That keeps the signal path clearer:
- governance emits the warning it already knows how to surface
- the Queen receives a direct callback or notification from that path
- the Queen's response is visible in the thread

This avoids introducing projection state that matters operationally but is not clearly evented or triggered.

---

## 4. Colony Chaining Fits Best as a Spawn Extension

Chaining is not a new lifecycle state. It is richer seed context for a new colony.

The repo already has the right seam for this:
- extend `ColonySpawned`
- resolve input material at spawn time
- inject it into context assembly

The important constraint is replay safety. That is why `InputSource.summary` should be resolved eagerly instead of re-reading the source colony later.

---

## 5. Config Approval Is the Natural Completion of Wave 18

Wave 18 shipped proposal-only config changes.

Wave 19 should close the loop in the smallest safe way:
- thread-scoped pending proposal
- TTL
- explicit operator approval
- re-validation through both existing guards
- apply
- persist
- emit the existing config-changed event

This is a trust-building learning loop, not an experimentation engine.

---

## 6. Tier Escalation Is a Good Intermediate Step

Full mid-run team mutation is still too large for this wave. But tier escalation is a lightweight version of adaptation that fits the current system:
- no new agents
- no topology rebuild
- no team surgery
- just a colony-scoped routing hint for later rounds

That makes it a reasonable Track C item.

The one caveat is persistence and auditability. If escalation meaningfully changes runtime behavior, the wave should be clear about whether that state is intentionally transient or whether it needs replay support later.

---

## 7. Agent Card Is a Legitimate Stretch, Not the Center

Serving `/.well-known/agent.json` is small, independent, and honest if it advertises only discoverability.

It should not pull focus from the core wave. The wave's center is:
- redirect
- chaining
- config approval
- tier escalation

Agent Card fits as a stretch or sidecar because it does not compete for the same architecture seams.

---

## 8. Likely Contract Shape

The narrowest credible contract expansion is:
- one new event: `ColonyRedirected`
- one existing event extension: `ColonySpawned.input_sources`
- one new core type: `InputSource`

That is a small enough change set for the value unlocked.

Other Wave 19 behavior can mostly ride existing state/event surfaces:
- config approval uses existing config-changed flow
- tier escalation can remain transient if the team accepts that tradeoff
- Agent Card requires no domain event change

---

## 9. Recommended Wave Shape

The wave shape that best matches the repo and operator goals is:

- Track A: redirect + governance-triggered Queen steering
- Track B: colony chaining + config approval completion
- Track C: tier escalation + audit UX, with Agent Card as stretch

That keeps the wave focused on strategic steering rather than drifting into broad autonomy or protocol work.
