"""
FormicOS v0.12.3 -- Queen Hypothesis Engine

Extracted from ``queen_loop.py`` to reduce monolith size.  Contains the
``HypothesisStatus`` enum, ``QueenHypothesis`` model, and the hypothesis
lifecycle functions (format context, log new hypotheses, resolve outcomes).

All functions accept explicit ``context_tree`` / ``colony_manager`` arguments
instead of accessing ``self`` — the ``QueenLoop`` delegates to these.
"""

from __future__ import annotations

import json
import logging
import time as _time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.models import DirectiveType, StrategicDirective

logger = logging.getLogger("formicos.queen.hypothesis_engine")

# ── Constants ────────────────────────────────────────────────────────────

HYPOTHESIS_LOG_KEY = "queen_hypothesis_log"
HYPOTHESIS_LOG_MAX_ENTRIES = 200  # Rolling cap
MAX_HYPOTHESIS_CHARS = 3_000  # v0.12.2 Phase 4: context window budget


# ── Models ───────────────────────────────────────────────────────────────


class HypothesisStatus(str, Enum):
    """Lifecycle of a Queen-generated hypothesis."""

    PROPOSED = "proposed"
    EXPERIMENT_EMITTED = "experiment_emitted"
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    EXPIRED = "expired"


class QueenHypothesis(BaseModel):
    """A single hypothesis the Queen forms from knowledge gaps + EvoFlow data.

    Defined here (not in models.py) per file-ownership constraints to avoid
    colliding with Coder 1's EvoFlow models.
    """

    hypothesis_id: str  # "hyp-00001"
    knowledge_gap: str  # The gap from the Context Tree that motivated this
    experiment_group: str  # Name from config/evoflow.yaml (e.g. "coder_efficiency")
    reasoning: str  # Queen's 1-2 sentence justification
    proposed_changes: list[dict[str, object]] = Field(default_factory=list)
    # e.g. [{"param_path": "recipes.coder.temperature", "variant_value": 0.3}]
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    emitted_directive_id: str = ""  # Links to the EXPERIMENT directive_id
    created_at: str = ""  # ISO 8601
    resolved_at: str = ""  # ISO 8601 (when confirmed/refuted/expired)


# ── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())


def _status_value(status: object) -> str:
    if hasattr(status, "value"):
        return str(status.value).lower()
    return str(status).lower()


# ── Hypothesis Context Formatting ────────────────────────────────────────


def format_hypothesis_context(
    context_tree: Any,
    colony_manager: Any,
    *,
    supercolony_scope: str = "supercolony",
    active_experiments_key: str = "active_experiments",
    get_active_colony_ids_fn: Any = None,
    load_evoflow_groups_fn: Any = None,
) -> str:
    """Build context block showing knowledge gaps and EvoFlow experiment groups.

    The Queen reads this to decide which multi-parameter experiment group
    to test next, mapping knowledge gaps -> experiment group selection ->
    EXPERIMENT directive emission.

    Parameters
    ----------
    context_tree : AsyncContextTree
    colony_manager : ColonyManager
    supercolony_scope : str
    active_experiments_key : str
    get_active_colony_ids_fn : callable
        Function to get active colony IDs.  Defaults to
        ``queen_loop.get_active_colony_ids``.
    load_evoflow_groups_fn : callable
        Function to load EvoFlow groups.  Defaults to
        ``research_coordinator.load_evoflow_groups``.
    """
    # Lazy import to avoid circular deps
    if get_active_colony_ids_fn is None:
        from src.queen_loop import get_active_colony_ids
        get_active_colony_ids_fn = get_active_colony_ids
    if load_evoflow_groups_fn is None:
        from src.queen.research_coordinator import load_evoflow_groups
        load_evoflow_groups_fn = load_evoflow_groups

    # 1. Knowledge gaps from Context Tree
    gaps: list[str] = []
    try:
        active_ids = get_active_colony_ids_fn(colony_manager)
        for colony_id in active_ids:
            colony_gaps = context_tree.get(
                "knowledge", f"{colony_id}.gaps", [],
            )
            if isinstance(colony_gaps, list):
                for g in colony_gaps:
                    if g not in gaps:
                        gaps.append(str(g))
    except Exception:
        pass

    # 2. EvoFlow experiment groups
    evoflow_groups = load_evoflow_groups_fn()

    # 3. Recent experiment results from the Pareto frontier
    experiments = context_tree.get(
        supercolony_scope, active_experiments_key, [],
    )
    recent_results: list[dict[str, object]] = []
    if isinstance(experiments, list):
        for exp in experiments:
            if isinstance(exp, dict) and exp.get("status") in (
                "evaluated", "completed",
            ):
                recent_results.append(exp)
        recent_results = recent_results[-5:]

    # 4. Existing hypotheses (to avoid re-proposing)
    existing_hyps = context_tree.get(
        supercolony_scope, HYPOTHESIS_LOG_KEY, [],
    )
    active_hyp_groups: list[str] = []
    if isinstance(existing_hyps, list):
        for h in existing_hyps:
            if isinstance(h, dict) and h.get("status") in (
                HypothesisStatus.PROPOSED.value,
                HypothesisStatus.EXPERIMENT_EMITTED.value,
            ):
                grp = h.get("experiment_group", "")
                if grp:
                    active_hyp_groups.append(grp)

    if not gaps and not evoflow_groups:
        return ""

    lines = [
        "## Hypothesis Generation Context",
        "",
    ]

    if gaps:
        lines.append("### Knowledge Gaps (from active colonies)")
        lines.append("")
        for i, gap in enumerate(gaps[:10], 1):  # Cap at 10 gaps
            lines.append(f"{i}. {gap}")
        lines.append("")

    if evoflow_groups:
        lines.append("### EvoFlow Experiment Groups")
        lines.append("")
        lines.append(
            "Select an experiment group whose parameters address the "
            "knowledge gaps above. Emit an EXPERIMENT directive with a "
            "multi-parameter payload matching the group's param paths."
        )
        lines.append("")
        for group in evoflow_groups:
            name = group.get("name", "?")
            desc = group.get("description", "")
            params = group.get("params", [])
            param_paths = [p.get("path", "") for p in params if isinstance(p, dict)]
            in_flight = " **(in-flight)**" if name in active_hyp_groups else ""
            lines.append(f"- **{name}**: {desc}{in_flight}")
            if param_paths:
                lines.append(f"  Params: {', '.join(param_paths)}")
        lines.append("")

    if recent_results:
        lines.append("### Recent Experiment Results (Pareto Frontier)")
        lines.append("")
        for res in recent_results:
            eid = res.get("experiment_id", "?")
            param = res.get("param_path", "?")
            status = res.get("status", "?")
            summary = res.get("result_summary", "")
            if isinstance(summary, dict):
                winner = summary.get("winner", "?")
                lines.append(
                    f"- [{eid}] {param}: {status} (winner={winner})"
                )
            else:
                lines.append(f"- [{eid}] {param}: {status}")
        lines.append("")

    lines.append(
        "To propose a hypothesis, emit an EXPERIMENT directive with:\n"
        '```json\n'
        '{"param_path": "<from group params>", '
        '"variant_value": <proposed value>, '
        '"hypothesis": "<your reasoning linking gap to param change>", '
        '"experiment_group": "<group name>", '
        '"target_colony_ids": [...]}\n'
        '```'
    )

    return "\n".join(lines)


