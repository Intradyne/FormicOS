# Wave 48 Acceptance Gates

Wave 48 is accepted when the operators can see one coherent task story and the
specialist castes are less blind without turning into general-purpose chaos.

## Gate 1: Reviewer Is Grounded But Still Read-Only

Must be true:

- the Reviewer can inspect real workspace truth relevant to review
- the Reviewer has read-only repo/diff visibility
- the Reviewer still lacks mutation tools

Fail if:

- the Reviewer still reviews only summaries and artifacts
- the Reviewer gains write power just to feel more capable

## Gate 2: Researcher Is Grounded And Has A Truthful Fresh-Info Path

Must be true:

- the Researcher can inspect real project files/structure
- the Researcher has a truthful way to gather fresh information
- the shipped design is documented honestly

Accepted designs:

- preferred: synchronous Forager mediation / `request_forage`
- fallback: bounded direct web access for Researcher

Fail if:

- the Researcher still only echoes memory/transcripts
- both web paths coexist ambiguously with no clear story
- the docs claim a clean mediated path that does not really exist

## Gate 3: Thread Timeline Is Real

Must be true:

- a thread-scoped timeline endpoint exists
- it returns chronological entries grounded in replay-safe truth
- the primary audit surface is thread-first, not workspace-first

Fail if:

- the timeline is only mocked in the frontend
- the endpoint is just a thin wrapper over unrelated workspace noise

## Gate 4: Colony Audit Carries Forager Attribution

Must be true:

- the colony audit payload can mark Forager-sourced knowledge
- provenance fields such as URL/domain/query/credibility are surfaced when
  truthfully available
- relevant forage-cycle context is included when it can be linked honestly

Fail if:

- the frontend is forced to guess provenance from thin payloads
- the audit UI implies provenance that the backend cannot support

## Gate 5: Preview Confirmation Uses Real Preview Truth

Must be true:

- the existing creator Review step consumes backend preview support
- it works for both `spawn_colony` and `spawn_parallel`
- the operator sees real launch truth before dispatch

Fail if:

- the UI still relies on a local rough estimate only
- preview works on one path but not the other
- the flow invents values the backend did not actually provide

## Gate 6: The Operator Story Is Connected

Must be true:

- the timeline is visible in the thread workflow
- timeline rows can open relevant colony and knowledge surfaces
- colony audit links naturally into knowledge/provenance detail

Fail if:

- the new timeline is just another disconnected page
- the operator still has to reconstruct the story manually

## Gate 7: Running-State Clarity Stays Bounded

Should be true:

- running colonies show a bounded "latest meaningful activity" signal
- the UI mines existing replay-safe previews and event rows first
- no raw artifact streaming was added casually

Fail if:

- the UI fabricates detailed activity from weak data
- the implementation bloats the event model just for prettier status text

## Gate 8: Product Identity Holds

Must be true:

- no benchmark-specific runtime path was added
- no Forager-as-normal-caste rewrite happened
- the wave still reads as "specialization without blindness"

Fail if:

- the caste changes exist mainly to improve benchmark scores
- the architecture gets more rigid instead of more truthful

## Gate 9: Docs And Recipes Match Reality

Must be true:

- reviewer/researcher recipes reflect the actual landed tool surfaces
- operator docs explain the thread timeline, audit enrichment, and preview flow
  truthfully
- deferred items remain explicitly deferred

Fail if:

- recipes mention tools or behaviors that did not ship
- docs overclaim running-state richness or the Researcher/Forager split

## Gate 10: Follow-On Measurement Remains Interpretable

Should be true:

- the packet leaves an explicit note that post-wave measurement must isolate
  caste grounding effects

Fail if:

- Wave 48 changes a major confound and the project pretends the later curve can
  be interpreted without ablations
