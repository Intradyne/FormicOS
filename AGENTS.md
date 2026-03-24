# AGENTS.md — Agent Capabilities and Coordination Rules

This file documents agent tools, knowledge integration, and coordination
rules for parallel AI coding agents working on FormicOS.

> **Status note:** This file reflects the post-Wave-51 state. Wave 52
> (The Coherent Colony) is the active wave. The event union is at 64.
> Docs and recipes should reflect what actually shipped. When a newer
> wave plan or dispatch prompt conflicts with this file, the active wave
> docs are the authority for that dispatch.

---

## Agent Tools (20 engine-level; caste recipes expose a subset by default)

Colony agents (coder, reviewer, researcher, archivist) have access to these
tools. Tool availability per caste is configured in `config/caste_recipes.yaml`.

### Knowledge & memory

| Tool | Description | Category |
|------|-------------|----------|
| `memory_search` | Search the unified knowledge catalog. Returns top-k entries ranked by the 6-signal Thompson Sampling composite score (semantic + confidence + freshness + status + thread + cooccurrence). Supports tiered retrieval: auto/summary/standard/full. | `vector_query` |
| `memory_write` | Write a new memory/knowledge entry to the institutional store. Subject to 4-axis security scan before acceptance. | `vector_write` |
| `knowledge_detail` | Retrieve full details of a specific knowledge entry by ID. Returns content, confidence (alpha/beta), domains, polarity, source colony. | `vector_query` |
| `transcript_search` | Search past colony transcripts for relevant approaches and patterns. Returns colony IDs and snippets — use `artifact_inspect` to see full details. Projection-based (keyword matching), not Qdrant-backed. | `vector_query` |
| `artifact_inspect` | Inspect a specific artifact from a completed colony by `colony_id` + `artifact_id`. Returns type, content preview, and source context. | `read_fs` |
| `knowledge_feedback` | Report whether a retrieved knowledge entry was useful. Positive feedback strengthens confidence; negative feedback signals staleness and increments prediction_error_count. | `vector_query` |

### Execution

| Tool | Description | Category |
|------|-------------|----------|
| `code_execute` | Execute code in the sandboxed workspace environment. | `exec_code` |
| `query_service` | Query a deterministic service handler (dedup, stale sweep, contradiction detection, confidence reset) or a registered external specialist such as `service:external:nemoclaw:*` when configured. | `delegate` |

### Workspace editing

| Tool | Description | Category |
|------|-------------|----------|
| `patch_file` | Apply surgical text replacements to a workspace file. Operations apply sequentially against an in-memory buffer; file written only if ALL succeed. Zero matches return nearby context with line numbers; multiple matches return all locations. Empty `replace` means deletion. | `write_fs` |

### Git workflow

| Tool | Description | Category |
|------|-------------|----------|
| `git_status` | Show working tree status (staged, unstaged, untracked). | `read_fs` |
| `git_diff` | Show changes in git repository. Optional `path` filter and `staged` flag. | `read_fs` |
| `git_commit` | Stage all changes and commit with a message. No remote push. | `write_fs` |
| `git_log` | Show recent commit history (default 10, max 50). | `read_fs` |

### File & network

| Tool | Description | Category |
|------|-------------|----------|
| `http_fetch` | Fetch a URL via HTTP GET. Respects workspace-level network policy. | `network_out` |
| `file_read` | Read a file from the workspace library by name. | `read_fs` |
| `file_write` | Write content to a file in the workspace. Workspace effector only — not an artifact persistence path. | `write_fs` |

### Spawn

| Tool | Description | Category |
|------|-------------|----------|
| `spawn_colony` | Spawn a sub-colony (agent-initiated). Subject to budget and nesting limits. | `delegate` |
| `get_status` | Retrieve workspace/thread/colony status for coordination decisions. | `read_fs` |
| `kill_colony` | Stop a colony when governance or operator policy requires it. | `delegate` |
| `search_web` | Search the web when enabled by caste policy and environment. | `search_web` |

### Tool availability by caste

