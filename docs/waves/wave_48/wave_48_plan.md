# Wave 48 -- The Operable Colony

**Theme:** Ground the specialists, connect the operator surfaces that already
exist, and turn the already-landed preview/progress substrate into a coherent
operator flow.

This is a composition-and-grounding wave. The frontend already has real
operator surfaces. Wave 47 already landed coding fluency. The missing work is
now:

- make the specialist castes less blind
- connect the thread, colony, knowledge, and Forager stories
- replace rough local launch guesses with real preview truth

**Identity test:** Every Must item passes: "Would a real operator want this if
the benchmark disappeared tomorrow?"

**Prerequisite:** Wave 47 accepted. Event union remains at 62. Wave 47 tools,
fast path, structural refresh, and preview are live. Validation at wave start:
`3254` Python tests passing, frontend build clean, lint/import checks clean.

**Contract:**

- No new event types.
- No new adapters or subsystems.
- No architecture rewrites.
- No benchmark-specific core paths.
- Do not rebuild operator surfaces that already exist.
- Do not turn the Forager into a normal in-colony worker.
- The Forager remains a service-backed acquisition path with operator-visible
  traces and policy controls.

## Why This Wave

The system already has:

- a directive panel
- colony audit
- Forager Activity in proactive briefing
- knowledge browser web-source provenance
- thread/workflow views
- preview support on both spawn paths

What it still lacks is coherence and grounded specialization:

- the Reviewer still cannot independently inspect live workspace truth
- the Researcher still cannot gather fresh information truthfully
- the colony audit does not carry enough Forager provenance
- the operator cannot see real preview truth in the existing Review flow
- the thread-level "what happened and why" story is still fragmented across
  separate surfaces

Wave 48 fixes the castes first, then connects the operator story.

Two research-informed guardrails also apply across the whole wave:

- **minimal colony first:** keep `fast_path` / small teams as the default for
  simple work; escalate to multi-caste colonies only when the task genuinely
  needs coordination breadth
- **tight context, not auto-context sprawl:** prefer curated, high-signal
  operator/audit context over large automatically assembled prompt blocks

## Repo Truth At Wave Start

Grounded against the live post-Wave-47 tree:

- `frontend/src/components/directive-panel.ts` already exists and is mounted in
  colony detail and Queen chat.
- `frontend/src/components/colony-audit.ts` already exists and is backed by
  `build_colony_audit_view()` in `src/formicos/surface/projections.py`.
- `frontend/src/components/proactive-briefing.ts` already includes Forager
  Activity.
- `frontend/src/components/knowledge-browser.ts` already shows web-source
  provenance.
- `frontend/src/components/colony-creator.ts` already has a Review/Launch step,
  but it still uses a local rough estimate instead of real preview truth.
- `src/formicos/surface/queen_tools.py` already supports preview on both spawn
  paths.
- `config/caste_recipes.yaml` still leaves `reviewer` and `researcher`
  under-grounded relative to their intended roles.

## Pillar 1: Ground The Specialists

**Class:** Must

**Identity test:** Specialized agents should be narrow, not blind. A Reviewer
that cannot inspect code and a Researcher that cannot gather fresh information
do not justify their overhead.

### 1A. Reviewer grounding

The Reviewer should become a real read-only quality gate.

Add to the `reviewer` recipe:

- `list_workspace_files`
- `read_workspace_file`
- `git_status`
- `git_diff`

Keep out:

- `write_workspace_file`
- `patch_file`
- `workspace_execute`
- `git_commit`

Principle: the Reviewer can inspect everything relevant to the change, but it
cannot mutate the workspace.

### 1B. Researcher repo grounding

The Researcher should at minimum be able to inspect the project it is trying
to reason about.

Add to the `researcher` recipe:

- `list_workspace_files`
- `read_workspace_file`

This allows project-aware synthesis rather than knowledge-base echo.

### 1C. Researcher fresh-information path

The Researcher must gain a truthful way to gather fresh information.

**Preferred path (Path B):** a bounded `request_forage` tool or equivalent
synchronous Forager mediation that:

- sends a topic/domain/context request through the existing Forager service
- keeps domain trust/distrust, rate limits, egress policy, and credibility
  scoring centralized
- returns compressed, provenance-rich findings rather than raw web noise

**Fallback path (Path A):** if synchronous Forager mediation proves too slow or
too invasive for this wave, grant the Researcher direct `search_web` and
`http_fetch` access as a bounded fallback and document the tradeoff honestly.

The accepted outcome is not "the Researcher touches the network" or "the
Researcher never touches the network" as an ideology. The accepted outcome is:
the Researcher has a truthful fresh-information path, and the product keeps one
clear story for source policy and provenance.

### Seams

