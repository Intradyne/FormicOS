**Wave:** 39 -- "The Supervisable Colony"

**Theme:** The operator becomes a durable co-author of the hive state, not
just a viewer. Every important system decision becomes inspectable at the
level it was made. Every assumption becomes editable. Every adaptation becomes
reversible. This is the control-plane wave that makes Waves 40-41's benchmark
and publication claims credible.

Wave 39 is not the public proof wave. It is the wave that makes FormicOS
transparent enough to trust before it becomes more adaptive and benchmarked in
public.

The wave has five pillars:

1. cognitive audit trail
2. editable hive state
3. completion and validator UX
4. governance-owned adaptation
5. configuration memory surfaces

**Prerequisite:** Wave 38 is accepted. The tool-level NemoClaw bridge works,
A2A compatibility is hardened, the internal benchmark harness exists, the
escalation outcome matrix exists, admission scoring is real, federation trust
is hardened, and temporal truth is surfaced where the substrate already has it.

**Contract target:** Wave 39 is the first narrow event expansion since Wave 33.
ADR-049 must be written and approved before Pillar 2 begins. The event union
grows from 55 to 58 through exactly three new event families:

1. `KnowledgeEntryOperatorAction`
2. `KnowledgeEntryAnnotated`
3. `ConfigSuggestionOverridden`

Everything else in Wave 39 should remain read-model, projection, route, or UI
work unless an ADR-backed blocker is discovered.

**Critical design rule:** Operator actions are replayable, reversible, and
local-first unless explicitly promoted into shared truth.

That means:

- `pin`, `unpin`, `mute`, `unmute`, `invalidate`, and `reinstate` are local
  editorial overlays by default
- those overlays affect retrieval and operator-facing interpretation
- they do **not** silently mutate shared Beta confidence truth
- they do **not** federate by default
- promotion into shared confidence or federated truth must be a separate,
  deliberate mechanism and is not part of Wave 39

**Recommended ADRs:**

- ADR-049: operator co-authorship event expansion
- audit-trail truthfulness policy only if Team 1 finds a real replay-boundary
  ambiguity that needs to be recorded

---

## Current Repo Truth At Wave Start

Wave 39 should start from the repo that exists, not from a roadmap abstraction.

- `routing_override` already exists as the current governance-owned capability
  escalation seam in `src/formicos/surface/projections.py`,
  `src/formicos/surface/queen_tools.py`, and `src/formicos/engine/runner.py`.
  Provider fallback is still a separate router concern.
- Colony knowledge accesses already exist in projection state via
  `KnowledgeAccessRecorded` handling in `src/formicos/surface/projections.py`.
- Operator directives already exist and are tracked in projection state.
- Parallel planning already exists and is replayed from `ParallelPlanCreated`.
- Outcome truth and escalation outcome reporting already exist from Wave 38.
- `frontend/src/components/colony-detail.ts`,
  `frontend/src/components/queen-overview.ts`,
  `frontend/src/components/proactive-briefing.ts`,
  `frontend/src/components/workflow-view.ts`, and
  `frontend/src/components/knowledge-browser.ts` already exist and are the
  natural Wave 39 UI seams.
- The current round and turn events do **not** preserve exact runtime
  `knowledge_prior` calculations or exact retrieval-ranking snapshots. Wave 39
  should therefore either:
  - present audit summaries reconstructed from replay-safe state, or
  - stop and justify a separate contract change

Wave 39 should **not** smuggle a second event expansion into the audit trail.
ADR-049 is the only intended contract change in this wave.

---

## Why This Wave

By the end of Wave 38, FormicOS is already making increasingly consequential
decisions:

- knowledge biases topology
- outcomes reinforce confidence
- branching diagnostics warn about collapse
- configuration memory begins to suggest what tends to work
- federation and admission policy shape what knowledge enters and wins
- escalation reporting now exposes capability changes

