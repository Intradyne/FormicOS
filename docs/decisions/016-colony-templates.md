# ADR-016: Colony Templates -- Reusable Colony Configurations

**Status:** Accepted
**Date:** 2026-03-14
**Depends on:** ADR-015 (Event Union Expansion), ADR-001 (Event Sourcing)

## Context

Every colony is currently created from scratch. The operator specifies task, castes, strategy, budget, and max rounds each time. There is no mechanism to save a working colony configuration and reuse it. The README mentions a `suggest-team` endpoint conceptually, but no template system or team suggestion is implemented.

Production usage patterns show that operators run similar colony configurations repeatedly -- "code review with coder+reviewer," "research sprint with researcher+archivist," "full-stack with all castes." Recreating these from scratch each time is friction that discourages use.

## Decision

### Templates are immutable YAML files in `config/templates/`

Storage is the filesystem, not SQLite or Qdrant. Templates are:
- Human-readable and hand-editable
- Git-trackable (version control for free)
- Loadable without a running database
- Simple enough that the overhead of a database is unjustified at alpha scale (< 100 templates)

### Template model

```python
class ColonyTemplate(BaseModel):
    model_config = ConfigDict(frozen=True)

    template_id: str            # uuid
    name: str                   # "Full-Stack Sprint"
    description: str            # LLM-generated or operator-written
    version: int = 1            # immutable versioning -- edits create new version
    caste_names: list[str]      # ["coder", "reviewer", "researcher"]
    strategy: str = "stigmergic"
    budget_limit: float = 1.0   # USD
    max_rounds: int = 25
    tags: list[str] = []        # ["code-review", "refactoring"]
    source_colony_id: str | None = None  # if saved from a completed colony
    created_at: str             # ISO 8601
    use_count: int = 0          # incremented via projection on ColonyTemplateUsed
```

### Immutable versioning

Editing a template does NOT modify the existing file. It creates a new file with `version: N+1` and the same `template_id`. The old version is retained. This ensures that `ColonyTemplateUsed` events always point to a valid template version that can be replayed.

### REST API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/templates` | GET | List all templates (latest version per template_id) |
| `/api/v1/templates` | POST | Create template (manual or from colony) |
| `/api/v1/templates/{id}` | GET | Get template detail including all versions |

### Colony creation with template

Extend the existing colony creation path (WS `spawn_colony` command and any REST equivalent) to accept an optional `template_id` field. When present:

1. Load template from `config/templates/{template_id}.yaml`
2. Use template's `caste_names`, `strategy`, `budget_limit`, `max_rounds` as defaults
3. Operator can override any field in the creation request
4. Emit `ColonyTemplateUsed` event linking the colony to the template
5. Proceed with normal colony spawn

### "Save as template" from completed colony

When a colony completes successfully, the operator can save its configuration as a template:

1. Read `ColonySpawned` event for the colony's configuration
2. Generate description via a single LLM call (Gemini Flash, cheap):
   ```
   Describe this colony configuration in one sentence:
   Task: {task}
   Castes: {caste_names}
   Strategy: {strategy}
   ```
3. Save as YAML in `config/templates/`
4. Emit `ColonyTemplateCreated` event

### Queen colony naming

Separate from templates but ships in the same phase because it improves the same user flow (colony creation).

After a colony is spawned, fire a single LLM call (Gemini Flash, temperature 0.3, max_tokens 20):
```
Generate a short, memorable project name (2-4 words, no quotes) for: {task_objective}
```

- Store as `ColonyProjection.display_name`
- Emit `ColonyNamed` event
- Fallback: if LLM fails or times out (500ms), keep `colony-{uuid[:8]}`
- The name is cosmetic -- routing, events, and correlation always use the UUID
- The operator can rename via a future WS command (emit another `ColonyNamed`)

### Suggest-team endpoint

`POST /api/v1/suggest-team` takes an objective string and returns recommended castes:

```json
{
  "objective": "Refactor the auth module to use JWT",
  "castes": [
    {"caste": "coder", "count": 1, "reasoning": "Implementation work"},
    {"caste": "reviewer", "count": 1, "reasoning": "Code quality gate"},
    {"caste": "researcher", "count": 1, "reasoning": "JWT best practices"}
  ]
}
```

Single LLM call with the objective + available castes from `caste_recipes.yaml`. Route to Gemini Flash with local fallback. Temperature 0.0. This is a suggestion -- the operator can accept, modify, or ignore it in the colony creation UI.

## Consequences

- **New surface file:** `surface/template_manager.py` (~200 LOC)
- **New config directory:** `config/templates/` with YAML files
- **New events:** `ColonyTemplateCreated`, `ColonyTemplateUsed`, `ColonyNamed` (from ADR-015)
- **Modified surface files:** `commands.py` (template_id in spawn), `queen_runtime.py` (naming), `runtime.py` (suggest-team)
- **No engine changes:** Templates are a surface-layer feature
- **No new dependencies:** YAML parsing via existing pyyaml, LLM calls via existing adapters
- **Rollback:** Delete template files, remove template_id from spawn commands. Events stay in store (harmless).