| Caste | Tools |
|-------|-------|
| Coder | `memory_search`, `memory_write`, `code_execute`, `workspace_execute`, `list_workspace_files`, `read_workspace_file`, `write_workspace_file`, `patch_file`, `git_status`, `git_diff`, `git_commit`, `git_log`, `knowledge_detail`, `transcript_search`, `artifact_inspect`, `knowledge_feedback` |
| Reviewer | `memory_search`, `knowledge_detail`, `transcript_search`, `artifact_inspect`, `knowledge_feedback`, `list_workspace_files`, `read_workspace_file`, `git_status`, `git_diff` |
| Researcher | `memory_search`, `memory_write`, `knowledge_detail`, `transcript_search`, `artifact_inspect`, `knowledge_feedback`, `list_workspace_files`, `read_workspace_file`, `http_fetch` |
| Archivist | `memory_search`, `memory_write`, `knowledge_detail`, `artifact_inspect` |
| Forager | `memory_search`, `memory_write`, `search_web`, `knowledge_detail` |

Additional tools (`file_read`, `file_write`, `query_service`,
`spawn_colony`, `get_status`, `kill_colony`, `search_web`) are available when
enabled via caste recipe configuration.

---

## Knowledge Integration

### Thread-scoped retrieval

When a colony has a `thread_id`, knowledge searches automatically use
two-phase retrieval:

1. **Thread phase** — Search entries scoped to the same thread. These get a
   thread bonus (1.0 × 0.07 weight) in the composite score.
2. **Workspace phase** — Search all workspace entries (no bonus).
3. **Merge + rank** — Deduplicate and sort by Thompson Sampling composite.

### Confidence evolution

Each knowledge entry carries `Beta(alpha, beta)` confidence posteriors. When
a colony completes:

- Accessed entries with a successful colony get a clipped quality-weighted alpha increase instead of a flat `+1`.
- Accessed entries with a failed colony get a bounded beta penalty derived from colony quality instead of a flat `+1`.
- `MemoryConfidenceUpdated` events are emitted per entry.

High-confidence entries are exploited reliably in retrieval. Uncertain entries
are explored occasionally. Low-confidence entries fade.

Operator overlays are separate from shared confidence truth. Pin/unpin,
mute/unmute, invalidate/reinstate, and annotations are replayable local-first
editorial actions; they do not silently mutate `conf_alpha` / `conf_beta`.

### Workflow step context

Agents receive workflow step context in their prompts when the colony is
associated with a workflow step. This includes the step description, index,
and expected outputs (if template-backed).

### Decay classes

Each entry carries a `decay_class` (ephemeral/stable/permanent) that
controls query-time gamma-decay of confidence:
- **ephemeral** (γ=0.98, ~34d half-life) — task-specific context
- **stable** (γ=0.995, ~139d half-life) — domain knowledge
- **permanent** (γ=1.0) — verified facts, no decay

Default is `ephemeral`. Archivists should classify entries explicitly.

### Co-occurrence scoring

When a colony accesses multiple entries, pairwise co-occurrence weights are
reinforced (1.05x). Co-occurrence is a scoring signal (weight 0.05, ADR-044)
using sigmoid normalization. Entries frequently co-accessed in successful
colonies score higher than identical entries without co-occurrence history.

### Entry sub-types

Entries carry a granular `sub_type`:
- Skills: `technique`, `pattern`, `anti_pattern`
- Experiences: `decision`, `convention`, `learning`, `bug`

Sub-types are classified during extraction and visible in the Knowledge
browser. API and MCP resources support `sub_type` filtering.

### Proactive intelligence

The Queen receives system intelligence briefings with 14 deterministic rules:
7 knowledge rules (contradiction, confidence decline, federation trust,
coverage gap, stale cluster, merge opportunity, federation inbound),
4 performance rules (strategy efficiency, diminishing rounds, cost outlier,
knowledge ROI), adaptive evaporation recommendations, branching-factor
stagnation diagnostics, and earned-autonomy recommendations. Three knowledge
rules include `suggested_colony` configurations for auto-dispatch.
Performance and autonomy rules analyze replay-derived workspace history and
are surfaced as Queen recommendations. Agents should check briefing insights
before spawning colonies in domains with known issues.

