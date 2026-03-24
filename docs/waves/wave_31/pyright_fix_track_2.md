# Wave 31 Pyright Fix — Track 2: Scattered Errors Across 11 Files

**Track:** 2 of 2
**Scope:** Type annotation fixes only. No behavioral changes.
**Target:** Eliminate 28 remaining pyright errors across 11 files.

---

## Reading Order

1. This file
2. Run `uv run pyright src/` to see current errors (ignore knowledge_catalog.py and config_validator.py — Track 1 handles those)

---

## Your Files

| File | Errors | Fix Category |
|------|--------|-------------|
| `src/formicos/surface/runtime.py` | 6 | Type annotations + remove unnecessary isinstance |
| `src/formicos/surface/colony_manager.py` | 6 | Remove unnecessary isinstance + type annotations |
| `src/formicos/engine/runner.py` | 4 | Type annotations on urlparse result |
| `src/formicos/core/events.py` | 3 | Type annotations on list fields |
| `src/formicos/core/settings.py` | 2 | Type annotation on yaml representer |
| `src/formicos/surface/app.py` | 2 | Access pattern + unnecessary comparison |
| `src/formicos/core/types.py` | 1 | Type annotation on list field |
| `src/formicos/surface/view_state.py` | 1 | Remove redundant annotation |
| `src/formicos/surface/queen_runtime.py` | 1 | Remove unnecessary isinstance |
| `src/formicos/surface/memory_extractor.py` | 1 | Return type annotation |
| `src/formicos/eval/run.py` | 1 | Protocol conformance |

## Do NOT Touch

- `knowledge_catalog.py` (Track 1)
- `config_validator.py` (Track 1)

---

## Fix 1: runtime.py (6 errors → 0)

### Lines 436-440: Live sync entry_id extraction

The `event_with_seq` is typed as `EventEnvelope` (the base), but the code accesses `.entry` and `.entry_id` which only exist on specific subtypes. The existing `pyright: ignore` comments suppress the access errors but leave the variable types partially unknown.

```python
# BEFORE (lines 436-440):
sync_id = ""
if etype == "MemoryEntryCreated":
    sync_id = event_with_seq.entry.get("id", "")  # pyright: ignore[reportAttributeAccessIssue]
elif etype == "MemoryEntryStatusChanged":
    sync_id = event_with_seq.entry_id  # pyright: ignore[reportAttributeAccessIssue]

# AFTER:
sync_id: str = ""
if etype == "MemoryEntryCreated":
    sync_id = str(getattr(event_with_seq, "entry", {}).get("id", ""))
elif etype == "MemoryEntryStatusChanged":
    sync_id = str(getattr(event_with_seq, "entry_id", ""))
```

This removes the `pyright: ignore` comments and uses `getattr` for safe access on the base type. The `str()` wrap ensures `sync_id` is always `str`.

### Line 1091: Unnecessary isinstance check

```python
# BEFORE:
art_dict = art if isinstance(art, dict) else {}

# AFTER:
art_dict: dict[str, Any] = art
```

The `colony.artifacts` field is `list[dict[str, Any]]`, so `art` is always a `dict`. The isinstance check is unnecessary. If you want to be defensive, keep it but add a `# type: ignore[reportUnnecessaryIsInstance]` comment — but removing it is cleaner since the type system already guarantees it.

---

## Fix 2: colony_manager.py (6 errors → 0)

### Line 747: Unnecessary isinstance on artifacts

Same pattern as runtime.py — `colony_proj.artifacts` is `list[dict[str, Any]]`, so each element is already `dict[str, Any]`.

```python
# BEFORE (lines 745-750):
art_list: list[dict[str, Any]] = []
for a in (colony_proj.artifacts or []):
    if isinstance(a, dict):
        art_list.append(a)
    elif hasattr(a, "model_dump"):
        art_list.append(a.model_dump())

# AFTER:
art_list: list[dict[str, Any]] = list(colony_proj.artifacts or [])
```

### Line 847: `art.get("artifact_type", ...)` on partially unknown type

```python
# BEFORE (lines 843-848):
for art in getattr(col_proj_b5, "artifacts", []):
    atype = ""
    if isinstance(art, dict):
        atype = str(
            art.get("artifact_type", "generic"),
        )

# AFTER:
for art in getattr(col_proj_b5, "artifacts", []):
    atype = ""
    art_d: dict[str, Any] = art if isinstance(art, dict) else {}
    if art_d:
        atype = str(art_d.get("artifact_type", "generic"))
```

