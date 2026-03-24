# Wave 50 -- The Learning Colony

## Theme

The system starts improving itself through its own experience. When the Queen
decomposes a task and the colony succeeds, she remembers how. When knowledge
proves useful across multiple workspaces, it becomes globally available. When
cloud APIs fail, the system degrades gracefully instead of burning money.

## Identity Test

Would a real operator want this if the benchmark disappeared tomorrow?

Yes. Nobody wants to re-explain their preferred team shape for the third
identical task. Nobody wants to manually copy knowledge between projects.
Nobody wants a $40 API bill from a retry storm.

## Prerequisite

Wave 49 accepted. Chat-first orchestration works. Queen messages carry
structured metadata (intent/render/meta). Thread compaction keeps long
sessions stable.

## Contract

- No new event types (hard rule -- union stays at 62)
- Additive fields on existing events ARE allowed when the current schema
  is not enough
- No new external dependencies
- No NeuroStack, no NemoClaw, no outer runtime

## Repo Truth At Wave Start

### Templates exist but are file-backed only

- ColonyTemplateCreated / ColonyTemplateUsed events exist
- TemplateProjection exists in projections.py (id, name, description,
  castes, strategy, source_colony_id, use_count)
- template_manager.py (158 lines) loads/saves YAML from config/templates/
- queen_tools.py imports load_templates() from disk
- config-memory.ts (237 lines) shows outcome-derived recommendations and
  overrides but does not surface templates directly
- 8 operator-authored YAML templates exist in config/templates/

Template consumers (Queen list_templates, inspect_template) currently read
from disk only. They do NOT read from TemplateProjection in projections.

### Knowledge is workspace-scoped only

- MemoryEntryCreated carries workspace_id
- memory_store.py search hard-filters by workspace_id
- knowledge_catalog.py search always filters by workspace_id
- MemoryEntryScopeChanged is thread-scoped only (old_thread_id,
  new_thread_id, workspace_id) -- no workspace-to-global semantics
- Projection handler (line 1504) only updates entry["thread_id"]

Global scope does NOT exist in current repo truth. It needs additive
fields on MemoryEntryScopeChanged plus plumbing in projections, memory
store, and knowledge catalog.

### ColonySpawned lacks provenance

- ColonySpawned does not carry who initiated the spawn
- "Queen-spawned" is inferable from thread context but not first-class
  replay truth
- An additive spawn_source field is the cleanest fix

### Reliability substrate is real

- _ProviderCooldown in runtime.py (line 95): sliding-window failure
  tracking with auto-cooldown (3 failures in 60s = 120s cooldown)
- LLMRouter._DEFAULT_FALLBACK: gemini -> local -> anthropic
- Anthropic adapter has _post_with_retry() with exponential backoff
- SQLite pragmas: WAL, synchronous=NORMAL, busy_timeout=5000,
  cache_size=-64000, wal_autocheckpoint=1000

---

## Pillar 1: Configuration Memory (Must)

### What it does

When the Queen decomposes a task and the colony succeeds above a quality
threshold, the system stores the decomposition as a replay-derived learned
template. On similar future tasks, the Queen proposes the template in the
preview card. The operator can accept, modify, or reject.

### Key design decisions

**Learned templates are replay-derived, not file-backed.**

Operator-authored templates stay in config/templates/ as YAML files.
Learned templates live in TemplateProjection (replay-derived from
ColonyTemplateCreated events). Template consumers (queen_tools.py
load_templates, list_templates, inspect_template) must merge both
sources: disk-backed operator templates AND projection-derived learned
templates.

This avoids auto-generating YAML files in the config directory.

**Auto-template qualification threshold:**

- Colony completed with quality >= 0.7
- Colony used 3+ rounds (fast_path one-shots are not interesting)
- Queen-spawned (requires additive spawn_source field on ColonySpawned)
- No template already exists for this task category + strategy combination

**v1 template matching is category-first:**

- Must: category match from task_classifier.py + usage/outcome stats
- Should (later): embedding similarity for finer-grained matching

**Learned-template truth must be explicit about what is emitted vs derived.**

