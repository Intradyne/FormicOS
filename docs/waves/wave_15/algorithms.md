# Wave 15 Algorithms and Implementation Reference

**Audience:** Offline coders implementing Wave 15 without internet access.
**Repo reality:** Wave 14 is complete. Use the post-Wave 14 repo state as baseline.

---

## 1. Repo module map (unchanged from Wave 14)

Wave 15 does not add new modules. All work targets existing files.

- `src/formicos/surface/app.py` -- HTTP routes, lifespan, first-run bootstrap
- `src/formicos/surface/runtime.py` -- Runtime, LLMRouter, build_agents, spawn_colony
- `src/formicos/surface/commands.py` -- WS command handlers
- `src/formicos/surface/mcp_server.py` -- MCP tool registration
- `src/formicos/surface/colony_manager.py` -- colony lifecycle
- `src/formicos/surface/projections.py` -- event projection handlers
- `src/formicos/surface/view_state.py` -- materialized views
- `src/formicos/surface/template_manager.py` -- template CRUD
- `src/formicos/engine/runner.py` -- round execution loop (FROZEN in Wave 15)
- `src/formicos/engine/context.py` -- context assembly (FROZEN in Wave 15)
- `config/templates/*.yaml` -- colony templates
- `config/caste_recipes.yaml` -- caste behavior definitions
- `frontend/src/components/formicos-app.ts` -- main shell
- `frontend/src/components/*.ts` -- all UI components

---

## 2. First-run bootstrap enhancement

**Owner:** Stream A
**File:** `src/formicos/surface/app.py` (lifespan function)

The current first-run code in `app.py` lifespan:

```python
# First-run bootstrap: create default workspace + thread if store is empty
if projections.last_seq == 0:
    log.info("app.first_run_detected")
    await runtime.create_workspace("default")
    await runtime.create_thread("default", "main")
    log.info("app.first_run_bootstrapped", workspace="default", thread="main")
```

Extend to:

```python
if projections.last_seq == 0:
    log.info("app.first_run_detected")
    await runtime.create_workspace("default")
    await runtime.create_thread("default", "main")

    # Verify default templates are readable on first boot
    from formicos.surface.template_manager import load_templates
    templates = await load_templates()
    log.info("app.first_run_templates_visible", count=len(templates))

    # Welcome message in Queen chat
    await runtime.emit_and_broadcast(QueenMessage(
        seq=0,
        timestamp=datetime.now(UTC),
        address="default/main",
        thread_id="main",
        role="queen",
        content=(
            "Welcome to FormicOS v3. I'm the Queen -- I orchestrate your agent colonies.\n\n"
            "To get started:\n"
            "1. Click the + button or type a task description below\n"
            "2. I'll suggest a team composition with tiers\n"
            "3. Adjust the team if you want, then click Spawn\n\n"
            "Try: 'Write a Python function that validates email addresses with tests'"
        ),
    ))
    log.info("app.first_run_bootstrapped", workspace="default", thread="main")
```

Note: `Runtime.send_queen_message()` currently emits `QueenMessage(role="operator")`, so the welcome message should emit `QueenMessage` directly with `role="queen"`, or use a new dedicated runtime helper if one is introduced without changing contracts.

Do NOT add a new event type for first-run detection. Use `projections.last_seq == 0` as the signal. This is a surface-layer concern, not a domain event.

---

## 3. Template YAML format (audit reference)

Templates should use the Wave 14 format with `castes:` and `governance:` blocks:

```yaml
name: full-stack
version: 1
description: "Balanced team for implementation tasks. Includes Archivist for knowledge extraction."
tags: [coding, implementation, refactoring]
castes:
  - caste: manager
    tier: heavy
    count: 1
  - caste: coder
    tier: standard
    count: 2
  - caste: reviewer
    tier: light
    count: 1
  - caste: archivist
    tier: light
    count: 1
governance:
  max_rounds: 12
  budget_usd: 5.0
```

**Audit checklist per template:**

1. Uses `castes:` list (not `caste_names:`)
2. Each slot has `caste`, `tier`, `count`
3. Has `governance.max_rounds` (reasonable: 6-25 depending on template)
4. Has `governance.budget_usd` (reasonable: $1-$10)
5. `description` is helpful to a first-time user
6. `tags` match the template's actual purpose

**KG visibility rule:** At least `full-stack`, `research-heavy`, and `documentation` templates must include an Archivist caste. Without Archivist, no KG entities are extracted and the Knowledge view stays empty.

---

## 4. Caste recipe audit reference

`config/caste_recipes.yaml` must include Wave 14 safety fields for every caste:

```yaml
coder:
  name: Coder
  description: "Writes and debugs code via tools"
  system_prompt: |
    You are a Coder agent...
  temperature: 0.2
  model_override: null
  tools: [memory_search, memory_write, code_execute]
  max_tokens: 4096
  max_iterations: 25
  max_execution_time_s: 300
```