### Line 926: Private import `_build_extraction_prompt`

```python
# BEFORE:
from formicos.surface.memory_extractor import (
    _build_extraction_prompt,
    ...
)

# AFTER — rename at source (memory_extractor.py) to make it public:
```

**Option A (preferred):** In `memory_extractor.py`, rename `_build_extraction_prompt` to `build_extraction_prompt` (remove leading underscore). Update the import in colony_manager.py line 926 to match. This is the right fix — the function is used cross-module, so it should not be private.

**Option B (if you want minimal diff):** Add `# pyright: ignore[reportPrivateUsage]` to line 926. This is a suppression, not a fix.

### Lines 940, 945: More unnecessary isinstance on `artifacts`

Same pattern — `artifacts` parameter is `list[dict[str, Any]]`. Each element is already a dict.

```python
# BEFORE (lines 939-948):
artifact_ids = [
    a.get("id", "") if isinstance(a, dict) else getattr(a, "id", "")
    for a in artifacts
]
art_dicts: list[dict[str, Any]] = []
for a in artifacts:
    if isinstance(a, dict):
        art_dicts.append(a)
    elif hasattr(a, "model_dump"):
        art_dicts.append(a.model_dump())

# AFTER:
artifact_ids = [str(a.get("id", "")) for a in artifacts]
art_dicts: list[dict[str, Any]] = list(artifacts)
```

Check the `artifacts` parameter type on `_extract_institutional_memory`. If it's `list[dict[str, Any]]`, the isinstance guards are unnecessary. If it's `list[Any]`, change the parameter type to `list[dict[str, Any]]` to match the callers.

---

## Fix 3: runner.py (4 errors → 0)

### Lines 539-540: `urlparse` hostname type

```python
# BEFORE:
domain = urlparse(url).hostname or ""
if not any(domain == d or domain.endswith(f".{d}") for d in allowed_domains):

# AFTER:
domain: str = urlparse(url).hostname or ""
if not any(domain == d or domain.endswith(f".{d}") for d in allowed_domains):
```

The `urlparse().hostname` returns `str | None`. The `or ""` makes it `str`, but pyright's narrowing doesn't always track through `or`. The explicit annotation resolves it.

---

## Fix 4: events.py (3 errors → 0)

Three `list` fields use `list[dict[str, Any]]` or `list[InputSource]` but pyright infers partial unknowns from the `Field(default_factory=list)` pattern.

### Line 160 (`ColonyStarted.input_sources`):
```python
# BEFORE:
input_sources: list[InputSource] = Field(
    default_factory=list,
    ...
)

# AFTER:
input_sources: list[InputSource] = Field(
    default_factory=list,  # type: ignore[assignment]
    ...
)
```

Actually — first check if `InputSource` is fully defined with type annotations. The real issue may be that `InputSource` has partially unknown fields. If so, the fix is to annotate `InputSource` fields. Check the `InputSource` class definition.

If `InputSource` is a Pydantic model or typed dataclass, the `Field(default_factory=list)` should work. Add explicit annotation if needed:

```python
input_sources: list["InputSource"] = Field(
    default_factory=lambda: list[InputSource](),
    ...
)
```

### Line 181 (`ColonyCompleted.artifacts`):
```python
# BEFORE:
artifacts: list[dict[str, Any]] = Field(
    default_factory=list,
    ...
)
```

The issue is `default_factory=list` produces `list[Unknown]`. Fix:
```python
artifacts: list[dict[str, Any]] = Field(
    default_factory=lambda: [],
    ...
)
```

Or explicitly:
```python
def _empty_dict_list() -> list[dict[str, Any]]:
    return []

# Then in the field:
artifacts: list[dict[str, Any]] = Field(default_factory=_empty_dict_list, ...)
```

The simplest fix is the lambda approach.

### Line 731 (`KnowledgeAccessRecorded.items`):
Same pattern — change `default_factory=list` to `default_factory=lambda: []`.

---

## Fix 5: settings.py (2 errors → 0)

### Lines 216, 219: `yaml.Dumper.represent_scalar` type

```python
# BEFORE:
def _str_representer(
    dumper: yaml.Dumper, val: str,
) -> yaml.ScalarNode:
    if "\n" in val:
        return dumper.represent_scalar(
            "tag:yaml.org,2002:str", val, style="|",
        )
    return dumper.represent_scalar("tag:yaml.org,2002:str", val)
```

PyYAML's `represent_scalar` has incomplete type stubs. The fix is to tell pyright the return type is known:

```python
def _str_representer(
    dumper: yaml.Dumper, val: str,
) -> yaml.ScalarNode:
    if "\n" in val:
        result: yaml.ScalarNode = dumper.represent_scalar(
            "tag:yaml.org,2002:str", val, style="|",
        )
        return result
    return dumper.represent_scalar("tag:yaml.org,2002:str", val)  # type: ignore[return-value]
```

Or simpler — just suppress with inline comments if the stubs are genuinely incomplete:
```python
return dumper.represent_scalar(  # type: ignore[return-value]
    "tag:yaml.org,2002:str", val, style="|",
)
return dumper.represent_scalar("tag:yaml.org,2002:str", val)  # type: ignore[return-value]
```

---

## Fix 6: app.py (2 errors → 0)

### Line 450: `_extract_institutional_memory` is protected

```python
# BEFORE:
asyncio.create_task(
    colony_manager._extract_institutional_memory(

# AFTER — make the method public in colony_manager.py:
```

**Option A (preferred):** Rename `_extract_institutional_memory` to `extract_institutional_memory` in colony_manager.py (remove leading underscore). Update the call in app.py line 450. This method is called cross-module, so it should not be private.

**Option B:** Add `# pyright: ignore[reportPrivateUsage]` to line 450. Suppression, not a fix.

**Coordinate with Fix 2** — if you make `_extract_institutional_memory` public, the import in colony_manager.py line 926 of `_build_extraction_prompt` is a separate issue (that's from memory_extractor.py).

### Line 518: Unnecessary comparison

```python
# BEFORE:
if service_router is not None:

# AFTER — remove the guard since service_router is always ServiceRouter:
```

Check the type of `colony_manager.service_router`. If it's `ServiceRouter` (not `ServiceRouter | None`), just remove the `if` guard and dedent the block. If the type is `Optional[ServiceRouter]`, the check is correct and pyright is wrong — suppress with `# type: ignore[reportUnnecessaryComparison]`.

---

## Fix 7: types.py (1 error → 0)

### Line 251: `artifacts` field same as events.py

```python
artifacts: list[dict[str, Any]] = Field(
    default_factory=lambda: [],
    ...
)
```

---

## Fix 8: view_state.py (1 error → 0)

### Line 385: Redundant type annotation

```python
# BEFORE:
nested_dict: dict[str, Any] = nested

# AFTER:
nested_dict = cast(dict[str, Any], nested)
```

Or if `nested` is already narrowed by isinstance:
```python
if isinstance(nested, dict):
    for key in ("n_ctx", "ctx_size", "context_window"):
        val = nested.get(key)
```

Remove the intermediate variable entirely if the isinstance guard makes pyright happy.

---

## Fix 9: queen_runtime.py (1 error → 0)

### Line 647: Unnecessary isinstance

```python
# BEFORE:
_total_colonies = thread.colony_count if isinstance(thread.colony_count, int) else 0

# AFTER:
_total_colonies: int = thread.colony_count
```

`colony_count` on the thread projection is already `int`. The isinstance guard is unnecessary.

---

## Fix 10: memory_extractor.py (1 error → 0)

### Line 118: Return type partially unknown

The `json.loads` return is `Any`. Pyright flags the return as `dict[Unknown, Unknown]`.

```python
# BEFORE:
result = json.loads(cleaned)
if isinstance(result, dict):
    return result

# AFTER:
result = json.loads(cleaned)
if isinstance(result, dict):
    return cast(dict[str, Any], result)
```

Add `from typing import cast` at the top if not present.

---

## Fix 11: eval/run.py (1 error → 0)

### Line 175: SqliteEventStore doesn't satisfy EventStorePort

This is likely a missing method or signature mismatch. Check what `EventStorePort` requires vs what `SqliteEventStore` implements. Common fixes:

- Add a missing method to `SqliteEventStore`
- Fix a return type mismatch
- Add `# type: ignore[arg-type]` if the adapter is correct but pyright can't verify (e.g., async signatures)

If the adapter is functionally correct and this is a stub limitation, suppress:
```python
runtime = Runtime(
    event_store=event_store,  # type: ignore[arg-type]
    ...
)
```

---

## Validation

After all fixes, run:

```bash
uv run pyright src/ 2>&1 | grep "error:" | wc -l
```

Combined with Track 1, the target is **0 errors**. If a few remain due to third-party stub limitations (PyYAML, qdrant-client), use targeted `# type: ignore` comments with the specific error code.

Full validation:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass. No behavioral changes — these are purely type annotation fixes.