- `config/caste_recipes.yaml`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/runtime.py`
- existing Forager service seam via runtime

## Pillar 2: Thread-First Audit And Attribution

**Class:** Must

**Identity test:** Operators need one coherent story for a task: what the
Queen planned, what colonies did, what the Forager found, what knowledge was
used, and what the operator changed.

### 2A. Thread timeline API

Add a thread-scoped timeline endpoint:

`GET /api/v1/workspaces/{ws}/threads/{thread}/timeline?limit=50`

The timeline should be thread-first, not workspace-first. A thread maps to one
operator task; a workspace-level feed is too noisy as the primary audit
surface.

Return chronological read-model entries drawn from replay-safe truth:

- Queen planning / workflow / colony spawn events
- colony lifecycle milestones
- Forager requests and completed cycles
- knowledge creation and access relevant to the thread's colonies
- operator interventions such as directives and knowledge overlays

This is a read-model query over existing truth, not a new event stream.

### 2B. Colony audit Forager enrichment

Extend `build_colony_audit_view()` so the audit payload can answer:

- which knowledge used by this colony was Forager-sourced
- what source URL/domain/query/credibility applied when available
- whether relevant forage cycles can be linked to this colony truthfully

Important nuance: this is not purely frontend work. The existing audit payload
is too thin for the desired UI, so bounded replay-safe read-model shaping is
allowed here.

Important live seam:

- `ForageRequested` already carries `colony_id` and `thread_id`
- the current compact `ForageCycleSummary` drops that linkage at summary-build
  time even though `_on_forage_cycle_completed` still has access to the
  originating request

Wave 48 is allowed to enrich the replay-derived summary with that linkage.

### 2C. Preview response shaping

Preview already exists on both spawn paths. Verify and, if needed, enrich the
response shape so the frontend Review step can show truthful launch data:

- estimated cost
- team shape / castes
- strategy
- fast-path mode
- target files
- parallel plan shape where applicable

Do not create a second preview subsystem. Tighten the existing one if needed.

### Seams

- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_tools.py`

## Pillar 3: Connected Operator Flow

**Class:** Must

**Identity test:** Operators should not have to reconstruct the story by
clicking across disconnected surfaces and mentally joining the data.

### 3A. Thread timeline component

Build a new thread-scoped timeline component using existing visual idioms:

- chronological rows
- type badges
- expandable details
- lightweight filtering

Keep v1 simple. A good event list is better than an ambitious unfinished
dashboard.

### 3B. Upgrade the existing Review step

Do not invent a separate confirmation subsystem first.

Upgrade `frontend/src/components/colony-creator.ts` so its existing
Review/Launch step calls the real preview path and shows real launch truth
before dispatch:

- estimated cost
- team shape
- strategy
- fast path when present
- target files when present
- parallel plan summary when applicable

### 3C. Cross-surface links

Connect the new and existing surfaces:

- timeline -> colony detail
- timeline -> knowledge browser
- colony audit -> knowledge browser
- colony audit -> source URLs where truthful

The value of the timeline is not just that it renders; it must also let the
operator jump into the relevant surface.

### Seams

- `frontend/src/components/thread-timeline.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/colony-creator.ts`
- `frontend/src/components/colony-audit.ts`
- `frontend/src/components/knowledge-browser.ts`
- `frontend/src/state/store.ts`
- `frontend/src/components/formicos-app.ts` if a small route/tab hook is needed

## Pillar 4: Running-State Clarity

**Class:** Should

**Identity test:** During long-running work, operators should see more than a
round counter.

### 4A. Latest meaningful activity

Use existing replay-safe previews and event rows before inventing raw file
streaming:

- most recent meaningful action
- recent tool/test/code preview when already available
- bounded, human-readable summary in running colony detail

Prefer the Manus-style distinction:

- **notify:** non-blocking progress/status signals
- **ask:** explicit operator input or intervention moments

Wave 48 should improve notifications, not invent new blocking asks where the
directive flow already exists.

This likely needs small store/plumbing work in addition to UI composition.

### 4B. Keep it bounded

Do not jump to raw partial-file streaming in this wave. Use existing previews
and current truth first.

### Seams

- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/colony-chat.ts`
- `frontend/src/state/store.ts`

## Pillar 5: Docs, Recipes, And Demo Truth

**Class:** Must

**Identity test:** The operator and contributor guidance should match what
actually shipped, and the demo story should follow the real product path.

### 5A. Recipe truth

Update recipe guidance for:

- grounded Reviewer behavior
- grounded Researcher behavior
- whichever fresh-information path actually shipped

Also encode the minimal-colony-first rule explicitly in Queen guidance:

- default to `fast_path` / smallest viable team for simple tasks
- reserve multi-caste colonies for genuinely complex, high-dependency, or
  high-uncertainty work

Do not write a six-caste canonical story that outruns repo truth. The Forager
remains service-backed.

### 5B. Operator docs truth

Update docs for:

- thread timeline
- enriched colony audit
- real Review-step preview/confirmation
- latest meaningful activity only if it actually lands

### 5C. Demo preparation

Prepare the end-to-end operator story:

- task submission
- preview/confirm
- running-state inspection
- thread timeline walk-through
- colony audit with Forager attribution
- knowledge provenance click-through

Use real system execution, not fabricated artifacts.

### Seams

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `README.md` if a small truthful capability update is warranted
- `docs/waves/wave_48/*`

## Priority Order

| Priority | Item | Pillar | Class | Why it passes the identity test |
|----------|------|--------|-------|----------------------------------|
| 1 | Reviewer grounding | 1 | Must | A quality gate must see the real code |
| 2 | Researcher repo grounding | 1 | Must | Research should be project-aware |
| 3 | Researcher fresh-information path | 1 | Must | Fresh unknowns need a truthful path, not echo |
| 4 | Thread timeline API/read-model | 2 | Must | Operators need one coherent task story |
| 5 | Colony audit Forager enrichment | 2 | Must | Operators need provenance, not just IDs |
| 6 | Review step uses real preview | 3 | Must | Operators want to see cost/plan before launch |
| 7 | Thread timeline component + integration | 3 | Must | The audit story must be visible in-product |
| 8 | Cross-surface links | 3 | Must | Navigation makes the story usable |
| 9 | Docs and recipe truth | 5 | Must | Guidance must match shipped behavior |
| 10 | Latest meaningful activity | 4 | Should | Operators want better running-state clarity |
| 11 | Demo preparation | 5 | Must | The operator story should be demonstrable |

## Team Assignment

### Team 1: Backend Enrichment + Fresh-Info Path

Owns Pillar 1 code seams and Pillar 2 backend seams.

Primary files:

- `src/formicos/surface/routes/api.py`
- `src/formicos/surface/projections.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/engine/tool_dispatch.py`
- `src/formicos/engine/runner.py`
- `src/formicos/surface/runtime.py` if the fresh-info path needs runtime wiring

This team keeps the backend/read-model story honest and owns the preferred
Forager-mediated research path if it lands.

### Team 2: Frontend Flow + Integration

Owns Pillar 3 and Pillar 4.

Primary files:

- `frontend/src/components/thread-timeline.ts`
- `frontend/src/components/thread-view.ts`
- `frontend/src/components/colony-creator.ts`
- `frontend/src/components/colony-audit.ts`
- `frontend/src/components/colony-detail.ts`
- `frontend/src/components/knowledge-browser.ts` if navigation/filter plumbing
  is needed
- `frontend/src/state/store.ts`
- `frontend/src/components/formicos-app.ts` only if a small route/tab hook is
  truly needed

This team does not rebuild existing surfaces. It connects them.

### Team 3: Recipes + Docs Truth

Owns Pillar 1 recipe changes and Pillar 5.

Primary files:

- `config/caste_recipes.yaml`
- `AGENTS.md`
- `CLAUDE.md`
- `docs/OPERATORS_GUIDE.md`
- `README.md` only if warranted
- `docs/waves/wave_48/*`

This team grounds the Reviewer/Researcher recipes and keeps the docs aligned
with what Teams 1 and 2 actually ship.

## Overlap Management

- `config/caste_recipes.yaml` is Team 3 owned. Team 1 does not touch it.
- `src/formicos/engine/tool_dispatch.py` and `src/formicos/engine/runner.py`
  are Team 1 owned in Wave 48 because the only expected changes there relate to
  the fresh-information path.
- `src/formicos/surface/queen_tools.py` is Team 1 owned; Team 2 consumes the
  preview shape in the frontend but does not edit the backend preview path.
- `frontend/src/state/store.ts` is Team 2 owned.

## What Wave 48 Does Not Include

- No new event types.
- No Forager-as-full-caste rewrite.
- No natural-language-only control redesign.
- No ambient CI monitoring subsystem.
- No meta-learning or self-orchestration optimization layer.
- No cross-workspace global knowledge transfer yet.
- No raw partial-file streaming.
- No benchmark-specific code paths.

## Smoke Test

1. Reviewer can inspect real workspace truth without gaining write power.
2. Researcher can inspect the project structure/files.
3. Researcher has a truthful fresh-information path, with the chosen design
   documented honestly.
4. Thread timeline API returns chronological thread-scoped entries.
5. Timeline entries include colony, Forager, knowledge, and operator actions
   where available.
6. Colony audit payload marks Forager-sourced knowledge and shows provenance
   fields where truthfully available.
7. The creator Review step calls real preview support and shows actual launch
   data before dispatch.
8. Thread timeline renders in-product and links to colony detail / knowledge
   browser.
9. Running colonies show more than just round X / maxRounds if Pillar 4 lands.
10. Docs match what actually shipped and what deferred.
11. Event union remains at 62.
12. Full CI remains clean.

## Post-Wave Validation

Wave 48 is not the full measurement wave, but it changes a major confound:
caste grounding.

The follow-on measurement matrix after Wave 48 should explicitly isolate:

- old castes vs grounded castes
- fast path vs colony
- knowledge off vs on
- foraging off vs on

Without that ablation, a rising or flat compounding curve will be hard to
interpret honestly.

## After Wave 48

After Wave 48, FormicOS should be:

- more legible to operators
- more honest about what each specialist can actually do
- better connected across thread, colony, Forager, and knowledge surfaces

The next major move after the Wave 48 / measurement cycle is not "more
orchestration." It is conservative cross-workspace knowledge transfer with
clear scope and promotion rules.

**empower -> deepen -> harden -> forage -> complete -> prove -> fluency -> operability**
