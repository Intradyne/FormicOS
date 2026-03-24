# Wave 31 Pyright Fix — Track 1: knowledge_catalog.py + config_validator.py

**Track:** 1 of 2
**Scope:** Type annotation fixes only. No behavioral changes.
**Target:** Eliminate 45 of 73 pyright errors (the two worst files).

---

## Reading Order

1. This file
2. Run `uv run pyright src/` to see current errors

---

## Your Files

| File | Errors | Action |
|------|--------|--------|
| `src/formicos/surface/knowledge_catalog.py` | 25 | **EDIT** — type annotations |
| `src/formicos/surface/config_validator.py` | 20 | **EDIT** — type annotations |

## Do NOT Touch

Every other file. This is a two-file fix.

---

## Task 1: knowledge_catalog.py (25 errors → 0)

All 25 errors come from two root causes:

### Root Cause A: `_normalize_legacy_skill` uses untyped `hit` parameter (lines 50-81)

The `hit` parameter is `Any`, and pyright can't infer types for `hit.metadata`, `meta.get(...)`, etc. The fix: type the intermediate variables.

**Line 52:** `meta` is inferred as `Unknown` because `hit.metadata` comes from `Any`.
```python
# BEFORE:
meta = hit.metadata if hasattr(hit, "metadata") else {}

# AFTER:
meta: dict[str, Any] = hit.metadata if hasattr(hit, "metadata") else {}
```

**Line 53:** Same pattern for `content`:
```python
# BEFORE:
content = hit.content if hasattr(hit, "content") else ""

# AFTER:
content: str = hit.content if hasattr(hit, "content") else ""
```

**Line 54:** `technique` inherits Unknown from `meta.get()`:
```python
# BEFORE:
technique = meta.get("technique", "")

# AFTER:
technique: str = str(meta.get("technique", ""))
```

**Lines 61-78:** All the `meta.get(...)` calls inside the `KnowledgeItem(...)` constructor need explicit casts. The cleanest fix is to annotate the return values where they feed into typed fields:

```python
return asdict(KnowledgeItem(
    id=str(hit.id) if hasattr(hit, "id") else "",
    canonical_type="skill",
    source_system="legacy_skill_bank",
    status="active",
    confidence=float(meta.get("confidence", 0.5)),
    title=technique if technique else str(content[:80].split("\n")[0]),
    summary=str(meta.get("when_to_use", "")),
    content_preview=str(content[:500]),
    source_colony_id=str(meta.get(
        "source_colony_id", meta.get("source_colony", ""),
    )),
    source_artifact_ids=[],
    domains=[],
    tool_refs=[],
    created_at=str(meta.get("extracted_at", "")),
    polarity="positive",
    legacy_metadata={
        "conf_alpha": meta.get("conf_alpha"),
        "conf_beta": meta.get("conf_beta"),
        "merge_count": meta.get("merge_count", 0),
        "algorithm_version": meta.get("algorithm_version", ""),
        "failure_modes": meta.get("failure_modes", ""),
    },
    score=float(hit.score) if hasattr(hit, "score") else 0.0,
))
```

The key changes: wrap `meta.get(...)` calls with `str(...)` or `float(...)` where the target field is `str` or `float`. The `legacy_metadata` dict values stay as `Any` (that's the correct type for `dict[str, Any]`).

### Root Cause B: `_projection_keyword_fallback` results list (lines 293-298)

**Line 293-297:** The `results` variable is inferred as `list[Unknown]` because `_normalize_institutional` returns `dict[str, Any]` but pyright loses track through the loop.

```python
# BEFORE:
results = []
for _, e in scored[:top_k]:
    item = _normalize_institutional(e, score=0.0)
    item["source"] = "keyword_fallback"
    results.append(item)
return results

# AFTER:
results: list[dict[str, Any]] = []
for _, e in scored[:top_k]:
    item = _normalize_institutional(e, score=0.0)
    item["source"] = "keyword_fallback"
    results.append(item)
return results
```

---

## Task 2: config_validator.py (20 errors → 0)

All 20 errors come from three root causes:

### Root Cause A: `yaml.safe_load` returns `Any` (lines 86-97)

**Line 86:** `data` is `Any` because `yaml.safe_load` returns `Any`. Then `data.get(...)` propagates Unknown through lines 89-96.

```python
# BEFORE:
data = yaml.safe_load(f) or {}

# AFTER:
data: dict[str, Any] = yaml.safe_load(f) or {}
```

**Lines 89-90:** `entry` and `path` cascade from the untyped `data`:
```python
# BEFORE:
for entry in data.get("experimentable_params", []):
    path = entry.get("path", "")

# AFTER:
for entry in data.get("experimentable_params", []):
    entry_d: dict[str, Any] = entry if isinstance(entry, dict) else {}
    path: str = str(entry_d.get("path", ""))
    if not path:
        continue
    rules[path] = {
        "type": str(entry_d.get("type", "float")),
        "min": entry_d.get("min", 0),
        "max": entry_d.get("max", 1),
    }
```

### Root Cause B: `_check_depth` and `_contains_forbidden` iterate over `obj.values()` (lines 112-132)

These functions accept `object` but iterate with `obj.values()` and `obj` (list). Pyright infers `v` as `Unknown` inside the dict/list branches.

**Lines 111-114 (`_check_depth`):**
```python
# BEFORE:
if isinstance(obj, dict):
    return any(_check_depth(v, max_depth, _current + 1) for v in obj.values())
if isinstance(obj, list):
    return any(_check_depth(v, max_depth, _current + 1) for v in obj)

# AFTER:
if isinstance(obj, dict):
    return any(_check_depth(v, max_depth, _current + 1) for v in cast(dict[str, Any], obj).values())
if isinstance(obj, list):
    return any(_check_depth(v, max_depth, _current + 1) for v in cast(list[Any], obj))
```

Add `from typing import cast` at the top if not already imported. Alternatively, use explicit type annotations on the loop variable — but `cast` is more concise for these generator expressions.

**Same pattern for `_contains_forbidden` (lines 125-134):**
```python
elif isinstance(obj, dict):
    for v in cast(dict[str, Any], obj).values():
        hit = _contains_forbidden(v)
        if hit is not None:
            return hit
elif isinstance(obj, list):
    for v in cast(list[Any], obj):
        hit = _contains_forbidden(v)
        if hit is not None:
            return hit
```

### Root Cause C: `ValidationError.errors()` returns partially unknown (lines 251-253)

**Lines 251-255:**
```python
# BEFORE:
if isinstance(exc, ValidationError):
    first_err = exc.errors()[0] if exc.errors() else {}
    msg = first_err.get("msg", str(exc))

# AFTER:
if isinstance(exc, ValidationError):
    errs = exc.errors()
    first_err: dict[str, Any] = errs[0] if errs else {}
    msg = str(first_err.get("msg", str(exc)))
```

---

## Validation

```bash
uv run pyright src/formicos/surface/knowledge_catalog.py src/formicos/surface/config_validator.py 2>&1 | grep "error"
```

Should show 0 errors for both files. Then run full validation:

```bash
ruff check src/ && pyright src/ && python scripts/lint_imports.py && pytest
```

All must pass. Do not introduce new errors in other files. Do not change any runtime behavior — these are purely type annotation fixes.
