You own the Wave 50 configuration-memory and reliability backend track.

This is the learning-substrate and hardening track. You are not building the
frontend surfaces, and you are not inventing an external memory system. Your
job is to make the existing colony-completion path produce replay-safe learned
templates, merge template sources for Queen consumption, add global knowledge
scope plumbing, and harden the reliability surface.

## Mission

Land the backend-heavy parts of Wave 50:

1. replay-derived learned templates from qualifying colony completions
2. template consumer merge: disk-backed operator templates + projection
   learned templates
3. additive global knowledge scope on MemoryEntryScopeChanged
4. two-phase retrieval (workspace then global) in memory search
5. additive spawn_source on ColonySpawned
6. circuit breaker enrichment and SQLite pragma upgrades

The core rule still applies:

**If the benchmark disappeared tomorrow, would we still want this change in
FormicOS?**

Yes. A system that remembers what worked and degrades gracefully is a real
operator feature.

## Read First

1. AGENTS.md
2. CLAUDE.md
3. docs/waves/wave_50/wave_50_plan.md
4. docs/waves/wave_50/acceptance_gates.md
5. src/formicos/core/events.py
6. src/formicos/surface/projections.py
7. src/formicos/surface/template_manager.py
8. src/formicos/surface/queen_tools.py
9. src/formicos/surface/queen_runtime.py
10. src/formicos/surface/colony_manager.py
11. src/formicos/surface/task_classifier.py
12. src/formicos/surface/memory_store.py
13. src/formicos/surface/knowledge_catalog.py
14. src/formicos/surface/runtime.py
15. src/formicos/adapters/store_sqlite.py
16. src/formicos/adapters/llm_anthropic.py

Before editing, verify:

- how template_manager.py loads templates from disk
- how queen_tools.py list_templates / inspect_template call load_templates
- how MemoryEntryScopeChanged currently works (thread-scope only)
- how memory_store.py search filters by workspace_id
- what fields TemplateProjection currently has
- what fields ColonySpawned currently has

## Owned Files

- src/formicos/core/events.py
- src/formicos/surface/projections.py
- src/formicos/surface/template_manager.py
- src/formicos/surface/queen_tools.py
- src/formicos/surface/queen_runtime.py
- src/formicos/surface/colony_manager.py
- src/formicos/surface/task_classifier.py
- src/formicos/surface/memory_store.py
- src/formicos/surface/knowledge_catalog.py
- src/formicos/surface/routes/knowledge_api.py
- src/formicos/surface/runtime.py
- src/formicos/adapters/store_sqlite.py
- docs/contracts/events.py
- docs/contracts/types.ts
- frontend/src/types.ts (type changes only, not rendering)
- targeted tests for all tracks

## Do Not Touch

- frontend component files
- frontend/src/state/store.ts
- config/caste_recipes.yaml
- docs files outside the Wave 50 packet
- config/templates/ YAML files (do not auto-generate new ones)

Team 2 owns frontend rendering. Team 3 owns docs/recipes truth.

## Required Work

### Track A: Additive Event Fields

Add backward-compatible fields to existing events. No new event types.

ColonySpawned gains:

    spawn_source: str = Field(
        default="",
        description="Who initiated: queen, operator, api, or empty.",
    )

MemoryEntryScopeChanged gains:

    new_workspace_id: str = Field(
        default="",
        description="Target workspace. Empty = global scope.",
    )

Verify that older events without these fields deserialize cleanly with
defaults. Update contract mirrors in docs/contracts/.

ColonyTemplateCreated also needs additive fields so learned templates carry
enough truth for replay-safe reuse without pretending everything is already
in the event:

    learned: bool = Field(default=False, ...)
    task_category: str = Field(default="", ...)
    max_rounds: int = Field(default=25, ...)
    budget_limit: float = Field(default=1.0, ...)
    fast_path: bool = Field(default=False, ...)
    target_files_pattern: str = Field(default="", ...)

Important:

- `success_count` / `failure_count` should remain replay-derived projection
  stats from ColonyTemplateUsed + colony outcomes
- do not invent a new template event type

### Track B: Auto-Template On Colony Success

When a colony completes, check whether it qualifies for auto-templating:

- quality >= 0.7
- rounds >= 3
- spawn_source == "queen" (after Track A lands)
- no existing learned template for the same task_category + strategy

If qualified, emit ColonyTemplateCreated with:

- source_colony_id pointing to the successful colony
- castes and strategy from the colony
- additive event fields carrying reusable preview defaults:
  - budget_limit
  - max_rounds
  - task_category from classify_task(colony.task)
  - learned: true
  - fast_path
  - target_files_pattern

The template is stored in TemplateProjection via replay. Do NOT write
YAML to config/templates/.

Implementation seam:

- the qualification check should happen in colony_manager.py after quality
  computation is available and before or within `_post_colony_hooks()`
- at that point you already have the key data needed for qualification:
  quality, round count, colony.task, colony.strategy, and the colony's
  replay-visible spawn provenance after Track A lands
- prefer this real completion seam over inventing a second post-hoc scan

TemplateProjection needs additive fields:

- success_count: int = 0
- failure_count: int = 0
- task_category: str = ""
- fast_path: bool = False
- target_files_pattern: str = ""
- learned: bool = False
- max_rounds: int = 25
- budget_limit: float = 1.0

Update _on_colony_template_created and _on_colony_template_used handlers.
Be explicit in code/comments about which fields are event-carried vs
replay-derived.

Important replay detail:

- `success_count` / `failure_count` are NOT increments on
  ColonyTemplateUsed alone
- the current `_on_colony_template_used` path should continue to track
  `use_count`
- success/failure stats must be updated from colony completion/failure
  truth by cross-referencing `colony.template_id`
- this is a cross-event projection update: template use establishes the
  link, colony completion/failure resolves the outcome

### Track C: Template Consumer Merge

template_manager.py load_templates() currently reads only from disk.

Add a merge path: load_templates() returns disk YAML templates as before.
A new function or parameter allows callers to also receive projection-
derived learned templates. Queen tools (list_templates, inspect_template)
merge both sources.

Important: do not break existing callers. The merge should be additive.
Disk templates and learned templates should be distinguishable by the
learned flag.

### Track D: Template-Aware Preview

When the Queen previews a task:

1. classify_task() returns category
2. Search TemplateProjection for learned templates matching category
3. If a match exists with success_count > 0, populate preview defaults
4. Pass template_id and template_name to the preview response for
   Team 2 to annotate the preview card

This should be a lightweight lookup in queen_runtime.py before
calling the existing preview path, not a new subsystem.

### Track E: Global Knowledge Scope

Add workspace-to-global promotion handling:

1. Extend _on_memory_entry_scope_changed in projections.py:
   - if new_workspace_id is present and empty, mark entry as global
   - add a "scope" field to the memory_entries dict: "thread" | "workspace" | "global"

2. Extend memory_store.py search:
   - after workspace-filtered search, also search global entries
   - global entries get a slight relevance discount

3. Extend knowledge_catalog.py search:
   - two-phase: workspace first, then global if budget remains
   - deduplicate across phases

4. Extend the existing promotion route in knowledge_api.py:
   - current route already emits MemoryEntryScopeChanged for
     thread->workspace promotion
   - expand it to support workspace->global promotion
   - keep the operator action replay-safe and backend-owned
   - Team 2 should call this route, not fabricate frontend-only events
   - today the route returns ALREADY_WORKSPACE_WIDE when `thread_id` is
     empty; that guard must be refined rather than left in place
   - add an explicit request parameter such as
     `target_scope: "workspace" | "global"` so the route can distinguish:
       - thread -> workspace promotion
       - workspace -> global promotion
   - when global is requested, emit MemoryEntryScopeChanged with the new
     additive `new_workspace_id=""` field instead of returning an error

### Track F: Reliability Hardening

1. Extend _ProviderCooldown in runtime.py:
   - add max_retries_per_request (default 3)
   - add optional notify_callback for cooldown activation
   - wire notify_callback to emit a QueenMessage with intent=notify

2. Extend LLMRouter.route():
   - track retry count per request
   - stop after max_retries_per_request across all providers

3. SQLite pragmas in store_sqlite.py:
   - add PRAGMA mmap_size=268435456
   - increase busy_timeout from 5000 to 15000

## Hard Constraints

- No new event types
- No YAML generation into config/templates/
- No external dependencies
- No embedding-based template matching in this wave
- No auto-promotion of knowledge entries
- No LLM-based template generation or evaluation

## Validation

Run at minimum:

1. python scripts/lint_imports.py
2. targeted tests for:
   - ColonyTemplateCreated additive field replay / backward compatibility
   - auto-template qualification and emission
   - template merge (disk + projection)
   - template-aware preview lookup
   - global scope promotion and retrieval
   - knowledge_api promotion route for workspace->global
   - circuit breaker per-request cap
   - SQLite pragma changes
3. python -m pytest tests/unit/test_restart_recovery.py -q
   (backward compatibility for new event fields)

## Summary Must Include

- exact additive fields added to ColonySpawned and MemoryEntryScopeChanged
- exact additive fields added to ColonyTemplateCreated
- whether contract mirrors were updated
- how learned templates are distinguished from operator templates
- how template merge works for Queen consumers
- how template-aware preview populates defaults
- how global scope is represented in memory entries
- how the knowledge promotion route was extended
- how two-phase retrieval works
- circuit breaker and pragma changes
- what you explicitly kept out to stay bounded