TemplateProjection currently has: id, name, description, castes,
strategy, source_colony_id, use_count.

Wave 50 adds projection fields:

- success_count
- failure_count
- task_category
- fast_path
- target_files_pattern
- learned (boolean to distinguish from operator templates)
- max_rounds
- budget_limit

The packet should not pretend all of these already travel through
ColonyTemplateCreated. For v1:

- `success_count` / `failure_count` are replay-derived from
  ColonyTemplateUsed plus colony outcomes
- the learned-template identity and reusable preview defaults should be
  carried explicitly via additive fields on ColonyTemplateCreated where
  needed, rather than hand-waved as "cheap wiring"

### Additive event field

Add to ColonySpawned (backward-compatible, defaults to empty):

    spawn_source: str = Field(
        default="",
        description="Who initiated: queen, operator, api, or empty.",
    )

Add to ColonyTemplateCreated (backward-compatible, defaults shown here as
illustrative packet truth):

    learned: bool = Field(
        default=False,
        description="True for replay-derived learned templates, false for operator-authored templates.",
    )
    task_category: str = Field(
        default="",
        description="Category from classify_task() used for v1 matching.",
    )
    max_rounds: int = Field(
        default=25,
        description="Default rounds when reusing this template.",
    )
    budget_limit: float = Field(
        default=1.0,
        description="Default budget when reusing this template.",
    )
    fast_path: bool = Field(
        default=False,
        description="Whether the learned template prefers fast_path.",
    )
    target_files_pattern: str = Field(
        default="",
        description="Optional compact target-files pattern for preview defaults.",
    )

### How the Queen uses templates

1. Queen receives task from operator
2. classify_task() returns category
3. Search templates by category match, prefer higher success_count
4. If strong match exists, populate preview with template defaults
5. Preview card shows "Based on previous success: [template name]"
6. Operator confirms, modifies, or ignores
7. After colony completes, update success_count or failure_count

---

## Pillar 2: Cross-Workspace Knowledge (Must)

### What it does

Add a global knowledge tier above workspace scope. Retrieval order:
task context -> workspace -> global. Promotion is conservative and
explicit.

### Key design decisions

**Global scope needs additive schema work.**

MemoryEntryScopeChanged currently has: entry_id, old_thread_id,
new_thread_id, workspace_id. It only supports thread-scope changes.

Wave 50 adds an additive field for workspace-scope promotion:

    new_workspace_id: str = Field(
        default="",
        description="Target workspace. Empty string = global scope.",
    )

The projection handler gains a new branch: if new_workspace_id is
present and empty, mark the entry as global-scoped. If non-empty,
move the entry to a different workspace.

**memory_store.py and knowledge_catalog.py gain two-phase retrieval:**

1. Search workspace-scoped entries (existing behavior)
2. If budget allows, search global entries (slightly discounted for
   scope distance)
3. Merge, deduplicate, rank by Thompson Sampling composite

The global discount prevents global entries from crowding out
workspace-specific knowledge.

**Explicit promotion (v1):**

- Operator selects a knowledge entry and clicks "Promote to Global"
- Calls the existing knowledge promotion surface, extended from
  thread->workspace to workspace->global in knowledge_api.py
- The route should accept an explicit target such as
  `target_scope = "workspace" | "global"` so a workspace-wide entry does
  not incorrectly trip the old "already workspace-wide" guard
- Emits MemoryEntryScopeChanged with new_workspace_id: ""
- Entry becomes visible in all workspace searches

The operator action path should be explicit in the packet. Team 2 should
not be forced to fabricate a frontend-only event dispatch trick.

**Auto-promotion candidates (Should, flagged not auto-promoted):**

- Entry used successfully across 3+ different workspaces
- Stable or permanent decay class
- Confidence >= 0.7
- Forager-sourced documentation preferred over task learnings

Candidates surface in the knowledge browser with a suggestion. The
operator decides. No auto-promotion in v1.

---

## Pillar 3: Reliability Hardening (Should)

### Circuit breaker enrichment

Extend _ProviderCooldown with:

- max_retries_per_request: total retry cap across all providers for a
  single LLM call (default 3)
