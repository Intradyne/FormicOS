# Operator's Guide to FormicOS

A practical guide for operators running FormicOS â€” from first workspace to
production knowledge management.

---

## Getting Started

### Prerequisites

- Python 3.12+ with `uv` package manager
- Docker Engine 24+ with Compose V2 (for containerized deployment)
- GPU with 24+ GB VRAM (recommended) or cloud API keys
- NVIDIA Container Toolkit (for local GPU inference)

For detailed deployment instructions including GPU setup, model downloads,
and persistence rules, see [DEPLOYMENT.md](DEPLOYMENT.md).

### Installation

```bash
uv sync                    # Install dependencies
python -m formicos         # Run locally
# or
docker compose up          # Run with Docker
```

### Creating a workspace

When FormicOS starts, create your first workspace via the Queen chat:

> "Create a workspace called my-project."

The Queen will set up the workspace with default configuration. You can
customize model assignments, budgets, and execution policies.

---

## Knowledge System Overview

FormicOS automatically builds institutional knowledge from colony work.

### A note on naming: "Memory" vs "Knowledge"

The operator-facing product uses "Knowledge" consistently: Knowledge
browser, knowledge entries, knowledge lifecycle. The backend event stream
uses "Memory" in several frozen event names (`MemoryEntryCreated`,
`MemoryConfidenceUpdated`, `MemoryEntryScopeChanged`, `MemoryEntryMerged`)
because these names were established before the terminology settled and
cannot be renamed without breaking replay compatibility.

The mapping is 1:1. A "memory entry" in the event log is a "knowledge
entry" in the UI and operator docs. When you see `Memory*` in event
names, logs, or projections, it refers to the same knowledge entries
visible in the Knowledge browser.

Similarly, the store property `skillBankStats` is a legacy internal name
for what the UI displays as knowledge statistics. The wire contract is
frozen; only the operator-facing label changed.

For a full mapping table and the complete replay-safety classification of
all capabilities, see [REPLAY_SAFETY.md](REPLAY_SAFETY.md).

### How knowledge is created

1. **Colony completes** â†’ archivist extracts skills and experiences
2. **Transcript harvest** â†’ scans raw output for bug fixes, conventions, configs
3. **Security scan** â†’ 5-axis scan rejects entries with credential leakage
4. **Dedup check** â†’ prevents near-duplicate entries (cosine threshold 0.92)
5. **Event emission** â†’ `MemoryEntryCreated` event persisted and indexed

### Entry types and sub-types

| Type | Sub-types | Description |
|------|-----------|-------------|
| **Skill** | technique, pattern, anti_pattern | Reusable knowledge |
| **Experience** | decision, convention, learning, bug | Observed outcomes |

### How knowledge is scored

Retrieval uses a 6-signal composite score (all normalized to [0, 1]):

| Signal | Weight | What it measures |
|--------|--------|-----------------|
| Semantic similarity | 0.38 | How well the entry matches the query |
| Thompson Sampling | 0.25 | Bayesian exploration/exploitation balance |
| Freshness | 0.15 | How recently the entry was created |
| Status bonus | 0.10 | Verified > candidate > stale |
| Thread bonus | 0.07 | Same-thread entries get a boost |
| Co-occurrence | 0.05 | Entries frequently accessed together |

### Decay classes

Each entry has a decay class that controls how fast confidence fades:

| Class | Decay rate (Î³) | Half-life | Use for |
|-------|---------------|-----------|---------|
| ephemeral | 0.98 | ~34 days | Task-specific context |
| stable | 0.995 | ~139 days | Domain knowledge, patterns |
| permanent | 1.0 | Never | Architectural decisions, invariants |

### Confidence tiers

The Knowledge browser shows confidence tier badges:

| Tier | Criteria |
|------|----------|
| **HIGH** | Mean â‰¥0.70 and CI width <0.20, with 3+ observations |
| **MODERATE** | Mean â‰¥0.45, with 3+ observations |
| **LOW** | Mean <0.45, with 3+ observations |
| **EXPLORATORY** | Fewer than 3 observations |
| **STALE** | Entry has been marked stale |

### Operator overlays and annotations

Operators can co-author the shared brain through replayable local overlays:

- **Pin / unpin** - protect an entry from fading out of retrieval on this
  instance without changing the canonical Beta posterior
- **Mute / unmute** - hide an entry from retrieval on this instance while
  keeping it visible in the browser and history views
- **Invalidate / reinstate** - mark an entry as locally rejected or restore it
  without silently changing shared confidence truth