That means the system is getting more opinionated about how work should be
done. The next question is not "can it do more?" but "can the operator see why
it did that, correct it when it is wrong, and trust that the correction will
survive replay?"

Without that control plane, future adaptation creates black-box risk:

- auto-escalation without inspectable reasons
- configuration suggestions without editable surfaces
- knowledge reuse without operator editorial authority
- status badges without task-specific success semantics

Wave 39 fixes that by turning operator participation into durable truth where
it must be durable, and by making the reasoning surfaces inspectable without
forcing raw transcript reading.

The sequence matters:

1. make the system supervisable
2. then make it more adaptive
3. then rehearse a benchmark
4. then make a public claim

---

## Pillar 1: Cognitive Audit Trail

Wave 39 should answer "why did this happen?" without asking the operator to
reverse-engineer the transcript manually.

This pillar is a read-model and UI pillar, not a new truth store.

### 1A. Colony reasoning view

For any colony, running or completed, surface a structured audit narrative
covering replay-safe truth such as:

- retrieved knowledge and downstream trust rationale
- directives received during execution
- manual or automatic escalations and their reasons
- governance actions per round
- outputs or entries produced by the colony
- downstream reuse of extracted knowledge where available

Important honesty rule:

- if a datum is not replay-safe today, do **not** render it as exact historical
  fact
- exact `knowledge_prior` or retrieval-ranking internals should only be shown
  if they are already preserved in replay-safe state
- otherwise the UI must label them as reconstructed or explanatory summaries

### 1B. Decision provenance chain

For Queen planning and thread-level orchestration, connect:

- Queen reasoning
- knowledge gaps
- `ParallelPlanCreated`
- planned colony groups
- actual colony execution
- final outcomes

The goal is a causal chain the operator can follow from:

"why was this plan proposed?" -> "what colonies actually ran?" -> "what did
the system learn?"

### Files

- `src/formicos/surface/projections.py` -- additive audit-view assembly
- `src/formicos/surface/routes/api.py` -- additive read-only audit route if
  needed
- `frontend/src/components/colony-audit.ts` -- NEW
- `frontend/src/components/colony-detail.ts` -- MODIFY
- `frontend/src/components/queen-overview.ts` -- MODIFY

### Risks

- overclaiming exact runtime internals that are not replay-safe
- building a giant transcript viewer instead of a compact reasoning surface
- sneaking in contract changes through "audit metadata"

### Acceptance

An operator can open a colony and understand:

- what knowledge was used
- what changed during execution
- why governance acted the way it did
- what the colony produced

without needing to read the full transcript to answer basic "why" questions.

---

## Pillar 2: Editable Hive State

Wave 39 makes the operator a durable co-author of the knowledge substrate.

This is the only pillar that expands the event union.

### 2A. Operator action overlays

Use one event family with a state-setting action enum:

`KnowledgeEntryOperatorAction`

Supported actions:

- `pin`
- `unpin`
- `mute`
- `unmute`
- `invalidate`
- `reinstate`

These actions rebuild local operator overlay state by replay:

- pinned entries
- muted entries
- invalidated entries

Important semantic rule:

- these actions are **editorial overlays**, not shared confidence mutations
- they do not emit `MemoryConfidenceUpdated`
- they do not silently change `conf_alpha` or `conf_beta`
- they do not federate by default

Retrieval path behavior:

- pinned entries receive local retrieval preference and decay protection
- muted entries are skipped from ordinary retrieval
- invalidated entries are excluded from normal retrieval and visually marked
  as operator-rejected on this instance

The original canonical knowledge record remains intact unless a later explicit
promotion path is added in a future wave.

### 2B. Operator annotations

Use a second event family:

`KnowledgeEntryAnnotated`

Payload should include:

- `entry_id`
- annotation text
- optional tag / classification
- actor
- scope / workspace
- timestamp

Annotations are additive operator truth. They appear:

- in the knowledge detail view
- in trust rationale surfaces
- in audit views where relevant

Federation policy:

- annotations are optionally federated by workspace policy
- additive explanation may federate
- behavioral overrides do not

### 2C. Config suggestion overrides

Use a third event family:

`ConfigSuggestionOverridden`

This event records when an operator edits a recommendation or plan before
execution, including:

- suggestion category
- original config
- overridden config
- reason
- actor
- timestamp

This is how the system learns not only what worked, but what the operator
preferred when presented with a recommendation.

### Files

- `src/formicos/core/events.py` -- 3 new event families only
- `src/formicos/surface/projections.py` -- overlay state, annotation index,
  config override history
- `src/formicos/surface/knowledge_catalog.py` -- retrieval respects overlays
- `src/formicos/surface/routes/knowledge_api.py` and/or
  `src/formicos/surface/routes/api.py` -- additive operator-action endpoints
- `frontend/src/components/knowledge-browser.ts` -- action menu, badges,
  annotation surfaces

### Federation policy

ADR-049 must make this explicit:

- `pin` / `unpin` / `mute` / `unmute` / `invalidate` / `reinstate`:
  local-only by default
- annotations: optionally federated by workspace policy
- config overrides: local by default unless a future explicit promotion path
  exists

### Risks

- conflating editorial authority with epistemic authority
- making operator corrections disappear on replay
- over-federating local operator preferences

### Acceptance

Operator edits survive replay and affect local retrieval or interpretation
without silently mutating shared confidence truth.

---

## Pillar 3: Completion and Validator UX

Wave 39 should make completion more honest across task types, not just code
tasks.

### 3A. Task-type validators

Add lightweight deterministic validators for task families beyond the existing
code-execution convergence path.

Candidate validators:

- code tasks: existing successful execution path remains
- research tasks: require non-trivial knowledge output or artifacts
- documentation tasks: require structured output
- review tasks: require actionable feedback rather than empty approval

Validation outputs should be tri-state:

- `pass`
- `fail`
- `inconclusive`

Important implementation rule:

- validator state must be replay-derivable from existing truth or computed from
  existing projection state
- do not add a second hidden runtime-only validator truth surface

### 3B. Visible validator results

Show validator result alongside quality where useful, but do not overclaim
validator coverage:

- validated success
- completed without validator confirmation
- stalled / force-halted

### 3C. Tri-state completion display

Every major status surface should distinguish:

- Done (validated)
- Done (unvalidated)
- Stalled

This should appear in:

- colony detail
- command-center completion cards
- thread-level colony status surfaces where practical

### Files

- `src/formicos/engine/runner.py` -- deterministic validator dispatch and
  auto-escalation interplay
- `src/formicos/surface/projections.py` -- replay-derivable validator fields
  or derived view support
- `src/formicos/surface/colony_manager.py` -- only if a small additive seam is
  needed to surface the result
- `frontend/src/components/colony-detail.ts` -- tri-state display
- `frontend/src/components/queen-overview.ts` -- tri-state colony cards

### Risks

- inventing validators that are really subjective LLM judgments
- storing non-replayable runtime-only validator truth
- collapsing "unvalidated" into either false success or false failure

### Acceptance

Operators can clearly distinguish validated success, unvalidated completion,
and stall/failure across the main Wave 39 surfaces.

---

## Pillar 4: Governance-Owned Adaptation

Adaptation lands here, but only inside the supervisable frame.

### 4A. Governance-triggered auto-escalation

Implement one bounded rule:

- if `stall_count >= 2`
- and the colony has a heavier available tier
- and budget allows another attempt
- then set `routing_override` to the next available tier and give the colony
  one more chance before force-halt

Critical rule:

- this must flow through `routing_override`
- this must not be buried inside provider fallback
- this remains governance-owned, inspectable, and reversible

Documentation and UI should describe it generically as:

"from the colony's starting tier to the next available tier"

not as "light to standard" or any other hard-coded default.

### 4B. Earned autonomy recommendations

Use the existing operator behavior projections to recommend autonomy changes by
insight category.

