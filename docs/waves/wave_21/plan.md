# Wave 21 Plan - Alpha Complete

**Wave:** 21 - "Alpha Complete"  
**Theme:** The system describes itself mechanically, the Queen becomes a stronger interface than the UI alone, and the stigmergy thesis becomes testable with real artifacts.  
**Contract changes:** 0 new events. The event union stays at 37. Ports stay frozen. Additive state/type fields are allowed where needed for the registry/debug surface and evaluation outputs.  
**Estimated LOC delta:** ~500 Python, ~40-60 TypeScript, ~100-140 config/eval/docs

---

## Why This Wave

After Wave 20, FormicOS is a real system:

- externally consumable through MCP and AG-UI
- internally productive through the sandbox and transcript surface
- more honest about local runtime truth through VRAM and protocol-status cleanup

What still prevents it from feeling like an alpha is not raw capability. It is legibility, leverage, and evidence.

**1. Too much truth is still maintained socially.**  
Wave 20 exposed live drift between backend snapshot truth, frontend types, and docs. Protocol status, MCP tool counts, AG-UI documentation, and VRAM shape all needed manual correction. The system still cannot answer "what am I?" from one authoritative place.

**2. The Queen still knows less than the UI in important places.**  
She can spawn, inspect, steer, and approve, but she still cannot read full colony output, search prior memory semantically, write a persistent artifact, or remember operator preferences across sessions. The UI still has important informational advantages over the conversational surface.

**3. The core thesis is still untested.**  
Stigmergic coordination, skill carry-forward, and pheromone-shaped routing are the core ideas. The infrastructure now exists to compare those ideas against simpler baselines. The missing piece is evaluation discipline, not another infrastructure wave.

Wave 21 addresses those three gaps without expanding the protocol surface and without adding new events.

---

## Tracks

### Track A - Self-Describing System + Queen Power Tools

**Goal:** The system can answer "what am I?" mechanically, and the Queen becomes a more capable operational interface.

#### A1. Capability registry

Add a deliberately boring registry object built during app assembly.

It should carry inventories, not just counts:

- `event_names`
- `mcp_tools`
- `queen_tools`
- `agui_events`
- `protocols`
- `castes`
- `version`

The key design rule is:

- declared truth, not magical introspection

The registry is assembled in the app factory from explicit manifests and mounted surfaces. It is then stored on `app.state.registry`.

**Important refinement:** do not reach into FastMCP private internals for tool descriptions. If the MCP surface needs names plus descriptions, export a small explicit manifest from `mcp_server.py` such as `MCP_TOOL_ENTRIES` and derive `MCP_TOOL_NAMES` from it.

New file:

- `src/formicos/surface/registry.py`

Files touched:

- `src/formicos/surface/app.py`
- `src/formicos/surface/mcp_server.py`

#### A2. `/debug/inventory`

Add a debug inventory route that returns the registry as JSON.

Purpose:

- operator visibility
- smoke/acceptance truth checks
- foundation for contract parity tests

This is not a new public protocol surface. It is a consolidated local-first debug surface for information the system already exposes piecemeal.

#### A3. Manifest-based contract parity

Each surface should export a small manifest rather than forcing one giant test to parse implementation details.

Manifests:

- Python events: `EVENT_TYPE_NAMES`
- MCP tools: `MCP_TOOL_ENTRIES` / `MCP_TOOL_NAMES`
- Queen tools: derived from `_queen_tools()`
- AG-UI events: `AGUI_EVENT_TYPES`
- TypeScript event names: `EVENT_NAMES`

The parity tests should check:

- Python event names vs TypeScript event names
- registry contents vs MCP/Queen/AG-UI manifests
- protocol declarations vs mounted surfaces

This is the mechanical answer to the Wave 20 drift bugs.

#### A4. Fix the `input_sources` projection gap

Wave 20 added transcript support for `input_sources`, but `ColonyProjection` still does not persist the field from `ColonySpawned`.

That means chained-colony transcript attribution is still silently incomplete.

Fix:

- add `input_sources` to `ColonyProjection`
- populate it in the colony spawn projection handler

This is small, but it matters because Track C depends on transcript truth.

#### A5. Queen tool: `read_colony_output`