- **Annotate** - attach operator notes such as "outdated as of 2026-03" or
  "prefer approach X in this workspace"

These actions survive replay, but they are local-first by default. They do
not automatically federate and they do not emit confidence mutations unless a
later explicit workflow promotes the judgment into shared truth.

### Audit and completion surfaces

Completed colonies now surface a structured audit view and a validator-aware
completion state:

- **Done (validated)** - task-specific validator passed
- **Done (unvalidated)** - colony completed, but no validator confirmed success
- **Stalled** - governance force-halted or the colony otherwise failed to
  complete

The colony audit view focuses on replay-safe truth: knowledge used,
directives, governance decisions, escalation history, redirect history, and
validator state. Runtime-only internals that were never persisted are
intentionally not shown as exact history.

---

## Proactive Intelligence

Current repo state: the briefing pipeline now includes 14 deterministic rules
across knowledge health, performance, evaporation, branching, and earned
autonomy recommendations. The older "7 rules" phrasing below only covers the
original knowledge-health subset.

The system generates intelligence briefings with 14 deterministic rules.
No LLM calls are made; briefings complete in <100ms under normal workspace sizes.

### Insight categories

| Category | Severity | What it means | What to do |
|----------|----------|--------------|------------|
| **Contradiction** | action_required | Two verified entries have opposite conclusions | Review and resolve before spawning colonies |
| **Confidence decline** | attention | Entry alpha dropped >20% from peak | Review entry for accuracy |
| **Federation trust drop** | attention | A peer's trust score fell below 0.5 | Review recent entries from that peer |
| **Coverage gap** | attention/info | Queries in a domain return irrelevant results | Spawn a research colony |
| **Stale cluster** | attention | A co-occurrence cluster has all high-error entries | Archive or update the cluster |
| **Merge opportunity** | info | Two entries share high domain and title overlap | Merge if redundant |
| **Federation inbound** | info | New knowledge from a peer in an uncovered domain | Review for relevance |
| **Strategy efficiency** | info | A strategy underperforms the best observed option | Prefer the higher-quality strategy |
| **Diminishing rounds** | attention | Colonies run long without quality gain | Lower round limits or adjust composition |
| **Cost outlier** | info | A colony costs far more than comparable work | Review tier/config choice |
| **Knowledge ROI** | attention | Spend is not yielding reusable knowledge | Revisit strategy or task framing |
| **Evaporation recommendation** | info | A domain's observed half-life differs from defaults | Review domain-specific decay suggestions |
| **Branching stagnation** | attention | Search diversity is collapsing around one attractor | Intervene before repeated failures compound |
| **Earned autonomy** | info | Operator behavior supports a policy promotion/demotion | Review the recommendation before changing policy |

### Where to see briefings

- **Queen prompt** â€” the Queen receives briefings automatically
- **MCP resource** â€” `formicos://briefing/{workspace_id}`
- **REST endpoint** â€” `GET /api/v1/briefing/{workspace_id}`
- **Frontend** â€” Proactive Briefing panel in the dashboard

---

## Federation

FormicOS instances can exchange knowledge via push/pull replication.

### Setup

```python
federation_manager.add_peer(
    peer_id="partner-instance",
    endpoint="https://partner:8080",
    replication_filter=ReplicationFilter(
        domain_allowlist=["python", "testing"],
        min_confidence=0.5,
    ),
)
```

### Trust model

Peer trust uses the 10th percentile of a Beta posterior (not the mean).
This penalizes uncertainty â€” a new peer with little history scores low.

- Trust evolves via validation feedback (success/failure after using
  foreign knowledge)
- Trust scores are visible in the Federation Dashboard
- Foreign knowledge is discounted by hop count: `trust * 0.7^hops`, capped so
  federated evidence never outweighs local knowledge on its own
- Retrieval also applies a federated status penalty so weak foreign candidate
  entries do not outrank strong local verified entries

### Conflict resolution

When contradictory entries arrive from different instances:

1. **Pareto dominance** â€” clear winner on 2+ criteria â†’ auto-resolve
2. **Adaptive threshold** â€” composite score comparison â†’ pick higher
3. **Competing hypotheses** â€” neither wins â†’ both kept for operator review

### Monitoring

The Federation Dashboard shows:
- Peer trust scores with visual bars
- Sync status and pending events
- Recent conflicts with resolution methods
- Entry flow counts (sent/received per peer)

---

## Maintenance

### Automatic (daily schedule)

