# Wave 74 Team C: Behavioral Overrides + Documentation

## Mission

Build workspace-scoped Queen behavioral override forms. The operator can
tune the Queen's team composition rules, disable specific tools, inject
custom behavioral rules, and override round/budget heuristics. All override
state is stored via existing `WorkspaceConfigChanged` events and injected
into the Queen's context. Update docs to reflect the Queen Command & Control
surface.

## Owned files

- `frontend/src/components/queen-overrides.ts` - new override forms component
- `src/formicos/surface/queen_runtime.py` - override injection in `_build_messages()` only
- `CLAUDE.md` - update Queen tab description and Queen tool count
- `docs/DEVELOPER_BRIDGE.md` - update with Queen C&C description

### Do not touch

- `frontend/src/components/queen-overview.ts` (Team A mounts your component)
- `src/formicos/surface/queen_tools.py` (Team A)
- `src/formicos/surface/queen_budget.py` (Team B reads it)
- `src/formicos/surface/operational_state.py`, `src/formicos/surface/app.py` (Team A)
- `src/formicos/core/events.py`, `src/formicos/surface/projections.py`
- `frontend/src/components/workspace-config.ts`, `frontend/src/components/workspace-browser.ts` (Team B)
- `queen_runtime.py` `_execute_tool()` (Team A adds counters there)

## Repo truth (read before coding)

### Workspace config storage

1. `WorkspaceConfigChanged` uses `field`, `old_value`, `new_value`.
   `new_value` is stored as a string in `ws.config[field]`.

2. Projection read path is:
   ```python
   runtime.projections.workspaces[workspace_id].config[field_name]
   ```

3. Existing frontend write path already exists:
   ```typescript
   store.send('update_config', workspaceId, { field, value })
   ```
   Reuse it. Do not invent a new settings transport.

### Queen message assembly

4. `_build_messages()` in `queen_runtime.py` is the correct injection seam.
   Base system prompt is appended first (line 1733). Team A also modifies the
   system prompt content at lines 1729-1733 (tool inventory self-assembly) but
   that happens BEFORE `messages.append()`. Your override block goes immediately
   after that append and before Queen notes/tool history (line 1735+).

5. `queen-overview.ts` is Team A-owned. You do not patch the Queen tab shell.
   Your job is to ship `fc-queen-overrides` plus a clean prop/event contract
   so Team A can mount it.

### Override keys

6. All four keys are in scope in this wave. Do not leave any of them as
   "documented but not editable."

| Key | Type | Purpose |
|---|---|---|
| `queen.disabled_tools` | JSON list of tool names | Tools that should require operator confirmation |
| `queen.custom_rules` | JSON string / free text | Workspace-specific behavioral guidance |
| `queen.team_composition` | JSON dict | Override task-type to team-shape suggestions |
| `queen.round_budget` | JSON dict | Override round/budget heuristics by complexity tier |

## Track 1: Override forms component

Create `frontend/src/components/queen-overrides.ts`.

```typescript
@customElement('fc-queen-overrides')
export class FcQueenOverrides extends LitElement {
  @property() workspaceId = '';
  @property({ type: Object }) workspace: any = null;
  @state() private _disabledTools: string[] = [];
  @state() private _customRules = '';
  @state() private _teamCompJson = '';
  @state() private _roundBudgetJson = '';
}
```

The component should:
- read initial values from `workspace?.config`
- parse JSON strings defensively
- emit `update-config` events with `{ field, value }`
- keep the UX simple and reliable over fancy schema editing

### 1a. Disabled tools

Read the Queen tool names from the caste recipe. After Team A lands, there are
42 Queen tools including `post_observation`; if you work in parallel, derive
from current recipe truth and keep the list additive.

Render them as checkboxes in a compact grid. Saving writes:
```typescript
this.dispatchEvent(new CustomEvent('update-config', {
  detail: {
    field: 'queen.disabled_tools',
    value: JSON.stringify(this._disabledTools),
  },
  bubbles: true,
  composed: true,
}));
```

### 1b. Custom rules

Free-text textarea. Saving writes:
`field: 'queen.custom_rules'`

### 1c. Team composition overrides

For Wave 74, a JSON editor is acceptable. Keep it honest and bounded.

```json
{
  "code_simple": "coder / sequential",
  "code_complex": "coder + reviewer / stigmergic",
  "research": "researcher + archivist / sequential"
}
```

Saving writes:
`field: 'queen.team_composition'`

