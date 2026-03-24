# Wave 51 Acceptance Gates

Wave 51 is accepted when the product surface becomes more truthful,
restart behavior becomes less surprising, and the remaining seams are clearly
classified instead of implied.

## Gate 1: Escalation Survives Replay

Must be true:

- `escalate_colony` no longer mutates only in-memory projection state
- escalation survives restart and replay, or the capability is explicitly
  demoted from durable behavior
- any new event shape is documented and replay-safe

Fail if:

- escalation still disappears after restart
- the UI implies durable escalation while the backend remains runtime-only

## Gate 2: Queen Notes Survive Replay Without Polluting Visible Chat

Must be true:

- saved Queen notes survive restart and replay
- the persistence path is evented or otherwise explicitly replay-safe
- private thread-note context is not accidentally turned into ordinary visible
  operator chat unless that is an intentional product decision

Fail if:

- notes still rely only on memory or YAML
- replay-safe persistence is achieved by leaking internal notes into the wrong
  conversational surface

## Gate 3: Ephemeral Capabilities Are Honest

Must be true:

- `dismiss-autonomy` is either replay-safe or explicitly described as ephemeral
- any intentionally short-lived operator action no longer masquerades as durable

Fail if:

- restart-lost state is still presented as if it should survive

## Gate 4: Visible Capabilities Are Reachable

Must be true:

- proactive briefing domain trust controls are reachable from the briefing
  surface that displays the state
- strategy pills no longer look interactive if they are not interactive

Fail if:

- the UI continues to display actionable-looking controls that do nothing

## Gate 5: Config-Memory Shows Degraded State Honestly

Must be true:

- independently failing data sections render an explicit muted unavailable state
- partial data no longer looks like complete data

Fail if:

- failed sections still vanish silently

## Gate 6: Queen Overview Explains Absence

Must be true:

- federation/outcomes sections render an explicit no-data or unavailable state
  when they cannot load

Fail if:

- missing sections are still silently omitted with no explanation

## Gate 7: Model / Protocol Freshness Is Legible

Should be true:

- the operator can see when model/protocol status was last refreshed
- stale state is visibly stale
- if periodic refresh was added, the UI actually updates over time

Fail if:

- long sessions still imply freshness with no indication that the data may be old

## Gate 8: Dead And Misleading Surface Artifacts Are Removed

Must be true:

- `fleet-view.ts` is removed or intentionally reinstated as a real surface
- operator-facing labels no longer say "Skill Bank"
- "Config Memory" is renamed to something that matches current function

Fail if:

- obvious dead or stale product language remains in the primary surface

## Gate 9: Deprecated Memory API Is Clearly Deprecated

Should be true:

- deprecated `/api/v1/memory` endpoints emit `Sunset` headers
- usage is logged so removal can be evidence-based

Fail if:

- deprecation remains only implicit
- the repo still cannot tell whether anything depends on those endpoints

## Gate 10: Replay-Safety Classification Exists As A Canonical Doc

Must be true:

- `docs/REPLAY_SAFETY.md` exists
- it classifies major capabilities as event-sourced, file-backed, in-memory,
  or ephemeral
- it matches actual backend behavior

Fail if:

- contributors still need to infer replay truth by reading scattered code
- the doc claims durability the runtime does not actually provide

## Gate 11: Historical Naming Is Explained Once, Not Repeated Everywhere

Should be true:

- the Memory/Knowledge naming bridge is documented
- frozen/legacy event types are explicitly commented as replay-compatibility
  artifacts where appropriate

Fail if:

- new readers still have to reverse-engineer whether "Memory" and "Knowledge"
  refer to the same substrate

## Gate 12: Wave 50 Landed Truth Is Preserved

Must be true:

- global promotion remains treated as landed substrate, not hidden behind
  a false "planned" UI state
- learned-template enrichment remains treated as landed substrate, not demoted
  to "future" by Wave 51 cleanup

Fail if:

- Wave 51 accidentally regresses or misstates already-landed Wave 50 capability

## Gate 13: Product Identity Holds

Must be true:

- Wave 51 reads as subtractive truth-alignment work
- no new backend subsystem appears
- no new external dependency appears
- the wave improves operator trust more than it increases complexity

Fail if:

- the packet turns into another architecture wave
- polish work becomes a pretext for broad new runtime features
