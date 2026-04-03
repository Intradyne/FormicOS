"""Operational playbook loader — Wave 54.

Loads task-class-keyed YAML playbooks from config/playbooks/ and formats
them as XML-tagged context blocks for injection into agent context at
position 2.5 (between round goal and workspace structure).

Common-mistakes anti-pattern cards are loaded separately (Wave 56.5 A)
and injected at position 2.6 — always on, caste-aware.

Playbooks are static, deterministic, and outside the knowledge system.
They tell agents the productive sequence of moves for their task class.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

_PLAYBOOK_DIR = Path(__file__).resolve().parents[3] / "config" / "playbooks"
_CACHE: dict[str, str] = {}
_COMMON_MISTAKES_CACHE: dict[str, str] = {}
_GENERATION_CACHE: str | None = None


def load_playbook(task_class: str, caste: str) -> str:
    """Load and format a playbook for the given task class and caste.

    Resolution order (first match wins):
      1. ``{task_class}_{caste}.yaml`` — caste-specific variant
      2. ``{task_class}.yaml`` — shared (must list the caste)
      3. ``generic_{caste}.yaml`` — caste-specific fallback
      4. ``generic.yaml`` — universal fallback

    Returns an empty string if no matching playbook is found.
    Results are cached in-process.
    """
    key = f"{task_class}:{caste}"
    if key in _CACHE:
        return _CACHE[key]

    # Build candidate file names: caste-specific variants first, then shared
    candidates = [
        f"{task_class}_{caste}",  # e.g. research_researcher
        task_class,                # e.g. research (must list caste)
        f"generic_{caste}",        # e.g. generic_reviewer
        "generic",                 # universal fallback
    ]

    for name in candidates:
        path = _PLAYBOOK_DIR / f"{name}.yaml"
        if not path.exists():
            continue
        try:
            import yaml  # noqa: PLC0415

            data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            log.warning("playbook_loader.parse_error", path=str(path))
            continue

        castes = data.get("castes", [])
        if caste not in castes:
            continue

        block = _format_playbook(data)
        _CACHE[key] = block
        log.info(
            "playbook_loader.loaded",
            task_class=task_class,
            caste=caste,
            playbook_file=name,
        )
        return block

    _CACHE[key] = ""
    return ""


def _format_playbook(data: dict[str, Any]) -> str:
    """Format a parsed YAML playbook dict into an XML-tagged context block."""
    steps = "\n".join(
        f"{i + 1}. {s}" for i, s in enumerate(data.get("steps", []))
    )
    productive = ", ".join(data.get("productive_tools", []))
    observation = ", ".join(data.get("observation_tools", []))
    obs_limit = data.get("observation_limit", 2)

    example = data.get("example", {})
    example_json = json.dumps(
        {"name": example.get("name", ""), "arguments": example.get("arguments", {})},
        ensure_ascii=False,
    )

    return (
        "<operational_playbook>\n"
        f"WORKFLOW: {data.get('workflow', '')}\n"
        f"STEPS:\n{steps}\n\n"
        f"PRODUCE OUTPUT WITH: {productive}\n"
        f"GATHER INFO WITH (limit {obs_limit}): {observation}\n\n"
        f"EXAMPLE:\n{example_json}\n"
        "</operational_playbook>"
    )


def load_all_playbooks() -> list[dict[str, Any]]:
    """Load all playbook YAML files for display purposes.

    Returns a list of dicts, each containing the raw playbook fields
    (task_class, castes, workflow, steps, productive_tools,
    observation_tools, observation_limit, example).
    """
    results: list[dict[str, Any]] = []
    if not _PLAYBOOK_DIR.is_dir():
        return results

    for path in sorted(_PLAYBOOK_DIR.glob("*.yaml")):
        try:
            import yaml  # noqa: PLC0415

            data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            log.warning("playbook_loader.parse_error", path=str(path))
            continue

        data["_file"] = path.stem
        results.append(data)

    return results


def load_common_mistakes(caste: str) -> str:
    """Load and format caste-aware common-mistakes anti-pattern cards.

    Always returns content (universal anti-patterns at minimum).
    Coder caste gets coder-specific cards prepended.

    Results are cached in-process.  Wave 56.5 Sub-packet A.
    """
    if caste in _COMMON_MISTAKES_CACHE:
        return _COMMON_MISTAKES_CACHE[caste]

    blocks: list[str] = []

    # Caste-specific file (e.g. common_mistakes_coder.yaml)
    caste_path = _PLAYBOOK_DIR / f"common_mistakes_{caste}.yaml"
    if caste_path.exists():
        items = _load_anti_patterns(caste_path)
        blocks.extend(items)

    # Universal file
    universal_path = _PLAYBOOK_DIR / "common_mistakes.yaml"
    if universal_path.exists():
        items = _load_anti_patterns(universal_path)
        blocks.extend(items)

    if not blocks:
        _COMMON_MISTAKES_CACHE[caste] = ""
        return ""

    text = (
        "<common_mistakes>\n"
        + "\n".join(f"- {b}" for b in blocks)
        + "\n</common_mistakes>"
    )
    _COMMON_MISTAKES_CACHE[caste] = text
    return text


def _load_anti_patterns(path: Path) -> list[str]:
    """Parse anti_patterns list from a YAML file."""
    try:
        import yaml  # noqa: PLC0415

        data: dict[str, Any] = (
            yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        )
    except Exception:
        log.warning("playbook_loader.anti_pattern_parse_error", path=str(path))
        return []
    return [
        str(item.get("rule", ""))
        for item in data.get("anti_patterns", [])
        if item.get("rule")
    ]


def compute_playbook_generation() -> str:
    """Compute a content-derived hash of all playbook + anti-pattern YAML files.

    Returns the first 12 hex chars of the SHA-256 digest.
    Cached in-process — call ``clear_cache()`` to invalidate.
    Wave 56.5 Sub-packet C.
    """
    global _GENERATION_CACHE  # noqa: PLW0603
    if _GENERATION_CACHE is not None:
        return _GENERATION_CACHE

    h = hashlib.sha256()
    if _PLAYBOOK_DIR.is_dir():
        for path in sorted(_PLAYBOOK_DIR.glob("*.yaml")):
            h.update(path.read_bytes())

    _GENERATION_CACHE = h.hexdigest()[:12]
    return _GENERATION_CACHE


_HINT_CACHE: dict[str, str | None] = {}


def _classify_task_simple(description: str) -> str:
    """Lightweight task classification by keyword overlap.

    Engine-local version that avoids importing from surface/.
    Mirrors the same keyword sets as ``surface.task_classifier``.
    """
    words = set(description.lower().split())
    _keywords: dict[str, set[str]] = {
        "code_implementation": {
            "implement", "build", "create", "add", "feature",
            "function", "class", "module", "write", "code",
        },
        "code_review": {"review", "audit", "check", "inspect", "lint", "pr"},
        "design": {"design", "architect", "plan", "structure", "diagram", "spec"},
        "research": {"research", "investigate", "explore", "survey", "analyze", "find", "search"},
        "creative": {"haiku", "poem", "story", "essay", "translate"},
    }
    best_name = "generic"
    best_overlap = 0
    for name, kw in _keywords.items():
        overlap = len(words & kw)
        if overlap > best_overlap:
            best_name, best_overlap = name, overlap
    return best_name

# Task-class defaults when no explicit decomposition block exists.
_DEFAULT_DECOMPOSITIONS: dict[str, dict[str, Any]] = {
    "code_implementation": {
        "confidence": 0.7,
        "colony_range": "3-5",
        "grouping": "group related files",
        "recommended_caste": "coder",
        "recommended_strategy": "stigmergic",
    },
    "code_review": {
        "confidence": 0.7,
        "colony_range": "1-3",
        "grouping": "one colony per module",
        "recommended_caste": "reviewer",
        "recommended_strategy": "sequential",
    },
    "design": {
        "confidence": 0.6,
        "colony_range": "2-3",
        "grouping": "docs vs skeletons",
        "recommended_caste": "coder",
        "recommended_strategy": "sequential",
    },
    "research": {
        "confidence": 0.6,
        "colony_range": "1-2",
        "grouping": "one per question",
        "recommended_caste": "researcher",
        "recommended_strategy": "sequential",
    },
}


def get_decomposition_hints(
    task_description: str,
    *,
    task_class: str | None = None,
) -> str | None:
    """Return a one-line decomposition hint for the Queen's planning brief.

    If *task_class* is provided, uses it directly. Otherwise falls back
    to keyword-based classification from the task description.
    The caller (surface layer) should pass the result of
    ``classify_task()`` when available.

    Returns ``None`` when the result would be too generic to be useful.
    """
    cache_key = task_class or task_description
    if cache_key in _HINT_CACHE:
        return _HINT_CACHE[cache_key]

    if task_class is None:
        task_class = _classify_task_simple(task_description)

    # Try to load explicit decomposition from curated playbook
    decomp = _load_decomposition_block(task_class)

    # Fall back to hardcoded defaults
    if decomp is None:
        decomp = _DEFAULT_DECOMPOSITIONS.get(task_class)

    if decomp is None:
        # Generic with no useful structural hint
        _HINT_CACHE[task_description] = None
        return None

    conf = decomp.get("confidence", 0.5)
    # Suppress hints below 0.5 confidence — too generic to be useful
    if conf < 0.5:
        _HINT_CACHE[task_description] = None
        return None

    hint = (
        f"{task_class} (conf={conf:.2f}) -> "
        f"{decomp.get('colony_range', '1-3')} colonies, "
        f"{decomp.get('grouping', 'default grouping')}, "
        f"{decomp.get('recommended_caste', 'coder')}-led, "
        f"{decomp.get('recommended_strategy', 'stigmergic')}"
    )
    _HINT_CACHE[task_description] = hint
    return hint


def _load_decomposition_block(task_class: str) -> dict[str, Any] | None:
    """Load the ``decomposition`` block from a curated playbook YAML."""
    path = _PLAYBOOK_DIR / f"{task_class}.yaml"
    if not path.exists():
        return None
    try:
        import yaml  # noqa: PLC0415

        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    return data.get("decomposition")


def clear_cache() -> None:
    """Clear all playbook caches (useful for testing)."""
    global _GENERATION_CACHE  # noqa: PLW0603
    _CACHE.clear()
    _COMMON_MISTAKES_CACHE.clear()
    _HINT_CACHE.clear()
    _GENERATION_CACHE = None


# -- Wave 78 Track 4: Playbook write helpers --


def save_playbook(data: dict[str, Any], filename: str | None = None) -> dict[str, Any]:
    """Save a playbook YAML file to config/playbooks/.

    If *filename* is None, generates one from ``data["task_class"]``.
    Returns the saved data dict (with ``_file`` set).
    """
    import yaml  # noqa: PLC0415

    _PLAYBOOK_DIR.mkdir(parents=True, exist_ok=True)

    if filename is None:
        tc = data.get("task_class", "auto_generated")
        # Sanitise to safe filename chars
        safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in str(tc))
        filename = f"auto_{safe}.yaml"

    if not filename.endswith(".yaml"):
        filename = f"{filename}.yaml"

    path = _PLAYBOOK_DIR / filename
    # Never overwrite curated playbooks — only auto_ prefixed ones
    if path.exists() and not path.name.startswith("auto_"):
        log.warning("playbook_loader.save_refused_curated", path=str(path))
        return {}

    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    data["_file"] = path.stem
    clear_cache()
    log.info("playbook_loader.saved", filename=filename)
    return data


def delete_playbook(filename: str) -> bool:
    """Delete a playbook YAML file. Only auto-generated files can be deleted."""
    if not filename.endswith(".yaml"):
        filename = f"{filename}.yaml"

    path = _PLAYBOOK_DIR / filename
    if not path.exists():
        return False
    if not path.name.startswith("auto_"):
        log.warning("playbook_loader.delete_refused_curated", path=str(path))
        return False

    path.unlink()
    clear_cache()
    log.info("playbook_loader.deleted", filename=filename)
    return True


def approve_playbook(filename: str) -> dict[str, Any]:
    """Mark a candidate playbook as approved by setting status=approved."""
    import yaml  # noqa: PLC0415

    if not filename.endswith(".yaml"):
        filename = f"{filename}.yaml"

    path = _PLAYBOOK_DIR / filename
    if not path.exists():
        return {}

    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data["status"] = "approved"
    path.write_text(
        yaml.dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    clear_cache()
    log.info("playbook_loader.approved", filename=filename)
    data["_file"] = path.stem
    return data