Add a Queen tool that can return full output for a given round/agent, truncated to a safe limit such as 4000 chars per agent.

This closes the most obvious "Queen knows less than the UI" gap.

Expected behavior:

- `colony_id` required
- `round_number` optional, default latest completed round
- `agent_id` optional, default all agents in that round
- include agent/model/tool-call context when available

#### A6. Queen tool: `search_memory`

Add a Queen semantic search tool across:

- skill bank
- workspace memory

Critical rule:

- reuse the existing two-collection retrieval pattern already used by `memory_search`
- do not invent a second retrieval policy for the Queen

If sharing code cleanly is awkward, duplicate a very small loop rather than creating a new retrieval architecture.

#### A7. Queen tool: `write_workspace_file`

Add a bounded write tool for workspace artifacts:

- summaries
- notes
- evaluation reports
- small structured outputs

Use the same directory the current workspace file HTTP surface uses:

- `data/workspaces/{workspace_id}/files/`

This should stay low-risk:

- extension whitelist
- size cap
- path sanitization
- overwrite allowed

While in this area, align Queen file semantics with the UI surface as much as practical. The current `read_workspace_files` tool is broader than the HTTP `/files/` surface; Wave 21 is a good time to make the Queen read/write story more coherent.

#### A8. Queen tool: `queen_note`

Add a small persistent preference-memory tool.

Scope:

- append/list notes
- per-workspace YAML file
- rolling cap on note count and note length
- only inject the latest bounded set into context

Important rule:

- do not imply the full note history gets injected forever

The right shape is a bounded operator-memory aid, not an unbounded prompt dump.

#### A9. Iteration bump

Raise `_MAX_TOOL_ITERATIONS` from 5 to 7.

This is enough room for multi-step Queen workflows without turning the loop into an open-ended search. Model-aware iteration scaling can be documented as optional stretch, not core scope.

---

### Track B - Structural Extraction

**Goal:** Reduce the surface-layer merge pressure without changing behavior.

#### B1. Split `app.py` into route modules

Extract route groups into:

- `surface/routes/api.py`
- `surface/routes/colony_io.py`
- `surface/routes/protocols.py`
- `surface/routes/health.py`

`app.py` should become factory-first:

- adapter wiring
- runtime construction
- lifespan
- registry construction
- route assembly
- static frontend mount

This is a mechanical extraction, not an architecture rewrite.

#### B2. Protocol truth reads from the registry

After Track A lands the registry, the protocol truth surfaces should consume it instead of maintaining separate facts.

Primary consumers:

- `view_state.py`
- Agent Card builder
- `/debug/inventory`

This is where the Wave 20 truthfulness wins get locked in structurally.

#### B3. View-state slimming (secondary)

If time remains, extract small presentation helpers from `view_state.py`.

Examples:

- caste colors/icons
- protocol formatting helpers
- small formatting tables

This is explicitly secondary. If the wave runs long, drop B3 first.

---

### Track C - Evaluation Infrastructure

**Goal:** Make the stigmergy thesis testable with exploratory but meaningful comparison artifacts.

#### C1. Task suite

Add 6-8 YAML task definitions under:

- `config/eval/tasks/`

The suite should span:

- simple tasks where sequential should win or tie
- moderate tasks where parallel exploration may help
- complex tasks where skill carry-forward may matter

Each task should define:

- `id`
- `description`
- `difficulty`
- `castes`
- `success_rubric`
- `budget_limit`
- `max_rounds`
- `model_assignments`

Keep these grounded in real operator-style tasks, not synthetic benchmarks.

#### C2. A/B harness

Add an in-process evaluation harness that runs:

- `stigmergic`
- `sequential`

with all other variables held constant.

Recommendation:

- use `runtime.spawn_colony()`
- wait for completion in-process
- use `build_transcript()` directly rather than going back through HTTP

That keeps Track C reliable and avoids making the evaluation wave depend on external transport plumbing.

#### C3. Comparison artifact

Generate:

- markdown report
- JSON result artifact

per task.

The artifact should show:

- quality
- cost
- wall time
- rounds
- status
- tool usage
- retrieved skills / chaining evidence
- final transcript reference