### Adaptive evaporation (Wave 42)

Pheromone evaporation in stigmergic mode is now bounded adaptive. The rate
interpolates from 0.95 (healthy) to 0.85 (stagnating) based on branching
factor (`exp(entropy)` over pheromone weights) and convergence stall count.
Low branching (< 2.0) combined with stalls triggers faster evaporation to
break search attractors. The control law is runner-local — no surface
imports. Stall influence is capped at 4 rounds.

### Colony outcome intelligence

Every completed colony produces a replay-derived `ColonyOutcome` tracking
quality, cost, rounds, knowledge extraction, and strategy. Four performance
rules analyze these outcomes per workspace. No new event types —
outcomes are rebuilt from the existing event log during replay.

### Web foraging (Wave 44)

The Forager adds a second knowledge input channel: bounded web acquisition.
When retrieval during colony work exposes a gap (low-confidence results),
the system issues a bounded web search, fetches pages through a controlled
egress gateway, extracts content, scores quality deterministically, and
admits entries through the standard `MemoryEntryCreated` path at `candidate`
status with conservative priors.

Architecture:

- `EgressGateway` — rate/size/domain controls, robots.txt enforcement
- `FetchPipeline` — Level 1 (httpx + trafilatura) with Level 2 fallback
- `ContentQuality` — 5-signal deterministic scoring (no LLM)
- `WebSearch` — pluggable search adapter with pre-fetch relevance filtering
- `ForagerService` — orchestrates the forage cycle with deterministic query
  templates and SHA-256 dedup

Four replay events: `ForageRequested`, `ForageCycleCompleted`,
`DomainStrategyUpdated`, `ForagerDomainOverride`. Individual search/fetch/
rejection details stay log-only.

**Current state:** Reactive, proactive, and operator-triggered foraging are
operational. Reactive foraging detects live-task gaps without blocking the
retrieval path on network I/O. Proactive foraging runs through the scheduled
maintenance loop: `proactive_intelligence` produces bounded `forage_signal`
metadata, `MaintenanceDispatcher` evaluates workspace briefings, and eligible
signals are handed to `ForagerService` as background work.

### Surgical editing (Wave 47)

The `patch_file` tool provides search-and-replace editing as a first-class
alternative to `write_workspace_file`. Operations apply sequentially against
an in-memory buffer; the file is written only if all operations succeed.
Failure contract: zero matches return nearby context with line numbers and
closest partial match; multiple matches return all matching locations.
Empty `replace` means deletion.

### Git workflow primitives (Wave 47)

Four git tools provide structured wrappers over common workspace git
operations: `git_status`, `git_diff`, `git_commit`, `git_log`. These are
first-class tool handlers (not recipe-level shell snippets). Safety
boundaries: no remote operations (push/pull/fetch), no force flags, no
rebase/cherry-pick/reset. Shell arguments are safely quoted.

### Fast path (Wave 47)

The Queen can spawn a colony with `fast_path=True` for simple single-agent
tasks. Fast-path colonies skip pheromone routing, convergence scoring, and
multi-agent topology construction while preserving normal event emission and
knowledge extraction. The choice is replay-safe: `fast_path` is a field on
`ColonySpawned` with `default=False`, so older events replay correctly.

### Per-round structural context refresh (Wave 47)

Coding colonies with non-empty `target_files` refresh structural context at
each round boundary (round 2+). The refreshed workspace structure is
injected as a visible `[Workspace Structure]` section in the Coder round
prompt. Non-coding colonies do not pay refresh cost. Changes made through
`workspace_execute` are captured because refresh is round-driven, not
tool-driven.

### Preview (Wave 47)

Both `spawn_colony` and `spawn_parallel` accept `preview=true`. Preview
returns a plan summary (team composition, task, estimated cost, fast-path
mode) without dispatching any work.