# ── Hypothesis Logging ───────────────────────────────────────────────────


async def log_hypotheses(
    context_tree: Any,
    experiment_directives: list[StrategicDirective],
    *,
    supercolony_scope: str = "supercolony",
) -> None:
    """Track EXPERIMENT directives as hypotheses in the hypothesis log."""
    existing = context_tree.get(
        supercolony_scope, HYPOTHESIS_LOG_KEY, [],
    )
    if not isinstance(existing, list):
        existing = []

    # Generate next hypothesis ID
    max_num = 0
    for h in existing:
        if isinstance(h, dict):
            hid = str(h.get("hypothesis_id", ""))
            if hid.startswith("hyp-"):
                try:
                    max_num = max(max_num, int(hid[4:]))
                except ValueError:
                    pass

    for directive in experiment_directives:
        max_num += 1
        # Parse the directive payload to extract experiment details
        payload_data: dict[str, object] = {}
        try:
            payload_data = json.loads(directive.payload)
        except Exception:
            pass

        hypothesis = QueenHypothesis(
            hypothesis_id=f"hyp-{max_num:05d}",
            knowledge_gap=str(payload_data.get("hypothesis", directive.evidence_summary)),
            experiment_group=str(payload_data.get("experiment_group", "")),
            reasoning=directive.evidence_summary,
            proposed_changes=[{
                "param_path": str(payload_data.get("param_path", "")),
                "variant_value": payload_data.get("variant_value"),
            }],
            status=HypothesisStatus.EXPERIMENT_EMITTED,
            emitted_directive_id=directive.directive_id,
            created_at=_now_iso(),
        )
        existing.append(hypothesis.model_dump(mode="json"))

    # Enforce rolling cap
    if len(existing) > HYPOTHESIS_LOG_MAX_ENTRIES:
        existing = existing[-HYPOTHESIS_LOG_MAX_ENTRIES:]

    await context_tree.set(
        supercolony_scope, HYPOTHESIS_LOG_KEY, existing,
    )
    logger.info(
        "Logged %d hypothesis/hypotheses from EXPERIMENT directives",
        len(experiment_directives),
    )


# ── Hypothesis Resolution ───────────────────────────────────────────────


async def resolve_hypothesis(
    context_tree: Any,
    experiment_id: str,
    outcome: str,
    *,
    supercolony_scope: str = "supercolony",
) -> bool:
    """Mark a hypothesis as confirmed or refuted based on experiment outcome.

    Called by the directive dispatcher when an experiment completes.

    Parameters
    ----------
    context_tree : AsyncContextTree
    experiment_id : str
        The experiment_id from the completed experiment.
    outcome : str
        ``"variant"`` -> confirmed, ``"control"`` -> refuted, else expired.

    Returns
    -------
    bool
        True if a matching hypothesis was found and updated.
    """
    existing = context_tree.get(
        supercolony_scope, HYPOTHESIS_LOG_KEY, [],
    )
    if not isinstance(existing, list):
        return False

    updated = False
    for h in existing:
        if not isinstance(h, dict):
            continue
        if h.get("emitted_directive_id") != experiment_id:
            continue
        if h.get("status") not in (
            HypothesisStatus.PROPOSED.value,
            HypothesisStatus.EXPERIMENT_EMITTED.value,
        ):
            continue

        if outcome == "variant":
            h["status"] = HypothesisStatus.CONFIRMED.value
        elif outcome == "control":
            h["status"] = HypothesisStatus.REFUTED.value
        else:
            h["status"] = HypothesisStatus.EXPIRED.value
        h["resolved_at"] = _now_iso()
        updated = True
        break

    if updated:
        await context_tree.set(
            supercolony_scope, HYPOTHESIS_LOG_KEY, existing,
        )
        logger.info(
            "Hypothesis for experiment '%s' resolved as '%s'",
            experiment_id, outcome,
        )

    return updated