**Required fields per caste:**

| Field | Coder | Reviewer | Researcher | Archivist | Manager |
|---|---|---|---|---|---|
| tools | memory_search, memory_write, code_execute | memory_search | memory_search, web_search | memory_search, memory_write | memory_search, delegate |
| max_iterations | 25 | 6 | 30 | 5 | 8 |
| max_execution_time_s | 300 | 90 | 600 | 60 | 120 |
| temperature | 0.2 | 0.1 | 0.3 | 0.1 | 0.2 |
| max_tokens | 4096 | 2048 | 4096 | 2048 | 2048 |

These values match the Wave 14 plan. If the live recipe file is missing `max_iterations` or `max_execution_time_s`, add them.

---

## 5. Nav consolidation: Fleet tab

**Owner:** Stream B
**Files:** `frontend/src/components/fleet-view.ts` (new), `frontend/src/components/formicos-app.ts`

Create a new `fleet-view.ts` that composes the existing `model-registry` and `castes-view` as sub-panels:

```typescript
@customElement('fc-fleet-view')
export class FcFleetView extends LitElement {
  @property({ type: Array }) localModels = [];
  @property({ type: Array }) cloudEndpoints = [];
  @property({ type: Array }) castes = [];
  @property({ type: Array }) tree = [];
  @property({ type: Object }) runtimeConfig = {};

  @state() private activeTab: 'models' | 'castes' = 'models';

  render() {
    return html`
      <div class="tabs">
        <button class="${this.activeTab === 'models' ? 'active' : ''}"
          @click=${() => this.activeTab = 'models'}>Models</button>
        <button class="${this.activeTab === 'castes' ? 'active' : ''}"
          @click=${() => this.activeTab = 'castes'}>Castes</button>
      </div>
      ${this.activeTab === 'models'
        ? html`<fc-model-registry .localModels=${this.localModels}
            .cloudEndpoints=${this.cloudEndpoints}
            .castes=${this.castes}
            .runtimeConfig=${this.runtimeConfig}></fc-model-registry>`
        : html`<fc-castes-view .castes=${this.castes} .tree=${this.tree}
            .runtimeConfig=${this.runtimeConfig}></fc-castes-view>`
      }
    `;
  }
}
```

Update `formicos-app.ts` NAV:

```typescript
// Before (6 tabs):
const NAV = [
  { id: 'queen', label: 'Queen', icon: '\u265B' },
  { id: 'knowledge', label: 'Knowledge', icon: '\u25C8' },
  { id: 'templates', label: 'Templates', icon: '\u29C9' },
  { id: 'models', label: 'Models', icon: '\u2B22' },
  { id: 'castes', label: 'Castes', icon: '\u2B21' },
  { id: 'settings', label: 'Settings', icon: '\u2699' },
];

// After (5 tabs):
const NAV = [
  { id: 'queen', label: 'Queen', icon: '\u265B' },
  { id: 'knowledge', label: 'Knowledge', icon: '\u25C8' },
  { id: 'templates', label: 'Templates', icon: '\u29C9' },
  { id: 'fleet', label: 'Fleet', icon: '\u2B22' },
  { id: 'settings', label: 'Settings', icon: '\u2699' },
];
```

---

## 6. Sidebar click-to-toggle

**Owner:** Stream B
**File:** `frontend/src/components/formicos-app.ts`

Replace:
```typescript
@mouseenter=${() => { this.sideOpen = true; }}
@mouseleave=${() => { this.sideOpen = false; }}
```

With a toggle button and click handler:
```typescript
// In the sidebar header area, add a toggle button
<div class="sidebar-toggle" @click=${() => { this.sideOpen = !this.sideOpen; }}>
  ${this.sideOpen ? '\u25C2' : '\u25B8'}
</div>
```

Set initial state: `@state() private sideOpen = true;`

Remove the mouseenter/mouseleave handlers entirely.

---

## 7. Empty state patterns

**Owner:** Stream B

Each empty state follows the same pattern:

```html
<div class="empty-state">
  <div class="empty-icon">{icon}</div>
  <div class="empty-title">{title}</div>
  <div class="empty-desc">{description}</div>
  {optional action button}
</div>
```

Shared CSS (add to `sharedStyles`):

```css
.empty-state {
  display: flex; flex-direction: column; align-items: center;
  justify-content: center; height: 100%; gap: 8px;
  text-align: center; padding: 40px;
}
.empty-icon { font-size: 32px; opacity: 0.3; }
.empty-title { font-size: 14px; font-weight: 600; color: var(--v-fg-muted); }
.empty-desc { font-size: 11px; color: var(--v-fg-dim); max-width: 300px; line-height: 1.5; }
```