- **Dedup consolidation** â€” merges near-duplicate entries
- **Stale sweep** â€” marks entries not accessed in 90 days as stale
- **Co-occurrence decay** â€” decays and prunes old co-occurrence weights
- **Distillation candidate identification** â€” flags dense co-occurrence
  clusters for future synthesis

### Manual (via Queen or API)

```
query_service(service_type="service:consolidation:dedup")
query_service(service_type="service:consolidation:stale_sweep")
query_service(service_type="service:consolidation:contradiction")
query_service(service_type="service:consolidation:confidence_reset")
```

The **confidence reset** handler resets stuck entries (50+ observations,
mean between 0.35-0.65) back to the Beta(5, 5) prior.

---

## Troubleshooting

### Knowledge entries not appearing

1. Check that the colony completed successfully (extraction only runs on success)
2. Verify the security scan passed (`scan_status` is not `high` or `critical`)
3. Check if the entry was deduped against an existing entry

### Confidence stuck at ~50%

Entries with many observations but a mean near 0.5 may have a dominant
prior. Use the confidence reset handler to reset to Beta(5, 5).

### Federation entries not syncing

1. Verify network connectivity between instances
2. Check replication filter settings (domain allowlist, min confidence)
3. Verify the entry's confidence exceeds the filter's `min_confidence`

### Proactive briefing shows no insights

This is normal for a healthy knowledge system. Insights only surface when
the deterministic rules detect actionable conditions (contradictions,
staleness, branching collapse, performance drift, and similar issues).

---

## Configuration Reference

### Key files

| File | Purpose |
|------|---------|
| `.env` | Environment variables (LLM keys, GPU config, ports) |
| `config/formicos.yaml` | Model routing, tier definitions, context windows |
| `config/caste_recipes.yaml` | Caste prompts, tool lists, model assignments |
| `config/templates/` | Colony templates (7 built-in) |
| `docker-compose.yml` | Docker stack definition |

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full configuration reference.

### Key constants (knowledge_constants.py)

| Constant | Value | Description |
|----------|-------|-------------|
| `PRIOR_ALPHA` | 5.0 | Beta distribution prior alpha |
| `PRIOR_BETA` | 5.0 | Beta distribution prior beta |
| `MAX_ELAPSED_DAYS` | 180 | Cap on gamma-decay elapsed days |
| `GAMMA_RATES` | ephemeral=0.98, stable=0.995, permanent=1.0 | Per-class decay rates |
| `COMPOSITE_WEIGHTS` | semantic=0.38, thompson=0.25, freshness=0.15, status=0.10, thread=0.07, cooccurrence=0.05 | Retrieval scoring weights (overridable per workspace) |

---

## Autonomy Configuration

### Autonomy levels

| Level | Behavior |
|-------|----------|
| `suggest` | Briefing shows insights and SuggestedColony data; no auto-dispatch (default) |
| `auto_notify` | Auto-dispatch for categories listed in `auto_actions`; operator notified |
| `autonomous` | All eligible categories auto-dispatch within budget/cap limits |

### Earned autonomy recommendations

FormicOS tracks operator follow-through and can recommend promoting or
demoting specific insight categories. Thresholds are asymmetric â€” earning
trust is harder than losing it:

- **Promotion** requires â‰¥5 follow-throughs in a category (harder to earn)
- **Demotion** triggers at â‰¥3 kills or high negative feedback (easier to lose)
- Recommendations are advisory â€” they do not silently change workspace policy
- Dismissals are remembered for a 7-day cooldown window
- Accepted changes still flow through normal workspace configuration

### Maintenance policy fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `autonomy_level` | AutonomyLevel | `suggest` | Controls dispatch behavior |
| `auto_actions` | list[str] | `[]` | Categories to auto-dispatch: `contradiction`, `coverage`, `staleness`, `distillation` |
| `max_maintenance_colonies` | int | 2 | Max concurrent maintenance colonies per workspace |
| `daily_maintenance_budget` | float | 1.0 | Daily USD budget cap (resets at UTC midnight) |

### Directive usage

| Type | When to use |
|------|-------------|
| `context_update` | New information the colony should know about |
| `priority_shift` | Reprioritize what the colony focuses on |
| `constraint_add` | New hard constraint (use `urgent` priority for critical constraints) |
| `strategy_change` | Switch colony approach (e.g., from breadth-first to depth-first) |

Set `priority: "urgent"` for directives that must appear before the task
description. Normal priority directives appear after task context.

### Where to send directives

- **Colony detail view** â€” the directive panel appears automatically below
  the round history when a colony is running. This is the primary steering
  surface.
