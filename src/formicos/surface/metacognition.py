"""Metacognitive nudges for institutional memory use (Wave 26).

Pure functions, no I/O. Called by queen_runtime.py.
Separates deterministic orchestration triggers (handled by other tracks)
from model-facing hints (this module).
"""

from __future__ import annotations

import time
from typing import Any

# Cooldown: minimum seconds between nudges of the same type
_DEFAULT_COOLDOWN_SECS = 300.0


# ---------------------------------------------------------------------------
# Nudge templates (model-facing hints, appended as developer messages)
# ---------------------------------------------------------------------------

NUDGE_PRIOR_FAILURES = (
    "Note: Prior colonies encountered failures in domains relevant to this task. "
    "Relevant experiences have been included in your context. "
    "Pay attention to negative-polarity entries -- they describe approaches that failed."
)

NUDGE_SAVE_CORRECTIONS = (
    "Note: You redirected or modified this colony's approach. "
    "Consider whether this correction reflects a transferable lesson. "
    "If so, it will be captured automatically on completion."
)

NUDGE_MEMORY_AVAILABLE = (
    "Note: Institutional memory is available for this workspace. "
    "Relevant skills and experiences have been pre-loaded into your context. "
    "You can also use memory_search to find additional entries."
)

_NUDGE_TEXT: dict[str, str] = {
    "prior_failures": NUDGE_PRIOR_FAILURES,
    "save_corrections": NUDGE_SAVE_CORRECTIONS,
    "memory_available": NUDGE_MEMORY_AVAILABLE,
}


def should_nudge(
    nudge_type: str,
    cooldown_state: dict[str, float],
    cooldown_secs: float = _DEFAULT_COOLDOWN_SECS,
) -> bool:
    """Check whether a nudge should fire, respecting cooldown.

    Mutates *cooldown_state* by recording the current timestamp when the
    nudge is allowed.  Returns True if the nudge should be emitted.
    """
    now = time.monotonic()
    last = cooldown_state.get(nudge_type, 0.0)
    if now - last < cooldown_secs:
        return False
    cooldown_state[nudge_type] = now
    return True


def check_prior_failures(
    task_domains: list[str],
    memory_entries: list[dict[str, Any]],
) -> bool:
    """Return True if negative experiences exist in overlapping domains."""
    if not task_domains or not memory_entries:
        return False
    task_set = set(task_domains)
    for entry in memory_entries:
        if entry.get("polarity") == "negative":
            entry_domains = set(entry.get("domains", []))
            if task_set & entry_domains:
                return True
    return False


def check_memory_available(
    memory_entry_count: int,
) -> bool:
    """Return True if the workspace has institutional memory entries."""
    return memory_entry_count > 0


def format_nudge(nudge_type: str) -> str:
    """Return the nudge text for a given type, or empty string if unknown."""
    return _NUDGE_TEXT.get(nudge_type, "")
