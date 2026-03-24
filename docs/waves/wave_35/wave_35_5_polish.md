# Wave 35.5 -- Orchestrator Dispatch: Surface Alignment

## Context

Wave 35 landed the self-maintaining colony: parallel planning, autonomy
levels, knowledge distillation, operator directives, per-workspace weights,
mastery restoration, and explainable decisions. 55 event types. Full
self-maintenance dispatch engine.

The architecture is extraordinary. The surface is embarrassing.

A frontend audit reveals:
- `queen-overview.ts` lines 56, 86, 149: still frames the system around
  `skillBankStats` and "skills" badges. The actual system is about knowledge
  entries with confidence tiers, decay classes, co-occurrence clusters, and
  federation provenance.
- `formicos-app.ts` line 475, 545: passes `skillBankStats` to queen-overview
  and settings-view. Zero references to proactive briefing, directives,
  workflow-view, or maintenance posture.
- `proactive-briefing.ts`: a 9KB component that is defined as
  `fc-proactive-briefing` but never used in any other component. Orphaned.
- `directive-panel.ts`: a 4.4KB component defined as `fc-directive-panel`.
  Never referenced elsewhere. Orphaned.
- `workflow-view.ts`: a 4.7KB component defined as `fc-workflow-view`.
  Never referenced elsewhere. Orphaned.
- `federation-dashboard.ts`: 8.7KB, also unreferenced from any parent.
- `thread-view.ts` lines 194-229: has its own inline workflow rendering
  (simple step list) that doesn't use fc-workflow-view or show the parallel
  DAG from Wave 35.
- `settings-view.ts` line 25: still carries SkillBankStats type.

Summary: 4 major capability components built but never wired into the app
shell. The main operator experience says "skills" in a system that has
knowledge entries, confidence evolution, proactive intelligence, federation,
self-maintenance, and parallel orchestration.

This is NOT a cosmetic problem. It means:
- The proactive briefing (7 deterministic insight rules, self-maintenance
  trigger) is invisible to operators
- Operator directives (4 types, urgent/normal) have no delivery surface
- Parallel planning DAG visualization exists but is unreachable
- Federation health dashboard exists but is unreachable
- Self-maintenance posture (autonomy level, budget, active colonies) has
  no surface at all

Use 3 parallel coder teams. Budget: 1-2 sessions each.

## Constraint

This is surface alignment, not a Wave 36 preview. The three rules:
1. No new backend architecture. No new events. No new models.
2. Every change makes an EXISTING component visible, not builds a new one.
3. Frontend-only changes plus minimal backend support (e.g., a REST endpoint
   that returns data already in projections).

## Context Documents

