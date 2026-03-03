"""
FormicOS v0.6.0 -- Governance Engine

Monitors colony health across orchestration rounds and emits actionable
decisions: continue, force-halt, intervene, or warn about tunnel vision.

Three detection subsystems:
  1. **Convergence** -- cosine similarity of consecutive round summary vectors.
  2. **Temporal stall** -- repeated failure patterns in TKG tuples.
  3. **Path diversity** -- distinct ``approach`` labels in a sliding window.

All thresholds are driven by ``ConvergenceConfig`` and ``TemporalConfig``
from the top-level FormicOS configuration.

This module depends only on ``src.models`` and ``numpy`` -- no other
internal imports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from src.models import (
    ConvergenceConfig,
    GovernanceRecommendation,
    TemporalConfig,
    TKGTuple,
)

logger = logging.getLogger(__name__)


# ── Data structures ──────────────────────────────────────────────────────

VALID_ACTIONS = frozenset(
    {"continue", "force_halt", "intervene", "warn_tunnel_vision"}
)

FAILURE_PREDICATES = frozenset(
    {"Failed_Test", "Error", "failed_test", "error"}
)


@dataclass
class GovernanceDecision:
    """Result of a single governance evaluation."""

    action: str  # one of VALID_ACTIONS
    reason: str
    recommendations: list[str] = field(default_factory=list)
    enriched_recommendations: list[GovernanceRecommendation] = field(
        default_factory=list
    )

    def __post_init__(self) -> None:
        if self.action not in VALID_ACTIONS:
            raise ValueError(
                f"Invalid action {self.action!r}; "
                f"expected one of {sorted(VALID_ACTIONS)}"
            )


@dataclass
class StallReport:
    """A detected temporal stall (repeated failure pattern)."""

    subject: str
    predicate: str
    occurrences: int
    round_nums: list[int] = field(default_factory=list)
    team_id: str | None = None


# ── Helpers ──────────────────────────────────────────────────────────────


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors.  Returns 0.0 for zero vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


# ── Engine ───────────────────────────────────────────────────────────────


class GovernanceEngine:
    """Colony governance -- convergence, stall detection, path diversity.

    Parameters
    ----------
    config : dict
        The full FormicOS configuration dict, or an object exposing
        ``convergence`` (:class:`ConvergenceConfig`) and
        ``temporal`` (:class:`TemporalConfig`) attributes.
    """

    def __init__(self, config: object) -> None:
        # Accept either a Pydantic model with `.convergence` / `.temporal`
        # or a plain dict with those keys.
        if isinstance(config, dict):
            self._conv: ConvergenceConfig = config.get(
                "convergence", ConvergenceConfig()
            )
            self._temp: TemporalConfig = config.get(
                "temporal", TemporalConfig()
            )
        else:
            self._conv = getattr(config, "convergence", ConvergenceConfig())
            self._temp = getattr(config, "temporal", TemporalConfig())

        # Convergence streak state
        self._convergence_streak: int = 0
        self._previous_decision: GovernanceDecision | None = None

        # Tunnel-vision consecutive-low-diversity streak
        self._tunnel_vision_streak: int = 0

    def apply_overrides(self, triggers: object) -> None:
        """Apply per-caste governance trigger overrides.

        Uses ``min()`` (most conservative) so no caste's safety net is
        silently bypassed when multiple castes share a colony.

        Parameters
        ----------
        triggers :
            A :class:`GovernanceTriggers` instance (or any object whose
            attributes are ``None`` for "keep default" or a numeric value).
        """
        sim = getattr(triggers, "similarity_threshold", None)
        if sim is not None:
            self._conv.similarity_threshold = min(
                self._conv.similarity_threshold, sim,
            )
        halt = getattr(triggers, "rounds_before_force_halt", None)
        if halt is not None:
            self._conv.rounds_before_force_halt = min(
                self._conv.rounds_before_force_halt, halt,
            )
        div = getattr(triggers, "path_diversity_warning_after", None)
        if div is not None:
            self._conv.path_diversity_warning_after = min(
                self._conv.path_diversity_warning_after, div,
            )
        stall_rep = getattr(triggers, "stall_repeat_threshold", None)
        if stall_rep is not None:
            self._temp.stall_repeat_threshold = min(
                self._temp.stall_repeat_threshold, stall_rep,
            )
        stall_win = getattr(triggers, "stall_window_minutes", None)
        if stall_win is not None:
            self._temp.stall_window_minutes = min(
                self._temp.stall_window_minutes, stall_win,
            )

    # ── Public API ───────────────────────────────────────────────────────

    def enforce(
        self,
        round_num: int,
        prev_summary_vec: list[float] | np.ndarray | None,
        curr_summary_vec: list[float] | np.ndarray | None,
    ) -> GovernanceDecision:
        """Evaluate convergence and return a governance decision.

        Parameters
        ----------
        round_num :
            Current orchestration round (0-based or 1-based).
        prev_summary_vec :
            Embedding vector of the *previous* round summary, or ``None``
            if this is the first round.
        curr_summary_vec :
            Embedding vector of the *current* round summary, or ``None``
            if summarisation was skipped.

        Returns
        -------
        GovernanceDecision
            ``action`` is one of ``continue``, ``force_halt``,
            ``intervene``, or ``warn_tunnel_vision``.
        """
        # Guard: missing vectors -- cannot compute similarity
        if prev_summary_vec is None or curr_summary_vec is None:
            self._convergence_streak = 0
            decision = GovernanceDecision(
                action="continue",
                reason="Missing summary vectors; skipping convergence check.",
            )
            self._previous_decision = decision
            return decision

        a = np.asarray(prev_summary_vec, dtype=np.float64)
        b = np.asarray(curr_summary_vec, dtype=np.float64)

        # Guard: mismatched dimensions
        if a.shape != b.shape:
            self._convergence_streak = 0
            decision = GovernanceDecision(
                action="continue",
                reason=(
                    f"Summary vector dimensions mismatch "
                    f"({a.shape} vs {b.shape}); skipping convergence check."
                ),
            )
            self._previous_decision = decision
            return decision

        similarity = _cosine_similarity(a, b)
        threshold = self._conv.similarity_threshold
        halt_after = self._conv.rounds_before_force_halt

        if similarity >= threshold:
            self._convergence_streak += 1
        else:
            # Streak broken
            self._convergence_streak = 0
            decision = GovernanceDecision(
                action="continue",
                reason=(
                    f"Similarity {similarity:.4f} below threshold "
                    f"{threshold}; streak reset."
                ),
            )
            self._previous_decision = decision
            return decision

        # Check if streak triggers force halt
        if self._convergence_streak >= halt_after:
            decision = GovernanceDecision(
                action="force_halt",
                reason=(
                    f"Convergence detected: similarity >= {threshold} "
                    f"for {self._convergence_streak} consecutive rounds "
                    f"(threshold: {halt_after})."
                ),
                recommendations=[
                    "Inject a Researcher agent to explore alternatives",
                    "Escalate to cloud model for higher capability",
                ],
                enriched_recommendations=[
                    GovernanceRecommendation(
                        action="inject_agent",
                        confidence_score=0.8,
                        evidence=f"Similarity {similarity:.4f} for {self._convergence_streak} rounds",
                    ),
                    GovernanceRecommendation(
                        action="escalate",
                        confidence_score=0.6,
                        evidence="Colony stuck; higher-capability model may break deadlock",
                    ),
                ],
            )
            self._previous_decision = decision
            return decision

        # High similarity but not yet at halt threshold -- intervene
        decision = GovernanceDecision(
            action="intervene",
            reason=(
                f"High similarity {similarity:.4f} (>= {threshold}) "
                f"for {self._convergence_streak} round(s); "
                f"approaching convergence."
            ),
            recommendations=[
                "Re-delegate failed subtasks to different agents",
                "Suggest user hint injection",
            ],
            enriched_recommendations=[
                GovernanceRecommendation(
                    action="redelegate",
                    confidence_score=0.7,
                    evidence=f"Similarity {similarity:.4f} approaching threshold",
                ),
            ],
        )
        self._previous_decision = decision
        return decision

    def path_diversity_score(
        self,
        round_history: list[dict],
        window: int = 5,
    ) -> int:
        """Count distinct ``approach`` labels in a sliding window.

        Parameters
        ----------
        round_history :
            List of round dicts, each containing an ``agent_outputs`` dict
            mapping agent IDs to their output dicts.  Each agent output may
            include an ``"approach"`` key.  Alternatively, each entry may
            be a flat dict with an ``"approach"`` key directly.
        window :
            Number of most-recent rounds to consider.

        Returns
        -------
        int
            Number of distinct (case-insensitive, stripped) approach labels.
            Returns 0 if no approaches are found.
        """
        if not isinstance(round_history, list):
            logger.warning(
                "Invalid round_history format (expected list); returning 0"
            )
            return 0

        recent = round_history[-window:] if len(round_history) > window else round_history

        approaches: set[str] = set()

        for entry in recent:
            if not isinstance(entry, dict):
                continue

            # Case 1: entry has agent_outputs with nested dicts
            agent_outputs = entry.get("agent_outputs")
            if isinstance(agent_outputs, dict):
                for _agent_id, output in agent_outputs.items():
                    if isinstance(output, dict):
                        approach = output.get("approach")
                        if approach and isinstance(approach, str):
                            approaches.add(approach.strip().lower())
                    elif isinstance(output, str):
                        # Raw string output -- no approach field
                        pass

            # Case 2: entry itself has an approach key (flat format)
            approach = entry.get("approach")
            if approach and isinstance(approach, str):
                approaches.add(approach.strip().lower())

        return len(approaches)

    def check_tunnel_vision(
        self,
        round_history: list[dict],
        round_num: int,
        window: int = 5,
    ) -> GovernanceDecision | None:
        """Detect tunnel vision (diversity == 1 for 2+ consecutive rounds).

        This is a convenience wrapper that calls :meth:`path_diversity_score`
        and maintains an internal streak counter.

        Returns
        -------
        GovernanceDecision or None
            A ``warn_tunnel_vision`` decision if triggered; ``None`` otherwise.
        """
        diversity = self.path_diversity_score(round_history, window=window)

        if diversity == 1:
            self._tunnel_vision_streak += 1
        else:
            self._tunnel_vision_streak = 0

        if self._tunnel_vision_streak >= 2:
            return GovernanceDecision(
                action="warn_tunnel_vision",
                reason=(
                    f"Path diversity has been 1 for "
                    f"{self._tunnel_vision_streak} consecutive checks "
                    f"(round {round_num}). All agents may be using the "
                    f"same approach."
                ),
                recommendations=[
                    "Inject a Researcher agent to explore alternatives",
                    "Re-delegate failed subtasks to different agents",
                ],
                enriched_recommendations=[
                    GovernanceRecommendation(
                        action="inject_agent",
                        confidence_score=0.75,
                        evidence=f"Diversity=1 for {self._tunnel_vision_streak} checks at round {round_num}",
                    ),
                    GovernanceRecommendation(
                        action="redelegate",
                        confidence_score=0.6,
                        evidence="All agents converged on same approach",
                    ),
                ],
            )
        return None

    def detect_stalls(
        self,
        tkg_tuples: list[TKGTuple | dict],
        round_num: int,
        team_id: str | None = None,
    ) -> list[StallReport]:
        """Scan TKG tuples for repeated failure patterns.

        A stall is detected when the same ``(subject, predicate)`` pair
        with a failure predicate (``Failed_Test``, ``Error``, etc.) appears
        >= ``stall_repeat_threshold`` times within recent rounds.

        Parameters
        ----------
        tkg_tuples :
            Full list of TKG tuples to scan.  Accepts either
            :class:`TKGTuple` instances or plain dicts.
        round_num :
            Current round number (used to define the recency window).
        team_id :
            If given, only consider tuples belonging to this team.

        Returns
        -------
        list[StallReport]
            One report per detected stall pattern.
        """
        threshold = self._temp.stall_repeat_threshold

        # Normalise to dicts for uniform access
        normalised: list[dict] = []
        for t in tkg_tuples:
            if isinstance(t, dict):
                normalised.append(t)
            elif isinstance(t, TKGTuple):
                normalised.append(t.model_dump())
            else:
                logger.warning("Skipping unrecognised TKG tuple type: %s", type(t))
                continue

        # Filter by team_id if specified
        if team_id is not None:
            normalised = [
                t for t in normalised if t.get("team_id") == team_id
            ]

        # Filter to failure predicates only
        failures = [
            t for t in normalised
            if t.get("predicate") in FAILURE_PREDICATES
        ]

        # Group by (subject, predicate)
        from collections import defaultdict

        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for t in failures:
            key = (t["subject"], t["predicate"])
            groups[key].append(t)

        reports: list[StallReport] = []
        for (subject, predicate), tuples in groups.items():
            if len(tuples) >= threshold:
                round_nums = sorted({t.get("round_num", 0) for t in tuples})
                reports.append(
                    StallReport(
                        subject=subject,
                        predicate=predicate,
                        occurrences=len(tuples),
                        round_nums=round_nums,
                        team_id=team_id,
                    )
                )

        return reports
