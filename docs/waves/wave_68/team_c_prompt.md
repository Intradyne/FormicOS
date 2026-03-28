# Wave 68 - Team C: Extension Contract & Routing

**Theme:** Make the Queen a better router by surfacing corpus coverage
declaratively through addon metadata and workspace taxonomy.

## Context

Read `docs/waves/wave_68/design_note.md` first. You are bound by all three
invariants. In particular, invariant 3 says the Queen is the router/composer
across sources.

Flexibility in this wave means the Queen can answer two questions without
hardcoded addon names:

- which source should I search?
- which addon should I refresh/reindex?

Read `CLAUDE.md` for hard constraints (event closed union, layer rules, etc.).
Read `AGENTS.md` for repo norms. This prompt overrides stale root
`AGENTS.md` for file ownership within this wave.

## Your Files (exclusive ownership)

- `src/formicos/surface/addon_loader.py` - `AddonManifest` field additions
- `addons/codebase-index/addon.yaml` - capability metadata
- `addons/docs-index/addon.yaml` - capability metadata
- `addons/git-control/addon.yaml` - capability metadata if truly meaningful
- `addons/proactive-intelligence/addon.yaml` - capability metadata if truly meaningful
- `src/formicos/surface/queen_tools.py` - `_list_addons()` text output +
  `set_workspace_tags`
- `config/caste_recipes.yaml` - Queen routing rule + tool list updates
- `src/formicos/surface/queen_runtime.py` - small tag injection at the top of
  `_build_thread_context()`
- `tests/unit/addons/test_addon_capability.py` - **new**
- `tests/unit/surface/test_workspace_taxonomy.py` - **new**

## Do Not Touch

- `src/formicos/surface/projections.py`
- `src/formicos/core/types.py`
- `src/formicos/core/events.py`
- `src/formicos/surface/knowledge_catalog.py`
- `src/formicos/surface/colony_manager.py`
- `_build_messages()` in `queen_runtime.py` - Team B owns
- `respond()` in `queen_runtime.py` - Teams A/B own
- any frontend files

## Overlap Coordination

- Team A inserts plan text at the bottom of `_build_thread_context()`. You only
  insert tags near the top after the goal line.
- Team A adds `mark_plan_step` to the Queen tool list. You also touch
  `caste_recipes.yaml` to add `set_workspace_tags` and routing guidance.
- Team B wants capability-backed addon coverage in the deliberation frame.
  Your `list_addons()` text and manifest metadata are the routing truth it
  should eventually prefer.

---

## Track 5: Addon Capability Metadata

### Problem

`_list_addons()` currently exposes mostly tool and handler inventory. That tells
the Queen what exists, but not what each addon actually covers. A strong router
needs model-visible answers to:

- what corpus type does this addon own?
- what files or paths does it cover?
- what is the primary search path?
- if the addon already supports refresh/reindex, how do I reach it?

Without that, the Queen has to guess and burn tool turns learning the shape of
the system.

### Implementation

**1. Extend `AddonManifest` with three optional fields.**

Add these fields in `addon_loader.py` with empty defaults:

```python
content_kinds: list[str] = Field(default_factory=list)
path_globs: list[str] = Field(default_factory=list)
search_tool: str = Field(default="")
```

This stays additive and backward-compatible.

Keep `content_kinds` free-form. Do not add a new enum for this wave.

**2. Update real addon manifests.**

Populate meaningful values for the addons that own corpora, especially:

- `addons/codebase-index/addon.yaml`
- `addons/docs-index/addon.yaml`

Only add metadata to `git-control` or `proactive-intelligence` if they truly
own a searchable corpus. Do not fabricate coverage.

Use the actual search tool names defined in each manifest.

**3. Make `_list_addons()` tell the Queen what matters.**

Update `_list_addons()` so the **text string** returned to the model includes a
capability summary per addon, for example:

```text
**docs-index**: Index and search workspace documentation
  Content: documentation
  Files: **/*.md, **/*.rst, **/*.txt
  Search via: search_docs
  Index via: incremental_reindex
```

Rules:

- capability data must be in the first tuple element (text), not hidden in a
  side dict
