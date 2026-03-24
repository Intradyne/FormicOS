# Wave 51: UI Surface Inventory

**Date:** 2026-03-20
**Scope:** Every operator-visible control and status surface in the shipped frontend.
**Method:** Component-by-component code audit of `frontend/src/components/` (36 components),
cross-referenced with `store.ts`, `types.ts`, `ws/client.ts`, and backend routes.

---

## 1. App Shell & Navigation

### formicos-app (`formicos-app.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Logo | click | Navigate home | internal view switch | — | truthful |
| Top nav tabs (queen/knowledge/playbook/models/settings) | tab bar | Switch major view | internal `selectedView` | — | truthful |
| Approval badge (count) | badge+click | Show approval queue | toggles overlay | `store.approvals.length` | truthful |
| Sidebar toggle | button | Collapse/expand tree sidebar | internal `sidebarOpen` | — | truthful |
| Create Demo button (startup shell) | button | Create demo workspace | `POST /api/v1/workspaces/create-demo` | `store.tree.length === 0` | truthful |

### fc-tree-nav (`tree-nav.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Node toggle (▶) | click | Expand/collapse children | internal `expandedIds` | `TreeNode.children` | truthful |
| Node selection | click | Navigate to workspace/thread/colony | `node-select` custom event → app shell | `TreeNode.id, type, status` | truthful |
| Status dots | display | Show colony status | — | `TreeNode.status` | truthful |
| Quality dots | display | Show quality score | — | `TreeNode.qualityScore` | truthful |

### fc-breadcrumb-nav (`breadcrumb-nav.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Crumb spans | click | Navigate to ancestor node | `navigate` custom event | breadcrumb path | truthful |

---

## 2. Queen / Chat-First

### fc-queen-chat (`queen-chat.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Thread tabs | click | Switch between Queen threads | internal `activeThreadId` | `store.queenThreads` | truthful |
| Add tab (+) | click | Create new thread | `new-thread` event → WS `create_thread` | — | truthful |
| Message input | text+enter | Send message to Queen | WS `send_queen_message` | `activeThreadId` | truthful |
| Send button | click | Send message | WS `send_queen_message` | input value | truthful |
| Pin button | click | Pin a message | `pin-message` custom event | message id | truthful |
| Directive toggle | click | Show/hide directive panel | internal `showDirectives` | — | truthful |
| Colony selector (directives) | dropdown | Select target colony | feeds `fc-directive-panel` | running colonies | truthful |

### fc-queen-overview (`queen-overview.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Resource usage meters | display | Show cost/token usage | — | `store.colonies` aggregated | truthful |
| Active plans section | display | Show DelegationPlan DAGs | — | `queenThread.active_plan` | partial — renders plan but parallel_groups display may be incomplete |
| Recent colony cards | click | Navigate to colony | `node-select` event | `store.tree` colonies | truthful |
| Embedded fc-queen-chat | composite | Chat interface | (see fc-queen-chat) | — | truthful |
| Embedded fc-proactive-briefing | composite | Briefing display | (see fc-proactive-briefing) | workspace id | truthful |
| Embedded fc-approval-queue | composite | Approval actions | (see fc-approval-queue) | — | truthful |
| Federation status | display | Show peer count/health | `GET /api/v1/federation/status` | — | partial — silent failure if endpoint missing |
| Outcomes summary | display | Show success rate/cost | `GET /api/v1/workspaces/{id}/outcomes` | workspace id | partial — silent failure if no outcomes |

### fc-directive-panel (`directive-panel.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Directive type dropdown | select | Choose directive type | internal `type` | 4 types: context_update, priority_shift, constraint_add, strategy_change | truthful |
| Priority toggle | button | Toggle normal/urgent | internal `urgent` | — | truthful |
| Content textarea | input | Compose directive text | internal `content` | — | truthful |
| Send button | click | Dispatch directive | `directive-send` event → WS `chat_colony` with metadata | colonyId, type, content, urgent | truthful |

### fc-preview-card (`fc-preview-card.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Confirm button | click | Approve colony spawn | `preview-confirm` event | PreviewCardMeta | truthful |
| Cancel button | click | Cancel preview | `preview-cancel` event | — | truthful |
| Open Full Editor | click | Switch to colony creator | `preview-open-editor` event | PreviewCardMeta | truthful |
| Template badge (learned/operator) | display | Show template provenance | — | `meta.template.learned` | partial — displays but backend learned templates not yet landed |
| Success/failure counts | display | Show template track record | — | `meta.template.successCount/failureCount` | partial — data depends on TemplateProjection enrichment (not landed) |

