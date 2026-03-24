# Wave 50 Acceptance Gates

Wave 50 is accepted when the system demonstrably learns from its own
experience and transfers knowledge across workspaces under operator control,
without introducing external dependencies or non-deterministic magic.

## Gate 1: Learned Templates Are Replay-Safe

Must be true:

- successful colonies above the quality threshold produce a ColonyTemplateCreated event
- learned templates are visible in TemplateProjection from replay
- older event logs without the new additive fields replay safely

Fail if:

- learned templates only exist as YAML files written to config/templates/
- templates are lost on projection rebuild
- backward compatibility is broken for existing events

## Gate 2: Template Consumers Merge Both Sources

Must be true:

- Queen list_templates and inspect_template show both operator-authored
  YAML templates and replay-derived learned templates
- the operator can distinguish which is which

Fail if:

- learned templates are invisible to the Queen tools
- operator YAML templates are broken by the merge
- the two sources silently duplicate

## Gate 3: Template Matching Informs Preview

Must be true:

- when the Queen previews a new task, she checks for matching templates
  by task category
- a matching template populates the preview card defaults
- the preview card indicates the template source

Fail if:

- template matching exists but the preview card shows no trace of it
- the template overrides without operator visibility
- matching uses embedding similarity in v1 instead of category-first

## Gate 4: Auto-Template Qualification Is Conservative

Must be true:

- only colonies above quality >= 0.7 with 3+ rounds are auto-templated
- only Queen-spawned colonies qualify
- no duplicate template for the same category + strategy combination

Fail if:

- every successful colony becomes a template
- fast_path one-shots are templated
- manually configured colonies are templated without provenance truth

## Gate 5: Global Knowledge Scope Exists And Is Explicit

Must be true:

- a knowledge entry can be promoted from workspace to global scope
- the promotion uses a real additive scope semantic, not a hack
- the promotion uses a real backend mutation path, not a frontend-only event trick
- global entries appear in retrieval across all workspaces
- global entries are discounted relative to workspace-local entries

Fail if:

- global scope is faked by empty-string workspace_id without schema support
- promotion silently moves entries without operator action
- global entries crowd out workspace-specific knowledge

## Gate 6: Promotion Is Operator-Controlled

Must be true:

- explicit "Promote to Global" is available in the knowledge browser
- the UI shows the entry's current scope clearly
- promotion emits a replay-safe event

Fail if:

- entries are auto-promoted without operator decision
- the promotion affordance is hidden or undiscoverable
- the event is not replay-safe

## Gate 7: Auto-Promotion Candidates Are Flagged Not Promoted

Should be true:

- entries meeting the candidate threshold are flagged in the UI
- the operator decides whether to promote

Fail if:

- candidates are auto-promoted
- the threshold is too loose (below 3 workspaces, below confidence 0.7)

## Gate 8: Circuit Breaker Prevents Cost Runaway

Should be true:

- a per-request retry cap exists across all providers
- provider cooldown emits a notify message in Queen chat
- the system degrades to local model rather than crashing

Fail if:

- infinite retry loops remain possible
- cooldown is silent (operator has no visibility)
- the system crashes instead of degrading

## Gate 9: SQLite Pragmas Are Upgraded

Should be true:

- mmap_size is set for read-heavy replay workloads
- busy_timeout is increased from current 5000ms

Fail if:

- pragmas are changed without documenting the rationale
- existing data integrity is compromised

## Gate 10: Product Identity Holds

Must be true:

- no new external dependency was introduced
- no NeuroStack or external memory system
- the wave reads as native FormicOS self-improvement

Fail if:

- the learning features depend on external retrieval
- templates or knowledge promotion require a foreign service

## Gate 11: Docs And Recipes Match Reality

Must be true:

- docs distinguish operator-authored from learned templates
- docs explain global knowledge promotion rules
- deferred items remain explicitly deferred

Fail if:

- docs claim embedding-based template matching that did not ship
- docs claim auto-promotion that is only candidate flagging