- **Queen chat** â€” a "Send Directive" toggle appears when colonies are
  running, allowing quick steering without navigating away from the chat.

### Weight tuning

Use `configure_scoring` MCP tool to set per-workspace retrieval weights:

```json
{
  "semantic": 0.43, "thompson": 0.25, "freshness": 0.15,
  "status": 0.10, "thread": 0.07, "cooccurrence": 0.0
}
```

- All 6 signals must be present; values must sum to 1.0
- Setting `cooccurrence: 0.0` disables co-occurrence boosting
- Higher `semantic` prioritizes embedding similarity over exploration
- View per-result breakdowns at `standard` or `full` retrieval tier via `ranking_explanation`

### Distillation

Enable by adding `"distillation"` to `auto_actions`. When dense co-occurrence
clusters are detected (â‰¥5 entries, avg weight >3.0), an archivist colony
synthesizes them. Review results via `KnowledgeDistilled` events. Distilled
entries have `decay_class="stable"` and elevated alpha.

---

## Colony Outcome Intelligence

Every completed colony produces a `ColonyOutcome` â€” a replay-derived summary
with quality score, cost, round count, knowledge extraction count, and
strategy used. No new events; outcomes are rebuilt from existing event log.

### Where to see outcomes

- **Colony detail view** â€” completed colonies show outcome badges (quality %,
  cost, extraction count)
- **REST endpoint** â€” `GET /api/v1/workspaces/{id}/outcomes?period=7d`
- **Proactive briefing** â€” four performance rules analyze outcomes:
  - **Strategy efficiency** â€” compares quality across strategies
  - **Diminishing rounds** â€” flags long-running low-quality colonies
  - **Cost outlier** â€” flags colonies costing >2.5x the workspace median
  - **Knowledge ROI** â€” flags spend without knowledge extraction

Outcome history also feeds:

- **Escalation reporting** - capability escalations through `routing_override`
  are tracked separately from provider fallback
- **Configuration intelligence** - recommendation surfaces that summarize
  which strategies, caste mixes, round ranges, and model tiers have worked best

### Configuration intelligence

The command center includes a Configuration Intelligence panel that summarizes
evidence-backed recommendations from colony outcomes and shows recent override
history. Treat it as an editable recommendation layer, not a hidden heuristic:
the system suggests what tends to work; the operator remains in charge.

### Maintenance posture

The command center shows the workspace's maintenance posture: autonomy level,
budget consumed vs. limit, active maintenance colonies. Budget consumption is
derived from completed maintenance-tagged colony outcomes.

---

## Execution Security

### Current posture

FormicOS uses two execution paths with different isolation levels:

| Path | Isolation | What it runs |
|------|-----------|-------------|
| **Sandbox** (`code_execute` tool) | Docker container: `--network=none`, `--memory=256m`, `--read-only` | Agent-authored code snippets |
| **Workspace executor** | Backend host process (no container) | Repo-backed commands: `git`, test runners, build tools |

The sandbox path provides basic container isolation. The workspace executor
runs on the backend host without isolation â€” this is the largest remaining
security gap.

### Docker socket access

The FormicOS container mounts `/var/run/docker.sock` to spawn sandbox
containers. This grants Docker daemon access. To mitigate:

- Set `SANDBOX_ENABLED=false` to disable sandbox spawning
- Remove the socket mount from `docker-compose.yml` to opt out entirely
- Consider Sysbox/gVisor runtimes for stronger nested-container isolation

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full security posture table
showing enforced controls vs. planned improvements.

### Budget controls

Colony-level budget limits exist (`budget_limit` per colony, default $5.00).
A basic budget gate stops model requests when remaining budget drops below
$0.10. Workspace-level budget aggregation and hierarchical enforcement are
not yet implemented.

---

## Adaptive Evaporation (Wave 42)

In stigmergic mode, pheromone weights decay toward 1.0 each round. The
evaporation rate is now adaptive rather than fixed:

| Condition | Rate | Effect |
|-----------|------|--------|
| Healthy exploration (high branching factor or no stalls) | 0.95 | Normal slow decay |
| Stagnation (low branching factor + convergence stalls) | 0.85-0.95 | Faster decay to break attractors |

The branching factor measures search diversity using `exp(entropy)` over
pheromone edge weights. When it drops below 2.0 and the colony has
convergence stalls, the evaporation rate interpolates linearly toward 0.85
to flatten the pheromone landscape and encourage exploration.

This is automatic and requires no operator configuration. The rate is always
bounded to `[0.85, 0.95]` and stall influence is capped at 4 rounds.

