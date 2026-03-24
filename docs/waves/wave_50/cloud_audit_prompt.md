Audit the live repo against the Wave 50 packet before implementation starts.

This is not a brainstorming exercise. It is a repo-truth check for the
template-learning seams, the cross-workspace knowledge plumbing, the
reliability hardening, and the product-identity guard.

## Core Questions

1. Does template_manager.py still load templates exclusively from YAML files?
2. Do Queen template tools (list_templates, inspect_template) still call
   load_templates() from disk without reading TemplateProjection?
3. Does MemoryEntryScopeChanged still only support thread-scope changes?
4. Does memory_store.py still hard-filter search by workspace_id?
5. Does ColonySpawned still lack a spawn_source provenance field?
6. Is the auto-template qualification threshold realistic given the current
   colony quality scoring?
7. Does the _ProviderCooldown still lack per-request retry caps and operator
   notification?

## Read First

1. docs/waves/wave_50/wave_50_plan.md
2. docs/waves/wave_50/acceptance_gates.md
3. docs/waves/wave_50/coder_prompt_team_1.md
4. docs/waves/wave_50/coder_prompt_team_2.md
5. docs/waves/wave_50/coder_prompt_team_3.md
6. AGENTS.md
7. CLAUDE.md

Then verify the relevant code seams directly.

## Verify These Specific Claims

### Claim A: Template consumers only read from disk

Check:

- src/formicos/surface/template_manager.py
- src/formicos/surface/queen_tools.py

Confirm that load_templates() reads YAML from config/templates/ and that
Queen tools call it without consulting TemplateProjection. This is the key
merge seam for Wave 50.

### Claim B: TemplateProjection schema is thinner than Wave 50 needs

Check:

- src/formicos/core/events.py (ColonyTemplateCreated)
- src/formicos/surface/projections.py (TemplateProjection class)

Confirm whether success_count, failure_count, task_category, fast_path,
target_files_pattern, max_rounds, budget_limit, and a learned flag are
present or absent. Confirm whether the packet is explicit enough about
which of these are additive event fields versus replay-derived projection
fields.

### Claim C: MemoryEntryScopeChanged is thread-only

Check:

- src/formicos/core/events.py
- src/formicos/surface/projections.py (_on_memory_entry_scope_changed)

Confirm that the event has only old_thread_id / new_thread_id / workspace_id
and the projection handler only updates thread_id. Confirm that adding
new_workspace_id is an additive backward-compatible change.

### Claim D: Memory search is workspace-locked

Check:

- src/formicos/surface/memory_store.py
- src/formicos/surface/knowledge_catalog.py

Confirm that search paths filter by workspace_id and do not support a
global-scope fallback.

### Claim E: ColonySpawned lacks spawn_source

Check:

- src/formicos/core/events.py

Confirm that ColonySpawned does not carry provenance about who initiated
the spawn. Assess whether adding spawn_source is additive and safe.

### Claim F: _ProviderCooldown is basic

Check:

- src/formicos/surface/runtime.py
- src/formicos/adapters/llm_anthropic.py

Confirm that the cooldown tracks failures per provider but lacks per-request
retry caps, operator notification, and health probes.

### Claim G: SQLite pragmas are close but not complete

Check:

- src/formicos/adapters/store_sqlite.py

Confirm current pragma set and verify whether mmap_size is absent and
busy_timeout is at 5000ms.

## Team-Split Audit

Check whether the proposed ownership is clean:

- Team 1: events, projections, runtime, template plumbing, reliability
- Team 2: knowledge browser, preview card, config memory, store, types
- Team 3: recipes, docs, measurement setup

Call out hidden overlap risk, especially in:

- src/formicos/surface/queen_tools.py (template merge logic)
- src/formicos/surface/projections.py (template + memory scope changes)
- src/formicos/surface/routes/knowledge_api.py (promotion route extension)
- frontend/src/state/store.ts (template + global scope handling)

## Product-Identity Audit

Answer explicitly:

1. Does each Must item help arbitrary operators?
2. Does the packet avoid external dependencies?
3. Does the packet distinguish operator-authored from learned templates?
4. Is global knowledge promotion operator-controlled?
5. Is auto-promotion flagging only, not auto-acting?

## Output Format

Return:

1. Findings first, ordered by severity, with file references
2. Repo-truth confirmation of the main Wave 50 seams
3. Any corrections needed before coder dispatch
4. A product-identity check
5. A short verdict: dispatch-ready or not, and why