### Grounded Reviewer (Wave 48)

The Reviewer caste gained read-only workspace access: `list_workspace_files`,
`read_workspace_file`, `git_status`, `git_diff`. This makes the Reviewer a
grounded quality gate that can inspect real code and diffs rather than
reviewing only summaries and artifacts. The Reviewer still has no mutation
tools (`write_workspace_file`, `patch_file`, `workspace_execute`, `git_commit`
remain excluded).

### Grounded Researcher (Wave 48)

The Researcher caste gained project awareness and a fresh-information path:

- `list_workspace_files` and `read_workspace_file` for inspecting the real
  project structure and code.
- `http_fetch` for targeted external lookups (documentation, API references)
  when institutional knowledge has gaps. Respects workspace domain allowlist.

Broader web search (`search_web`) is not available to Researcher agents.
Systematic web acquisition remains the Forager service's responsibility.
The mediated Forager path (`request_forage`) was not implemented in this
wave — it remains a future option.

### Minimal colony first (Wave 48)

Queen guidance now defaults to the smallest viable team for each task:

- Trivial tasks: single agent with `fast_path=true`
- Simple code tasks: single coder, no reviewer unless independently needed
- Multi-caste colonies: reserved for complex, multi-file, high-uncertainty work

This is a product rule, not a benchmark optimization. Simple work should not
pay unnecessary multi-agent coordination overhead.

### Conversational colony infrastructure (Wave 49)

Wave 49 established the infrastructure for chat-first Queen orchestration.

**What landed:**

- `QueenMessage` gained three additive optional fields: `intent`
  (`notify` / `ask`), `render` (`text` / `preview_card` / `result_card`),
  and `meta` (structured payload). All are replay-safe with defaults.
- `QueenMessageProjection` passes metadata through to frontends.
- Contract mirrors updated (`docs/contracts/events.py`, `docs/contracts/types.ts`,
  `frontend/src/types.ts`) with `PreviewCardMeta` and `ResultCardMeta` types.
- `frontend/src/state/store.ts` handles metadata from events and snapshots.
- `fc-preview-card.ts` component: renders task, team, strategy, cost,
  fast-path, target files, with Confirm/Cancel actions.
- `fc-result-card.ts` component: renders colony status, rounds, cost,
  quality score, extracted entries, with audit/timeline/detail deep links.
- Queen recipe updated with chat-first orchestration, preview-first
  dispatch, and ask-vs-notify guidance.

- `queen-chat.ts` renders preview and result cards inline when render
  metadata is present. Ask messages get a visual accent + badge; notify
  messages render at reduced opacity. Heuristic fallback for messages
  ending with `?` when no explicit intent is set.
- `queen-overview.ts` defaults to chat-first (`chatExpanded = true`).
  Compact status header shows running count, session cost, active plans,
  knowledge count.
- `formicos-app.ts` dispatches colony directly from stored preview
  parameters on confirm, sends visible confirmation message to thread.
  Result card navigation wired to navTree.

- `queen_runtime.py` emits `intent="notify"` + `render="preview_card"` +
  preview payload on preview proposals, and `intent="notify"` +
  `render="result_card"` + result payload (colony_id, task, status,
  rounds, cost, quality_score, skills_extracted, contract_satisfied) on
  colony completion follow-ups.
- Deterministic Queen thread compaction: 6000-token budget, 10-message
  recent window, pinned asks + active previews preserved, structured-
  metadata-first summary block for older history. No LLM summarizer.

**What did not land:**

- Inline adjust deferred — "Open Full Editor" escape hatch provides the
  drill-down path.

**Architectural note:** No new event types were added. The structured
metadata rides on existing `QueenMessage` events via additive optional
fields. No new runtime, external dependency, or intelligence subsystem
was introduced.

### Configuration intelligence and cross-workspace knowledge (Wave 50)

Wave 50 shipped two self-improvement capabilities: learned templates from
successful colonies, and a global knowledge tier above workspace scope.

