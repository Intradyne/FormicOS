# Wave 60.5: The Cockpit Pass

**Date**: 2026-03-23
**Status**: Planning
**Depends on**: Wave 60 (shipped, 3434 tests)
**Theme**: The operator should feel like they are commanding a hive, not chatting with a bot.

---

## Origin

First real operator session on the Wave 60 stack. Six complaints emerged in
the first 5 minutes. Every one is visible immediately and makes the system
feel unfinished to the person it is built for. These are not feature
requests -- they are friction points in the primary interaction surface.

---

## Seven tracks in three tiers

### Tier 1: Behavioral (the Queen talks back, not executes)

#### Track 1: Queen deliberation mode (HIGHEST PRIORITY)

**The problem.** The operator asked "what kind of project do you think
would be a good showcase?" The Queen immediately spawned a colony, burned
1.2M local tokens, and returned an inconclusive result. The operator wanted
a conversation. The Queen heard a task.

**Root cause.** Two things conspire to make the Queen over-eager:

1. The Queen system prompt in `config/caste_recipes.yaml` (line 45-67) says
   "preview-first" but also says "skip preview for trivial fast_path tasks
   where the overhead is not justified." The Queen interprets ambiguous
   questions as straightforward tasks and skips preview.

2. The intent fallback parser in `adapters/queen_intent_parser.py` has no
   DELIBERATE category. Its vocabulary is SPAWN, KILL, REDIRECT, APOPTOSIS,
   or nothing. When the Queen produces exploratory prose ("I think we
   could..."), the regex at line 36-48 catches "Let's spawn" / "I'll
   create" and fires a SPAWN. There is no regex that catches "What do you
   think" / "Help me plan" / "Let's discuss" and returns DELIBERATE.

**The fix has two parts.** Both must land together -- the prompt change
sets the expectation, the parser change enforces it when the LLM still
over-reaches.

Part A -- System prompt revision (`config/caste_recipes.yaml`, Queen
section starting at line 9). This is the higher-effort part because the
wording must make deliberation the default without making the Queen
refuse to act when the operator gives a clear directive.

Step A1: Add a deliberation directive block between the "Chat-first
orchestration" section (line 40) and the "How to respond" section
(line 56):

```
## Deliberation vs execution
Not every operator message is a task. When the operator asks a question
("what do you think", "what would be good", "help me plan", "should we",
"let's discuss"), respond conversationally: suggest options, ask
clarifying questions, propose a plan. Do NOT call spawn_colony or
spawn_parallel for questions. Wait for a clear directive ("do it", "go
ahead", "let's build that", "spawn a colony for X") before dispatching.

When in doubt: respond with a plan and ask "Shall I proceed?" rather
than spawning immediately. The operator should always feel heard before
the hive starts working.
```

Step A2: Remove the "skip preview for trivial" escape hatch. Currently
lines 45-48 read:

```
**Preview-first:** Before dispatching work, use preview=true to show the
operator the proposed plan (team, cost, strategy). Let the operator
confirm or adjust before committing resources. Skip preview only for
trivial fast_path tasks where the overhead is not justified.
```

Replace with:

```
**Preview-first:** Before dispatching ANY work, use preview=true to show
the operator the proposed plan (team, cost, strategy). The operator
confirms or adjusts before resources are committed. No exceptions.
```

Also update line 66-67 which currently reads "If the task is clear,
preview first, then spawn on confirmation. Skip preview for trivial
fast_path tasks." Replace with "Always preview first, then spawn on
operator confirmation."

**Prompt wording caution**: The new text must NOT make the Queen passive.
She should still proactively propose plans, suggest approaches, and
recommend team composition. The change is: she proposes and waits for
"go" instead of proposing and immediately executing. Test the wording
against these scenarios:
- "Build me a CLI tool" -> should preview, wait for confirmation
- "What should we build?" -> should discuss, not preview
- "Go ahead with that plan" -> should execute immediately
- "Let's do it" (after a plan) -> should execute immediately

Part B -- Intent parser deliberation guard
(`adapters/queen_intent_parser.py`). This is the simpler part (~20
lines).

Add a deliberation detector that runs BEFORE the SPAWN regex at line
115. If the Queen's prose contains deliberation patterns AND does not
contain explicit action markers, return `{"action": "DELIBERATE"}` which
`intent_to_tool_call()` maps to no-op (pass through as chat).

```python
_DELIBERATION_RE = re.compile(
    r"(?i)(?:"
    r"(?:I\s+think|we\s+could|here\s+are\s+(?:some|a\s+few)|"
    r"you\s+might|let\s+me\s+suggest|options?\s+(?:include|are)|"
    r"what\s+(?:about|if)|consider|some\s+ideas|my\s+recommendation)"
    r")",
)

_ACTION_MARKERS_RE = re.compile(
    r"(?i)(?:spawning\s+now|I['']ll\s+(?:go\s+ahead|dispatch|create\s+a\s+colony))"
)
```

In `parse_intent_regex()` at line 115, insert before the existing
SPAWN tool-name regex check (line 126):

```python
# Wave 60.5: deliberation guard -- exploratory prose should not trigger SPAWN
if _DELIBERATION_RE.search(text) and not _ACTION_MARKERS_RE.search(text):
    return {"action": "DELIBERATE"}
```

In `intent_to_tool_call()` at line 308, add early return:

```python
if intent["action"] == "DELIBERATE":
    return {}  # no tool call -- pass through as chat
```

**Files owned**: `config/caste_recipes.yaml` (Queen section only),
`adapters/queen_intent_parser.py`

**Do NOT touch**: `queen_runtime.py`, `queen_tools.py`

**Validation**: Ask the Queen "what kind of project would be a good
showcase?" -- she should respond with options, not spawn a colony. Then
say "Let's build a CLI framework" -- she should preview, not execute.
Then say "Go ahead" -- she should execute.

---

### Tier 2: Layout and visibility (what you see on launch)

#### Track 2: Dashboard-first layout

**The problem.** The operator opens FormicOS and sees a chat interface.
The 37-component rich dashboard -- colonies, knowledge entries, model
registry, proactive briefings, outcome history -- is secondary. The app
feels like "another chatbot" instead of a hive mind cockpit.

**Current state.** `formicos-app.ts` line 25 defines 5 tabs: Queen,
Knowledge, Playbook, Models, Settings. The default view is `'queen'`
which renders `fc-queen-overview` -- this IS a dashboard component with
resource grids, health metrics, colony cards, and outcome summaries. But
the Queen chat (`fc-queen-chat`) dominates the right panel, and the
overall feel is chat-centric.

**The fix.** Restructure the Queen tab layout so the dashboard is primary
and the chat is a collapsible sidebar rail:

1. `queen-overview.ts`: Make the main panel full-width when chat is
   collapsed. The dashboard IS the landing page. Colony grid, knowledge
   health, outcome summary, proactive briefings -- all visible on first
   render.

2. `formicos-app.ts`: The queen-chat rail should start collapsed on
   workspace entry. Show a "Ask the Queen" FAB or header button that
   expands the chat panel. The operator sees the hive WORKING first, with
   the Queen available for conversation on demand.

3. The mental model: the operator opens FormicOS to CHECK ON THEIR HIVE,
   not to chat. The dashboard is the cockpit. The Queen is the radio.

**Files owned**: `frontend/src/components/formicos-app.ts` (layout only),
`frontend/src/components/queen-overview.ts` (layout only)

**Do NOT touch**: Backend, queen_runtime.py, store.ts

**Validation**: Open workspace -- dashboard fills the viewport. Queen
chat is accessible but not dominant.

---

#### Track 3: Colony workspace sandbox viewer

**The problem.** You can see individual agent output well -- what the
coder wrote, what the reviewer said. But you cannot see the colony's
actual workspace sandbox -- the files it created, the code it produced.
The workspace sandbox is the WORK PRODUCT. Showing agent chat without
the deliverable is like showing a meeting transcript without the
artifact.

**Current state.** `colony-detail.ts` shows topology graph, agent
metrics, quality score, memory count, and task description.
`colony-audit.ts` shows knowledge used, directives, and governance
actions. Neither shows the colony's produced artifacts in a browseable
view.

Artifact data already exists at the projection level:
`ColonyProjection.artifacts` (projections.py line 374) is a
`list[dict[str, Any]]` populated by `artifact_extractor.py` during live
execution and replayed via `ColonyCompleted.artifacts` (projections.py
line 1095). The `read_colony_output` Queen tool (queen_tools.py line
570) can read colony output. But there is NO REST endpoint to retrieve
artifacts -- they are only accessible via projections in-process.

**The fix.**

Backend (net-new endpoint, ~30 lines):
- Create `GET /api/v1/colonies/{colony_id}/artifacts` endpoint in
  `routes/api.py`. This is a NEW route, not a modification to existing
  endpoints. Read `runtime.projections.colonies[colony_id].artifacts`
  and return the list. Each artifact has `id`, `artifact_type`, `name`,
  `content`, `language` fields (see `artifact_extractor.py` Artifact
  dataclass at line 18). Return `[{id, name, artifact_type, content,
  language}]`.

Frontend:
- Add an "Artifacts" or "Output" tab to `colony-detail.ts` that fetches
  from the artifacts endpoint and renders file contents with syntax
  highlighting (use `<pre><code>` blocks with the existing mono font
  stack).

**Files owned**: `routes/api.py` (one new endpoint),
`frontend/src/components/colony-detail.ts` (one new tab)

**Validation**: Open a completed colony that ran code_execute -- see the
generated files in an Artifacts tab.

---

#### Track 4: Budget dashboard panel

**The problem.** Wave 60 Track 4 added `api_cost` and `local_tokens`
properties to `BudgetSnapshot` and made the budget enforcer truthful.
But there is no UI for the operator to see current spend, set budget
limits, or view per-colony cost breakdown. The data is all there. The
visibility is absent.

**Current state.** `workspace-config.ts` has an `fc-meter` showing
"Budget Used" with `$value/$max`, an edit button for budget cap, and a
reset button. This is functional but hidden inside the workspace config
panel. `queen-overview.ts` shows total cost in the workspace header line
(`${cols.length} colonies . $${totalCost.toFixed(2)}`). Neither shows
API vs local split, per-colony breakdown, or per-model spend.

**The fix.** Add a budget section to the Queen overview dashboard:

1. In `queen-overview.ts`, add a "Budget" section after the outcome
   summary grid showing:
   - API spend: `$X.XX of $Y.YY` with a progress bar (use existing
     `fc-meter` atom)
   - Local compute: `X,XXX tokens processed` (informational, not metered)
   - Per-model spend: small table showing which models burned money

2. Expose the budget data: the existing
   `GET /api/v1/workspaces/{id}` endpoint already returns workspace data
   including budget. If per-model breakdown is not included, add a
   `model_spend` field to the workspace projection summary that
   aggregates `model_usage` data from `BudgetSnapshot`.

**Files owned**: `frontend/src/components/queen-overview.ts` (additive),
`routes/api.py` (extend workspace response if needed)

**Validation**: Open workspace dashboard -- see API spend, local tokens,
and per-model breakdown.

---

### Tier 3: Controls and configuration (the operator as commander)

#### Track 5: Settings controls (display-only to editable)

**The problem.** The settings tab (`settings-view.ts`) shows protocol
status, retrieval diagnostics, and skill bank stats. Nothing is
adjustable. The "shared control surface" claim requires actual controls.

**Current state.** Settings view is 100% read-only. But the backend has
full config mutation support:

- `suggest_config_change` / `approve_config_change` Queen tools exist
  (queen_tools.py lines 484-511, 396-405) with structural validation
  via `config_validator.py` and experimentable-param whitelist via
  `experimentable_params.yaml`
- `set_maintenance_policy` MCP tool (mcp_server.py lines 395-455)
  handles autonomy level, auto_actions, max_maintenance_colonies,
  daily_maintenance_budget
- `configure_scoring` MCP tool (mcp_server.py lines 484-544) handles
  composite weight overrides per workspace
- `WorkspaceConfigChanged` events (core/events.py lines 342-356) persist
  all changes and survive replay
- Config override recording already exists at
  `POST /api/v1/workspaces/{id}/config-overrides`

**The fix.** Make key settings adjustable in `settings-view.ts`:

1. **Autonomy level** -- dropdown: suggest / auto_notify / autonomous.
   Calls `POST /api/v1/workspaces/{id}/config-overrides` or a new
   thin endpoint that emits `WorkspaceConfigChanged`.

2. **Default budget per colony** -- number input. Currently
   `governance.default_budget_per_colony: 1.00` in formicos.yaml.

3. **Max rounds per colony** -- number input. Currently
   `governance.max_rounds_per_colony: 25`.

4. **Default strategy** -- toggle: sequential / stigmergic. Currently
   `routing.default_strategy: "stigmergic"`.

5. **Convergence threshold** -- slider 0.80-1.00. Currently
   `governance.convergence_threshold: 0.95`.

Each control calls a settings update endpoint that emits a
`WorkspaceConfigChanged` event. The existing `config_validator.py`
validation and `experimentable_params.yaml` whitelist gate all changes.

**Files owned**: `frontend/src/components/settings-view.ts`

**Do NOT touch**: `config_validator.py`, `experimentable_params.yaml`,
`mcp_server.py`, `routes/api.py`

**Note**: This is pure frontend work. The backend is fully built --
`suggest_config_change`/`approve_config_change` Queen tools,
`config_validator.py`, `experimentable_params.yaml` whitelist,
`WorkspaceConfigChanged` events, and the
`POST /api/v1/workspaces/{id}/config-overrides` endpoint all exist and
are operational. No backend changes needed.

**Validation**: Change autonomy level in Settings. Refresh page. Setting
persists (it is an event, therefore it replays).

---

#### Track 6: Model registry hierarchy

**The problem.** The model registry (`model-registry.ts`) shows every
model as a separate card in a flat list. With 7+ models this is visual
noise. The operator thinks in providers, not individual model addresses.

**Current state.** Local models section renders a flat `.model-list`.
Cloud endpoints section renders flat `.ep-card` elements. Cascade grid
shows per-caste model preferences in a 5-column grid. There is a
`providerOf()` helper and `providerColor()` in `helpers.ts`, but
**`providerOf()` is stale** -- it only recognizes `anthropic/` and
`gemini/` prefixes (helpers.ts lines 65-70). Everything else falls
through to `'llama-cpp'`. Missing providers: `openai/`, `deepseek/`,
`minimax/`, `ollama-cloud/`, `mistral/`, `groq/`.

**The fix.** Two steps -- fix the helper first, then build the grouped UI.

Step 1: Fix `providerOf()` in `helpers.ts` (prerequisite). Update the
function to recognize all configured providers:

```typescript
export function providerOf(model: string): string {
  const prefixes = [
    'anthropic/', 'gemini/', 'openai/', 'deepseek/',
    'minimax/', 'ollama-cloud/', 'mistral/', 'groq/',
  ];
  for (const p of prefixes) {
    if (model.startsWith(p)) return p.slice(0, -1);
  }
  return 'llama-cpp';
}
```

Step 2: Group models by provider/endpoint. Each provider is a
collapsible section showing connection status and aggregate spend.
Expand to see individual models with context window, cost rates, and
tool support flags.

```
v openai          connected    spend: $0.23
    gpt-4o        ctx 128K  out 16K  $2.50/$10.00 per 1M
    gpt-4o-mini   ctx 128K  out 16K  $0.15/$0.60 per 1M

v ollama-cloud    connected    spend: $0.00
    qwen3-coder:480b  ctx 262K  out 16K  free

v llama-cpp       loaded       slots: 0/2 idle
    Qwen3-Coder-30B  ctx 40K  out 8K  local

> deepseek        no_key       (collapsed, dimmed)
> minimax         no_key       (collapsed, dimmed)
```

Implementation: use `providerOf()` to group `ModelRegistryEntry` items.
Render each group as a collapsible card. Collapsed providers with no API
key are visually de-emphasized (lower opacity, no expand indicator).

**Files owned**: `frontend/src/components/model-registry.ts`,
`frontend/src/helpers.ts` (providerOf() fix)

**Do NOT touch**: Backend, formicos.yaml, model routing logic

**Validation**: Open Models tab -- see providers grouped, not flat cards.

---

#### Track 7: Model registry update (config-only)

**The problem.** The registry only has gpt-4o and gpt-4o-mini from
OpenAI. Missing current-generation models from multiple providers.

**Current state.** `config/formicos.yaml` lines 35-187 list 6 active
models and several commented-out entries (Anthropic tokens exhausted,
Gemini commented out). The registry needs updating with current model
IDs, context windows, and pricing.

**The fix.** Update the model registry in `config/formicos.yaml` with
current model information from each provider. The operator is
researching current model data separately. When that data arrives,
update the registry entries with correct:

- Model address (API model string)
- Context window
- Max output tokens
- Cost per input/output token (per-token, not per-1M)
- Tool support flags
- Time multiplier estimates

Providers to update: OpenAI, Anthropic, Google/Gemini, DeepSeek,
MiniMax, Mistral, Groq. Add any new models that belong in the lineup.
Re-enable commented-out providers with correct API strings if keys are
available.

**Source data**: `docs/research/api reference.md` -- operator-verified
model reference with exact API strings, pricing, and context windows for
all 7 providers:
- OpenAI: gpt-5.4, gpt-4.1 family, o3/o4-mini reasoning series
- Anthropic: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5
- Gemini: 3.1-pro-preview, 3-flash-preview, 2.5-pro/flash/flash-lite
- MiniMax: M2.7, M2.5 (+ highspeed variants)
- DeepSeek: deepseek-chat (V3.2), deepseek-reasoner (R2)
- Mistral: codestral-2508, devstral-2512, mistral-small-2603
- Groq: gpt-oss-20b/120b, llama-3.3-70b, llama-3.1-8b

**Files owned**: `config/formicos.yaml` (registry section only)

**Do NOT touch**: Any source code. This is a pure config change.

**Validation**: Start FormicOS. Model registry tab shows all configured
models with correct metadata. No startup errors from malformed entries.

---

## Workspace file library (deferred)

The operator noted that workspace file library shows up attached to
individual colonies instead of at the workspace level. Investigation
shows `knowledge-view.ts` already has a "Library" tab with workspace-
level file upload and browsing via
`GET /api/v1/workspaces/{id}/files` and
`POST /api/v1/workspaces/{id}/library`. This may be a navigation
discovery issue rather than a missing feature. Deferred pending operator
re-evaluation after Track 2 (dashboard-first layout) ships, since the
layout change may resolve the discoverability problem.

---

## Track dependency graph

```
Track 1 (Queen deliberation)   -- independent, highest priority
Track 2 (Dashboard layout)     -- independent
Track 3 (Colony artifacts)     -- independent
Track 4 (Budget dashboard)     -- DEPENDS ON Track 2
Track 5 (Settings controls)    -- independent
Track 6 (Model hierarchy)      -- independent (fix providerOf() first)
Track 7 (Model config)         -- independent, config-only
```

**Track 2 MUST complete before Track 4.** Track 2 restructures the
Queen overview layout (dashboard-primary, chat-collapsed). Track 4 adds
a budget section to that layout. If Track 4 targets the old layout, the
budget panel will land in the wrong place and need rework. Sequence:
dispatch Track 2, verify landing, then dispatch Track 4 against the new
layout.

All other tracks have zero file overlap and can run fully parallel.

---

## Priority order

| # | Track | Why first |
|---|-------|-----------|
| 1 | Queen deliberation | Destroys first impression. Operator feels unheard. |
| 2 | Dashboard layout | Makes FormicOS feel like a chatbot, not a cockpit. |
| 3 | Colony artifacts | Operator cannot see what the hive produced. |
| 4 | Budget dashboard | Cost visibility is table stakes for any paid tool. |
| 5 | Settings controls | "Shared control surface" claim requires controls. |
| 6 | Model hierarchy | Visual clarity, lower friction than above. |
| 7 | Model config | Config-only, research complete. |

---

## Team split recommendation

**Team A (behavior + layout)**: Tracks 1, 2, 4
- Queen prompt revision + intent parser deliberation guard
- Dashboard-first layout restructure
- Budget section in queen-overview.ts
- Touches: caste_recipes.yaml, queen_intent_parser.py, formicos-app.ts,
  queen-overview.ts

**Team B (controls + visibility)**: Tracks 3, 5, 6
- Colony artifact viewer (backend endpoint + frontend tab)
- Settings controls (settings-view.ts + thin API if needed)
- Model registry hierarchy (model-registry.ts)
- Touches: routes/api.py (one endpoint), colony-detail.ts,
  settings-view.ts, model-registry.ts

**Track 7** (model config): Separate, can run in parallel with either
team. Research data in `docs/research/api reference.md`.

Zero file overlap between teams. Both teams can run all sub-tracks in
parallel.

---

## Hard constraints

1. Do NOT modify `queen_runtime.py` or `queen_tools.py` -- the
   deliberation fix lives in the system prompt and intent parser.
2. Do NOT add new event types -- use existing `WorkspaceConfigChanged`.
3. Do NOT modify `docs/specs/` or `docs/reference/` -- they are current.
4. Every settings change must emit an event (replay-safe).
5. Frontend changes are Lit Web Components only (no framework switch).
6. Budget display must show API cost vs local tokens separately (Wave 60
   cost truth distinction).

---

## The meta-point

These seven tracks serve one goal: **flip the hierarchy from chat-first
to cockpit-first.** The dashboard is the cockpit. The Queen is the
strategic advisor. The colonies are the workforce. The knowledge browser
is the institutional memory. The budget panel is the financial controls.
The settings are the command dials. Right now the chat dominates and
everything else is secondary. This wave inverts that.