---

## Surgical Editing (Wave 47)

The `patch_file` tool lets Coder agents make precise search-and-replace
edits instead of rewriting entire files with `write_workspace_file`.

### Usage

```text
patch_file(
  path="src/app.py",
  operations=[
    {"search": "old_function_name", "replace": "new_function_name"},
    {"search": "import os\n", "replace": ""}
  ]
)
```

- Operations apply sequentially against an in-memory buffer
- The file is written only if **all** operations succeed
- Empty `replace` means deletion
- No regex — exact text matching only

### Failure contract

| Condition | Behavior |
|-----------|----------|
| Zero matches | Error with nearby context, line numbers, and closest partial match |
| Multiple matches | Error listing all matching locations with line numbers |
| Partial failure | File unchanged; error reports the failing operation index |

### When to use

Prefer `patch_file` for targeted changes (renaming, inserting, deleting
specific lines). Use `write_workspace_file` when creating new files or when
the majority of file content changes.

---

## Git Workflow Primitives (Wave 47)

Four first-class git tools replace shell-string construction for common
workspace git operations.

| Tool | Purpose | Parameters |
|------|---------|------------|
| `git_status` | Working tree status (staged, unstaged, untracked) | None |
| `git_diff` | Show changes | `path` (optional), `staged` (optional, default false) |
| `git_commit` | Stage all and commit | `message` (required) |
| `git_log` | Recent commit history | `n` (optional, default 10, max 50) |

### Safety boundaries

Wave 47 git tools exclude:

- Remote operations (push, pull, fetch)
- Force flags
- Rebase, cherry-pick, reset workflows
- Branch creation/switching (deferred to future wave)

All shell arguments are safely quoted. Commits stage all changes and commit
locally — no remote push.

---

## Fast Path (Wave 47)

Simple single-agent tasks can skip colony coordination overhead.

### How it works

When the Queen spawns a colony with `fast_path=true`:

- The colony runs with a single agent
- Pheromone routing, convergence scoring, and multi-agent topology are skipped
- Normal event emission and knowledge extraction are preserved
- The colony completes after the first round produces output

### Replay safety

`fast_path` is a field on the `ColonySpawned` event (default `false`).
Older events without the field replay as `fast_path=false`. The execution
mode choice survives replay.

### When the Queen uses it

The Queen considers `fast_path=true` for trivial tasks: quick lookups,
single-file changes, short Q&A. Complex multi-file work or tasks needing
reviewer feedback should use the normal colony path.

---

## Preview (Wave 47)

Both spawn paths support a preview mode that returns a plan summary without
dispatching work.

### Usage

- `spawn_colony(preview=true)` — returns team composition, task, estimated
  cost, and fast-path mode indication
- `spawn_parallel(preview=true)` — returns DAG summary with task count,
  group count, and estimated cost

Preview is useful for operators who want to confirm the Queen's plan before
committing resources.

---

## Structural Context Refresh (Wave 47)

Coding colonies with `target_files` now get current workspace structure at
each round boundary, not just at colony start.

- Only colonies with non-empty `target_files` pay the refresh cost
- Refresh happens from round 2 onward (round 1 uses initial analysis)
- Changes from any source (including `workspace_execute`) are captured
- The refreshed structure appears as a visible `[Workspace Structure]`
  section in the Coder's round prompt

Non-coding colonies are unaffected.

---

## Grounded Specialists (Wave 48)

Wave 48 gives the Reviewer and Researcher castes real workspace access so
they can verify claims against code truth rather than reviewing only
summaries and knowledge-base echoes.

### Reviewer: read-only quality gate

The Reviewer can now:

- Browse workspace files (`list_workspace_files`)
- Read source code (`read_workspace_file`)
- See working tree status (`git_status`)
- Inspect diffs (`git_diff`)

The Reviewer still **cannot** mutate the workspace — no `write_workspace_file`,
`patch_file`, `workspace_execute`, or `git_commit`.

### Researcher: project-aware synthesis with targeted external lookups

The Researcher can now:

- Browse and read workspace files (same tools as Reviewer)
- Fetch targeted external URLs (`http_fetch`) when institutional knowledge
  has gaps — documentation pages, API references, etc.

The Researcher does **not** have `search_web` access. Broader web discovery
remains the Forager service's responsibility. If a Researcher identifies a
domain gap that needs systematic web acquisition, it should note this
explicitly so the operator or Queen can trigger a forage cycle.