**What shipped:**

- Additive event fields: `spawn_source` on ColonySpawned, learned-template
  fields on ColonyTemplateCreated (`learned`, `task_category`, `max_rounds`,
  `budget_limit`, `fast_path`, `target_files_pattern`), `new_workspace_id`
  on MemoryEntryScopeChanged.
- Auto-template creation on qualifying colony completions (quality >= 0.7,
  rounds >= 3, Queen-spawned, no duplicate category+strategy).
- Template consumer merge: `load_all_templates()` merges disk YAML +
  projection-derived learned templates (disk wins on ID collision).
- TemplateProjection enrichment with success_count, failure_count
  cross-derived from colony outcomes.
- Task classifier integration: category-first lookup in preview and
  auto-template.
- Global knowledge scope: projections set `scope="global"` and clear
  `workspace_id` on promotion; two-phase retrieval with 0.9x global
  discount; promotion route accepts `target_scope="global"`.
- Knowledge listing scope filter (API accepts `scope` query param).
- Preview card template annotation: template name, learned/operator badge,
  success/failure counts.
- Circuit breaker: per-request retry cap (`max_retries_per_request`,
  default 3) with cooldown notify callback.
- SQLite PRAGMA upgrades: `mmap_size=256MB`, `busy_timeout=15000ms`.
- Workspace-scoped template API: `GET /api/v1/workspaces/{id}/templates`.
- Phase 0 measurement matrix defined.

**Architectural note:** Wave 50 added no new event types. All schema changes
were additive fields on existing events. Learned templates are replay-derived
(TemplateProjection), not auto-generated YAML files. No external memory
system or auto-promotion. The event union was 62 at the end of Wave 50.

### Final polish and UX truth (Wave 51)

Wave 51 made the surface more truthful without adding new subsystems.

**Replay-safety fixes (Team 1):**

- `ColonyEscalated` event added: escalation routing overrides now survive
  restart and replay (previously in-memory mutation only).
- `QueenNoteSaved` event added: Queen thread notes are now event-sourced.
  Notes are private (not visible in operator chat). YAML backup remains as
  fallback.
- `dismiss-autonomy` classified as intentionally ephemeral: recommendations
  regenerate each briefing cycle, so persisting dismissals would create
  stale overrides.
- Deprecated `/api/v1/memory` endpoints now emit RFC 8594 `Sunset` +
  `Deprecation` headers and log usage via structlog.
- Duplicate config-override routes documented as intentional (different UX
  flows, same underlying event).
- `docs/REPLAY_SAFETY.md` created: canonical replay-safety classification
  for all capabilities.
- Legacy/frozen events (`SkillConfidenceUpdated`, `SkillMerged`,
  `ContextUpdated`) marked with FROZEN comments.

**Surface truth fixes (Team 2):**

- Configuration Intelligence (renamed from "Config Memory"): failed data
  sections now show "unavailable" placeholder instead of vanishing silently.
- Queen overview: federation/outcomes sections show explicit unavailable
  states on failure.
- Model registry: shows "Updated Xs ago" + 60-second auto-refresh.
- Settings protocols: shows "Snapshot data -- refreshes on reconnect."
- Proactive briefing: domain trust/distrust/reset buttons wired inline.
- Strategy pills replaced with plain text labels (no false affordance).
- `fleet-view.ts` deleted (dead code, never rendered by app shell).

**Event union:** 62 to 64 (`ColonyEscalated`, `QueenNoteSaved`). All
contract mirrors updated.

### The Coherent Colony (Wave 52)

Wave 52 made the system describe itself consistently and extended
intelligence reach to external intake paths. Two packets:

**Packet A -- Control-plane coherence:**

- Canonical version source: `formicos.__version__` is the single
  authority; CapabilityRegistry and Agent Card both read from it.
- ADR 045/046/047 status corrected from "Proposed" to "Accepted."
- Frontend protocol status text: stale "Not implemented" / "planned" /
  "Agent Card discovery only" replaced with accurate "Inactive" labels.
