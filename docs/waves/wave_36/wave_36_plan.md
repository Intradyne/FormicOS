# Wave 36 Plan -- The Glass Colony

**Wave:** 36 -- "The Glass Colony"
**Theme:** The first version you'd proudly post on GitHub. Every capability from Waves 33-35 becomes visible, demoable, and compelling in a single session. A new user lands, creates a demo workspace, watches the system plan in parallel with visible reasoning, sees knowledge extract with confidence annotations, watches a contradiction get resolved autonomously, and understands what FormicOS is -- all within 10 minutes. The backend gains colony performance intelligence and scheduled knowledge refresh. The frontend gains a polished command center, a guided demo path, and visual cohesion.

**Prerequisite:** Wave 35.5 landed (accepted with follow-up debt). Surface alignment complete: proactive briefing visible on landing, workflow DAG in thread view, directive panel in colony-detail, maintenance posture and federation health cards on queen-overview, stale "skills" vocabulary eliminated. ColonyOutcome projection collecting silently. 2,119 tests passing.

**Follow-up debt from 35.5 (absorbed into this wave):**
- queen-chat.ts `runningColonies` prop not wired at either mount point (formicos-app.ts:551, queen-overview.ts:198). The directive toggle never appears in queen-chat. Fix: one-line wiring at each mount point.
- Maintenance posture card shows policy (autonomy level, max colonies, budget limit) but not consumption (spent-vs-limit). Fix: derive daily spend from ColonyOutcome projection.

**Critical runtime debt (discovered in live testing):**
- Governance engine cannot distinguish 'task solved, agent repeating itself' from 'agent genuinely stuck.' A colony that solves a coding task in round 1 via successful code_execute (exit=0) then gets force-halted as failed with quality_score=0.0 because rounds 2-6 show stability=1.0 + progress<0.01. This poisons ColonyOutcome, outcome badges, performance insights, and operator trust. Fix: treat successful code_execute + stable output as convergence evidence, not stall evidence. This is a Wave 36 prerequisite.

**Contract changes:** No new event types (union stays at 55). ColonyOutcome data surfaced via new REST endpoint. Scheduled maintenance triggers extend existing dispatcher. Colony performance insights extend ProactiveBriefing. One possible ADR (047) for outcome metrics retention policy.

---

## Why this wave

After 35.5, a returning operator sees a system that tells the truth. Proactive briefing at the top, active plans below, maintenance posture and federation health visible. But a first-time visitor -- someone arriving from GitHub, evaluating FormicOS, or watching a demo -- still faces a wall. They see a dashboard with no narrative. Colony cards with no context for why they exist. A knowledge browser with no explanation of why it matters. There's no "start here" experience that reveals the system's capabilities in a coherent sequence.

Wave 36 builds the story. The guided demo path is the centerpiece: a prepared workspace with seeded knowledge (including a deliberate contradiction), pre-configured self-maintenance, and a suggested task. The operator drives, the system performs, and a lightweight annotation layer explains what just happened at each step. Every capability from Waves 33-35 participates. The demo is real execution, not simulation.

The backend half activates what 35.5 collected. The ColonyOutcome projection has been silently deriving metrics. Wave 36 surfaces those metrics as outcome badges on colony cards and performance insights in the Queen's briefing. Scheduled knowledge refresh extends the maintenance dispatcher with time-based triggers. These make the system visibly self-aware about its own operational health.

---

## Track A: Command Center + Colony Intelligence

### A0. Absorb 35.5 debt (prerequisite for everything else)

Two small fixes before any Track A work begins.

**Wire runningColonies into queen-chat:** At both mount points where `fc-queen-chat` is rendered, pass the list of running colonies so the directive toggle actually appears.

In `formicos-app.ts` at line 551:
```html
<fc-queen-chat
  ...existing props...
  .runningColonies=${this._getRunningColonies()}
></fc-queen-chat>
```

In `queen-overview.ts` at line 198:
```html
<fc-queen-chat
  ...existing props...
  .runningColonies=${this._getRunningColonies()}
></fc-queen-chat>
```

The `_getRunningColonies()` helper filters the colony list for `status === 'running'` and maps to `{id, name}`. ~5 lines per file.

**Wire maintenance budget consumption into posture card:** The maintenance posture card (queen-overview.ts:310) currently shows the policy budget limit but not how much has been spent today. The `ColonyOutcome` projection (from 35.5 Track C) has the cost data. Sum costs for maintenance colonies spawned today and display as `$X.XX / $Y.YY` instead of just `$Y.YY`.

