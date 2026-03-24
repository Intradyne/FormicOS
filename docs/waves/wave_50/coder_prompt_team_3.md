You own the Wave 50 recipe, docs-truth, and measurement-setup track.

This is the guidance-and-truth pass. You are not inventing runtime behavior.
You are aligning Queen guidance, operator docs, and the Wave 50 packet with
what Teams 1 and 2 actually ship.

## Mission

Update the repo guidance to reflect Wave 50 reality:

1. document configuration memory and learned templates truthfully
2. document cross-workspace knowledge promotion rules
3. set up the Phase 0 measurement framework
4. keep the Wave 50 packet honest about what shipped and what deferred

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. Honest self-improvement guidance makes the system usable at scale.

## Read First

1. AGENTS.md
2. CLAUDE.md
3. docs/OPERATORS_GUIDE.md
4. config/caste_recipes.yaml
5. docs/waves/wave_50/wave_50_plan.md
6. docs/waves/wave_50/acceptance_gates.md

Before editing, reread the final Team 1 and Team 2 landed files.
You can draft docs and measurement scaffolding in parallel, but the final
truth-refresh pass on status/docs must happen after Team 1 and Team 2 land.

## Owned Files

- config/caste_recipes.yaml
- AGENTS.md
- CLAUDE.md
- docs/OPERATORS_GUIDE.md
- docs/waves/wave_50/*
- README.md only if a small truthful capability update is warranted

## Do Not Touch

- product code
- frontend code
- backend code
- contract/event code

## Required Work

### Track A: Queen Guidance For Templates

Update the Queen recipe to:

- mention that template suggestions may appear in preview cards
- instruct the Queen to reference template name when using one
- keep minimal-colony-first and fast_path-default guidance from Wave 48
- do not imply the Queen learns new strategies automatically

### Track B: Configuration Memory Docs

Document:

- the distinction between operator-authored templates (YAML) and learned
  templates (replay-derived)
- auto-template qualification rules: quality >= 0.7, rounds >= 3,
  Queen-spawned, no duplicate for category + strategy
- how templates are proposed in preview cards
- that template matching is category-first in v1

### Track C: Cross-Workspace Knowledge Docs

Document:

- the global knowledge tier and retrieval order
- explicit promotion rules and the "Promote to Global" affordance
- auto-promotion candidate criteria (flagged, not auto-promoted):
  - used across 3+ workspaces
  - stable/permanent decay class
  - confidence >= 0.7
  - Forager-sourced documentation preferred
- that auto-promotion does NOT happen in v1

### Track D: Measurement Setup

Define the Phase 0 measurement matrix:

- old recipes vs grounded recipes (Wave 48 ablation)
- fast_path vs colony
- knowledge off vs on
- foraging off vs on
- template suggestion on vs off (Wave 50 addition)

This does not need to run yet. It needs to be documented so the next
measurement pass has a clear protocol.

### Track E: Packet Truth

Refresh the Wave 50 packet after the substrate lands:

- what shipped
- what deferred
- where the implementation narrowed the original plan
- whether learned templates are truly replay-safe
- whether global scope promotion really works across workspaces

### Track F: Architectural Truth

Keep these points explicit:

- no new event types were added
- additive fields were added to ColonySpawned, ColonyTemplateCreated,
  and MemoryEntryScopeChanged
- learned templates are replay-derived, not file-backed
- no external memory system is required
- no auto-promotion happened (candidates only)
- global promotion uses a real backend route, not a frontend-only event trick

## Hard Constraints

- Do not fabricate shipped learning behaviors
- Do not overclaim template intelligence
- Do not imply auto-promotion shipped if only candidate flagging landed
- Do not reintroduce NeuroStack or external-memory language
- ASCII only in all documentation (no mojibake)

## Validation

Run at minimum:

1. grep sweep for stale template/knowledge/scope claims
2. any lightweight docs validation already used in the repo

## Summary Must Include

- exactly how the Queen recipe guidance changed
- how operator-authored vs learned templates are documented
- how global knowledge promotion rules are explained
- what the measurement matrix looks like
- which parts of the original plan were deferred