### 1d. Round / budget overrides

This key is in scope. Provide at least a compact JSON editor:

```json
{
  "simple": { "rounds": 4, "budget": 1.5 },
  "standard": { "rounds": 8, "budget": 2.5 },
  "complex": { "rounds": 14, "budget": 4.0 }
}
```

Saving writes:
`field: 'queen.round_budget'`

### 1e. Mount contract for Team A

Team A owns `queen-overview.ts`. Hand them this exact mount contract:

```html
<fc-queen-overrides
  .workspaceId=${this.activeWorkspaceId}
  .workspace=${sel}
  @update-config=${(e: CustomEvent) =>
    store.send('update_config', this.activeWorkspaceId, e.detail)}
></fc-queen-overrides>
```

Do not patch the shell directly.

## Track 2: Override injection in `queen_runtime.py`

Add a helper on the Queen runtime:

```python
def _build_override_block(self, workspace_id: str) -> str:
    ws = self._runtime.projections.workspaces.get(workspace_id)
    if not ws:
        return ""
    cfg = ws.config
    parts: list[str] = []

    disabled = cfg.get("queen.disabled_tools")
    if disabled:
        tools = json.loads(disabled) if isinstance(disabled, str) else disabled
        if tools:
            parts.append(
                "DISABLED TOOLS (require operator confirmation): "
                + ", ".join(tools)
            )

    custom = cfg.get("queen.custom_rules")
    if custom:
        rules = json.loads(custom) if isinstance(custom, str) else custom
        if rules:
            parts.append(f"OPERATOR RULES:\n{rules}")

    team_comp = cfg.get("queen.team_composition")
    if team_comp:
        overrides = json.loads(team_comp) if isinstance(team_comp, str) else team_comp
        if overrides:
            parts.append("TEAM COMPOSITION OVERRIDES:")
            for task_type, composition in overrides.items():
                parts.append(f"  {task_type}: {composition}")

    round_budget = cfg.get("queen.round_budget")
    if round_budget:
        overrides = json.loads(round_budget) if isinstance(round_budget, str) else round_budget
        if overrides:
            parts.append("ROUND / BUDGET OVERRIDES:")
            for complexity, limits in overrides.items():
                rounds = limits.get("rounds")
                budget = limits.get("budget")
                parts.append(f"  {complexity}: rounds={rounds}, budget={budget}")

    if not parts:
        return ""
    return "# Workspace Behavioral Overrides\n\n" + "\n\n".join(parts)
```

Inject it in `_build_messages()` immediately after the base system prompt:

```python
override_block = self._build_override_block(workspace_id)
if override_block:
    messages.append({"role": "system", "content": override_block})
```

This is a behavioral nudge, not hard enforcement. Do not add tool-dispatch
gating in this wave.

## Track 3: Documentation updates

### 3a. `CLAUDE.md`

Make surgical updates only:
- mention Wave 74 Queen Command & Control
- update Queen tool count to 42 (anticipates Team A adding `post_observation`;
  Team C merges before Team A, so the count is forward-looking — this is
  intentional per the B→C→A merge order)
- add `docs/waves/wave_74/` to relevant paths if appropriate

Do not rewrite the document.

### 3b. `docs/DEVELOPER_BRIDGE.md`

Add a short section explaining that the Queen tab now shows:
- display board
- continuation / plan state
- operating procedures
- behavioral overrides
- health / budget visibility

Keep it concise. This is for developers using the bridge, not a full operator
manual.

## Validation

```bash
cd frontend && npm run build
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

Verify in a running stack:
- override forms load current workspace config values
- each save path writes the correct `queen.*` config key
- Queen prompt gets an override block after the base system prompt
- all four keys render and round-trip

## Acceptance criteria

- [ ] `queen-overrides.ts` renders editors for all 4 keys
- [ ] Override forms read initial state from workspace config
- [ ] Saving overrides emits `update-config` with correct field names and JSON values
- [ ] `_build_override_block()` reads all 4 keys from workspace config
- [ ] Override block is injected after the base system prompt
- [ ] Team A receives the final `fc-queen-overrides` mount contract; Team C does not patch `queen-overview.ts`
- [ ] `CLAUDE.md` updated with Wave 74 Queen C&C and correct Queen tool count
- [ ] `docs/DEVELOPER_BRIDGE.md` updated with a concise Queen C&C section
- [ ] No regressions - frontend builds clean and backend checks pass