**Tradeoff note:** The preferred design was a mediated `request_forage` tool
that would route Researcher queries through the Forager service's domain
trust, rate limits, and credibility scoring. This was deferred. The current
`http_fetch` fallback gives Researchers targeted URL access but bypasses
Forager provenance tracking.

### Minimal colony first

Queen guidance now defaults to the smallest viable team:

- **Trivial tasks** → single agent, `fast_path=true`
- **Simple code** → single coder (no reviewer unless independently needed)
- **Complex work** → multi-caste colony with coordination

This is a product rule: simple work should not pay multi-agent overhead.

---

## Conversational Colony (Wave 49)

Wave 49 begins the shift toward chat-first Queen orchestration. The
intended operator flow:

1. Type a task in Queen chat
2. See a structured preview card inline (team, cost, strategy)
3. Confirm or adjust inline
4. Watch bounded progress (Queen-authored summaries, not raw event spam)
5. Inspect a structured result card with deep links
6. Drill into audit, timeline, or colony detail only when needed

### What landed

- `QueenMessage` events carry optional structured metadata: `intent`
  (notify/ask), `render` (text/preview_card/result_card), and `meta`
  (structured payload). Additive, optional, replay-safe.
- **Preview cards** render inline in Queen chat showing task, team shape,
  strategy, fast-path badge, cost estimate, and target files. Confirm /
  Cancel / Open Full Editor actions available.
- **Result cards** render inline showing status (color-coded), rounds,
  cost, quality score, extracted knowledge count, and validator verdict.
  Deep-link buttons navigate to colony detail, audit, and timeline.
- **Ask/notify distinction:** ask messages show a left-border accent and
  "needs input" badge. Notify messages render at reduced opacity. Heuristic
  fallback treats messages ending with `?` as ask when no explicit intent
  is set.
- **Chat-first layout:** Queen chat is now the default primary surface
  (`chatExpanded = true`). Dashboard available via "Show Dashboard" toggle.
- **Compact status header** above chat shows running colony count, session
  cost, active plans, and knowledge count.
- **Confirm flow:** confirming a preview card dispatches the colony
  directly from stored preview parameters — no second LLM restatement
  needed. A visible confirmation message is recorded in the thread.
- Contract types (`PreviewCardMeta`, `ResultCardMeta`) defined in both
  backend and frontend.
- Queen recipe guidance reflects preview-first dispatch and ask-vs-notify
  conversational discipline.

### Backend metadata emission

The Queen runtime populates metadata on persisted thread messages:

- **Preview proposals** emit with `intent="notify"`, `render="preview_card"`,
  and a `meta` payload containing the full preview (team, cost, strategy,
  target files). The frontend renders this as an inline preview card.
- **Colony completions** emit with `intent="notify"`,
  `render="result_card"`, and a `meta` payload containing colony_id, task,
  status, rounds, cost, quality_score, skills_extracted, and
  contract_satisfied. The frontend renders this as an inline result card
  with deep links.

Cards reconstruct from persisted thread state — they survive refresh,
reconnect, and snapshot rebuilds.

### Queen thread compaction

Long Queen conversations degrade gracefully instead of hitting a hard
context wall. When thread history exceeds a token budget (6000 tokens),
older messages are compacted into a structured summary block:

- The 10 most recent messages are always kept in full
- Unresolved `ask` messages and active preview cards are pinned
- Older history compacts into a structured-metadata-first block
- No LLM summarizer — compaction is deterministic and replay-safe

### What was deferred

- Inline adjust controls — deferred in favor of the "Open Full Editor"
  escape hatch for complex parameter changes.

### Architectural notes

- Wave 49 added no new event types. The event union stayed at 62 at the end
  of that wave.
- Structured metadata rides on existing `QueenMessage` events via additive
  optional fields — this is the key contract move.
- No new runtime, external dependency, or intelligence subsystem was
  introduced. The Queen is not "smarter" — the presentation layer is
  being improved.
- The dashboard remains available. Chat-first is a layout priority change,
  not a dashboard deletion.

---

## Configuration Intelligence (Wave 50)

Wave 50 introduced a distinction between two kinds of colony templates:

### Operator-authored templates

These are the existing YAML files in `config/templates/`. You write them by
hand, describing a team shape, strategy, and parameters for a recurring task
type. The Queen checks `list_templates` before spawning and uses a matching
template when one fits.

There are currently 8 operator-authored templates in the repository.

### Learned templates

When the Queen spawns a colony and it succeeds above a quality threshold, the
system stores the decomposition as a replay-derived learned template. On
similar future tasks, the Queen proposes the template in the preview card.
The operator can accept, modify, or reject.