**Wire `@send-colony-message` on the queen-overview mount:** The queen-overview mount in `formicos-app.ts` (lines 470-492) handles `@navigate`, `@approve`, `@deny`, `@send-message` and others but does NOT forward `@send-colony-message`. The directive panel in queen-chat fires `send-colony-message` events that bubble up through queen-overview, but formicos-app never catches them on that mount. The handler already exists at line 505 (on `fc-colony-detail`). Add the same handler to the queen-overview mount. Without this, the directive toggle appears but sending a directive silently does nothing.

**Wire maintenance budget consumption into posture card:** The maintenance posture card (queen-overview.ts:310) currently shows the policy budget limit but not how much has been spent today. The `ColonyOutcome` projection (from 35.5 Track C) has the cost data. Sum costs for maintenance colonies spawned today and display as spent/limit.

**A0c. Governance convergence detection (prerequisite for demo path)**

In `engine/runner.py`, the governance engine treats `stability >= threshold AND progress < threshold` as a stall signal, leading to force-halt with `succeeded=false`. This is correct for genuinely stuck colonies but wrong for colonies that solved their task and have nothing left to do.

Fix: when evaluating the stall condition, also check whether the most recent round included a successful `code_execute` (exit_code == 0). If the round has at least one successful execution AND outputs are stable AND no newer failing execution contradicts the success, reclassify from `stall` to `converged`. Converged colonies get `ColonyCompleted` with `succeeded=true`.

This is NOT 'any exit=0 equals completion.' The conditions are:
- at least one code_execute with exit_code == 0 in the current or recent round
- outputs are stable / repeated (the existing stability check)
- no subsequent failing execution contradicts the success

Scope: Signal 1 only (governance-side detection). Signal 2 (explicit agent completion tool) is stretch / 36.5.

All four A0 fixes are prerequisites. Resolve before other Track A work begins.

### A1. Command center visual hierarchy

Wave 35.5 wired the right components into queen-overview but the layout is flat -- briefing, posture cards, active plans, and colony cards all stack with equal visual weight. Wave 36 creates a clear hierarchy.

**Layout:**

```
+-----------------------------------------------+
| PROACTIVE BRIEFING (full width, top)           |
| Top 3 insights by severity. Action buttons.    |
| "Knowledge system healthy" when empty.         |
+-------------------+---------------------------+
| ACTIVE WORK       | SYSTEM HEALTH             |
| Active plans (DAG) | Knowledge pulse           |
| Running colonies   | - 247 entries, avg 68%    |
| Pending approvals  | - 12 created / 3 merged   |
|                    |   / 1 distilled in 24h    |
|                    | Maintenance posture       |
|                    | Federation health         |
+-------------------+---------------------------+
| RECENT COMPLETIONS                             |
| Colony cards with outcome badges               |
+-----------------------------------------------+
```

The current queen-overview already has all these sections from 35.5. The change is:
- Group them into the three-row layout (briefing / active+health / history)
- Add a "Knowledge Pulse" summary replacing the old one-line stats: entries created, merged, distilled, and decayed in the last 24 hours, derived from the event stream or projections
- Colony cards in "Recent Completions" gain outcome badges (see A2)
- Active plans section from 35.5 (line 390) gets promoted to the left column alongside running colonies

This is a CSS layout restructure + data wiring, not a component rewrite. The queen-overview.ts file is 13.7 KB and well-organized after 35.5's changes.

### A2. Colony outcome metrics surfaced

The `ColonyOutcome` projection from 35.5 has been collecting data silently. Surface it.

**Colony cards get outcome badges:** In the queen-overview colony card rendering (and colony-detail header), show quality, cost, and extraction count for completed colonies:

```html
<div class="outcome-badges">
  <span class="quality-badge">Quality: ${(outcome.quality_score * 100).toFixed(0)}%</span>
  <span class="cost-badge">$${outcome.total_cost.toFixed(2)}</span>
  <span class="extraction-badge">${outcome.entries_extracted} extracted</span>
</div>
```