Wave 39 scope:

- recommend promotion or demotion
- do not auto-apply those changes
- promotion still uses existing `WorkspaceConfigChanged`

Suggested thresholds:

- require meaningful evidence
- earning trust should be slower than losing it
- dismissed recommendations should cool down before reappearing

### Files

- `src/formicos/engine/runner.py` -- auto-escalation rule only
- `src/formicos/surface/proactive_intelligence.py` -- earned autonomy
  recommendation rules
- `src/formicos/surface/projections.py` -- operator response-pattern
  aggregation
- `src/formicos/surface/queen_runtime.py` -- briefing integration
- `frontend/src/components/proactive-briefing.ts` -- accept / dismiss surfaces

### Risks

- conflating provider fallback with capability escalation
- letting adaptation outrun inspectability
- making autonomy changes automatic before evidence is strong enough

### Acceptance

Adaptation is visible, recommendation-backed, and reversible. Auto-escalation
uses the existing governance seam, and earned autonomy remains operator-approved.

---

## Pillar 5: Configuration Memory Surfaces

Wave 39 should show "what tends to work here" as an editable recommendation
layer rather than a hidden heuristic.

### 5A. Configuration recommendation display

Surface recommendation panels such as:

- strategy
- caste composition
- round limits
- model tier

Each recommendation should include evidence from outcome history and the
escalation matrix.

### 5B. Pre-spawn configuration editing

When a recommendation or plan is shown before spawn, the operator should be
able to edit it before launch.

Those edits are durable through `ConfigSuggestionOverridden`.

### 5C. Configuration history

Show how recommendations changed over time so the operator can see the system's
learning process rather than just its current preference.

### Files

- `src/formicos/surface/proactive_intelligence.py` -- recommendation assembly
- `src/formicos/surface/queen_runtime.py` -- summary and briefing integration
- `frontend/src/components/config-memory.ts` -- NEW
- `frontend/src/components/queen-overview.ts` -- MODIFY
- `frontend/src/components/workflow-view.ts` -- MODIFY for pre-spawn edit
  overlay

### Risks

- hidden heuristics disguised as recommendations
- separating the configuration panel from the evidence that produced it
- recording overrides without making them visible later

### Acceptance

Recommendation surfaces are visible, editable, evidence-backed, and durable
where operator overrides are supposed to be durable.

---

## ADR-049: Operator Co-Authorship Event Expansion

ADR-049 must be written and approved before Pillar 2 implementation begins.

It must justify exactly three event families:

1. `KnowledgeEntryOperatorAction`
2. `KnowledgeEntryAnnotated`
3. `ConfigSuggestionOverridden`

For each, ADR-049 must define:

- payload schema
- replay argument using the "vanish on replay = lie" test
- federation behavior
- downstream consumers
- rejected alternatives

Rejected alternatives that should already be documented:

- separate event type per operator action
- projection-only operator overlays
- automatic federation of all operator actions
- silent confidence mutation from local editorial actions

---

## Priority Order

Cut from the bottom if Wave 39 runs long.

| Priority | Item | Pillar | Risk | Class |
|----------|------|--------|------|-------|
| 1 | ADR-049 and 3-event expansion | 2 | Low | Must |
| 2 | Colony reasoning view | 1A | Low | Must |
| 3 | Entry-level operator overlays | 2A | Medium | Must |
| 4 | Knowledge annotations | 2B | Low | Must |
| 5 | Task-type validators | 3A | Medium | Must |
| 6 | Tri-state completion display | 3C | Low | Must |
| 7 | Auto-escalation through `routing_override` | 4A | Medium | Must |
| 8 | Pre-spawn configuration editing | 5B | Medium | Should |
| 9 | Earned autonomy recommendations | 4B | Medium | Should |
| 10 | Configuration memory panel | 5A | Low | Should |
| 11 | Decision provenance chain | 1B | Low | Should |
| 12 | Configuration history | 5C | Low | Stretch |
| 13 | Expanded validator-result surfaces | 3B | Low | Stretch |

