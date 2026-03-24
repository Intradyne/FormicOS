"""Conflict resolution for contradictory knowledge entries (Wave 33 C7).

Three-phase resolution:
1. Pareto dominance (obvious winner on 2+ criteria)
2. Composite score with adaptive threshold
3. Keep both as competing hypotheses

Wave 41 A3: adds unified detection/classification layer.
``classify_pair`` distinguishes contradiction vs complement vs temporal
update before resolution. ``detect_contradictions`` scans an entry set
and returns classified pairs — the single entry point that both
``maintenance.py`` and ``proactive_intelligence.py`` now call.

Wave 42: class-aware resolution upgrade (Stage 2).
``resolve_classified`` respects the relation produced by ``classify_pair``:
  - contradiction → confidence-aware three-phase resolution (Beta posterior mean)
  - complement → Resolution.complement (keep both, link as co-usable)
  - temporal_update → Resolution.temporal_update (newer supersedes older)
"""

from __future__ import annotations

import time as _time_mod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from formicos.core.types import Resolution

# ---------------------------------------------------------------------------
# Wave 41 A3 Stage 1: pair classification
# ---------------------------------------------------------------------------


class PairRelation(Enum):
    """How two overlapping knowledge entries relate to each other."""

    contradiction = "contradiction"  # opposite conclusions on same domain
    complement = "complement"        # compatible, different aspects
    temporal_update = "temporal_update"  # newer supersedes older


@dataclass(frozen=True)
class ClassifiedPair:
    """Result of classifying the relationship between two entries."""

    entry_a_id: str
    entry_b_id: str
    relation: PairRelation
    domain_overlap: float  # Jaccard similarity on domains
    detail: str = ""
    # For temporal_update: which entry is newer
    newer_id: str = ""


def jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity coefficient. Returns 0.0 if both sets are empty."""
    if not set_a and not set_b:
        return 0.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def classify_pair(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
    *,
    overlap_threshold: float = 0.3,
) -> ClassifiedPair | None:
    """Classify the relationship between two knowledge entries.

    Returns None if the entries don't overlap enough to be related.

    Classification rules:
      - contradiction: opposite polarity with domain overlap >= threshold
      - temporal_update: same polarity, same entry_type, domain overlap
        >= 0.5, and created_at differs (newer supersedes older)
      - complement: same domain overlap >= threshold but neither
        contradiction nor temporal update
    """
    domains_a = set(_str_list(entry_a.get("domains")))
    domains_b = set(_str_list(entry_b.get("domains")))
    overlap = jaccard(domains_a, domains_b)

    if overlap < overlap_threshold:
        return None

    id_a = entry_a.get("id", "")
    id_b = entry_b.get("id", "")
    pol_a = entry_a.get("polarity", "neutral")
    pol_b = entry_b.get("polarity", "neutral")

    # Contradiction: opposite polarity on overlapping domains
    opposite = (
        (pol_a == "positive" and pol_b == "negative")
        or (pol_a == "negative" and pol_b == "positive")
    )
    if opposite:
        return ClassifiedPair(
            entry_a_id=id_a,
            entry_b_id=id_b,
            relation=PairRelation.contradiction,
            domain_overlap=overlap,
            detail=f"Opposite polarity ({pol_a} vs {pol_b})",
        )

    # Temporal update: same type, high overlap, different timestamps
    type_a = entry_a.get("entry_type", "")
    type_b = entry_b.get("entry_type", "")
    created_a = entry_a.get("created_at", "")
    created_b = entry_b.get("created_at", "")

    if (
        type_a == type_b
        and type_a  # both have a type
        and overlap >= 0.5
        and created_a != created_b
        and created_a
        and created_b
    ):
        newer = id_a if created_a > created_b else id_b
        return ClassifiedPair(
            entry_a_id=id_a,
            entry_b_id=id_b,
            relation=PairRelation.temporal_update,
            domain_overlap=overlap,
            detail=f"Same type ({type_a}), newer entry supersedes",
            newer_id=newer,
        )

    # Complement: overlapping domains, compatible polarity
    return ClassifiedPair(
        entry_a_id=id_a,
        entry_b_id=id_b,
        relation=PairRelation.complement,
        domain_overlap=overlap,
        detail="Compatible entries on overlapping domains",
    )


def detect_contradictions(
    entries: dict[str, dict[str, Any]],
    *,
    status_filter: set[str] | None = None,
    min_alpha: float = 0.0,
    overlap_threshold: float = 0.3,
) -> list[ClassifiedPair]:
    """Scan entries for contradictions, complements, and temporal updates.

    This is the single detection entry point that both maintenance.py
    and proactive_intelligence.py should call.

    Parameters
    ----------
    entries:
        Dict of entry_id -> entry dict.
    status_filter:
        If provided, only consider entries with status in this set.
    min_alpha:
        Minimum conf_alpha to consider (filters low-confidence noise).
    overlap_threshold:
        Jaccard threshold for domain overlap.
    """
    candidates = [
        (eid, e) for eid, e in entries.items()
        if (status_filter is None or e.get("status") in status_filter)
        and float(e.get("conf_alpha", 0)) >= min_alpha
    ]

    results: list[ClassifiedPair] = []
    seen: set[tuple[str, str]] = set()

    for i, (eid_a, ea) in enumerate(candidates):
        for eid_b, eb in candidates[i + 1:]:
            pair_key = (min(eid_a, eid_b), max(eid_a, eid_b))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            # Ensure entries carry their dict key as "id" for classify_pair
            a_with_id = ea if ea.get("id") else {**ea, "id": eid_a}
            b_with_id = eb if eb.get("id") else {**eb, "id": eid_b}

            classified = classify_pair(
                a_with_id, b_with_id, overlap_threshold=overlap_threshold,
            )
            if classified is not None:
                results.append(classified)

    return results


def _str_list(val: Any) -> list[str]:  # noqa: ANN401
    """Safely extract a list of strings from a value."""
    if isinstance(val, list):
        return [str(v) for v in val]  # type: ignore[reportUnknownArgumentType,reportUnknownVariableType]
    return []


# ---------------------------------------------------------------------------
# Wave 33 C7: three-phase conflict resolution
# ---------------------------------------------------------------------------


@dataclass
class ConflictResult:
    resolution: Resolution
    primary_id: str
    secondary_id: str | None = None
    primary_score: float = 0.0
    secondary_score: float = 0.0
    method: str = ""  # "pareto", "threshold", "competing", "complement", "temporal_update"
    detail: str = ""  # Wave 42: inspectable explanation


# ---------------------------------------------------------------------------
# Wave 42 Stage 2: class-aware resolution
# ---------------------------------------------------------------------------


def resolve_classified(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
    classification: ClassifiedPair | None = None,
) -> ConflictResult:
    """Resolve conflict respecting the pair classification.

    Wave 42 Stage 2: the primary resolution entry point.
    - contradiction → three-phase confidence-aware resolution
    - complement → keep both linked as complementary
    - temporal_update → newer supersedes older

    Falls back to classify_pair() when classification is not provided.
    Falls back to resolve_conflict() when classification is None (no overlap).
    """
    if classification is None:
        classification = classify_pair(entry_a, entry_b)

    if classification is None:
        # Entries don't overlap enough — use contradiction resolver directly
        return _resolve_contradiction(
            entry_a, entry_b,
            ClassifiedPair(
                entry_a.get("id", ""), entry_b.get("id", ""),
                PairRelation.contradiction, 0.0, detail="No classification (fallback)",
            ),
        )

    if classification.relation == PairRelation.complement:
        return _resolve_complement(entry_a, entry_b, classification)

    if classification.relation == PairRelation.temporal_update:
        return _resolve_temporal_update(entry_a, entry_b, classification)

    # PairRelation.contradiction — use upgraded confidence-aware resolver
    return _resolve_contradiction(entry_a, entry_b, classification)


def _resolve_complement(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
    classification: ClassifiedPair,
) -> ConflictResult:
    """Complement: keep both, link as co-usable. No winner."""
    id_a = entry_a.get("id", "")
    id_b = entry_b.get("id", "")
    score_a = _beta_mean(entry_a)
    score_b = _beta_mean(entry_b)
    # Primary is the higher-confidence entry for display ordering
    if score_a >= score_b:
        return ConflictResult(
            Resolution.complement, id_a, id_b,
            primary_score=score_a, secondary_score=score_b,
            method="complement",
            detail=f"Complementary entries ({classification.domain_overlap:.0%} domain overlap). "
                   f"Both retained as co-usable.",
        )
    return ConflictResult(
        Resolution.complement, id_b, id_a,
        primary_score=score_b, secondary_score=score_a,
        method="complement",
        detail=f"Complementary entries ({classification.domain_overlap:.0%} domain overlap). "
               f"Both retained as co-usable.",
    )


def _resolve_temporal_update(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
    classification: ClassifiedPair,
) -> ConflictResult:
    """Temporal update: newer supersedes older, older preserved as historical."""
    id_a = entry_a.get("id", "")
    id_b = entry_b.get("id", "")
    newer_id = classification.newer_id
    older_id = id_b if newer_id == id_a else id_a
    newer_score = _beta_mean(entry_a if newer_id == id_a else entry_b)
    older_score = _beta_mean(entry_b if newer_id == id_a else entry_a)
    return ConflictResult(
        Resolution.temporal_update, newer_id, older_id,
        primary_score=newer_score, secondary_score=older_score,
        method="temporal_update",
        detail=f"Temporal update: {newer_id[:12]} supersedes {older_id[:12]}. "
               f"Older entry preserved as historical.",
    )


def _resolve_contradiction(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
    classification: ClassifiedPair,
) -> ConflictResult:
    """Contradiction: upgraded confidence-aware three-phase resolution.

    Uses Beta posterior mean instead of raw observation count for evidence,
    and proper ISO-timestamp-based recency scoring.
    """
    id_a = entry_a.get("id", "")
    id_b = entry_b.get("id", "")

    # Evidence: Beta posterior mean (alpha / (alpha + beta))
    mean_a = _beta_mean(entry_a)
    mean_b = _beta_mean(entry_b)
    rec_a = _recency_score(entry_a)
    rec_b = _recency_score(entry_b)
    prov_a = len(entry_a.get("merged_from", []))
    prov_b = len(entry_b.get("merged_from", []))

    # Phase 1: Pareto dominance (2+ criteria clearly stronger)
    a_dominates = 0
    b_dominates = 0
    margin = 0.15  # posterior mean difference threshold

    if mean_a - mean_b > margin:
        a_dominates += 1
    elif mean_b - mean_a > margin:
        b_dominates += 1
    if rec_a - rec_b > 0.2:
        a_dominates += 1
    elif rec_b - rec_a > 0.2:
        b_dominates += 1
    if prov_a > prov_b + 1:
        a_dominates += 1
    elif prov_b > prov_a + 1:
        b_dominates += 1

    if a_dominates >= 2:
        return ConflictResult(
            Resolution.winner, id_a, id_b,
            primary_score=mean_a, secondary_score=mean_b,
            method="pareto",
            detail=f"Pareto dominance: {id_a[:12]} stronger on {a_dominates}/3 criteria.",
        )
    if b_dominates >= 2:
        return ConflictResult(
            Resolution.winner, id_b, id_a,
            primary_score=mean_b, secondary_score=mean_a,
            method="pareto",
            detail=f"Pareto dominance: {id_b[:12]} stronger on {b_dominates}/3 criteria.",
        )

    # Phase 2: Composite score with adaptive threshold
    score_a = 0.5 * mean_a + 0.3 * rec_a + 0.2 * _normalize(prov_a)
    score_b = 0.5 * mean_b + 0.3 * rec_b + 0.2 * _normalize(prov_b)

    # Adaptive threshold: tighter when both entries have more observations
    total_obs_a = float(entry_a.get("conf_alpha", 5)) + float(entry_a.get("conf_beta", 5))
    total_obs_b = float(entry_b.get("conf_alpha", 5)) + float(entry_b.get("conf_beta", 5))
    avg_obs = (total_obs_a + total_obs_b) / 2
    threshold = 0.05 + 2.0 / max(avg_obs, 1.0)

    if abs(score_a - score_b) > threshold:
        winner = id_a if score_a > score_b else id_b
        loser = id_b if score_a > score_b else id_a
        return ConflictResult(
            Resolution.winner, winner, loser,
            primary_score=max(score_a, score_b),
            secondary_score=min(score_a, score_b),
            method="threshold",
            detail=f"Composite threshold: winner={winner[:12]} "
                   f"(score diff={abs(score_a - score_b):.3f} > threshold={threshold:.3f}).",
        )

    # Phase 3: Keep both as competing hypotheses
    primary = id_a if score_a >= score_b else id_b
    secondary = id_b if score_a >= score_b else id_a
    return ConflictResult(
        Resolution.competing, primary, secondary,
        primary_score=max(score_a, score_b),
        secondary_score=min(score_a, score_b),
        method="competing",
        detail=f"Competing hypotheses: scores too close "
               f"(diff={abs(score_a - score_b):.3f} <= threshold={threshold:.3f}).",
    )


def resolve_conflict(
    entry_a: dict[str, Any],
    entry_b: dict[str, Any],
) -> ConflictResult:
    """Resolve conflict between two entries (legacy entry point).

    Wave 42: now delegates to resolve_classified() which respects
    the pair classification. Kept for backward compatibility.
    """
    return resolve_classified(entry_a, entry_b)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _beta_mean(entry: dict[str, Any]) -> float:
    """Beta posterior mean: alpha / (alpha + beta). Returns [0, 1]."""
    alpha = float(entry.get("conf_alpha", 5.0))
    beta_val = float(entry.get("conf_beta", 5.0))
    if alpha <= 0 and beta_val <= 0:
        return 0.5
    return alpha / (alpha + beta_val) if (alpha + beta_val) > 0 else 0.5


def _recency_score(entry: dict[str, Any]) -> float:
    """ISO-timestamp-based recency with 90-day half-life. Returns [0, 1].

    Wave 42: upgraded from length-based heuristic to proper timestamp decay.
    """
    created = entry.get("created_at", "")
    if not created:
        return 0.0
    try:
        dt = datetime.fromisoformat(created)
        age_days = (_time_mod.time() - dt.timestamp()) / 86400.0
        return 2.0 ** (-age_days / 90.0)
    except (ValueError, TypeError):
        return 0.0


def _normalize(value: float) -> float:
    """Normalize a non-negative value to [0, 1] using sigmoid-like scaling."""
    if value <= 0:
        return 0.0
    return value / (value + 10.0)


__all__ = [
    "ClassifiedPair",
    "ConflictResult",
    "PairRelation",
    "classify_pair",
    "detect_contradictions",
    "jaccard",
    "resolve_classified",
    "resolve_conflict",
]
