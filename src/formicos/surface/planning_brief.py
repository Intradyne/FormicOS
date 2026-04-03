"""Conditional planning brief for Queen decomposition turns (Wave 80/82).

Formats the structured planning signals (from ``planning_signals.py``)
into a compact text block injected into the Queen context. No LLM calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()

_CHARS_PER_TOKEN = 4


async def build_planning_brief(
    runtime: Runtime,
    workspace_id: str,
    thread_id: str,
    operator_message: str,
    *,
    token_budget: int,
) -> str:
    """Build a scored planning brief from structured signals.

    Returns a compact text block (under *token_budget* tokens) or an empty
    string if no useful signal is available.
    """
    from formicos.surface.planning_signals import build_planning_signals  # noqa: PLC0415

    char_budget = token_budget * _CHARS_PER_TOKEN

    signals = await build_planning_signals(
        runtime, workspace_id, thread_id, operator_message,
    )

    lines: list[str] = []

    # 1. Patterns
    patterns = signals.get("patterns", [])
    if patterns:
        parts = [
            f"{p['title']} (q={p['quality']}, score={p['score']})"
            for p in patterns[:3]
        ]
        lines.append(f"Patterns: {' | '.join(parts)}")
    else:
        # Fallback: outcome stats from previous_plans
        prev = signals.get("previous_plans", [])
        if prev and isinstance(prev, list) and prev:
            first = prev[0]
            if "evidence" in first:
                lines.append(f"Patterns: prior outcomes ({first['evidence']})")

    # 2. Playbook
    playbook = signals.get("playbook")
    if playbook and isinstance(playbook, dict):
        hint = playbook.get("hint", "")
        if hint:
            lines.append(f"Playbook: {hint}")

    # 3. Worker capability
    cap = signals.get("capability")
    if cap and isinstance(cap, dict):
        summary = cap.get("summary")
        short = cap.get("short_name", "")
        if summary:
            lines.append(f"Worker: {summary}")
        elif short:
            lines.append(f"Worker: {short}")

    # 4. Coupling
    coupling = signals.get("coupling")
    if coupling and isinstance(coupling, dict):
        source = coupling.get("source", "")
        if source == "structural_planner":
            hint_text = coupling.get("hint", "")
            if hint_text:
                lines.append(f"Coupling: {hint_text}")
        elif coupling.get("has_file_refs"):
            lines.append("Coupling: file references detected")

    # 5. Saved plan patterns (Wave 84.5 / 85)
    saved = signals.get("saved_patterns", [])
    if saved:
        sp = saved[0]
        name = sp.get("name", "unnamed")
        match_score = sp.get("match_score", 0)
        colonies = sp.get("colony_count", 0)
        outcome_q = sp.get("outcome_quality", 0)

        # Build match-basis cues
        cues: list[str] = []
        if match_score >= 0.5:
            cues.append("task-class")
        if match_score >= 0.8:
            cues.append("files")
        basis = "+".join(cues) if cues else "match"

        # Only show q= when outcome quality is actually present
        parts = [f"match={match_score:.2f}"]
        if outcome_q and outcome_q > 0:
            parts.append(f"q={outcome_q:.2f}")
        parts.append(f"{colonies} colon{'ies' if colonies != 1 else 'y'}")
        parts.append(basis)

        lines.append(f"Saved: {name} ({', '.join(parts)})")

    if not lines:
        return ""

    brief = "PLANNING BRIEF\n" + "\n".join(f"- {line}" for line in lines)

    if len(brief) > char_budget:
        brief = brief[:char_budget].rsplit("\n", 1)[0]

    # Wave 84.5: structured observability
    log.info(
        "planning_brief.assembled",
        pattern_count=len(signals.get("patterns", [])),
        playbook_source=(
            signals.get("playbook", {}).get("source", "")
            if signals.get("playbook") else ""
        ),
        capability_source=(
            signals.get("capability", {}).get("short_name", "")
            if signals.get("capability") else ""
        ),
        saved_pattern=bool(saved),
        previous_plan_count=len(signals.get("previous_plans", [])),
        brief_tokens=len(brief) // 4,
    )
    log.debug("planning_brief.full_text", brief=brief)

    return brief


# Kept for backward compat and direct test usage


def _fallback_outcome_stats(runtime: Runtime, workspace_id: str) -> str:
    """Use outcome stats as a fallback when knowledge catalog is sparse."""
    try:
        stats = runtime.projections.outcome_stats(workspace_id)
    except Exception:
        return ""

    if not stats:
        return ""

    total_q = 0.0
    count = 0
    strategies: dict[str, int] = {}
    for s in stats:
        q = s.get("avg_quality", 0.0)
        n = s.get("count", 0)
        strat = s.get("strategy", "unknown")
        if n > 0:
            total_q += q * n
            count += n
            strategies[strat] = strategies.get(strat, 0) + n

    if count == 0:
        return ""

    avg_q = total_q / count
    top_strat = max(strategies, key=strategies.get) if strategies else "unknown"  # type: ignore[arg-type]
    return f"Patterns: prior outcomes (n={count}, avg_q={avg_q:.2f}, {top_strat})"