- External stream idle: A2A attach and AG-UI run streams no longer emit
  terminal `RUN_FINISHED` on inactivity. Idle keepalive with eventual
  `idle_disconnect` CUSTOM event (non-terminal, colony may still run).

**Packet B -- Intelligence reach + visible learning:**

- Queen tool-result hygiene: tool output wrapped as untrusted prompt data
  with per-result truncation and oldest-first history compaction,
  matching the colony runner's prompt-boundary safety.
- Thread-aware Queen retrieval: automatic pre-spawn retrieval and the
  `memory_search` tool now pass `thread_id` for thread-scoped ranking.
- A2A learned-template reach: A2A uses `load_all_templates()` with
  projection templates. Learned templates are eligible during team
  selection. Response exposes selection metadata (source, template_id,
  learned, category).
- External budget truth: AG-UI no longer silently inherits a `5.0`
  runtime default. Both A2A and AG-UI use classifier-derived budgets and
  the workspace spawn gate (`BudgetEnforcer.check_spawn_allowed()`).
- AG-UI classifier-informed defaults: omitted castes use deterministic
  `classify_task()` instead of hardcoded coder+reviewer.
- Learned template visibility: new `_rule_learned_template_health` in
  proactive intelligence surfaces template count, success rate, and top
  templates in the Queen briefing.
- Recent outcome digest: new `_rule_recent_outcome_digest` surfaces a
  compact summary of the last 20 colony outcomes in the Queen briefing.
- Briefing selection: dedicated 2-slot `learning_loop` section ensures
  new signals are not crowded out by existing knowledge/performance caps.

**Event union:** unchanged at 64. No new event types. No new external
dependencies. No new subsystems.

---

## Federation

FormicOS instances can exchange knowledge via push/pull replication.

### How it works

1. Each instance maintains an `ObservationCRDT` per knowledge entry with
   per-instance observation counters and timestamps.
2. **Push:** Local CRDT events are sent to trusted peers, filtered by
   replication rules (domain allowlist, min confidence, entry types).
3. **Pull:** Remote events are received, applied to projections, with
   cycle prevention (skip own-instance events).
4. **Trust:** Peer trust is tracked via `PeerTrust` — the 10th percentile
   of a Beta posterior. Foreign knowledge is discounted by hop count.
5. **Conflicts:** Contradictory entries use Pareto dominance → adaptive
   threshold → competing hypotheses (three-phase resolution).

### For operators

- Trust scores are visible in the Agent Card (`/.well-known/agent.json`).
- Federation is opt-in per peer. No automatic discovery.
- Replication filters control what knowledge crosses instance boundaries.
- Validation feedback (success/failure) updates peer trust bidirectionally.

---

## Queen Tools (21)

The Queen has a separate tool set defined in `caste_recipes.yaml`:

**Colony lifecycle:** `spawn_colony`, `spawn_parallel`, `kill_colony`,
`redirect_colony`, `escalate_colony`, `inspect_colony`, `get_status`

**Templates:** `list_templates`, `inspect_template`

**Knowledge & files:** `memory_search`, `read_workspace_files`,
`write_workspace_file`, `read_colony_output`

**Config:** `suggest_config_change`, `approve_config_change`, `queen_note`

**Thread management:** `set_thread_goal`, `define_workflow_steps`,
`complete_thread`, `archive_thread`

**Services:** `query_service`

### Parallel planning

`spawn_parallel` accepts a DelegationPlan — a DAG of ColonyTask items grouped
into `parallel_groups`. Tasks within a group run concurrently. Groups execute
sequentially. The Queen states reasoning, references knowledge gaps, and
estimates cost. Emits `ParallelPlanCreated` event.

### Preview and fast path (Wave 47)

Both `spawn_colony` and `spawn_parallel` accept `preview=true` to return a
plan summary without dispatching. `spawn_colony` also accepts `fast_path=true`
for simple single-agent tasks that skip coordination overhead.

### Operator directives

