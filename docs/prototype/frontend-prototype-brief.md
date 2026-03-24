# FormicOS v2 — Full Frontend Prototype Brief

**What this document is:** Everything a UI designer needs to build a complete, interactive React prototype for FormicOS. The prototype will be a single JSX file (like the Phase 1 prototype) that uses mock data aligned with the real backend contracts. It serves as the visual specification for the production Lit Web Components implementation.

**What the designer provides separately:** Visual style, design tokens, typography, color system, spacing, and aesthetic direction. This brief covers structure, data, views, and interactions only.

---

## 1. What FormicOS Is

FormicOS is a **local-first multi-agent AI colony operating system**. An operator talks to a **Queen** AI coordinator, which spawns **colonies** of specialist AI agents (Coder, Reviewer, Researcher, Archivist) that work together through stigmergic coordination — shared environmental signals rather than direct messaging. Agents communicate through **pheromone-weighted topology edges** that strengthen when communication is useful and decay when it isn't.

The operator's job is to **direct, monitor, and intervene**. They describe objectives, the Queen recommends a team composition, the operator launches colonies from scratch or from saved templates, monitors progress through real-time streaming events, and can kill, redirect, or adjust colonies mid-execution.

### Key mental model

```
Operator ←→ Queen (AI coordinator, always available)
                ↓
           Workspace (project scope)
                ↓
            Thread (execution context)
                ↓
            Colony (self-organizing agent team)
              ↓        ↓        ↓
           Agent    Agent    Agent
           (Coder)  (Reviewer) (Researcher)
```

Colonies execute in **rounds**. Each round has 5 phases: Goal → Intent → Route → Execute → Compress. Agents produce output, a convergence score measures progress, and the governance engine intervenes if colonies stall or diverge.

### What makes this different from a chat UI

This is NOT a chatbot. It's an **operations console** for a fleet of AI agents. The Queen is one interface, but the core experience is watching colonies work, understanding their progress, seeing which models are routing where, browsing the accumulated skill bank, managing templates, and intervening when needed. Think mission control, not Slack.

---

## 2. The Backend — Every Data Surface

### 2.1 WebSocket (primary real-time channel)

Connect to `ws://localhost:8080/ws`. The protocol is:

**Outbound (frontend → backend) — Commands:**

| Command | Purpose | Key payload fields |
|---------|---------|-------------------|
| `subscribe` | Start receiving events for a workspace | `workspaceId`, `afterSeq?` |
| `unsubscribe` | Stop receiving events | `workspaceId` |
| `send_queen_message` | Operator talks to Queen | `threadId`, `content` |
| `spawn_colony` | Create a new colony | `threadId`, `task`, `casteNames`, `strategy`, `maxRounds`, `budgetLimit`, `modelAssignments?`, `templateId?` |
| `kill_colony` | Terminate a running colony | `colonyId`, `killedBy?` |
| `create_merge` | Connect output of one colony to another | `fromColony`, `toColony` |
| `prune_merge` | Remove a merge edge | `edgeId` |
| `broadcast` | Share colony output to all siblings | `threadId`, `fromColony` |
| `approve` | Approve a pending action | `requestId` |
| `deny` | Deny a pending action | `requestId` |
| `update_config` | Change a workspace or system setting | `scope`, `targetId`, `field`, `value` |

**Inbound (backend → frontend) — Two message types:**

1. **`state` message** — Full `OperatorStateSnapshot` sent on subscribe and periodically. Contains the entire tree, all merges, queen threads, approvals, protocol status, models, castes, and config.

2. **`event` message** — Individual events streamed in real time. 27 event types (see §2.3).

### 2.2 REST Endpoints

| Endpoint | Method | Purpose | Response shape |
|----------|--------|---------|---------------|
| `/health` | GET | System health | `{status, services, uptime}` |
| `/api/v1/skills` | GET | Browse skill bank | `[{id, text_preview, confidence, conf_alpha, conf_beta, uncertainty, algorithm_version, extracted_at, source_colony}]` |
| `/api/v1/skills?sort=confidence&limit=50` | GET | Sorted/filtered skills | Same as above |
| `/api/v1/templates` | GET | List colony templates | `[{template_id, name, description, caste_names, strategy, budget_limit, max_rounds, tags, use_count, source_colony_id, version}]` |
| `/api/v1/templates` | POST | Create a template | `{template_id, name, ...}` |
| `/api/v1/templates/{id}` | GET | Template detail | Single template object |
| `/api/v1/suggest-team` | POST | AI recommends castes for an objective | Request: `{objective}`. Response: `{castes: [{caste, count, reasoning}]}` |