**Colony detail "Outcome" section:** Add a section to colony-detail.ts (42 KB, the largest component) for completed colonies showing:
- Quality score with context ("3 entries extracted, 2 reached HIGH confidence within 48h")
- Token efficiency (total cost / entries extracted, compared to workspace average)
- Knowledge impact: which entries were created, their current confidence tier, whether subsequent colonies accessed them
- Maintenance flag: if tagged `["maintenance"]`, show which insight triggered it and whether the insight cleared

**REST endpoint:**
```
GET /api/v1/workspaces/{id}/outcomes?period=7d
```
Returns aggregated ColonyOutcome stats. Period: 24h, 7d, 30d. Used by the command center's knowledge pulse and by the Queen's performance briefing. Data source: `projections.colony_outcomes` dict (already populated from 35.5).

### A3. Queen performance briefing

Extend `proactive_intelligence.py` with colony performance insight rules. Same pattern as knowledge insights: deterministic, no LLM, pure projection queries.

**4 new rules analyzing ColonyOutcome data:**

| Signal | Condition | Insight |
|--------|-----------|---------|
| Strategy efficiency | Stigmergic completes > 20% faster than sequential for 3+ agent colonies (>= 5 data points per strategy) | "Stigmergic strategy is 23% faster for complex tasks" |
| Diminishing rounds | Quality delta < 5% for last 2 rounds in colonies with max_rounds > N (>= 3 data points) | "Quality plateaus after round 4 for researcher colonies" |
| Cost outlier | Colony cost > 3x workspace average for similar caste composition | "Colony X cost $4.20 -- 3.2x your average coder+reviewer colony" |
| Knowledge ROI | Entries extracted in last 7 days with 0 subsequent accesses | "12 entries extracted this week, none reused -- extraction may be too granular" |

The Queen sees these alongside knowledge insights in her briefing injection (queen_runtime.py). She can reference them: "Using stigmergic strategy because performance data shows 23% faster completion for this type of task."

These are **recommendations, not automation.** The Queen decides whether to follow them. No automatic configuration changes. This is the "interpret" layer. Wave 37's Experimentation Engine adds "act."

### A4. Scheduled knowledge refresh

Extend the maintenance dispatcher with time-based triggers. Same autonomy levels from ADR-046 apply.

**Three scheduled triggers:**

**Approaching staleness:** Stable-decay entries whose projected alpha will cross the LOW threshold within 30 days. Produces a KnowledgeInsight with SuggestedColony for re-validation.

**Domain health check:** Domains with no new entries in 60+ days. Produces a coverage-style insight recommending a lightweight research colony.

**Distillation refresh:** Distilled entries whose source cluster has grown (new entries co-occurring with the cluster post-distillation). Recommends re-synthesis.

Implementation: 3 new rule functions in `proactive_intelligence.py`, producing KnowledgeInsight objects with SuggestedColony data. Wired through the existing MaintenanceDispatcher in `surface/self_maintenance.py` (NOT `surface/maintenance.py`). No new events -- maintenance colonies spawn via existing ColonySpawned with tags. ~100 LOC total.

### Track A files

| File | Changes |
|------|---------|
| `frontend/src/components/formicos-app.ts` | Wire runningColonies to queen-chat (line 551) |
| `frontend/src/components/queen-overview.ts` | Wire runningColonies (line 198), three-row layout, knowledge pulse, outcome badges, maintenance consumption |
| `frontend/src/components/colony-detail.ts` | Outcome section for completed colonies |
| `surface/routes/api.py` | `/workspaces/{id}/outcomes` endpoint |
| `surface/proactive_intelligence.py` | 4 performance rules + 3 scheduled refresh rules |
| `surface/self_maintenance.py` | Scheduled trigger integration with MaintenanceDispatcher |
| `engine/runner.py` | A0c: governance convergence detection (stall vs converged reclassification) |
| `surface/queen_runtime.py` | Performance insights in Queen briefing injection |

---

## Track B: Guided Demo Path + Public Narrative

### B1. Guided first-run demo experience

The centerpiece. An in-app experience that walks a new operator through one thread showing every major capability. Real execution, not simulation.

**Demo workspace template** (`config/templates/demo-workspace.yaml`):
- 8-10 pre-seeded knowledge entries across 2 domains ("Python API patterns" and "authentication")
- Varying confidence tiers: 3 HIGH, 3 MODERATE, 2 EXPLORATORY
- Varying decay classes: 2 stable, 6 ephemeral
- One deliberate contradiction: Entry A (HIGH, verified) says "use JWT for stateless auth," Entry B (HIGH, verified) says "use session cookies for security-sensitive auth" -- both correct in context but flagged as contradiction by the proactive intelligence rules
- Maintenance policy: `auto_notify` with `auto_actions: ["contradiction"]`
- Federation: disabled (too complex for first demo)