### fc-result-card (`fc-result-card.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Colony Detail link | click | Navigate to colony | `result-navigate` event target='colony' | ResultCardMeta.colonyId | truthful |
| Timeline link | click | Navigate to timeline | `result-navigate` event target='timeline' | ResultCardMeta.threadId | truthful |
| Quality/cost/knowledge badges | display | Show colony outcome | — | ResultCardMeta fields | truthful |

---

## 3. Colony Detail

### fc-colony-detail (`colony-detail.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Export panel file checkboxes | checkbox | Select files for export | internal selection | colony files, artifacts | truthful |
| Export action button | click | Download colony ZIP | `GET /api/v1/colonies/{id}/export` | selected files | truthful |
| Artifact detail rows | click | Expand/collapse artifact | internal toggle | colony artifacts | truthful |
| Knowledge trace links | click | Navigate to knowledge entry | `navigate-knowledge` event | entry ids | truthful |
| Embedded fc-colony-chat | composite | Colony messaging | (see fc-colony-chat) | — | truthful |
| Embedded fc-round-history | composite | Round timeline | (see fc-round-history) | — | truthful |
| Embedded fc-topology-graph | composite | Pheromone topology | — | colony.topology | truthful |
| Embedded fc-directive-panel | composite | Send directives | (see fc-directive-panel) | — | truthful |
| Embedded fc-colony-audit | composite | Audit trail | (see fc-colony-audit) | — | truthful |

### fc-colony-chat (`colony-chat.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Message input | text+enter | Send message to colony | `send-colony-message` event → WS `chat_colony` | colonyId | truthful |
| Send button | click | Send message | same as above | — | truthful |

### fc-colony-audit (`colony-audit.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Knowledge entry titles | click | Navigate to knowledge | `navigate-knowledge` event | entry ids | truthful |
| Audit sections (knowledge/directives/governance/escalations) | display | Show audit trail | `GET /api/v1/colonies/{id}/audit` | colony id | truthful |

### fc-colony-creator (`colony-creator.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Objective textarea (Step 1) | input+enter | Describe task | internal | — | truthful |
| Suggest Team button (Step 2) | click | Get LLM team suggestion | `POST /api/v1/suggest-team` | objective text | truthful |
| Template cards (Step 2) | click | Select template | internal | `GET /api/v1/templates` | truthful |
| Caste toggle buttons (Step 3) | click | Add/remove castes | internal team list | — | truthful |
| Tier pills (Step 3) | click | Change tier (light/standard/heavy/flash) | internal | — | truthful |
| Count +/- buttons (Step 3) | click | Adjust agent count (1-5) | internal | — | truthful |
| Service attachment chips (Step 3) | click | Attach service colonies | internal | available services | truthful |
| Budget/MaxRounds/Strategy inputs (Step 3) | input | Configure colony params | internal | — | truthful |
| Launch button (Step 4) | click | Spawn colony | `spawn-colony` event → WS `spawn_colony` | full config | truthful |

---

## 4. Thread / Workflow

### fc-thread-view (`thread-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Thread name header | click+edit | Rename thread inline | WS `rename_thread` | threadId | truthful |
| Merge mode toggle | button | Enable colony merge selection | internal `mergeMode` | — | truthful |
| Colony cards (merge mode) | click | Select colonies for merge | WS `create_merge` | colony ids | truthful |
| Timeline toggle | button | Show/hide thread timeline | internal | — | truthful |
| Workflow step rows | display | Show step status | — | `thread.workflow_steps` | truthful |

### fc-thread-timeline (`thread-timeline.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Filter pills | click | Toggle event type filters | internal filter set | — | truthful |
| Timeline rows | click | Navigate to event source | custom event | event ids | truthful |

### fc-workflow-view (`workflow-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Reasoning toggle | click | Expand/collapse plan reasoning | internal | plan_reasoning | truthful |
| Task cards | display | Show parallel group status | — | DelegationPlanPreview | truthful |
| Dependency connectors | display | Animated group dependencies | — | parallel_groups | truthful |

---

## 5. Knowledge

### fc-knowledge-browser (`knowledge-browser.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Sub-tabs (catalog/graph) | click | Switch knowledge view | internal | — | truthful |
| Search input | input (debounced) | Search knowledge | `GET /api/v1/knowledge/search` | query, workspace | truthful |
| Type filter pills | click | Filter by skill/experience | internal filter | — | truthful |
| Status filter pills | click | Filter by candidate/verified/etc | internal filter | — | truthful |
| Sort pills (newest/confidence/relevance) | click | Change sort order | internal | — | truthful |
| Entry detail toggle | click | Expand/collapse entry | internal | — | truthful |
| Power panel toggle | click | Show operator controls | internal | — | truthful |
| Promote button (thread→workspace) | click | Promote entry scope | `POST /api/v1/knowledge/{id}/promote` target_scope=workspace | entry id | truthful |
| Promote button (workspace→global) | click | Promote to global scope | `POST /api/v1/knowledge/{id}/promote` target_scope=global | entry id | **partial** — UI exists, backend endpoint exists, but global scope projections/retrieval not landed |
| Scope badges (thread/workspace/global) | badge | Show entry scope | — | entry scope field | **partial** — global badge renders but no entries will have global scope yet |
| Operator action buttons (pin/mute/invalidate) | click | Apply operator overlay | `POST /api/v1/knowledge/{id}/action` | entry id | truthful |
| Annotation button | click | Add annotation | `POST /api/v1/knowledge/{id}/annotate` | entry id | truthful |