- notify_callback: emit a QueenMessage with intent=notify when a
  provider enters cooldown, so the operator sees it in chat
- health_probe: lightweight check before resuming traffic after cooldown

Extend LLMRouter.route():

- Track retry count per request, not just per provider
- On Nth retry failure, return structured error instead of trying the
  next provider forever

### SQLite pragma upgrades

- Add: PRAGMA mmap_size=268435456 (256MB memory-mapped I/O)
- Increase: busy_timeout from 5000 to 15000
- Both are cheap, well-documented reliability improvements

---

## Team Assignment

### Team 1: Configuration Memory + Reliability Backend

Owns the learning substrate and reliability hardening.

Primary files:
- src/formicos/core/events.py (additive spawn_source on ColonySpawned,
  additive learned-template fields on ColonyTemplateCreated)
- src/formicos/surface/projections.py (template success/failure tracking,
  global scope handling in memory_entries)
- src/formicos/surface/queen_runtime.py (template lookup before preview,
  auto-template on colony success)
- src/formicos/surface/queen_tools.py (template-aware preview, merge
  disk and projection template sources)
- src/formicos/surface/colony_manager.py (emit ColonyTemplateCreated on
  qualifying completions)
- src/formicos/surface/template_manager.py (merge disk + projection
  templates in load_templates)
- src/formicos/surface/task_classifier.py (expose category for template
  matching)
- src/formicos/surface/routes/knowledge_api.py (extend promotion route
  from thread->workspace to workspace->global)
- src/formicos/surface/runtime.py (circuit breaker enrichment)
- src/formicos/adapters/store_sqlite.py (pragma upgrades)
- Tests for auto-template, template retrieval, global scope, circuit
  breaker, pragma changes

### Team 2: Cross-Workspace Knowledge Frontend + Template UX

Owns the operator surfaces for both features.

Primary files:
- frontend/src/components/knowledge-browser.ts (Promote to Global
  button, scope indicators, promotion candidates)
- frontend/src/components/fc-preview-card.ts (template annotation on
  preview cards)
- frontend/src/components/config-memory.ts (template success rate,
  learned vs operator template indicators)
- frontend/src/state/store.ts (handle global-scoped entries, template
  stats)
- frontend/src/types.ts (global scope field, template usage stats)

### Team 3: Recipes + Docs + Measurement

Owns guidance and measurement setup.

Primary files:
- config/caste_recipes.yaml (Queen prompt: mention template suggestions)
- CLAUDE.md, AGENTS.md, docs/OPERATORS_GUIDE.md
- Phase 0 measurement setup: caste-grounding ablation matrix
- Document auto-promotion candidate rules explicitly
- Document the operator-authored vs learned template distinction

---

## What Wave 50 Does NOT Include

- No new event types (union stays at 62)
- No LLM-based template generation
- No auto-promotion of knowledge (candidates flagged, operator decides)
- No embedding similarity for template matching in v1
- No DSPy/GEPA prompt optimization
- No DGM-style self-modification
- No NeuroStack or external memory system
- No event store snapshotting

---

## Smoke Test

1. Operator submits "refactor the auth middleware" in Workspace A
2. Queen proposes a plan, operator confirms, colony succeeds at quality 0.82
3. Colony completes -> system auto-stores a learned template
4. Operator submits "refactor the payment middleware" in same workspace
5. Queen preview card shows "Based on previous success" with previous team
   shape pre-filled
6. Operator confirms or adjusts
7. Operator discovers a useful Forager entry about Docker caching
8. Operator clicks "Promote to Global" in knowledge browser
9. In Workspace B, the entry appears in retrieval with a "Global" badge
10. Cloud provider goes down mid-colony
11. LLMRouter retries twice, enters cooldown, falls to local Qwen3
12. Queen chat shows a notify message about the outage
13. Colony completes on local model
14. Full CI remains clean

---

## After Wave 50

The compounding curve has two dimensions: accumulated domain knowledge
(knowledge base) AND accumulated orchestration knowledge (configuration
memory). Task 100 benefits from everything learned in tasks 1-99.

empower -> deepen -> harden -> forage -> complete -> prove ->
fluency -> operability -> conversation -> learning