- group by addon, not by raw tool spec alone
- if an addon already exposes an obvious refresh/index trigger or handler,
  surface that path in text as `Index via: ...`
- do not add a new manifest field for refresh/index unless you discover the
  existing manifest cannot represent it at all

This is the core routing seam for the Queen.

**4. Add a Queen routing rule in `caste_recipes.yaml`.**

Add a short system-prompt rule that says:

- call `list_addons` when the operator asks to search, index, or learn from
  content
- route by `content_kinds` and `path_globs`
- use `memory_search` only for institutional memory / experience / conventions
- use addon search tools for addon-owned corpora
- use the addon's surfaced refresh/index path for reindex requests
- if multiple addons match, prefer the narrowest `path_globs` or the
  operator's explicit path
- treat workspace tags as hints, not hard constraints

Also update the Queen tool count and add both `mark_plan_step` and
`set_workspace_tags` to the tool list.

### Tests

Create `tests/unit/addons/test_addon_capability.py` with at least:

1. `test_manifest_parses_with_capability_fields`
2. `test_manifest_parses_without_capability_fields`
3. `test_list_addons_includes_capability_text`
4. `test_list_addons_includes_refresh_path_when_present`

The last test should prove that the model-visible text distinguishes the
search path from the refresh/index path when the addon already exposes one.

---

## Track 6: Soft Workspace Taxonomy

### Problem

The Queen still lacks cheap, explicit workspace priors. Names are often too
opaque to tell whether a workspace is about auth, docs, Python, infra, or
something else. That makes routing and plan composition weaker than they need
to be.

The fix here is **soft taxonomy**, not validation. Tags should steer the Queen,
not reject new concepts.

### Correct event/projection contract

`WorkspaceConfigChanged` uses:

- `field`
- `old_value`
- `new_value`

Do not use `key` / `value`.

Workspace config is read from `ws.config`, not from a separate projection map.

### Implementation

**1. Add `set_workspace_tags`.**

Add a Queen tool in `queen_tools.py` that:

- accepts `tags: list[str]`
- normalizes to lowercase, stripped strings
- caps to 20 tags and 50 chars per tag
- emits `WorkspaceConfigChanged` with:
  - `field="taxonomy_tags"`
  - `old_value` from the existing config entry if present
  - `new_value` as JSON

Follow the exact event-emission pattern already used by the config tools in
`queen_tools.py`. Do not invent a new one.

**2. Inject tags near the top of `_build_thread_context()`.**

At the top of `_build_thread_context()`, right after the goal line, read:

```python
ws.config.get("taxonomy_tags")
```

Parse the JSON string and render a single line like:

```text
Tags: python, auth, web-api
```

This should be a small hint, not a giant block.

**3. Add a gentle hint for brand-new tagless workspaces.**

If the workspace has no tags and fewer than 3 threads, append a brief hint
about `set_workspace_tags`. The hint should disappear once tags exist or the
workspace is no longer brand new.

### Tests

Create `tests/unit/surface/test_workspace_taxonomy.py` with at least:

1. `test_set_workspace_tags_emits_config_event`
2. `test_tags_normalized_and_capped`
3. `test_thread_context_includes_tags`
4. `test_auto_suggest_nudge_for_tagless_workspace`

---

## Acceptance Gates

- [ ] `AddonManifest` parses with and without the new optional fields
- [ ] Existing manifests remain backward-compatible
- [ ] Updated manifests contain real capability values for real corpus addons
- [ ] `_list_addons()` text includes `Content:`, `Files:`, and `Search via:`
- [ ] `_list_addons()` distinguishes search path from refresh/index path when present
- [ ] Queen system prompt includes routing guidance based on source coverage
- [ ] `set_workspace_tags` emits `WorkspaceConfigChanged` with `field` / `old_value` / `new_value`
- [ ] Tags are read from `ws.config`
- [ ] Tags are injected near the top of `_build_thread_context()`
- [ ] Tagless-workspace hint fires only for small/new workspaces
- [ ] No new event types are added

## Validation

```bash
pytest tests/unit/addons/test_addon_capability.py -v
pytest tests/unit/surface/test_workspace_taxonomy.py -v

ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```