### 2.3 The 27 Event Types

Events stream via WebSocket. Each has `seq`, `timestamp`, `address`, and `type`. Group them by what the operator cares about:

**Colony lifecycle:** `ColonySpawned`, `ColonyCompleted`, `ColonyFailed`, `ColonyKilled`, `ColonyNamed`
**Round execution:** `RoundStarted`, `PhaseEntered`, `AgentTurnStarted`, `AgentTurnCompleted`, `RoundCompleted`
**Topology:** `MergeCreated`, `MergePruned`
**Context:** `ContextUpdated`
**Configuration:** `WorkspaceCreated`, `ThreadCreated`, `WorkspaceConfigChanged`, `ModelRegistered`, `ModelAssignmentChanged`
**Operator interaction:** `ApprovalRequested`, `ApprovalGranted`, `ApprovalDenied`, `QueenMessage`
**Cost:** `TokensConsumed`
**Skill bank:** `SkillConfidenceUpdated`, `SkillMerged`
**Templates:** `ColonyTemplateCreated`, `ColonyTemplateUsed`

### 2.4 The State Snapshot (full shape)

```typescript
{
  tree: TreeNode[]              // Workspace → Thread → Colony hierarchy
  merges: MergeEdge[]           // Cross-colony data flow edges
  queenThreads: QueenThread[]   // Conversation history with Queen
  approvals: ApprovalRequest[]  // Pending operator decisions
  protocolStatus: {
    mcp:  { status, tools }     // MCP server status
    agui: { status, events }    // AG-UI protocol status
    a2a:  { status, card }      // A2A discovery status
  }
  localModels: LocalModel[]     // GPU-loaded models
  cloudEndpoints: CloudEndpoint[] // Cloud provider status
  castes: CasteDefinition[]     // Available agent roles
  runtimeConfig: RuntimeConfig  // System + workspace + governance + routing config
}
```

---

## 3. Mock Data for the Prototype

### 3.1 Two workspaces

**Workspace "refactor-auth"** — Active development workspace
- Thread "main" with 2 colonies:
  - **"Auth Refactor Sprint"** (running, round 4/10, 3 agents: coder + reviewer + archivist, stigmergic, convergence 0.72, cost $0.38, budget $2.00)
  - **"Dependency Analysis"** (completed, round 5/5, 2 agents, convergence 0.95, cost $0.62, quality 0.81, 3 skills extracted)
- Thread "experiment" with 1 colony:
  - **"OAuth2 PKCE Spike"** (queued, not started, 1 researcher agent)
- Merge edge: Dependency Analysis → Auth Refactor Sprint (compressed output flows as context)
- 1 pending approval: Cloud escalation to opus-4.6 for coder ($0.42 est.)

**Workspace "research-ttt"** — Research workspace
- Thread "main" with 1 colony:
  - **"TTT Memory Survey"** (running, round 2/10, 2 agents: researcher + coder, convergence 0.41, cost $0.21)

### 3.2 Three LLM providers

| Provider | Models | Status |
|----------|--------|--------|
| llama-cpp (local) | Qwen3-30B-A3B Q4_K_M (loaded, 21.1GB VRAM, 2 slots, 8K ctx) | green |
| Anthropic (cloud) | claude-sonnet-4.6, claude-haiku-4.5 | connected, $0.62 spent of $10 limit |
| Gemini (cloud) | gemini-2.5-flash, gemini-2.5-flash-lite | connected, $0.04 spent |

### 3.3 Routing table (active)

| Caste | Execute phase model | Goal phase model |
|-------|-------------------|-----------------|
| queen | anthropic/claude-sonnet-4.6 | anthropic/claude-sonnet-4.6 |
| coder | anthropic/claude-sonnet-4.6 | (default) |
| reviewer | llama-cpp/gpt-4 | (default) |
| researcher | gemini/gemini-2.5-flash | (default) |
| archivist | gemini/gemini-2.5-flash | (default) |

### 3.4 Five castes