**The demo flow:**

Step 1 -- "Try the Demo" button on the Queen landing page (queen-overview.ts), accessible via a prominent card in the system health column or from a help menu. Note: the true no-workspace state renders through the startup shell in formicos-app.ts (line 388-458), which is a transient bootstrap screen. The demo button belongs on queen-overview (after bootstrap completes), not the startup shell. If the operator already has workspaces, the button appears as a secondary option.

Step 2 -- Proactive briefing immediately shows the seeded contradiction: "Knowledge conflict: Entry A says JWT for auth, Entry B says session cookies for auth. Both high-confidence. Action: Investigate." The operator sees the system has opinions before they've done anything.

Step 3 -- Suggested task as placeholder text in queen-chat: "Build me an email validator with unit tests." Operator sends it. Queen generates a DelegationPlan visible in the workflow DAG. Parallel groups visible. Queen explains why she chose this decomposition.

Step 4 -- Colonies execute. DAG nodes pulse blue (running), turn green (completed). Cost accumulator ticks. Knowledge extracts -- new entries appear in the knowledge browser with confidence tier annotations (EXPLORATORY for brand new). Operator can hover and see the score breakdown.

Step 5 -- The demo guide triggers a one-shot maintenance evaluation (deterministic, not waiting for the periodic loop). The dispatcher fires because `auto_notify` is configured. Spawns a research colony to investigate the contradiction. MAINTENANCE_COLONY_SPAWNED notification visible. The research colony runs and resolves the contradiction. Briefing updates -- the insight clears. The operator sees the system maintaining itself.

Step 6 -- A completion card summarizes: "FormicOS planned 3 colonies (2 in parallel), extracted N knowledge entries, detected and resolved 1 contradiction autonomously. The Queen explained every decision along the way." Links to deeper documentation.

**Demo guide component** (`frontend/src/components/demo-guide.ts`, ~250 LOC):

Not a modal wizard. A compact, persistent annotation bar that appears below the proactive briefing during the demo. It shows the current step ("Step 3: Watch the Queen plan") with a one-sentence description of what to look at. It advances automatically based on AG-UI events (ParallelPlanCreated -> advance to Step 4, ColonyCompleted -> advance to Step 5, MAINTENANCE_COLONY_SPAWNED -> advance to Step 5, etc.). The operator can dismiss it at any time.

**Backend support:**
```
POST /api/v1/workspaces/create-demo
```
Creates workspace from demo template. Returns workspace_id. Emits standard workspace creation events. No special demo mode in the backend -- the demo workspace is a real workspace with seeded data.

### B2. Orchestration visualization polish

Wave 35.5 wired the DAG. Wave 36 polishes it for demo readability.

**In workflow-view.ts (4.7 KB post-35.5):**
- Group labels: "Group 1: Research" / "Group 2: Implementation" (derived from the task descriptions in the plan)
- Animated state transitions: nodes fade from gray to pulsing-blue on spawn, fill green on completion, flash red on failure
- Dependency arrows: dashed while waiting, solid while active, annotated with "input_from" when dependencies exist
- Running cost accumulator at the bottom of the DAG
- Elapsed time per group and total
- Compact mini-DAG for queen-overview's "Active Plans" section (nodes as colored dots, arrows as lines, status as dot color). Clicking navigates to the full thread view.

### B3. README and public narrative

The current README (8 KB, recently updated in 35.5) is a solid technical description. Wave 36 restructures it for the "first 60 seconds" experience.

**README.md restructure:**

1. **One-paragraph elevator pitch** (rewrite first paragraph to lead with the operator experience, not the stigmergy theory)
2. **30-second GIF** -- the demo flow compressed into an animated screenshot (created from an actual demo run, not mocked)
3. **"What makes it different"** -- 4 bullets, each connecting a capability to a visible experience:
   - "Plans work in parallel and shows you why" (link to DAG screenshot)
   - "Extracts and maintains institutional knowledge" (link to knowledge browser)
   - "Detects problems and fixes them" (link to self-maintenance screenshot)
   - "Explains every decision" (link to score breakdown screenshot)