Four directive types: `context_update`, `priority_shift`, `constraint_add`,
`strategy_change`. Delivered via `chat_colony` with directive metadata.
Priority: `urgent` (before task) or `normal` (after task, before round history).

### Operator/MCP maintenance controls

Per-workspace maintenance and scoring controls are currently exposed through
the operator/MCP surface, not as Queen chat tools:
- `set_maintenance_policy`
- `get_maintenance_policy`
- `configure_scoring`

---

## Shared Workflow Expectations

These apply to all tracks in this repo unless the operator says otherwise.

Expanded reference:
- `docs/DEVELOPMENT_WORKFLOW.md` — canonical workflow cadence, prompt
  checklist, seam acceptance discipline, and clean-room smoke guidance

### Plan from proven seams

- Start from the current wave docs, ADRs, and code reality.
- When something looks wrong, determine whether it is:
  - substrate truth,
  - surface truth,
  - or deployment/runtime truth.
- Do not assume the running Docker/UI state matches the current source tree.
- Before freezing a packet, separate findings into:
  - confirmed current drivers,
  - re-verify before packet freeze,
  - already landed,
  - reference-only/future.

### Parallel work should be bounded

- Each coder owns explicit files and should stay inside them.
- Prompts should include:
  - mission,
  - owned files,
  - do-not-touch list,
  - validation commands,
  - overlap reread rules if any.
- Avoid tracks that only lay plumbing without leaving a usable capability unless the wave explicitly requires it.
- Prefer disjoint write sets for true parallel waves.
- If one docs file is the canonical truth source, give it one owner.
- Docs-only tracks may start immediately but finish in a second truth pass
  after code tracks land.

### Dispatch follows a consistent cadence

Unless the active wave says otherwise, use this sequence:

1. Planning pass
- verify repo truth against the current wave docs and source tree
- decide what is in-wave versus follow-up debt

2. Packet maturity check
- if the next wave is still being shaped while the current one is active, keep it provisional
- write full gates/prompts only when the real leftovers are known

3. Packet audit
- write the packet, run a seam-focused audit against the live repo, and patch the smallest set of docs needed
- remove stale findings and already-landed work from active scope before dispatch

4. Coder dispatch
- produce bounded prompts with ownership, validation, and overlap reread rules
- if multiple teams can start immediately, add a short parallel-start note with:
  - who owns what,
  - which seams are single-owner,
  - which findings no team should reopen,
  - whether a docs track is intentionally a two-pass finisher

5. Integrator acceptance
- review the shared seams and replay path before attempting broad smoke coverage

6. Clean-room smoke
- verify runtime behavior with fresh or isolated state and record what "clean" meant

7. Polish pass
- improve startup flow, operator clarity, naming, and docs only after substrate truth is accepted

### Integration happens in two passes

1. Seam acceptance
- Review overlap files, additive contract changes, replay behavior, shared helpers, and protocol surfaces.
- Prefer seam-focused inspection over rereading the entire wave.

2. Clean-room smoke
- For final runtime acceptance, use fresh persisted state or an isolated new data root.
- Do not inherit old colonies, old transcripts, or old workspace files unless the test is explicitly about migration/replay.
- Record exactly how clean state was achieved.

### Acceptance reporting must classify what remains

- If the object model and replay path are sound, accept the substrate even if UI truth still needs a polish pass.
- Leftover issues should be labeled clearly as:
  - blocker,
  - surface-truth debt,
  - tuning debt,
  - docs debt,
  - runtime/deployment debt.
- Future-wave plans should inherit only what actually remains after acceptance, not stale debt carried forward by habit.
- A docs-truth finisher track will often land last. That is normal if it is
  integrating final code truth rather than guessing ahead of it.

---

## Audit Allowance

Each track may fix additional low-risk issues if all of the following are true:

- the bug is discovered while working inside that track's owned files
- the fix stays inside that track's ownership
- the fix does not create new architecture or cross-track contract changes
- the fix is reported explicitly in the track summary

This is allowance for polish, not permission to sprawl.
