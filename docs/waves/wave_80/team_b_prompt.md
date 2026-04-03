# Wave 80 Team B Prompt

## Mission

Turn two existing passive resources into planning-time signals:

- curated playbooks
- worker capability knowledge

The Queen should be able to ask for a short structural hint and a short
worker-capability summary without parsing whole playbooks or relying on
hardcoded prompt prose.

## Owned Files

- `src/formicos/engine/playbook_loader.py`
- `src/formicos/surface/capability_profiles.py` (new)
- `config/capability_profiles.json` (new)
- `config/playbooks/code_implementation.yaml`
- `config/playbooks/design.yaml`
- `config/playbooks/research.yaml`
- `config/playbooks/code_review.yaml`
- `config/playbooks/generic.yaml`
- `tests/unit/engine/test_playbook_hints.py` (new)
- `tests/unit/surface/test_capability_profiles.py` (new)

## Do Not Touch

- `src/formicos/surface/queen_runtime.py`
- `src/formicos/surface/queen_tools.py`
- `src/formicos/core/types.py`
- `src/formicos/engine/runner.py`

## Repo Truth To Read First

1. `src/formicos/engine/playbook_loader.py:31-111`
   Playbooks currently load execution workflow, not decomposition hints.

2. `src/formicos/surface/task_classifier.py:72-84`
   `classify_task()` is the current deterministic task-class seam.

3. `config/playbooks/*.yaml`
   The YAML files currently carry workflow/tool guidance, not colony-count
   or grouping metadata.

4. `src/formicos/surface/runtime.py:931-939`
   `resolve_model()` is the real model cascade.

## What To Build

### 1. `get_decomposition_hints()`

Add a small helper to `playbook_loader.py`, for example:

```python
def get_decomposition_hints(task_description: str) -> str | None:
    ...
```

Rules:

- Use `classify_task(task_description)` as the first discriminator
- Prefer an explicit `decomposition` block on the matching curated
  playbook
- Fall back to deterministic task-class defaults if no decomposition
  block exists
- Return a one-line hint with a confidence marker
- Return `None` when the result would be too generic to be useful

Good output:

```text
code_implementation (conf=1.00) -> 3-5 colonies, grouped files, coder-led, stigmergic
```

### 2. Playbook `decomposition` blocks

Add an optional top-level `decomposition` block to the highest-value
curated playbooks:

```yaml
decomposition:
  confidence: 1.0
  colony_range: "3-5"
  grouping: "group semantically related files; avoid 1-file splits"
  recommended_caste: "coder"
  recommended_strategy: "stigmergic"
```

Keep this small and structural. Do not duplicate the full workflow steps.

### 3. Capability profile loader

Create `src/formicos/surface/capability_profiles.py` and
`config/capability_profiles.json`.

Recommended behavior:

- Load shipped defaults from `config/capability_profiles.json`
- Optionally merge a runtime override file from:
  `<data_dir>/.formicos/runtime/capability_profiles.json`
- Resolve by:
  1. exact model address
  2. last path segment
  3. simple suffix normalization such as removing `-swarm`

Provide a small public helper, for example:

```python
def summarize_capability(model_addr: str, data_dir: str = "") -> str | None:
    ...
```

Good output:

```text
qwen3.5-4b (n=24) -> 3-4 files optimal, 1-file -16%, focused can reach 0.738
```

## Important Constraints

- Do not make this auto-learning yet; v1 is shipped defaults plus optional
  override file
- Do not add a new database or event type
- Do not require embeddings or Qdrant for playbook hints
- Keep the helper outputs short enough for a planning brief line

## Validation

Add focused tests that prove:

1. Exact and fallback playbook hints work
2. Generic tasks return either a cautious generic hint or `None`
3. Capability profiles resolve both full addresses and short aliases
4. Runtime override data cleanly merges over shipped defaults

Run:

- `python -m pytest tests/unit/engine/test_playbook_hints.py -q`
- `python -m pytest tests/unit/surface/test_capability_profiles.py -q`
- `python -m pytest tests/unit/surface/test_queen_tools.py -q`

## Overlap Note

You are not alone in the codebase. Team A will consume your helper names
directly. Keep the public API small and stable. Team C is independent;
do not touch `queen_tools.py` or `core/types.py`.