### fc-knowledge-view (`knowledge-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Tab pills (graph/library) | click | Switch view | internal | — | truthful |
| Graph filter pills | click | Filter by entity type | internal | — | truthful |
| Graph nodes | click | Select node, show detail | internal | KG data | truthful |
| Connection links in detail | click | Navigate to connected node | internal | edge data | truthful |
| Upload button (library tab) | click | Upload + ingest file | `POST /api/v1/workspaces/{id}/ingest` | workspace id | truthful |
| Refresh button (library tab) | click | Reload file list | `GET /api/v1/workspaces/{id}/files` | workspace id | truthful |

---

## 6. Settings / Models / Playbook

### fc-settings-view (`settings-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Event Store label | display | Show "Single SQLite · WAL mode · append-only" | — | — | truthful (informational) |
| Coordination Strategy pills | display | Show stigmergic/sequential | — | — | **stale** — display-only, implies configurability but has no handlers |
| Protocol status rows (MCP/AG-UI/A2A) | display | Show protocol status | — | `store.protocolStatus` | truthful (informational) |
| Embedded fc-retrieval-diagnostics | composite | Retrieval latency | (see below) | — | truthful |

### fc-retrieval-diagnostics (`retrieval-diagnostics.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Latency meters | display | Show retrieval pipeline timing | `GET /api/v1/retrieval-diagnostics` | — | truthful |

### fc-workspace-config (`workspace-config.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Model selector dropdowns (per caste) | select | Override model for caste | WS `update_config` | current model assignments | truthful |
| Governance edit inputs | input | Update governance settings | WS `update_config` | current governance config | truthful |

### fc-model-registry (`model-registry.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Model cards | click | Expand/collapse model details | internal | `store.localModels` | truthful |
| Endpoint cards | click | Expand/collapse endpoint | internal | `store.cloudEndpoints` | truthful |
| Policy inline edit fields | input | Modify model policy | `PATCH /api/v1/models/{address}` | current policy | truthful |
| Policy save buttons | click | Save policy changes | same as above | — | truthful |

### fc-playbook-view (`playbook-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Tab pills (templates/castes) | click | Switch sub-view | internal | — | truthful |
| Modal backdrop | click | Close editor overlay | internal | — | truthful |

### fc-template-browser (`template-browser.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| New Template button | click | Open template editor | `new-template` event | — | truthful |
| Template cards | click | Select template | `select-template` event | template data | truthful |
| Edit/Duplicate buttons | click | Edit or duplicate template | `edit-template`/`duplicate-template` events | template id | truthful |

### fc-template-editor (`template-editor.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Name/Description inputs | input | Edit template metadata | internal | — | truthful |
| Caste rows (+/-) | click | Add/remove castes | internal | — | truthful |
| Count input per caste | input | Set agent count | internal | — | truthful |
| Tag chips (remove) | click | Remove tag | internal | — | truthful |
| Tag input | input | Add tag | internal | — | truthful |
| Strategy/Budget/MaxRounds | input | Configure template params | internal | — | truthful |
| Save button | click | Save template | `POST /api/v1/templates` or PUT | template data | truthful |
| Cancel button | click | Discard changes | `cancel` event | — | truthful |

### fc-castes-view (`castes-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Caste list items | click | Select caste | internal | `store.castes` | truthful |
| Add button (+) | click | Create new caste | `new-caste` event | — | truthful |
| Edit Recipe button | click | Open caste editor | `edit-caste` event | caste id | truthful |

### fc-caste-editor (`caste-editor.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Caste ID input (new only) | input | Set caste identifier | internal | — | truthful |
| Name/Description/System Prompt | input | Edit recipe fields | internal | — | truthful |
| Temperature input | input | Set temperature | internal | — | truthful |
| Tool chips | click | Toggle tool inclusion | internal | available tools | truthful |
| Tier model dropdowns | select | Assign model per tier | internal | registered models | truthful |
| Cancel button | click | Discard | `cancel` event | — | truthful |
| Save button | click | Save caste recipe | `PUT /api/v1/castes/{id}` | caste data | truthful |