4. **Architecture overview** -- keep the existing 4-layer diagram
5. **Getting started** -- keep existing docker compose flow, add "Try the Demo" as step 1 after launch
6. **Capability matrix** -- existing content, with links to ADRs

**Screenshots directory** (`docs/screenshots/`): Annotated screenshots from the demo flow. Each has a caption. These illustrate the README and provide the demo-guide component's visual reference.

**CHANGELOG.md**: Narrative changelog covering the Wave 33-36 arc. Not a commit log -- the story of how FormicOS gained intelligence, federation, self-maintenance, and transparency.

### Track B files

| File | Changes |
|------|---------|
| `config/templates/demo-workspace.yaml` | NEW: seeded entries, contradiction, maintenance policy |
| `frontend/src/components/demo-guide.ts` | NEW (~250 LOC): persistent annotation bar for demo flow |
| `frontend/src/components/workflow-view.ts` | Animations, group labels, cost/time, mini-DAG variant |
| `frontend/src/components/queen-overview.ts` | "Try the Demo" button, mini-DAG in active plans |
| `surface/routes/api.py` | `/workspaces/create-demo` endpoint |
| `README.md` | Restructure for first-60-seconds experience |
| `docs/screenshots/` | NEW: annotated demo screenshots |
| `CHANGELOG.md` | NEW: narrative Wave 33-36 history |

---

## Track C: Cohesion + Final Hardening

### C1. Component consistency audit

30 Lit components, built across 10 waves by different coder teams. Visual consistency pass:

**Colors:** All confidence tiers must use the same palette everywhere (knowledge-browser, colony-detail, queen-overview, workflow-view, proactive-briefing). Define canonical CSS variables if they don't exist:
```css
--confidence-high: #22C55E;
--confidence-moderate: #EAB308;
--confidence-low: #EF4444;
--confidence-exploratory: #A78BFA;
--confidence-stale: #6B7280;
```

**Empty states:** Every component that can be empty shows a meaningful message. Audit all 30 components. Common gaps: empty colony list, empty knowledge browser, empty federation dashboard, empty workflow view. Each should have a specific message ("No colonies running" not just blank space).

**Loading states:** Components that fetch data (federation summary fetch in queen-overview, outcome data) should show skeleton loading, not blank flashes.

**Typography:** All stats use `var(--f-mono)`. All labels use consistent weight. Audit for hardcoded font sizes that should use CSS variables.

### C2. Demo path integration test

The most important test in the system. If the demo breaks, the public release breaks.

```python
async def test_demo_workspace_full_flow():
    """Create demo -> briefing shows contradiction -> colonies execute ->
    knowledge extracts -> maintenance resolves contradiction."""

    # Step 1: Create demo workspace from template
    ws = await create_demo_workspace()
    assert len([e for e in projections.memory_entries.values()
                if e["workspace_id"] == ws.id]) >= 8

    # Step 2: Briefing shows the seeded contradiction
    briefing = generate_briefing(ws.id, projections)
    contradictions = [i for i in briefing.insights if i.category == "contradiction"]
    assert len(contradictions) >= 1
    assert contradictions[0].severity == "action_required"

    # Step 3: Spawn colonies via Queen (or direct API for test speed)
    # Verify knowledge extraction produces new entries
    ...

    # Step 4: Maintenance dispatcher fires for contradiction
    dispatched = await dispatcher.evaluate_and_dispatch(ws.id, briefing)
    assert len(dispatched) >= 1
    maintenance_colonies = [c for c in projections.colonies.values()
                           if "maintenance" in c.get("tags", [])]
    assert len(maintenance_colonies) >= 1

    # Step 5: After resolution, contradiction insight clears
    briefing_after = generate_briefing(ws.id, projections)
    contradictions_after = [i for i in briefing_after.insights
                           if i.category == "contradiction"]
    # May or may not clear depending on colony outcome -- verify the flow completes
```

### C3. Performance benchmarks

The demo must feel responsive. Validate:
- Command center renders in < 200ms with 50+ entries and 10+ colonies
- Proactive briefing generation (all rules) in < 100ms
- Tiered retrieval at summary tier in < 50ms
- WebSocket initial state snapshot in < 500ms
- Demo workspace creation (template expansion + seeding) in < 3s
- Full demo flow (Steps 1-6) completes in < 5 minutes wall time

### C4. Final documentation pass