No frontend comparison panel is required for alpha proof. Markdown is enough.

#### C4. Alpha polish (stretch)

If the core evaluation path is green, use remaining time for:

- first-run audit
- error-state audit
- quickstart audit
- performance baseline notes

This is stretch, not headline scope.

---

## Execution Shape

| Team | Track | First lands on | Notes |
|---|---|---|---|
| Coder 1 | A | `registry.py`, `mcp_server.py`, `queen_runtime.py`, `events.py`, `projections.py`, `app.py` | Lands registry shape and Queen tools first |
| Coder 2 | B | `routes/*.py`, `app.py`, `view_state.py` | Rereads `app.py` after Coder 1 lands registry construction |
| Coder 3 | C | `config/eval/`, `src/formicos/eval/` | Independent of A/B |

### Serialization rules

- Coder 1 lands registry construction in `app.py` first.
- Coder 2 rereads `app.py` after that and then performs route extraction.
- Coder 3 stays independent.

### Overlap-prone files

| File | Teams | Resolution |
|---|---|---|
| `src/formicos/surface/app.py` | 1 + 2 | Registry/factory first, extraction second |
| `src/formicos/surface/mcp_server.py` | 1 | Explicit MCP manifest if needed for registry truth |
| `src/formicos/surface/queen_runtime.py` | 1 | Four new tools plus iteration bump |
| `src/formicos/surface/projections.py` | 1 | `input_sources` persistence fix |
| `src/formicos/surface/view_state.py` | 2 | Registry consumer |

---

## Acceptance Criteria

Wave 21 is complete when:

1. `app.state.registry` exists and inventories events, MCP tools, Queen tools, AG-UI events, protocols, castes, and version.
2. `GET /debug/inventory` returns the registry cleanly.
3. Manifest-based parity checks catch event/tool/protocol drift.
4. `ColonyProjection.input_sources` is populated from `ColonySpawned` and transcripts reflect it truthfully.
5. The Queen has four new tools:
   - `read_colony_output`
   - `search_memory`
   - `write_workspace_file`
   - `queen_note`
6. `read_colony_output` returns full round/agent output with bounded truncation.
7. `search_memory` searches both skill bank and workspace memory using the existing two-collection pattern.
8. `write_workspace_file` saves artifacts into the same workspace files surface the operator can browse.
9. `queen_note` persists across sessions and injects only a bounded latest-N note set into context.
10. `app.py` is split into route modules and reduced to a factory-focused file.
11. Protocol status and Agent Card read from the registry instead of duplicating facts.
12. The task suite exists under `config/eval/tasks/`.
13. The evaluation harness can run at least one task under both strategies and emit artifacts.
14. A markdown comparison report is generated.
15. Existing tests/builds remain green.

### Smoke traces

1. `GET /debug/inventory` shows 37 events, live protocol entries, and current tool inventories.
2. Parity tests fail cleanly if an event/tool manifest drifts.
3. A completed colony can be queried with `read_colony_output` for latest round output.
4. `search_memory` returns relevant skill-bank/workspace-memory hits for a natural-language query.
5. `write_workspace_file` creates a visible workspace artifact under the existing files surface.
6. `queen_note save` survives a restart and `queen_note list` shows the saved note.
7. A chained colony transcript shows persisted `input_sources`.
8. `python -m formicos.eval.run --task <id> --runs 3` produces both strategy runs and a comparison artifact.

---

## Not In Wave 21

| Item | Reason |
|---|---|
| New events | Capability surface stays frozen |
| New protocol surfaces | MCP + AG-UI + Agent Card are enough for alpha |
| AG-UI bidirectional steering | Not required for this milestone |
| Frontend comparison panel | Markdown/JSON artifacts are enough |
| Statistical claims | Three runs per strategy is exploratory only |
| RL / self-evolution | Depends on evaluation outcomes |
| Broad `view_state.py` refactor | Secondary to route extraction |

---

## Final framing

Wave 21 should feel like the alpha milestone because it produces three things at once:

- the system can describe itself
- the Queen can do materially more useful work
- the thesis can finally be tested with evidence instead of intuition

If the docs keep that shape and avoid overpromising beyond the live repo seams, this is a strong wave.
