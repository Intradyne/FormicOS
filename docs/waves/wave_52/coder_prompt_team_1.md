You own the Wave 52 backend/control-plane coherence and intelligence-reach
track.

This is the only track allowed to touch backend code for Wave 52. Your job is
to make the system describe itself consistently at the protocol layer and to
wire existing intelligence into more intake paths without inventing new
subsystems.

## Mission

Land the backend-heavy parts of Wave 52:

1. canonical version unification across package, registry, and Agent Card
2. Queen tool-result hygiene parity with the colony runner seam
3. thread-aware Queen retrieval
4. A2A learned-template reach using the already-shipped projection template path
5. external budget truth, plus bounded spawn-gate parity if it stays in scope
6. learned-template visibility in Queen briefing
7. recent outcome digest in Queen briefing
8. AG-UI smarter omitted defaults only if it stays bounded and honest
9. external stream timeout truth only if it stays bounded

Core rule:

**Do not invent new intelligence. Cash in the intelligence the system already has.**

## Read First

1. `AGENTS.md`
2. `CLAUDE.md`
3. `docs/waves/wave_52/wave_52_plan.md`
4. `docs/waves/wave_52/acceptance_gates.md`
5. `docs/waves/wave_52/capability_control_inventory.md`
6. `docs/waves/wave_52/control_plane_seam_map.md`
7. `docs/waves/wave_52/control_plane_findings.md`
8. `docs/waves/wave_52/task_intelligence_inventory.md`
9. `docs/waves/wave_52/learning_loop_seam_map.md`
10. `docs/waves/wave_52/intelligence_findings.md`
11. `docs/waves/wave_52/information_tool_flow_findings.md`
12. `src/formicos/__init__.py`
13. `src/formicos/surface/app.py`
14. `src/formicos/surface/routes/protocols.py`
15. `src/formicos/surface/routes/a2a.py`
16. `src/formicos/surface/agui_endpoint.py`
17. `src/formicos/surface/proactive_intelligence.py`
18. `src/formicos/surface/queen_runtime.py`
19. `src/formicos/surface/template_manager.py`

Before editing, re-verify these truths:

- A2A still imports `load_templates`, not `load_all_templates`
- Queen tools already use `load_all_templates(... projection_templates=...)`
- A2A already passes a per-colony `budget_limit`
- AG-UI still passes no `budget_limit` and falls back to the runtime default of `5.0`
- neither external intake path currently uses the Queen-style workspace spawn gate
- package/registry/Agent Card version strings still disagree
- the Queen tool loop still feeds raw tool results back to the model
- `retrieve_relevant_memory()` supports `thread_id` but the Queen path does not pass it
- A2A and AG-UI still emit terminal timeout on mere inactivity
- Queen briefing selection is narrow enough that new insight types may require
  a small selection-path adjustment

## Owned Files