**Queen Overview** (when no colonies exist):
- Icon: crown
- Title: "Ready to orchestrate"
- Desc: "Describe a task below, or pick a template to spawn your first colony."
- Action: show 2-3 template cards with spawn buttons

**Thread View** (when thread has no colonies):
- Icon: hexagon
- Title: "No colonies yet"
- Desc: "Spawn a colony from the Queen tab or click + below."

**Knowledge View** (when skill bank is empty):
- Icon: graph
- Title: "Knowledge grows with experience"
- Desc: "Skills and graph entities appear here after your first completed colony."

---

## 8. Cost ticker budget regime colors

**Owner:** Stream B
**File:** `frontend/src/components/colony-detail.ts`

Add a helper function:

```typescript
function budgetColor(remaining: number, total: number): string {
  if (total <= 0) return 'var(--v-fg-dim)';
  const pct = remaining / total;
  if (pct >= 0.70) return 'var(--v-success)';
  if (pct >= 0.30) return 'var(--v-warn)';
  if (pct >= 0.10) return 'var(--v-accent)';
  return 'var(--v-danger)';
}
```

Apply to the cost display in the colony header. The thresholds match ADR-022's budget regime injection -- operator and agents see the same signal.

---

## 9. Code execution result cards

**Owner:** Stream B
**File:** `frontend/src/components/colony-detail.ts` (or new `code-result-card.ts`)

Render `CodeExecuted` events inline in colony detail:

```html
<div class="code-result ${blocked ? 'blocked' : exitCode === 0 ? 'success' : 'failure'}">
  <span class="code-icon">${blocked ? '🛡' : exitCode === 0 ? '✅' : '❌'}</span>
  <span class="code-summary">${blocked ? 'Code blocked' : exitCode === 0 ? `Code executed (${durationMs}ms)` : `Code failed: ${stderrPreview}`}</span>
  <button class="expand-btn" @click=${toggleExpand}>...</button>
</div>
```

CodeExecuted data is available in the colony snapshot from Wave 14 events. The rendering accesses the same event data that feeds the colony chat.

---

## 10. Connection state indicator

**Owner:** Stream B
**File:** `frontend/src/components/formicos-app.ts`

The store already tracks `connection` state ('connected' | 'disconnected' | 'connecting').

Add to the topbar:

```html
<span class="conn-dot" style="background: ${
  connection === 'connected' ? 'var(--v-success)' :
  connection === 'connecting' ? 'var(--v-warn)' : 'var(--v-danger)'
}"></span>
${connection !== 'connected' ? html`<span class="conn-label">${
  connection === 'connecting' ? 'Reconnecting...' : 'Disconnected'
}</span>` : nothing}
```

CSS for `.conn-dot`: 6px circle, inline in the topbar-right area.

---

## 11. Smoke test protocol

**Owner:** Stream C

### End-to-end colony smoke

Prerequisites: Anthropic API key in `.env`, all containers healthy.

```bash
# 1. Verify health
curl http://localhost:8080/health
# Expected: {"status": "ok", "last_seq": N}

# 2. Open browser to http://localhost:8080
# Expected: v3 shell loads, Queen tab active, welcome message visible

# 3. Open Colony Creator (+ button)
# 4. Type: "Write a Python function that validates email addresses with tests"
# 5. Click "Suggest Team"
# Expected: Team suggestion with castes + tiers + reasoning

# 6. Click "Spawn"
# Expected: Colony appears in navigator, chat shows "Round 1/N"

# 7. Watch colony run
# Expected: Chat messages for each round, code execution results (if coder runs code)

# 8. Colony completes
# Expected: "Completed in N rounds. Cost: $X.XX" in chat
# Expected: skills_extracted > 0 in colony detail
# Expected: Knowledge view shows new entities (if Archivist was present)

# 9. Click "Save as Template"
# Expected: Modal with auto-generated name/description

# 10. Spawn second colony using saved template
# Expected: Spawns with same castes/tiers
# Expected: memory_search retrieves skills from first colony
```

### Provider fallback smoke

```bash
# 1. Set invalid GEMINI_API_KEY in .env
# 2. Restart containers
# 3. Spawn colony with heavy-tier agent (routes to Gemini by default)
# 4. Verify: structured logs show fallback_triggered=true
# 5. Verify: colony completes using fallback provider
# 6. Verify: Gemini adapter enters cooldown (check logs for "provider_cooldown")
```

### Sandbox smoke (if gVisor available)

```bash
# 1. Spawn colony with code_execute-capable template
# 2. Wait for coder to call code_execute
# 3. Check colony chat for code execution result line
# 4. Check logs for "code_executed" structured entry
# 5. Verify: container pool shows 3 warm containers
```