**Auto-template qualification rules:**

- Colony completed with quality >= 0.7
- Colony used 3+ rounds (fast_path one-shots are not interesting)
- Queen-spawned (`spawn_source` provenance on ColonySpawned)
- No template already exists for the same task category + strategy

**v1 template matching** is category-first: the task classifier assigns a
category, and templates are matched by category + usage/outcome stats.
Embedding similarity for finer-grained matching is deferred.

### What shipped

- Additive event fields: `spawn_source` on ColonySpawned,
  learned-template fields on ColonyTemplateCreated (`learned`,
  `task_category`, `max_rounds`, `budget_limit`, `fast_path`,
  `target_files_pattern`)
- Auto-template creation on qualifying colony completions
- Template consumer merge: `load_all_templates()` reads from both disk
  YAML and replay-derived TemplateProjection (disk wins on ID collision)
- TemplateProjection enrichment with success_count, failure_count
  cross-derived from colony outcomes
- Task classifier integration: category-first lookup in preview and
  auto-template
- Preview cards display template name and source when a template is used
  ("Based on previous success: [name]" with learned/operator badge and
  success/failure counts)
- Workspace-scoped template API: `GET /api/v1/workspaces/{id}/templates`
  returns merged operator + learned templates

Learned templates are replay-derived by design -- they live in
TemplateProjection, not as auto-generated YAML files.

---

## Cross-Workspace Knowledge (Wave 50)

Wave 50 added a global knowledge tier above workspace scope.

### Retrieval order

1. Task context (thread-scoped entries)
2. Workspace knowledge
3. Global knowledge (0.9x discount to avoid crowding out local knowledge)

### Explicit promotion

The operator selects a knowledge entry and clicks "Promote to Global." This
emits a `MemoryEntryScopeChanged` event with the new scope, making the entry
visible in all workspace searches.

Both promotion paths are operational:
- Thread to workspace: standard promotion
- Workspace to global: uses the additive `new_workspace_id` field on
  `MemoryEntryScopeChanged` (empty string signals global scope)

### Auto-promotion candidates (flagged, not auto-promoted)

Entries meeting these criteria are flagged as global promotion candidates:

- Used successfully across 3+ different workspaces
- Stable or permanent decay class
- Confidence >= 0.7
- Forager-sourced documentation preferred over task learnings

Candidates surface as suggestions in the Knowledge browser with a hint
badge. The operator decides. No auto-promotion in v1.

### What shipped

- Additive `new_workspace_id` field on MemoryEntryScopeChanged
- Global scope handling in projections (sets `scope="global"`, clears
  `workspace_id`)
- Two-phase retrieval (workspace then global) with 0.9x global discount
- Knowledge promotion route accepts `target_scope="global"`
- Knowledge listing scope filter (API accepts `scope` query param;
  catalog includes global entries in workspace listings)
- Frontend global scope badges, "Promote to Global" button, "Global
  Only" filter, and promotion candidate hint badge

### Architectural notes

- No new event types were added. Global scope uses additive fields on the
  existing MemoryEntryScopeChanged event.
- No external memory system is required.
- The global discount prevents global entries from outranking workspace-local
  knowledge of equal quality.

---

## Web Foraging (Wave 44)

FormicOS can actively seek knowledge from the web when retrieval exposes gaps.
The Forager is a bounded, auditable acquisition channel â€” not a crawler or
autonomous browser.

### How it works

1. **Gap detection** â€” Retrieval identifies low-confidence results, coverage
   gaps, or stale clusters during live colony work.
2. **Search** â€” The system issues a bounded web search using deterministic
   query templates derived from the gap signal.
3. **Fetch** â€” Pages are fetched through a controlled egress gateway with
   rate limits, domain controls, and size limits.
4. **Extract** â€” Content is extracted from HTML (via trafilatura), scored for
   quality using deterministic heuristics (no LLM), and deduplicated.
5. **Admit** â€” Entries that pass admission scoring are created through the
   normal `MemoryEntryCreated` path at `candidate` status with conservative
   priors.
6. **Lifecycle** â€” From this point, forager-sourced entries follow the same
   lifecycle as colony-produced knowledge: Thompson Sampling retrieval,
   confidence evolution, decay, and operator overlays.

### Trigger modes

| Mode | When it fires | Priority | Status |
|------|---------------|----------|--------|
| **Reactive** | Low-confidence retrieval during live colony work | Highest | Operational |
| **Proactive** | Briefing rules detect stale clusters, coverage gaps | Background | Operational |
| **Operator** | Manual operator request | Direct control | Operational |

