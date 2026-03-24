"""Memory entry security scanner -- synchronous, sub-50ms, stdlib only (Wave 26 B1).

Evaluates memory entry content for security risk signals across four axes.
Runs on every entry BEFORE ``MemoryEntryCreated`` is emitted so that
``scan_status`` is baked into the persisted event payload.  No re-scanning
on replay.

Consumed by: ``memory_extractor.py`` (Track A extraction pipeline).
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Composite score -> tier mapping
# ---------------------------------------------------------------------------

_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (2.8, "critical"),
    (2.0, "high"),
    (1.2, "medium"),
    (0.5, "low"),
)


def _tier_from_score(score: float) -> str:
    for threshold, label in _THRESHOLDS:
        if score >= threshold:
            return label
    return "safe"


# ---------------------------------------------------------------------------
# Axis 1 -- Content risk patterns
# ---------------------------------------------------------------------------

_RE_EXEC = re.compile(
    r"\beval\s*[(]|\bexec\s*[(]|subprocess\.(?:run|call|Popen)|os\.(?:system|popen)",
    re.IGNORECASE,
)
_RE_SUDO = re.compile(r"\bsudo\s+\S+", re.IGNORECASE)
_RE_EXFIL = re.compile(
    r"curl\s+.*-d\s|wget\s+.*--post|requests\.post\s*\(",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Axis 2 -- Supply chain risk patterns
# ---------------------------------------------------------------------------

_RE_PIPE_SHELL = re.compile(
    r"(?:curl|wget)\s[^\n|]{0,200}\|\s*(?:ba)?sh\b",
    re.IGNORECASE,
)
_RE_TRANSITIVE_INSTALL = re.compile(
    r"pip\s+install\s+git\+|npm\s+install\s+https?://|npx\s+\S+",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Axis 3 -- Vulnerability risk patterns
# ---------------------------------------------------------------------------

_RE_PROMPT_INJECT = re.compile(
    r"ignore\s+(?:previous|all|above)\s+instructions|system\s*:\s*you\s+are",
    re.IGNORECASE,
)
_RE_CREDENTIAL = re.compile(
    r"(?:api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^'\"]{8,}",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Axis 4 -- Capability risk: dangerous tool combinations
# ---------------------------------------------------------------------------

_DANGEROUS_TOOL_COMBOS: list[set[str]] = [
    {"http_fetch", "file_write"},
    {"code_execute", "http_fetch"},
    {"file_write", "code_execute"},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Scan a memory entry and return risk assessment.

    Returns::

        {
            "tier": "safe" | "low" | "medium" | "high" | "critical",
            "score": float,
            "axes": {
                "content": float,
                "supply_chain": float,
                "vulnerability": float,
                "capability": float,
            },
            "findings": ["list of matched pattern descriptions"],
        }
    """
    content = f"{entry.get('content', '')} {entry.get('title', '')}"
    tool_refs = set(entry.get("tool_refs", []))

    scores: dict[str, float] = {
        "content": 0.0,
        "supply_chain": 0.0,
        "vulnerability": 0.0,
        "capability": 0.0,
    }
    findings: list[str] = []

    # -- Content risk --
    if _RE_EXEC.search(content):
        scores["content"] += 1.0
        findings.append("exec/eval pattern")
    if _RE_SUDO.search(content):
        scores["content"] += 0.8
        findings.append("sudo usage")
    if _RE_EXFIL.search(content):
        scores["content"] += 1.2
        findings.append("data exfiltration pattern")

    # -- Supply chain risk --
    if _RE_PIPE_SHELL.search(content):
        scores["supply_chain"] += 1.5
        findings.append("pipe-to-shell")
    if _RE_TRANSITIVE_INSTALL.search(content):
        scores["supply_chain"] += 1.0
        findings.append("transitive install from URL/git")

    # -- Vulnerability risk --
    if _RE_PROMPT_INJECT.search(content):
        scores["vulnerability"] += 1.5
        findings.append("prompt injection pattern")
    if _RE_CREDENTIAL.search(content):
        scores["vulnerability"] += 1.0
        findings.append("embedded credential")

    # -- Capability risk --
    for combo in _DANGEROUS_TOOL_COMBOS:
        if combo.issubset(tool_refs):
            scores["capability"] += 0.8
            findings.append(f"dangerous tool combo: {sorted(combo)}")

    composite = sum(scores.values())

    return {
        "tier": _tier_from_score(composite),
        "score": round(composite, 2),
        "axes": scores,
        "findings": findings,
    }


__all__ = ["scan_entry"]