---

## Team Assignment

### Team 1: Audit Trail + Validators + Auto-Escalation

Owns:

- Pillar 1
- Pillar 3
- Pillar 4A

Primary files:

- `src/formicos/engine/runner.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/colony_manager.py`
- `src/formicos/surface/routes/api.py` if additive audit read route is needed
- `frontend/src/components/colony-audit.ts`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/queen-overview.ts`

### Team 2: Editable Hive State + ADR-049 Event Expansion

Owns:

- ADR-049 implementation
- Pillar 2A
- Pillar 2B

Primary files:

- `src/formicos/core/events.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/routes/knowledge_api.py`
- `src/formicos/surface/routes/api.py` only for additive operator-action routes
- `frontend/src/components/knowledge-browser.ts`

### Team 3: Earned Autonomy + Configuration Memory + Pre-Spawn Editing

Owns:

- Pillar 4B
- Pillar 5

Primary files:

- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/projections.py`
- `frontend/src/components/proactive-briefing.ts`
- `frontend/src/components/config-memory.ts`
- `frontend/src/components/queen-overview.ts`
- `frontend/src/components/workflow-view.ts`

### Overlap rules

- `src/formicos/surface/projections.py`
  - Team 1: audit-view and validator support
  - Team 2: operator overlays and annotation index
  - Team 3: operator response patterns and config-memory support
  - all three teams must reread this file before merge
- `frontend/src/components/queen-overview.ts`
  - Team 1: compact audit / completion truth
  - Team 3: configuration memory and recommendation surfaces
  - keep the changes additive and reread before merge
- `src/formicos/surface/routes/api.py`
  - Team 1 owns additive audit read surfaces
  - Team 2 owns additive operator-action surfaces only if knowledge routes are
    not the better home

---

## What Wave 39 Does Not Include

- no Aider Polyglot adapter
- no public benchmark submission
- no federated distillation
- no Pattern 2 external-agent `LLMPort` wrapping
- no automatic promotion of local editorial overlays into shared confidence
- no casual second event expansion for audit metadata

---

## Smoke Test

1. Open a completed colony and inspect the audit trail. Verify that the trail
   shows replay-safe reasoning surfaces without requiring raw transcript
   reading.
2. Pin an entry, replay from the event log, and verify the pin persists.
3. Mute an entry, run retrieval in the same domain, and verify it is skipped.
   Unmute it and verify it reappears.
4. Annotate an entry, replay, and verify the annotation still appears in the
   detail and trust surfaces.
5. Edit a pre-spawn plan or recommendation, verify the override is recorded,
   and verify execution uses the edited config.
6. Stall a colony that has a heavier tier available. Verify auto-escalation
   fires through `routing_override`, gives the colony one more chance, and is
   visible in the audit trail.
7. Accumulate enough operator-response evidence in one insight category and
   verify the Queen recommends a promotion or demotion rather than silently
   changing autonomy.
8. Run task types with and without meaningful outputs and verify the validator
   and tri-state completion surfaces distinguish validated / unvalidated /
   stalled correctly.
9. Replay the full event log and verify operator actions and overrides survive.
10. Full CI: `ruff`, `pyright`, `lint_imports`, `pytest`, frontend build all
    clean.

---

## After Wave 39

FormicOS is supervisable. The operator is a durable co-author of local hive
state. Editorial actions survive replay. Retrieval and recommendation behavior
can be inspected and corrected without conflating local preference with shared
epistemic truth. Adaptation is visible, bounded, and reversible.

Wave 40 can then focus on rehearsal: Aider adapter work, benchmark-specific
tuning, and cost/performance shaping. Wave 41 can make a public claim with a
system that is transparent enough to audit.

The product thesis after Wave 39:

**FormicOS is an editable shared brain with operator-visible traces, where
every important decision is inspectable, every local assumption is editable,
and every adaptation is reversible.**
