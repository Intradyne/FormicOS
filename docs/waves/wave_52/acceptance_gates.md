# Wave 52 Acceptance Gates

Wave 52 has two packets:
- **Packet A:** control-plane coherence
- **Packet B:** intelligence reach + visible learning

These gates are written so all three teams can work in parallel without losing
the acceptance bar for either packet.

## Packet A -- Control-Plane Coherence

### Gate A1 -- Canonical Version Truth

Pass if:
- package version, CapabilityRegistry version, and Agent Card version all agree
- the value comes from one authoritative source instead of multiple hardcoded constants

Fail if:
- any protocol surface still reports a version fork

### Gate A2 -- Event Count Truth

Pass if:
- all maintained Wave 52-touched docs/status surfaces that mention event count agree on `64`

Fail if:
- any maintained touched surface still says `62` or `65`

### Gate A3 -- ADR Truth

Pass if:
- ADR 045/046/047 no longer read as future work
- they clearly indicate accepted/shipped substance

Fail if:
- any of those ADRs still imply the feature is merely proposed

### Gate A4 -- Protocol Description Truth

Pass if:
- settings and topbar protocol surfaces no longer display stale fallback copy such as
  `Not implemented`, `planned`, or `Agent Card discovery only` for live surfaces
- transport naming is internally consistent

Fail if:
- a live protocol is still described as unimplemented

### Gate A5 -- Docs Claim Truth

Pass if:
- stale protocol/control-plane claims found in owned docs are corrected
- known example: `/debug/inventory` truth is accurate

Fail if:
- Wave 52-touched docs still make an obviously false claim about live protocol surfaces

### Gate A6 -- Stream Lifecycle Truth

Pass if:
- A2A attach and AG-UI run streams do not emit terminal `RUN_FINISHED` solely
  because 300 seconds passed without an event
- if idle behavior remains, it is explicit and non-terminal

Fail if:
- inactivity is still reported as run termination

## Packet B -- Intelligence Reach + Visible Learning

### Gate B0 -- Queen Tool-Result Hygiene

Pass if:
- Queen tool results are treated as untrusted prompt data
- large tool-result history is compacted under pressure
- Queen tool-result handling is materially aligned with the colony runner seam

Fail if:
- Queen tool results still re-enter the model as raw unsanitized prompt text

### Gate B1 -- Thread-Aware Queen Retrieval

Pass if:
- Queen automatic pre-spawn retrieval passes `thread_id`
- thread-scoped retrieval can affect the primary Queen path

Fail if:
- the Queen path still leaves the thread-aware retrieval seam unused

### Gate B2 -- A2A Learned-Template Reach

Pass if:
- A2A can see learned templates, not only disk-authored templates
- a matching learned template can influence team selection
- the response exposes enough metadata for the caller to see what was selected

Fail if:
- learned templates remain invisible to A2A intake

### Gate B3 -- External Budget Truth

Pass if:
- A2A's per-colony budget behavior remains explicit
- AG-UI no longer silently falls back to the runtime default budget
- if spawn-gate parity lands, A2A and AG-UI both use the workspace spawn gate
- the behavior is honest when caller budget is absent vs present

Fail if:
- AG-UI budget behavior remains an implicit `5.0` default with no clear contract

### Gate B4 -- AG-UI Omitted-Defaults Truth

Pass if one of the following is true:
- omitted castes use deterministic server-selected defaults and this is reported honestly
- or the current omitted-default behavior is intentionally retained and explicitly documented

Fail if:
- AG-UI behavior changes but the caller cannot tell what the server selected

### Gate B5 -- Learned Templates Are Visible To The Operator

Pass if:
- Queen briefing can surface learned-template intelligence using existing projection truth
- the operator can see that templates were learned and how they are performing

Fail if:
- the intelligence exists in projections but remains invisible in the Queen briefing

### Gate B6 -- Recent Outcomes Are Visible To The Operator

Pass if:
- Queen briefing includes a compact digest of recent colony outcomes
- the digest is grounded in existing outcome projections

Fail if:
- the wave claims visible learning but does not surface recent success/failure quality signals

### Gate B7 -- Briefing Selection Actually Includes New Signals

Pass if:
- the Queen briefing selection logic allows the new B4/B5 signals to appear in routine practice

Fail if:
- new insight types are technically emitted but are consistently crowded out by the existing selection cap

## Parallel Safety Gates

### Gate P1 -- Disjoint Ownership

Pass if:
- Team 1 stays in backend/control-plane code files
- Team 2 stays in frontend protocol/status files
- Team 3 stays in docs/ADR/handoff files

Fail if:
- teams spill into each other's write sets without a clear seam reason

### Gate P2 -- Team 3 Final Truth Refresh

Pass if:
- Team 3 rereads Team 1 and Team 2 outcomes before finalizing `status_after_plan.md`

Fail if:
- docs are frozen before final repo truth is known

## Final Wave Acceptance

Wave 52 is accepted when:
- Packet A gates pass
- Packet B gates pass
- all three team summaries align with final repo truth
- CI remains clean or only pre-existing unrelated failures remain
- no out-of-scope protocol expansion or new subsystem work slipped into the wave

## Remaining-Issue Classification

Anything left after Wave 52 must be labeled as one of:
- blocker
- control-plane truth debt
- intelligence-reach debt
- surface-truth debt
- docs debt
- runtime/deployment debt
- advisory/model-dependent