| ID | Name | Icon | Description |
|----|------|------|-------------|
| queen | Queen | ♛ | Strategic coordinator — spawns colonies, manages fleet |
| coder | Coder | ⟨/⟩ | Implementation — writes and debugs code |
| reviewer | Reviewer | ⊘ | Quality gate — reviews, verifies, flags |
| researcher | Researcher | ◎ | Information — retrieves, synthesizes, cites |
| archivist | Archivist | ⧫ | Memory — compresses, extracts skills, distills |

### 3.5 Skill bank (8-12 entries)

Mix of confidences and ages. Include:
- 2-3 high confidence skills (alpha ~15, beta ~3, conf ~0.83)
- 2-3 medium confidence (alpha ~5, beta ~4, conf ~0.56)
- 2-3 low confidence / new (alpha ~2, beta ~2, conf ~0.50)
- 1 merged skill (marked with merge badge, shows "merged from 2 skills")
- Fields per skill: `id`, `text_preview`, `confidence`, `conf_alpha`, `conf_beta`, `uncertainty`, `algorithm_version`, `extracted_at`, `source_colony`

### 3.6 Colony templates (3 presets)

| Name | Castes | Strategy | Budget | Use count | Tags |
|------|--------|----------|--------|-----------|------|
| Code Review | coder, reviewer | stigmergic | $1.00 | 12 | code, review |
| Research Sprint | researcher, archivist | stigmergic | $2.00 | 5 | research |
| Full Stack | coder, reviewer, researcher, archivist | stigmergic | $3.00 | 3 | code, research, full |

### 3.7 Queen chat history

Two threads with realistic conversation. Include:
- Operator messages (instructions, questions)
- Queen responses (status updates, strategy explanations)
- Event annotations inline (ColonySpawned, RoundCompleted, ModelRouted, PheromoneUpdate, SkillExtracted)
- Each event annotation has a `kind` tag for visual differentiation: `spawn`, `merge`, `metric`, `pheromone`, `route`

### 3.8 Round-by-round data for the running colony

For "Auth Refactor Sprint" (4 rounds), each round needs:
- Round number and phase name
- Per-agent: name, caste, model used (shows routing), tokens consumed, status, output summary (1-2 sentences)
- Tool calls made (e.g., `["memory_search", "memory_write"]`)
- Duration in ms
- Convergence score progression: 0.21 → 0.48 → 0.72 → (current)

---

## 4. Views and Layouts

### 4.1 Global Shell

**Persistent elements across all views:**

- **Left sidebar** — Tree navigation showing workspace → thread → colony hierarchy. Each colony shows status dot (running/completed/failed/queued/killed), display name, and a quality dot (green/amber/red/gray) for completed colonies. Collapsible workspace groups. Active colony highlighted.

- **Top bar** — Protocol status indicators (MCP/AG-UI/A2A), system health dot, current workspace name, and a global search or command palette trigger.

- **Queen chat panel** — Always-accessible, collapsible/expandable from the right side or bottom. Shows the conversation with the Queen for the current workspace's active thread. Operator can type messages. Queen responses stream in. Event annotations appear inline.

- **Approval badge** — If pending approvals exist, show a badge count on the top bar or sidebar. Clicking opens the approval queue.

### 4.2 Queen Overview (home/default view)

The Queen's operational dashboard. Shows:

- **Colony fleet** — All colonies across all workspaces as cards or a compact table. Each shows: display name (or UUID fallback), status badge, round progress (e.g., "R4/10"), caste icons, routing badge (colored by provider mix: green=local, blue=gemini, amber=anthropic), cost, convergence, quality score (if completed).

- **Skill bank summary** — Total skills, average confidence, recently added. Link to full skill browser.

- **Resource meters** — VRAM usage (21.1/32 GB), API spend by provider (Anthropic $X, Gemini $Y), colony count (running/queued/completed).

- **Template quick-launch** — Show the 3 most-used templates as quick-launch cards. "New Colony" button opens the creation flow.

### 4.3 Colony Detail (selected colony)

The primary monitoring view when a colony is selected. This is where the operator spends most of their time watching work happen.

**Header section:**
- Colony display name + UUID subtitle
- Status badge with color
- Task description (full text)
- Strategy badge (stigmergic/sequential)
- Template source badge (if spawned from template)
- Round progress: "Round 4 of 10" with a progress bar
- Cost: "$0.38 / $2.00 budget"
- Convergence: "0.72" with a trend sparkline across rounds
- Kill button (red, requires confirmation)