> **Note:** Proactive foraging runs on the scheduled maintenance cadence. The
> briefing pipeline emits bounded `forage_signal` metadata, the maintenance
> dispatcher evaluates those signals under the workspace autonomy policy, and
> eligible signals are handed to `ForagerService` as background work.

### What the Forager cannot do in v1

- No browser automation (Playwright/Level 3 fetch)
- No crawling or spidering
- No authenticated web access
- No autonomous browsing
- No fetching arbitrary URLs â€” only search-result URLs plus operator-approved
  domain overrides

### Operator domain controls

Operators can control which domains the Forager trusts or distrusts:

| Action | Effect |
|--------|--------|
| **trust** | Allow fetching from this domain |
| **distrust** | Block all fetching from this domain |
| **reset** | Remove the override, return to default behavior |

Domain overrides are replayable events (`ForagerDomainOverride`) that survive
restart. They extend the existing operator co-authorship model (pin/mute/
invalidate) to domain-level scope.

### Domain strategy memory

The Forager learns which fetch level works best per domain. After repeated
failures at Level 1 (httpx + trafilatura), it escalates to Level 2 (fallback
extractors). Domain strategies are persisted via `DomainStrategyUpdated`
events and survive replay.

### Forager provenance

Forager-sourced entries carry auditable metadata:

- `source_url` â€” where the content came from
- `fetch_timestamp` â€” when it was fetched
- `fetch_level` â€” which extraction level succeeded
- `forager_trigger` â€” what triggered the forage (reactive/proactive/operator)
- `forager_query` â€” the search query used
- `quality_score` â€” deterministic content quality score

Forager provenance also carries normalized `source_domain` and a
`source_credibility` tier score. Admission blends that credibility into the
provenance dimension, so authoritative documentation starts with a stronger
provenance signal than an unknown blog while still entering at `candidate`
status through the same lifecycle gate.

### Replay surface

The Forager added exactly 4 event types in Wave 44 (union grew from 58 to 62):

| Event | Purpose |
|-------|---------|
| `ForageRequested` | Records when/why a forage cycle started |
| `ForageCycleCompleted` | Summary of what the cycle accomplished |
| `DomainStrategyUpdated` | Learned fetch-level preference per domain |
| `ForagerDomainOverride` | Operator domain trust/distrust/reset action |

Individual search requests, fetch attempts, and content rejections are
structured-logged but stay log-only in v1.

### What remains deferred

- **Near-duplicate detection** -- only SHA-256 exact hash dedup exists.
  Rephrased content from multiple sources is not caught.
- **Search consistency** -- web search requests use their own httpx client,
  not the full EgressGateway policy surface, so search traffic does not get
  the same domain/robots/rate-limit treatment as fetch traffic.
- **Operator forage API** -- four REST endpoints provide operator control:
  `POST .../forager/trigger` (manual forage), `POST .../forager/domain-override`
  (trust/distrust/reset), `GET .../forager/cycles` (cycle history),
  `GET .../forager/domains` (domain strategies and overrides).
  Web-sourced entries display provenance in the knowledge browser (source URL,
  domain, credibility, quality score). A richer dedicated UI beyond these
  API endpoints and browser badges remains future work.

Standard and full retrieval tiers surface `competing_with` context when a
retrieved entry has an unresolved competing hypothesis in the replay-derived
projection state.


## Demo Workspace

A pre-seeded demo workspace lets new operators explore FormicOS capabilities
in a single session.

### Creating a demo workspace

Send `POST /api/v1/workspaces/create-demo`. This creates a real workspace
with:

- **10 knowledge entries** across two domains (Python API patterns,
  Authentication)
- Multiple confidence tiers and decay classes
- **One deliberate contradiction** (JWT vs. server-side sessions) â€” the
  proactive briefing flags this as `action_required`
- **auto_notify maintenance policy** â€” contradictions auto-dispatch when
  detected

### Demo walkthrough

1. Create the demo workspace (via API or future "Try Demo" button)
2. Open the **Intelligence Briefing** â€” you should see the contradiction
3. Ask the Queen to resolve it, or let auto-dispatch handle it
4. Watch the colony execute, extract knowledge, and update confidence
5. Re-check the briefing â€” the system is learning

### Suggested demo task

The template includes a suggested task: "Build me an email validator library
with unit tests." This exercises colony execution, knowledge retrieval,
extraction, and code artifacts.