Every document must be accurate, complete, and written for someone who has never seen FormicOS. This is the last pass before public release.

**CLAUDE.md:** Complete post-36 state. Colony performance insights, scheduled refresh triggers, demo workspace template, outcome REST endpoint. Every ADR referenced. Every key file path current.

**OPERATORS_GUIDE.md:** Complete operator manual including the demo walkthrough, daily operations, maintenance configuration, federation setup, directive usage, weight tuning, and troubleshooting.

**KNOWLEDGE_LIFECYCLE.md:** Full lifecycle including colony performance feedback loop, scheduled refresh triggers, distillation refresh.

**AGENTS.md:** All castes, all tools, all interaction patterns including the knowledge_feedback tool and directive handling.

**ADR index** (`docs/decisions/INDEX.md`): Single page listing all ADRs (001-046+) with one-line summaries and status. The "how did we get here" document.

### Track C files

| File | Changes |
|------|---------|
| `frontend/src/components/*.ts` | Consistency audit (colors, empty states, loading, typography) |
| `tests/integration/test_demo_flow.py` | NEW: full demo path test |
| `tests/integration/test_performance.py` | NEW: render and response benchmarks |
| `CLAUDE.md` | Final rewrite |
| `docs/OPERATORS_GUIDE.md` | Final rewrite |
| `docs/KNOWLEDGE_LIFECYCLE.md` | Final rewrite |
| `AGENTS.md` | Final rewrite |
| `docs/decisions/INDEX.md` | NEW: ADR index |

---

## File Ownership Matrix

| File | Track A | Track B | Track C |
|------|---------|---------|---------|
| `formicos-app.ts` | **MODIFY** (runningColonies wiring) | -- | -- |
| `queen-overview.ts` | **OWN** (layout, pulse, consumption, runningColonies) | "Try Demo" button, mini-DAG | -- |
| `colony-detail.ts` | **MODIFY** (outcome section) | -- | -- |
| `workflow-view.ts` | -- | **OWN** (animations, polish) | -- |
| `demo-guide.ts` | -- | **CREATE** | -- |
| `queen-chat.ts` | -- | -- | -- |
| `surface/proactive_intelligence.py` | **OWN** (7 new rules) | -- | -- |
| `engine/runner.py` | **MODIFY** (A0c convergence detection) | -- | -- |
| `surface/self_maintenance.py` | **MODIFY** (scheduled triggers in dispatcher) | -- | -- |
| `surface/routes/api.py` | **MODIFY** (outcomes endpoint) | **MODIFY** (create-demo) | -- |
| `config/templates/demo-workspace.yaml` | -- | **CREATE** | -- |
| `README.md` | -- | **OWN** | -- |
| All test/doc files | -- | -- | **OWN** |

**Overlap: queen-overview.ts** is touched by both Track A (layout + data) and Track B (demo button + mini-DAG). Split: Track A owns the layout structure, data sections, and knowledge pulse. Track B adds the "Try Demo" button (a single `html` block at the top) and the compact DAG rendering in the active plans section. Track A should land first since the layout restructure defines where Track B's additions go.

**Overlap: routes/api.py** is touched by both Track A (outcomes endpoint) and Track B (create-demo endpoint). Different route registrations, no conflict.

---

## Sequencing

**Track A starts immediately.** A0 (debt fixes) is prerequisite for the rest. A1-A4 can proceed in parallel within the track.

**Track B starts immediately but the demo guide (B1) should be last within the track.** B2 (orchestration polish) and B3 (README) can start first. The demo guide depends on the demo workspace template, which depends on knowing the exact flow. Build the template and README first, then the guide.

**Track C runs last.** The consistency audit needs to see A and B's final state. The demo integration test needs the template from B. The documentation pass needs all features landed.

**Team assignment for 3 coder teams:**
- Team 1 (Track A): Debt fixes + command center layout + outcome surfacing + performance briefing + scheduled refresh
- Team 2 (Track B): Demo template + orchestration polish + demo guide + README + screenshots
- Team 3 (Track C): Consistency audit + integration tests + performance benchmarks + final documentation

---

## What Wave 36 Does NOT Include