**Agent table:**
- One row per agent: caste icon + name, model (with provider-colored dot: green/blue/amber), tokens consumed, status dot, pheromone weight
- The model column is critical — it shows which provider each agent is actually using (the routing table in action)

**Round history (the big new feature):**
- Expandable timeline showing every round
- Each round shows: round number, phase, convergence delta, cost, duration
- Expand a round to see per-agent details: output summary (1-2 sentence compressed text), tool calls as pills, tokens, model used, duration
- This is the "what actually happened" view — the operator can trace every decision

**Topology graph (if stigmergic):**
- Node-link diagram showing agents as nodes, pheromone edges as weighted connections
- Edge thickness = pheromone weight
- Edge color or animation = trend (strengthening/weakening/stable)
- Node color = caste color
- This should be visually prominent — it's the signature visualization of the stigmergic system

**Governance section:**
- Convergence score trend (line chart across rounds)
- Stall warnings (if any)
- Governance interventions (if any)
- Path diversity indicator

**Merge edges (if any):**
- Show incoming merge edges (data flowing IN from other colonies)
- Show outgoing merge edges (data flowing OUT to other colonies)
- Each edge shows source/target colony name and status

### 4.4 Colony Creation Flow (multi-step)

This is a modal or full-screen flow triggered by "New Colony" button.

**Step 1: Describe**
- Large text input for the objective
- On submit, two parallel calls:
  - `POST /api/v1/suggest-team` → shows recommended castes below the input
  - Template suggestions → shows matching templates as cards
- The operator sees: "Suggested team: Coder + Reviewer + Researcher" with reasoning for each
- Below that: "Or start from a template:" with template cards (name, castes, use count)

**Step 2: Configure**
- Caste list with add/remove controls
- Each caste shows: icon, name, resolved model from routing table (with provider color), and optionally a tier/model override dropdown
- Budget input with default from workspace config
- Max rounds input (default 25)
- Strategy selector (stigmergic/sequential)
- If from template: show "from {template_name}" badge with option to save customizations as new template

**Step 3: Launch**
- Summary of what's about to happen
- Confirm button
- After launch: colony card appears with a name shimmer → Queen-assigned name fills in (~1 second)
- Auto-navigate to colony detail view

### 4.5 Skill Browser

A dedicated view for browsing the skill bank:

- **Skill cards/rows** showing:
  - Text preview (first ~100 characters)
  - Confidence as a number AND a visual bar
  - Uncertainty indicator: narrow bar = well-established, wide bar = needs more data
  - `conf_alpha` / `conf_beta` on hover/tooltip (e.g., "15 successes, 3 failures")
  - Source colony name
  - Age (relative time from `extracted_at`)
  - Algorithm version badge
  - "Merged" badge if the skill was created by merging two others

- **Sort controls:** By confidence (default), by freshness, by uncertainty (least certain first — for exploration)
- **Filter:** Minimum confidence threshold slider
- **Empty state:** "No skills yet. Complete a colony to start building the skill bank."

### 4.6 Template Browser

Accessible from colony creation flow Step 1 and as a standalone view:

- Template cards showing: name, description, caste icons, strategy badge, budget, use count, tags
- "Save as template" action on completed colony detail views
- Template detail: full config, version history, source colony link

### 4.7 Thread View

Shows all colonies within a thread with their merge edges as arrows between cards:

- Colony cards in a horizontal or vertical flow
- Merge edge arrows showing data flow direction
- Broadcast indicator (if a colony's output was broadcast to siblings)
- Controls: Create Merge, Prune Merge, Broadcast buttons

### 4.8 Model Registry

Shows all available models and their status:

- **Local models section:** Model name, quantization, VRAM usage, context window, slot count, status dot
- **Cloud providers section:** Provider name, available models, connection status, spend vs limit meter
- **Routing table visualization:** Shows the caste × phase routing table as a grid or matrix. Each cell shows the model address with provider color. Highlights where cloud models are used vs local.

### 4.9 Workspace Config

Settings for the current workspace:

- Per-caste model override dropdowns (null = inherit from system default)
- Budget setting
- Strategy default
- Governance parameters (max rounds, convergence threshold, stall detection)

### 4.10 Settings

System-level configuration:

- Embedding model info
- Data directory
- Protocol status details
- Event store stats (total events, last sequence)

---

## 5. Interaction Patterns

### 5.1 Real-time updates

The frontend receives events via WebSocket and updates views reactively:

- **Colony status changes** → update colony card status dot
- **Round progress** → update round counter, add to round history, update convergence chart
- **Agent turns** → update agent status dots, show activity indicator, add output to round detail
- **Colony naming** → replace UUID/shimmer with display name
- **Queen messages** → append to chat thread
- **Approvals** → badge count increases
- **Skill events** → update skill browser if open
- **Template events** → update template browser and use counts

### 5.2 Dark cockpit principle

When everything is healthy, the UI should be **quiet**. Information surfaces when it's relevant:

- Running colonies show activity. Completed colonies fade to a muted state.
- Governance warnings appear only when triggered.
- Approval badges appear only when actions are pending.
- Cost meters only get visually prominent when approaching budget limits.

### 5.3 Operator intervention points

- **Kill colony** — red button, requires confirmation
- **Approve/deny** — inline on approval cards
- **Merge/prune** — from thread view or colony detail
- **Broadcast** — share colony output to siblings
- **Model override** — change caste model assignment
- **Config change** — budget, rounds, governance
- **Template save** — save completed colony config
- **Queen directive** — type a message in chat panel

---

## 6. What's New Since the Phase 1 Prototype

| Feature | Wave | Frontend impact |
|---------|------|----------------|
| Quality scoring | 8 | Quality dot on colony cards. Numeric score on detail. |
| Skill crystallization | 8 | "Skills extracted: N" on completed colonies. Skill browser. |
| Cost tracking | 8 | Real cost numbers. Budget meters. |
| Compute routing | 9 | Per-agent model column with provider color. Routing badges. |
| Skill confidence | 9 | Confidence bars in skill browser. |
| Skill bank stats | 9 | "N skills, avg confidence X" on Queen overview. |
| 3-provider routing | 10 | Three provider colors (green/blue/amber). |
| Skill browser | 10 | Full component with sort, filter, empty state. |
| Bayesian confidence | 11 | Mean ± uncertainty. Alpha/beta on hover. |
| LLM dedup | 11 | "Merged" badge on merged skills. |
| Colony templates | 11 | Template browser, "from template" badge, save-as-template. |
| Queen naming | 11 | Display names. Name shimmer → fill on creation. UUID subtitle. |
| Suggest-team | 11 | AI-recommended castes in creation flow. |
| Multi-step creation | 11 | Describe → Configure → Launch flow. |

---

## 7. Component Inventory (16 minimum)

1. **AppShell** — Layout with sidebar, top bar, content area, queen chat panel
2. **TreeNav** — Sidebar tree: workspace → thread → colony hierarchy
3. **QueenChat** — Collapsible chat panel with message history and input
4. **QueenOverview** — Fleet dashboard: colony cards, skill summary, resources, templates
5. **ColonyCard** — Compact card: name, status, round, castes, routing badge, cost, quality
6. **ColonyDetail** — Full monitoring view: header, agents, rounds, topology, governance
7. **RoundTimeline** — Expandable round-by-round history with per-agent output
8. **TopologyGraph** — Node-link pheromone diagram (SVG)
9. **ColonyCreator** — Multi-step modal: Describe → Configure → Launch
10. **SkillBrowser** — Skill bank with confidence bars, sort, filter, merge badges
11. **TemplateBrowser** — Template list with use counts, tags, save-as-template
12. **ThreadView** — Colony cards with merge edge arrows
13. **ModelRegistry** — Local + cloud models, routing table visualization
14. **WorkspaceConfig** — Per-caste model overrides, budget, governance
15. **ApprovalQueue** — Pending actions with approve/deny buttons
16. **Settings** — System config, protocol status, event store info

---

## 8. Constraints

- **Single JSX file.** Self-contained React with inline styles and mock data.
- **Mock data only.** No real WebSocket connections. All data hardcoded.
- **All views navigable.** Tab/routing mechanism to click through all views.
- **Desktop-first.** Assume 1920×1080 minimum viewport.
- **Real data shapes.** Mock data matches the TypeScript contract types.
- **Style provided separately.** This brief covers structure and data. The operator provides visual direction independently.
