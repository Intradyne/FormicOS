"""Institutional memory extraction from colony results (Wave 26 A4).

Dual extraction: skills (procedural) + experiences (tactical).
Called by colony_manager after ColonyCompleted/ColonyFailed.
Fire-and-forget -- does NOT block colony lifecycle.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any, cast

import structlog

from formicos.core.types import (
    DecayClass,
    EntrySubType,
    MemoryEntry,
    MemoryEntryPolarity,
    MemoryEntryStatus,
    MemoryEntryType,
    ScanStatus,
)

log = structlog.get_logger()
_MIN_CONTENT_LEN = 30


def _normalize_domain(raw: str) -> str:
    """Normalize a domain tag: lowercase, spaces/hyphens → underscores."""
    return re.sub(r"[\s\-]+", "_", raw.strip()).lower()


def _normalize_domains(raw_domains: list[Any]) -> list[str]:
    """Normalize a list of domain tags, deduplicating after normalization."""
    seen: set[str] = set()
    result: list[str] = []
    for d in raw_domains:
        normed = _normalize_domain(str(d))
        if normed and normed not in seen:
            seen.add(normed)
            result.append(normed)
    return result
_ENVIRONMENT_NOISE_PHRASES = (
    "workspace not configured",
    "workspace directory remains unconfigured",
    "workspace configuration issues",
    "not available in the current environment",
    "git command is unavailable",
    "git command is not available",
    "tool call failure",
    "pytest is not installed",
    "test runner fails due to missing",
    "test runner not available",
    "module not found",
    "pip install",
    "package not installed",
    "import error",
    "no module named",
    "extracting transferable knowledge",
)
_ENVIRONMENT_NOISE_CONTEXTS = (
    "workspace", "environment", "git", "tool", "command",
    "sandbox", "install", "pytest", "pip", "import",
)
_ENVIRONMENT_NOISE_ERRORS = (
    "command not found", "permission denied",
    "no such file or directory", "unavailable", "not configured",
    "not installed", "missing module", "cannot import",
)


def is_environment_noise_text(text: str) -> bool:
    """Return True when *text* looks like run-local environment chatter."""
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(phrase in normalized for phrase in _ENVIRONMENT_NOISE_PHRASES):
        return True
    return (
        any(ctx in normalized for ctx in _ENVIRONMENT_NOISE_CONTEXTS)
        and any(err in normalized for err in _ENVIRONMENT_NOISE_ERRORS)
    )


def build_extraction_prompt(
    task: str, final_output: str, artifacts: list[dict[str, Any]],
    colony_status: str, failure_reason: str | None,
    contract_result: dict[str, Any] | None,
    task_class: str = "generic",
    existing_entries: list[dict[str, Any]] | None = None,
) -> str:
    """Build the LLM prompt for dual skill+experience extraction."""
    parts = [
        "You are extracting institutional memory from a completed colony run.",
        f"\nTASK: {task}\nSTATUS: {colony_status}",
    ]
    if failure_reason:
        parts.append(f"FAILURE REASON: {failure_reason}")
    if contract_result and not contract_result.get("satisfied", True):
        missing = ", ".join(contract_result.get("missing", []))
        parts.append(f"CONTRACT: NOT satisfied. Missing: {missing}")
    if final_output:
        parts.append(f"\nFINAL OUTPUT (truncated):\n{final_output[:2000]}")
    if artifacts:
        parts.append("\nARTIFACTS PRODUCED:")
        for art in artifacts[:5]:
            name = art.get("name", "?")
            atype = art.get("artifact_type", "generic")
            preview = art.get("content", "")[:200]
            parts.append(f"- {name} ({atype}): {preview}")

    # Wave 59: curation context — show existing entries so LLM can decide
    # whether to CREATE, REFINE, MERGE, or NOOP
    if existing_entries:
        parts.append("\nEXISTING ENTRIES (most relevant to this task domain):")
        for ee in existing_entries[:10]:
            ee_id = ee.get("id", "?")
            ee_title = ee.get("title", "untitled")
            ee_conf = float(ee.get("confidence", 0.5))
            ee_access = int(ee.get("access_count", 0))
            ee_domain = ee.get("primary_domain", "")
            ee_content = str(ee.get("content", ""))[:200]
            parts.append(
                f'- [{ee_id}] "{ee_title}" '
                f"(conf: {ee_conf:.2f}, accessed: {ee_access}x"
                f'{f", domain: {ee_domain}" if ee_domain else ""})\n'
                f"  Content: {ee_content}"
            )

    if existing_entries and colony_status == "completed":
        parts.append(
            "\nFor each piece of knowledge from this colony, decide:\n"
            '- CREATE: New knowledge not covered by existing entries.\n'
            '  Include all entry fields (title, content, domains, etc.)\n'
            '- REFINE: An existing entry should be updated with insights from\n'
            '  this colony. Provide "entry_id" + "new_content" (+ optional "new_title")\n'
            '- MERGE: Two entries should be combined. Provide "target_id" +\n'
            '  "source_id" + "merged_content"\n'
            '- NOOP: Existing entry already covers this adequately\n\n'
            'Return JSON: {"actions": [{"type": "CREATE"|"REFINE"|"MERGE"|"NOOP", ...}]}\n\n'
            "Be conservative. REFINE only when the colony produced genuinely new\n"
            "information that makes an existing entry more precise, more actionable,\n"
            "or corrects an error. NOOP is the right choice when existing coverage\n"
            "is adequate.\n"
        )
    elif colony_status == "completed":
        parts.append(
            "\nExtract knowledge that would help a FUTURE task you have not "
            "seen yet. Focus on reusable techniques, not task-specific details.\n"
            "Ask: would an agent working on a completely different problem "
            "benefit from knowing this?\n\n"
            'SKILLS: For each: "title", "content" (actionable instruction), '
            '"when_to_use", "failure_modes", "domains" (list), "tool_refs" (list), '
            '"sub_type" ("technique"|"pattern"|"anti_pattern")\n\n'
            'EXPERIENCES: For each: "title", "content" (1-2 sentences), '
            '"trigger", "domains", "tool_refs", "polarity" ("positive"/"neutral"), '
            '"sub_type" ("decision"|"convention"|"learning"|"bug")\n'
        )
    else:
        parts.append(
            '\nThis colony FAILED. Extract only tactical lessons.\n\n'
            'EXPERIENCES: For each: "title", "content" (warning, 1-2 sentences), '
            '"trigger", "domains", "tool_refs", "polarity": "negative", '
            '"sub_type" ("decision"|"convention"|"learning"|"bug")\n'
        )
    parts.append(
        'For each entry, classify "decay_class":\n'
        '- "ephemeral": task-specific observations, temporary workarounds\n'
        '- "stable": domain knowledge, established patterns, architectural decisions\n'
        '- "permanent": verified definitions, mathematical facts, immutable truths\n'
        'Default to "ephemeral" if uncertain.\n'
    )
    parts.append(
        f'Tag each entry with "primary_domain": "{task_class}". '
        "This classifies the task context the knowledge was extracted from.\n"
    )
    if not (existing_entries and colony_status == "completed"):
        parts.append(
            'Return JSON: {"skills": [...], "experiences": [...]}\n'
            "Empty arrays if no transferable knowledge. Be conservative."
        )
    return "\n".join(parts)


def build_memory_entries(
    raw: dict[str, Any], colony_id: str, workspace_id: str,
    artifact_ids: list[str], colony_status: str,
) -> list[dict[str, Any]]:
    """Convert LLM extraction output into MemoryEntry dicts."""
    entries: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    for i, skill in enumerate(raw.get("skills", [])):
        if len(skill.get("content", "")) < _MIN_CONTENT_LEN:
            continue
        if is_environment_noise_text(
            f"{skill.get('title', '')} {skill.get('content', '')}",
        ):
            continue
        try:
            dc = DecayClass(skill.get("decay_class", "ephemeral"))
        except ValueError:
            dc = DecayClass.ephemeral
        try:
            st = EntrySubType(skill["sub_type"]) if skill.get("sub_type") else None
        except ValueError:
            st = None
        entries.append(MemoryEntry(
            id=f"mem-{colony_id}-s-{i}", entry_type=MemoryEntryType.skill,
            status=MemoryEntryStatus.candidate, polarity=MemoryEntryPolarity.positive,
            title=skill.get("title", f"skill-{i}"), content=skill["content"],
            summary=skill.get("when_to_use", ""), source_colony_id=colony_id,
            source_artifact_ids=artifact_ids,
            domains=_normalize_domains(skill.get("domains", [])),
            tool_refs=skill.get("tool_refs", []), confidence=0.5,
            scan_status=ScanStatus.pending, created_at=now, workspace_id=workspace_id,
            decay_class=dc, sub_type=st,
        ).model_dump())

    for i, exp in enumerate(raw.get("experiences", [])):
        if len(exp.get("content", "")) < _MIN_CONTENT_LEN:
            continue
        if is_environment_noise_text(
            f"{exp.get('title', '')} {exp.get('content', '')}",
        ):
            continue
        pol_str = "negative" if colony_status != "completed" else exp.get("polarity", "neutral")
        try:
            polarity = MemoryEntryPolarity(pol_str)
        except ValueError:
            polarity = MemoryEntryPolarity.neutral
        try:
            dc = DecayClass(exp.get("decay_class", "ephemeral"))
        except ValueError:
            dc = DecayClass.ephemeral
        try:
            st = EntrySubType(exp["sub_type"]) if exp.get("sub_type") else None
        except ValueError:
            st = None
        entries.append(MemoryEntry(
            id=f"mem-{colony_id}-e-{i}", entry_type=MemoryEntryType.experience,
            status=MemoryEntryStatus.candidate, polarity=polarity,
            title=exp.get("title", f"experience-{i}"), content=exp["content"],
            summary=exp.get("trigger", ""), source_colony_id=colony_id,
            source_artifact_ids=artifact_ids,
            domains=_normalize_domains(exp.get("domains", [])),
            tool_refs=exp.get("tool_refs", []),
            confidence=0.5 if colony_status == "completed" else 0.4,
            scan_status=ScanStatus.pending, created_at=now, workspace_id=workspace_id,
            decay_class=dc, sub_type=st,
        ).model_dump())

    return entries


def parse_extraction_response(text: str) -> dict[str, Any]:
    """Defensively parse LLM JSON response. Handles code fences and partial JSON."""
    cleaned = re.sub(r"^```\w*\n|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, dict):
            parsed = cast("dict[str, Any]", result)
            # Wave 59: detect mixed format (actions + legacy keys)
            if "actions" in parsed and ("skills" in parsed or "experiences" in parsed):
                log.warning("extraction.mixed_format_detected")
            return parsed
    except json.JSONDecodeError:
        pass
    # Find first balanced JSON object
    start = cleaned.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(cleaned)):
            depth += (cleaned[i] == "{") - (cleaned[i] == "}")
            if depth == 0:
                try:
                    return cast("dict[str, Any]", json.loads(cleaned[start : i + 1]))
                except json.JSONDecodeError:
                    break
    # Wave 58: json_repair fallback for cloud model responses (Gemini wraps
    # in markdown fences with trailing text that the regex doesn't fully strip).
    try:
        import json_repair  # noqa: PLC0415

        result = json_repair.loads(cleaned)
        if isinstance(result, dict):
            return result  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        pass
    log.warning("memory_extractor.parse_failed", text_preview=text[:200])
    return {"skills": [], "experiences": []}


# ---------------------------------------------------------------------------
# Wave 33 A1: Transcript harvest — second extraction pass on full transcript
# ---------------------------------------------------------------------------

HARVEST_TYPES: dict[str, str] = {
    "bug": "experience",
    "decision": "experience",
    "convention": "skill",
    "learning": "experience",
}

# Maps harvest type → EntrySubType value (Wave 34 B3).
# Harvest types already align 1:1 with EntrySubType enum members.
HARVEST_SUB_TYPE_MAP: dict[str, str] = {
    "bug": "bug",
    "decision": "decision",
    "convention": "convention",
    "learning": "learning",
}


def build_harvest_prompt(turns: list[dict[str, Any]]) -> str:
    """Build LLM prompt for transcript harvest classification.

    Each turn is a dict with agent_id, caste, content, event_kind, round_number.
    """
    parts = [
        "You are reviewing a colony transcript to harvest institutional knowledge.",
        "For each turn, classify as KEEP or SKIP.",
        "KEEP entries are classified by type: bug, decision, convention, or learning.",
        "",
        "TURNS:",
    ]
    for i, turn in enumerate(turns):
        agent = turn.get("agent_id", "unknown")
        caste = turn.get("caste", "unknown")
        rnd = turn.get("round_number", "?")
        content = str(turn.get("content", ""))[:500]
        parts.append(f"\n[Turn {i}] agent={agent} caste={caste} round={rnd}")
        parts.append(content)

    parts.append(
        "\n\nFocus on reusable insights — patterns, pitfalls, or decisions "
        "that would help a future task in a different domain.\n"
        'Return JSON: {"entries": [{"turn_index": N, '
        '"type": "bug"|"decision"|"convention"|"learning", '
        '"summary": "one-sentence summary"}]}\n'
        "Only include KEEP entries. Empty array if nothing notable."
    )
    return "\n".join(parts)


def parse_harvest_response(text: str) -> list[dict[str, Any]]:
    """Parse harvest LLM response into classified entries.

    Returns list of {turn_index, type, summary}.
    Uses json_repair for robustness (already a dependency).
    """
    cleaned = re.sub(r"^```\w*\n|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # Try json_repair as fallback
        try:
            import json_repair  # noqa: PLC0415

            result = json_repair.loads(cleaned)
        except Exception:  # noqa: BLE001
            log.warning("harvest.parse_failed", text_preview=text[:200])
            return []

    raw_entries: list[Any]
    if isinstance(result, dict):
        result_dict = cast("dict[str, Any]", result)
        found = result_dict.get("entries", [])
        raw_entries = cast("list[Any]", found) if isinstance(found, list) else []
    elif isinstance(result, list):
        raw_entries = cast("list[Any]", result)
    else:
        return []

    validated: list[dict[str, Any]] = []
    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue
        if "type" not in entry or "summary" not in entry:
            continue
        if entry["type"] not in HARVEST_TYPES:
            continue
        if is_environment_noise_text(str(entry.get("summary", ""))):
            continue
        validated.append(cast("dict[str, Any]", entry))
    return validated


__all__ = [
    "build_extraction_prompt",
    "build_harvest_prompt",
    "build_memory_entries",
    "is_environment_noise_text",
    "parse_extraction_response",
    "parse_harvest_response",
]