- **No Experimentation Engine.** Outcome data is being collected and surfaced. Wave 37 experiments against it with controlled A/B testing on colony configuration.
- **No operator behavior learning.** Wave 37 data collection, Wave 38 activation. Same collect-interpret-act cadence.
- **No federated distillation.** Single-instance distillation proven in Wave 35. Cross-instance synthesis is Wave 37+.
- **No visual workflow composition.** Canvas-based editor for drawing workflows. Future if there's demand.
- **No earned autonomy.** Autonomy levels remain operator-set per ADR-046.
- **No automatic configuration changes.** Performance insights are recommendations only. The Queen decides; the system doesn't auto-tune.

---

## Smoke Test (Post-Integration)

1. Open the app. Navigate to Queen landing page. "Try the Demo" button visible in system health area. Click it. Demo workspace created in < 3s.
2. Command center shows three-row layout: briefing at top, active work + health in middle, recent completions at bottom.
3. Proactive briefing immediately shows the seeded contradiction (severity: action_required).
4. Knowledge pulse shows "8 entries, avg confidence XX%, 0 changes in 24h" (freshly seeded).
5. Type "Build me an email validator with tests" in queen-chat. Queen generates DelegationPlan. DAG visible with group labels, reasoning collapsible.
6. Colonies execute. DAG nodes animate (gray -> blue pulse -> green). Cost accumulator ticks.
7. Colony that solves a coding task via successful code_execute is marked `completed` (not `failed`). ColonyOutcome.succeeded is true. Quality score is non-zero.
8. Colonies complete. Outcome badges appear on colony cards (quality, cost, entries extracted).
9. Colony detail shows Outcome section with token efficiency and knowledge impact.
10. Maintenance dispatcher fires. Research colony spawns (MAINTENANCE_COLONY_SPAWNED visible). Contradiction resolves. Briefing insight clears.
11. Demo guide annotation advances through steps automatically.
12. Queen-chat directive toggle appears (runningColonies now wired). Can send CONTEXT_UPDATE to a running colony from chat.
13. Maintenance posture shows consumption: "$0.24 / $1.00" (after maintenance colony).
14. Queen performance briefing shows strategy insight (if enough outcome data).
15. Scheduled refresh: create a stable entry, advance time, verify "approaching staleness" insight.
16. All confidence tiers use same colors everywhere (consistency audit).
17. All empty states show meaningful messages (consistency audit).
18. README tells the FormicOS story with demo GIF and 4 "what makes it different" bullets.
19. Demo integration test passes end-to-end.
20. Full CI: ruff, pyright, lint_imports, pytest, frontend build all clean.

---

## Priority Stack (if scope must be cut)

| Priority | Item | Track | Rationale |
|----------|------|-------|-----------|
| 1 | A0: 35.5 debt fixes | A | Blocks directive visibility and consumption display |
| 2 | B1: Guided demo experience | B | The "post on GitHub" centerpiece |
| 3 | A1: Command center layout | A | Demo needs a coherent landing page |
| 4 | B2: Orchestration viz polish | B | The DAG is the most visually distinctive feature |
| 5 | A2: Colony outcome surfacing | A | Makes the command center data-rich |
| 6 | C4: Final documentation | C | "Ship ready" means readable docs |
| 7 | B3: README + narrative | B | First thing a GitHub visitor sees |
| 8 | C1: Consistency audit | C | Professional polish |
| 9 | A3: Queen performance briefing | A | Impressive but not blocking demo |
| 10 | C2: Demo integration test | C | Ensures the demo doesn't regress |
| 11 | A4: Scheduled refresh | A | Extends existing dispatcher |
| 12 | C3: Performance benchmarks | C | Important for feel, not function |

---

## After Wave 36

FormicOS is public. The GitHub repo has a compelling README with a demo GIF, a working in-app demo that shows every capability, a command center that tells the system's story at a glance, and documentation that a new contributor can follow.

The Wave 33-36 arc is complete:
- **Wave 33:** Built the architecture (federation, CRDTs, credential scanning, co-occurrence)
- **Wave 34:** Added intelligence (tiered retrieval, proactive insights, co-occurrence scoring, agent feedback)
- **Wave 35:** Enabled autonomy (parallel planning, self-maintenance, distillation, directives, mastery restoration)
- **Wave 36:** Made it visible (command center, guided demo, outcome intelligence, public narrative)

Wave 37 picks up the learning colony: the Experimentation Engine (controlled A/B on colony configuration using Wave 36's outcome baseline), operator behavior data collection, and federated distillation. The system doesn't just maintain itself -- it improves itself.

But that's next. Wave 36 ships.