---

## 7. Intelligence / Briefing

### fc-proactive-briefing (`proactive-briefing.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Refresh button | click | Fetch latest briefing | `GET /api/v1/workspaces/{id}/briefing` | workspace id | truthful |
| Insight cards | display | Show 14 deterministic rules | — | briefing data | truthful |
| Forage cycle rows | display | Show recent forage cycles | `GET /api/v1/workspaces/{id}/forager/cycles` | workspace id | truthful |
| Domain chips (trusted/distrusted) | display | Show domain trust state | `GET /api/v1/workspaces/{id}/forager/domains` | workspace id | **partial** — data displayed but inline trust/distrust action buttons not fully wired |

### fc-demo-guide (`demo-guide.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Trigger Maintenance button | click | Fetch briefing manually | `GET /api/v1/workspaces/{id}/briefing` | workspace id | truthful |
| Dismiss button | click | Hide guide bar | internal | — | truthful |

---

## 8. Config Memory (Wave 50)

### fc-config-memory (`config-memory.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Refresh button | click | Re-fetch all config data | 3 endpoints (see below) | workspace id | truthful |
| Recommendation cards | display | Show config suggestions | `GET /api/v1/workspaces/{id}/config-recommendations` | workspace id | truthful |
| Override history | display | Show past overrides | `GET /api/v1/workspaces/{id}/config-overrides` | workspace id | truthful |
| Template cards | display | Show learned vs operator templates | `GET /api/v1/workspaces/{id}/templates` | workspace id | **partial** — fetches data but learned template enrichment (success/failure counts, category) not landed |

---

## 9. Federation

### fc-federation-dashboard (`federation-dashboard.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Peer trust table | display | Show federation peer health | `GET /api/v1/federation/status` | — | truthful |
| Conflict resolution log | display | Show resolution history | same endpoint | — | truthful |
| Federation stats | display | Show replication stats | same endpoint | — | truthful |

---

## 10. Approval Queue

### fc-approval-queue (`approval-queue.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Approve button | click | Approve governance request | `approve` event → WS `approve` | request id | truthful |
| Deny button | click | Deny governance request | `deny` event → WS `deny` | request id | truthful |

---

## 11. Data Display Components

### fc-round-history (`round-history.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Toggle header | click | Show/hide all rounds | internal | — | truthful |
| Round headers | click | Expand/collapse individual round | internal | `colony.rounds` | truthful |

---

## 12. Unused Components

### fc-fleet-view (`fleet-view.ts`)

| Control | Type | Intent | Target | State Inputs | Status |
|---------|------|--------|--------|-------------|--------|
| Tab pills (models/castes) | click | Switch sub-view | internal | — | **dead** — component defined but never rendered by app shell |

---

## 13. Atomic/Display Components (no interactive controls)

| Component | File | Purpose |
|-----------|------|---------|
| fc-dot | atoms.ts | Status indicator dot |
| fc-pill | atoms.ts | Rounded badge |
| fc-meter | atoms.ts | Progress meter |
| fc-btn | atoms.ts | Styled button (wrapper) |
| fc-defense-gauge | atoms.ts | Circular defense score gauge |
| fc-pheromone-bar | atoms.ts | Pheromone level bar |
| fc-sparkline | atoms.ts | Inline sparkline chart |
| fc-quality-dot | atoms.ts | Quality score indicator |
| fc-gradient-text | atoms.ts | Gradient text wrapper |

---

## Summary

| Surface Group | Components | Interactive Controls | Truthful | Partial | Stale | Dead |
|--------------|-----------|---------------------|----------|---------|-------|------|
| App Shell & Nav | 3 | 8 | 8 | 0 | 0 | 0 |
| Queen / Chat | 5 | 22 | 19 | 3 | 0 | 0 |
| Colony Detail | 4 | 18 | 18 | 0 | 0 | 0 |
| Thread / Workflow | 3 | 8 | 8 | 0 | 0 | 0 |
| Knowledge | 2 | 16 | 13 | 3 | 0 | 0 |
| Settings / Config | 8 | 26 | 24 | 0 | 1 | 0 |
| Intelligence | 2 | 4 | 3 | 1 | 0 | 0 |
| Config Memory | 1 | 3 | 2 | 1 | 0 | 0 |
| Federation | 1 | 0 | 0 | 0 | 0 | 0 |
| Approval | 1 | 2 | 2 | 0 | 0 | 0 |
| Unused | 1 | 2 | 0 | 0 | 0 | 2 |
| Atoms (display) | 9 | 0 | 0 | 0 | 0 | 0 |
| **Total** | **40** | **109** | **97** | **8** | **1** | **2** |