- `src/formicos/__init__.py`
- `src/formicos/surface/app.py`
- `src/formicos/surface/routes/protocols.py`
- `src/formicos/surface/routes/a2a.py`
- `src/formicos/surface/agui_endpoint.py`
- `src/formicos/surface/proactive_intelligence.py`
- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_tools.py` only if a small retrieval piggyback stays bounded
- targeted backend tests you add for this track

## Do Not Touch

- frontend component files
- `frontend/src/state/store.ts` unless Team 2 explicitly says it is needed
- `AGENTS.md`
- `CLAUDE.md`
- `docs/A2A-TASKS.md`
- `docs/AG-UI-EVENTS.md`
- ADR files under `docs/decisions/`
- Wave 52 audit docs

Team 2 owns frontend protocol/status truth. Team 3 owns docs/ADR truth.

## Parallel-Safe Coordination Rules

1. Team 1 is authoritative for backend protocol/intake behavior changes.
2. Do not require Team 2 to consume a brand-new backend shape unless it is
   strictly necessary for live status truth.
3. If A2A selection metadata changes, keep it additive and call it out clearly
   so Team 3 can document it.
4. If AG-UI omitted-default behavior stays unchanged, state that explicitly.

## Required Work

### Track A1: Canonical version unification

Required outcome:
- one authoritative version source
- registry and Agent Card both read from it

Preferred implementation order:
1. use the package/version constant already present in repo truth
2. remove hardcoded version forks from backend protocol surfaces

### Track B0: Queen tool-result hygiene parity

Current truth:
- the colony runner wraps tool results as untrusted data and compacts old
  results under pressure
- the Queen loop still feeds raw tool result text back as plain user messages

Required outcome:
- Queen tool results are treated as untrusted prompt data
- per-result size is bounded
- old tool-result history is compacted instead of silently inflating context

Keep this bounded to the Queen loop unless extracting a shared helper is truly trivial.

### Track B0.5: Thread-aware Queen retrieval

Current truth:
- `retrieve_relevant_memory()` accepts `thread_id`
- Queen automatic retrieval does not currently pass it

Required outcome:
- Queen pre-spawn retrieval becomes thread-aware on the primary path

If this stays tiny, also consider passing thread context into manual Queen
`memory_search` while you are already on the seam. Do not sprawl for it.

### Track B1: A2A learned-template reach

Required outcome:
- A2A sees learned templates
- selection remains deterministic relative to current learned state
- caller can see what template/team choice was made

Important constraint:

The wiring change is small, but selection observability matters. If `_select_team()`
needs a small refactor so A2A can return template/provenance metadata, keep it
bounded and additive. Do not build a new planner.

### Track B2: External budget truth and spawn-gate parity

Required outcome:
- AG-UI no longer gets a silent runtime-default budget
- AG-UI budget behavior is explicit: caller-provided or server-selected
- if you keep spawn-gate parity in scope, A2A and AG-UI both use the
  Queen-style workspace spawn gate before spawn

Do not assume runtime-level spawn enforcement already solves this.

### Track B3: AG-UI smarter omitted defaults

This is optional if it stays small and honest.

Acceptable outcomes:
1. keep current omitted-default behavior and document it explicitly
2. use deterministic server-selected defaults informed by existing classifier/template logic

If you change behavior:
- expose that the defaults were server-selected
- do not pretend AG-UI now has full Queen-like intelligence

### Track B4: Learned-template visibility in Queen briefing

Required outcome:
- a returning operator can see that the system has learned templates and how
  they are performing

### Track B5: Recent outcomes digest in Queen briefing

Required outcome:
- Queen briefing includes a compact outcome summary grounded in real projection data

Critical seam rule:

If you add new insight types in `proactive_intelligence.py`, make sure
`queen_runtime.py` actually gives them room to surface. Do not land invisible
intelligence.

More explicit guidance:
- the Queen briefing currently shows top 3 non-performance insights and top 2
  performance insights
- new learned-template / outcome-digest signals will otherwise compete for the
  same non-performance slots
- either add a dedicated learning-loop briefing section or raise the
  non-performance slot count enough for the new signals to appear routinely

### Track A7: External stream timeout truth

This is optional if it stays bounded.

Current truth:
- A2A and AG-UI emit terminal `RUN_FINISHED status=timeout` after 300s without an event
- the colony may still be running

Acceptable outcomes:
1. replace terminal timeout with a non-terminal idle/keepalive behavior
2. or keep current behavior only if you can make the semantics explicitly truthful

Do not turn this into a new streaming architecture project.

## Hard Constraints

- No new event types
- No new backend subsystem
- No protocol expansion
- No token streaming work
- No AG-UI Tier 2 work
- No full A2A conformance work
- No silent Queen auto-template substitution
- Do not touch frontend-owned or docs-owned files

## Validation

Run at minimum:

1. `python scripts/lint_imports.py`
2. `python -m ruff check src/formicos/__init__.py src/formicos/surface/app.py src/formicos/surface/routes/protocols.py src/formicos/surface/routes/a2a.py src/formicos/surface/agui_endpoint.py src/formicos/surface/proactive_intelligence.py src/formicos/surface/queen_runtime.py src/formicos/surface/queen_tools.py`
3. `python -m pytest tests/unit/surface -q`
4. targeted tests for:
   - version truth
   - Queen tool-result hygiene or prompt-boundary wrapping
   - thread-aware Queen retrieval
   - A2A learned-template reach
   - AG-UI budget truth and any spawn-gate parity you land
   - briefing learned-template visibility or outcome digest logic
   - stream timeout truth if you touch it

## Summary Must Include

- which version source became canonical
- whether Queen tool results now have runner-style prompt-boundary protection
- whether Queen automatic retrieval now uses thread-aware retrieval
- whether A2A now sees learned templates and how selection metadata is exposed
- whether AG-UI still had a silent `5.0` default or now has explicit budget truth
- whether spawn-gate parity landed for A2A and AG-UI or was deliberately deferred
- whether AG-UI omitted-default behavior changed or stayed explicit
- whether external timeout semantics changed or were deliberately deferred
- what learned-template and outcome signals now appear in the Queen briefing
- whether `queen_runtime.py` needed a selection tweak to surface them
- what you deliberately kept out to stay bounded
