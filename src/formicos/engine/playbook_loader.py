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


def clear_cache() -> None:
    """Clear all playbook caches (useful for testing)."""
    global _GENERATION_CACHE  # noqa: PLW0603
    _CACHE.clear()
    _COMMON_MISTAKES_CACHE.clear()
    _GENERATION_CACHE = None