Read before dispatching coders:
- frontend/src/components/formicos-app.ts (app shell, routing, state)
- frontend/src/components/queen-overview.ts (main landing, stale skills refs)
- frontend/src/components/proactive-briefing.ts (orphaned component)
- frontend/src/components/directive-panel.ts (orphaned component)
- frontend/src/components/workflow-view.ts (orphaned component)
- frontend/src/components/federation-dashboard.ts (orphaned component)
- frontend/src/components/thread-view.ts (inline workflow, doesn't use DAG)
- frontend/src/components/settings-view.ts (stale SkillBankStats)
- docs/design-system-v4.md (component conventions, CSS variables)

---

## Team 1: Command Center Cleanup

Rename the stale vocabulary and surface the proactive briefing + maintenance
posture on the main operator landing page.

### Task 1a: Kill "skills" / "skill bank" terminology

Every reference to "skills" and "skillBankStats" in the primary operator
surfaces must become "knowledge entries" or just "knowledge." This is a
vocabulary change, not a data model change -- the backend already uses
"knowledge entries" everywhere.

**queen-overview.ts:**
- Line 31: `.skills-badge` CSS class -> `.knowledge-badge`
- Line 34: `.skill-stats` CSS class -> `.knowledge-stats`
- Line 56: `skillBankStats: SkillBankStats` property -> `knowledgeStats`
  (or whatever the projection already provides -- check what data is
  available from the WebSocket state). If the backend still sends a
  `skillBankStats` key, the rename is in the rendering only (map the
  property, don't break the WS contract).
- Line 86-88: "X skills" -> "X entries" and "avg confidence" stays
  (it's already correct)
- Line 149, 159: "skills extracted" badge -> "knowledge extracted" badge

**settings-view.ts:**
- Line 25: SkillBankStats type reference -> update to match queen-overview

**formicos-app.ts:**
- Lines 475, 545: `.skillBankStats` prop passing -> rename to match

**Search for any other "skill" references in the component directory:**
```bash
grep -rn "skill" frontend/src/components/*.ts
```
Replace ALL instances in user-facing text. Preserve references in code
comments that document historical context ("formerly called skills").

### Task 1b: Surface proactive briefing on queen-overview

The `fc-proactive-briefing` component exists and renders a list of
KnowledgeInsight objects sorted by severity with action buttons. It just
needs to be placed in the operator's main view.

**In queen-overview.ts:**

Add `fc-proactive-briefing` as the FIRST content section, above the colony
list. The briefing is the operator's "what needs attention" signal and
should be the first thing they see.

```html
<!-- Above the existing colony cards section -->
<fc-proactive-briefing
  .insights=${this.briefingInsights}
  .workspaceId=${this.currentWorkspaceId}
></fc-proactive-briefing>
```

The data source: check if the proactive briefing data is already available
in the WebSocket state snapshot. If not, add a lightweight fetch from the
`/api/v1/workspaces/{id}/briefing` REST endpoint (already exists from
Wave 34 B2) on workspace change. Cache it. Refresh on a 60-second interval
or on relevant AG-UI events (KNOWLEDGE_EXTRACTED, CONFIDENCE_UPDATED,
MAINTENANCE_COLONY_SPAWNED).

If the briefing has zero insights, the component should show a single-line
"Knowledge system healthy -- no issues detected" rather than an empty space.

### Task 1c: Add maintenance posture card

The operator needs to see their workspace's autonomy level, active
maintenance colonies, and daily budget consumption at a glance. This is
NOT a new component -- it's a small card in the queen-overview.

Add a "Maintenance" card in the queen-overview stats area (near the
existing resource meters at lines 99-101):

```html
<div class="maintenance-posture">
  <span class="label">Maintenance</span>
  <span class="value">${this.autonomyLevel}</span>
  <span class="detail">
    ${this.activeMaintenanceColonies} active
    | $${this.dailyBudgetUsed.toFixed(2)}/$${this.dailyBudgetLimit.toFixed(2)}
  </span>
</div>
```

Data comes from the workspace projection's MaintenancePolicy. Available
via the same WebSocket state or REST endpoint.

### Acceptance criteria:
- Zero references to "skills" or "skill bank" in user-facing text across
  all primary operator surfaces (queen-overview, settings-view, formicos-app)
- `fc-proactive-briefing` rendered in queen-overview, above colony cards
- Briefing shows insights sorted by severity with action buttons
- Empty briefing shows "healthy" message (not blank space)
- Maintenance posture (level, active colonies, budget) visible on landing
- No new backend endpoints (use existing REST + WebSocket data)
- Lit components compile, render, pass any existing frontend tests

---

## Team 2: Orchestration Legibility

Make the parallel planning DAG and workflow execution visible and
understandable in the main operator flow.

### Task 2a: Wire fc-workflow-view into thread-view

`thread-view.ts` currently renders workflow steps as a simple inline list
(lines 194-229). The `fc-workflow-view` component exists with proper DAG
rendering (grouped tasks, arrows, truncated reasoning at line 88) but
is never used.

Replace the inline workflow rendering in thread-view with fc-workflow-view.
The thread projection already has `active_plan` and `parallel_groups` data
(stored by the ParallelPlanCreated projection handler from Wave 35).

```html
<!-- Replace the inline workflow-checklist section (lines 204-228) -->
${this.threadData?.active_plan
  ? html`<fc-workflow-view
      .plan=${this.threadData.active_plan}
      .parallelGroups=${this.threadData.parallel_groups}
      .colonies=${this.activeColonies}
    ></fc-workflow-view>`
  : this._renderSimpleWorkflowSteps()  /* fallback for threads without plans */
}
```

Keep the simple step rendering as a fallback for threads that predate
parallel planning or that don't have a DelegationPlan.

### Task 2b: Enrich workflow-view with live progress cues

The current `fc-workflow-view` (4.7KB) shows grouped tasks and arrows but
is sparse. Add three things without a rewrite:

**Queen reasoning display:** The DelegationPlan has a `reasoning` field.
Show it as a collapsible section above the DAG: "Queen's reasoning: Chose
to run research and schema in parallel because they have no data dependency.
Research results will feed into the implementation colony."

**Live colony status per node:** Each node in the DAG should show the
colony's current status (spawned/running/completed/failed) with a small
color indicator. Green dot for completed, pulsing blue for running, red
for failed, gray for not yet started.

**Cost and knowledge annotations:** Each completed node should show token
cost and entries extracted (if any). Both are available on the colony
projection.

### Task 2c: Surface active plans on queen-overview

When any thread in the current workspace has an active parallel plan, show
a compact "Active Plans" section on the queen-overview. This makes multi-
colony orchestration visible even when the operator isn't in a specific
thread view.

```html
${this.activePlans.length > 0 ? html`
  <div class="active-plans">
    <span class="section-title">Active Plans</span>
    ${this.activePlans.map(plan => html`
      <div class="plan-summary">
        <span class="thread-name">${plan.threadName}</span>
        <span class="group-progress">${plan.completedGroups}/${plan.totalGroups} groups</span>
        <span class="colony-status">${plan.runningColonies} running</span>
      </div>
    `)}
  </div>
` : nothing}
```

### Acceptance criteria:
- Thread view shows fc-workflow-view (DAG) for threads with active plans
- Thread view falls back to simple step list for legacy threads
- Workflow DAG shows Queen's reasoning (collapsible)
- DAG nodes show live colony status (color indicators)
- Completed nodes show cost + extracted entries
- Active plans visible on queen-overview landing page
- Lit components compile and render

---

## Team 3: Operator Steering Surface + Outcome Foundation

Wire the directive panel into the colony execution experience and lay
the silent outcome tracking foundation.

### Task 3a: Surface directive panel in colony-detail

`fc-directive-panel` exists with a directive type selector, priority
toggle, and content field. It needs to appear in the colony execution
view so operators can steer running colonies.

**In colony-detail.ts:**

Add `fc-directive-panel` to the running colony view. It should appear
when the colony status is "running" (not for completed or failed). Place
it below the round history and above the artifacts section.

```html
${this.colonyData?.status === 'running' ? html`
  <fc-directive-panel
    .colonyId=${this.colonyData.id}
    @directive-sent=${this._onDirectiveSent}
  ></fc-directive-panel>
` : nothing}
```

The `_onDirectiveSent` handler should call the `chat_colony` MCP tool
(or the WebSocket equivalent) with the directive_type and priority from
the panel's event payload.

### Task 3b: Surface directive panel in queen-chat

The Queen chat is where most operator interaction happens. When the Queen
has spawned colonies, the operator should be able to send directives from
the chat panel without navigating to colony-detail.

**In queen-chat.ts:**

Add a small "Send Directive" button that expands the directive panel
inline. This is a secondary surface (colony-detail is primary) for quick
steering without navigation.

### Task 3c: Add silent ColonyOutcome projection (backend)

This is the Wave 36 data foundation. Derive outcome metrics from existing
events -- NO new events needed.

**In surface/projections.py**, add a `ColonyOutcome` derived view computed
from existing colony events:

```python
@dataclass
class ColonyOutcome:
    colony_id: str
    workspace_id: str
    thread_id: str
    succeeded: bool
    total_rounds: int
    total_cost: float
    duration_ms: int
    entries_extracted: int
    entries_accessed: int
    quality_score: float  # from ColonyQualityScored if available
    caste_composition: list[str]
    strategy: str
    maintenance_source: str | None  # from tags if maintenance colony
```

Compute from: ColonySpawned + ColonyCompleted + TokensConsumed +
MemoryEntryCreated + KnowledgeAccessRecorded + ColonyQualityScored.
Store as `colony_outcomes: dict[str, ColonyOutcome]` on ProjectionStore.

This is a read model computed from existing events. No new events. No new
API endpoints (yet -- Wave 36 will surface this data). The projection
exists silently, ready for Wave 36's command center to consume.

### Task 3d: Update demo docs for new surface reality

The demo scenarios from Wave 34 (docs/demos/) reference the old UI. Update
them to reflect:
- Proactive briefing visible on landing page
- Directive panel available during colony execution
- Workflow DAG visible in thread view
- Maintenance posture visible
- Knowledge vocabulary (not "skills")

This is a doc-only change. No code.

### Acceptance criteria:
- Directive panel visible in colony-detail when colony is running
- Directive panel accessible from queen-chat during active colonies
- Directive send dispatches to chat_colony with directive_type
- ColonyOutcome projection computed from existing events
- Colony outcomes dict populated after colony completions
- Demo docs reference updated UI surfaces
- Lit components compile and render
- pytest clean, pyright clean for backend projection changes

---

## Integration check (after all 3 teams)

- Open the app. Land on queen-overview. Verify:
  - Zero "skills" or "skill bank" text visible
  - Proactive briefing section present (with insights or "healthy" message)
  - Maintenance posture card shows autonomy level + budget
  - Active plans section shows any running parallel workflows
- Navigate to a thread with a parallel plan. Verify:
  - fc-workflow-view renders the DAG (not just a step list)
  - Queen reasoning is visible (collapsible)
  - Colony nodes show live status
- Navigate to a running colony. Verify:
  - Directive panel visible below round history
  - Can send a CONTEXT_UPDATE directive
  - Directive appears in colony's AG-UI stream
- Check queen-chat. Verify:
  - "Send Directive" button appears when colonies are running
- Run full test suite:
  - `ruff check src/`
  - `pyright src/`
  - `lint_imports.py`
  - `pytest`
  - Frontend build compiles without errors
