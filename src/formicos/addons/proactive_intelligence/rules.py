"""Proactive intelligence: deterministic insight generation from projection signals.

15 rules surface actionable knowledge system intelligence. No LLM calls.
7 knowledge rules, 4 performance rules (Wave 36), evaporation (Wave 37),
branching stagnation (Wave 37), earned autonomy (Wave 39),
popular-but-unexamined (Wave 58.5).
Cost efficiency reporting (Wave 41 B4).
Injected into Queen context and exposed via MCP resource + REST endpoint.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

import structlog
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SuggestedColony(BaseModel):
    """Colony configuration that could resolve this insight.

    Wave 35 will add auto-dispatch. Wave 34.5 just structures the data.
    """

    task: str
    caste: str  # "researcher" | "archivist" | "coder"
    strategy: str  # "sequential" | "stigmergic"
    max_rounds: int = 5
    rationale: str = ""
    estimated_cost: float = 0.0  # USD cost estimate for budget tracking


class KnowledgeInsight(BaseModel):
    """A single proactive insight for the operator or Queen."""

    severity: str = Field(
        ..., description="info | attention | action_required",
    )
    category: str = Field(
        ...,
        description=(
            "confidence | contradiction | federation | coverage"
            " | staleness | merge | inbound"
        ),
    )
    title: str = Field(..., description="One-line summary")
    detail: str = Field(..., description="2-3 sentence explanation")
    affected_entries: list[str] = Field(default_factory=list)
    suggested_action: str = Field(default="")
    suggested_colony: SuggestedColony | None = None
    forage_signal: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Bounded forage signal for the ForagerService. When present, "
            "the maintenance dispatcher can hand this to ForagerService "
            "to trigger a proactive forage cycle. Shape matches "
            "ForagerService.handle_forage_signal() input."
        ),
    )


class ProactiveBriefing(BaseModel):
    """System intelligence briefing, assembled from projection signals."""

    workspace_id: str
    generated_at: str
    insights: list[KnowledgeInsight]
    total_entries: int
    entries_by_status: dict[str, int]
    avg_confidence: float
    prediction_error_rate: float
    active_clusters: int
    distillation_candidates: int = 0
    federation_summary: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Insight rules
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {
    "action_required": 0,
    "attention": 1,
    "info": 2,
}


def _parse_ts(ts: str) -> datetime | None:
    """Best-effort ISO timestamp parse."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _jaccard(a: list[str], b: list[str]) -> float:
    """Jaccard similarity between two string lists."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _str_list(val: Any) -> list[str]:
    """Safely extract a list[str] from a dict value."""
    if not isinstance(val, list):
        return []
    result: list[str] = []
    for item in val:  # pyright: ignore[reportUnknownVariableType]
        result.append(str(item))  # pyright: ignore[reportUnknownArgumentType]
    return result


def _word_overlap(a: str, b: str) -> float:
    """Word-level Jaccard between two strings (lowercased)."""
    wa = set(a.lower().split())
    wb = set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


# -- Rule 1: Confidence decline ------------------------------------------------


def _rule_confidence_decline(
    entries: dict[str, dict[str, Any]],
) -> list[KnowledgeInsight]:
    """Entry alpha dropped >20% in 7 days."""
    insights: list[KnowledgeInsight] = []
    now = datetime.now(tz=UTC)
    cutoff = now - timedelta(days=7)

    for eid, e in entries.items():
        alpha = float(e.get("conf_alpha", 0))
        if alpha <= 0:
            continue
        peak = float(e.get("peak_alpha", alpha))
        if peak <= 0:
            continue
        # Only flag if confidence update was recent (within 7 days)
        last_update = _parse_ts(str(e.get("last_confidence_update", "")))
        if last_update is None or last_update < cutoff:
            continue
        decline = (peak - alpha) / peak
        if decline > 0.20:
            title_str = e.get("title", eid[:12])
            domains = _str_list(e.get("domains"))
            insights.append(KnowledgeInsight(
                severity="attention",
                category="confidence",
                title=f"Confidence declining: {title_str}",
                detail=(
                    f"Entry alpha dropped {decline:.0%} from peak {peak:.1f} "
                    f"to {alpha:.1f}. Recent colonies found it less useful."
                ),
                affected_entries=[eid],
                suggested_action="Review entry for accuracy or staleness.",
                forage_signal={
                    "trigger": "proactive:confidence_decline",
                    "gap_description": (
                        f"Entry '{title_str}' confidence declined {decline:.0%}. "
                        f"May need fresh external knowledge."
                    ),
                    "topic": title_str,
                    "domains": domains,
                    "context": f"alpha dropped from {peak:.1f} to {alpha:.1f}",
                    "max_results": 3,
                },
            ))
    return insights


# -- Rule 2: Contradiction ------------------------------------------------


def _rule_contradiction(
    entries: dict[str, dict[str, Any]],
) -> list[KnowledgeInsight]:
    """Classified pair insights: contradictions, temporal updates, complements.

    Wave 41 A3: delegates detection to the shared seam in
    conflict_resolution.detect_contradictions, then wraps results
    as KnowledgeInsight objects for the briefing pipeline.

    Wave 42: class-aware precision — contradictions get action_required,
    temporal updates get attention, complements get info.
    """
    from formicos.surface.conflict_resolution import (  # noqa: PLC0415
        PairRelation,
        detect_contradictions,
        resolve_classified,
    )

    pairs = detect_contradictions(
        entries,
        status_filter={"verified", "stable", "promoted"},
        min_alpha=5.0,
    )

    insights: list[KnowledgeInsight] = []
    for pair in pairs:
        ea = entries.get(pair.entry_a_id, {})
        eb = entries.get(pair.entry_b_id, {})
        title_a = ea.get("title", pair.entry_a_id[:12])
        title_b = eb.get("title", pair.entry_b_id[:12])

        if pair.relation == PairRelation.contradiction:
            # Resolve to get inspectable detail
            result = resolve_classified(ea, eb, pair)
            insights.append(KnowledgeInsight(
                severity="action_required",
                category="contradiction",
                title=f"Knowledge conflict: {title_a} vs {title_b}",
                detail=(
                    f"Two high-confidence entries have opposite conclusions "
                    f"with {pair.domain_overlap:.0%} domain overlap. "
                    f"Both are verified. Resolution: {result.method} "
                    f"({result.detail})"
                ),
                affected_entries=[pair.entry_a_id, pair.entry_b_id],
                suggested_action=(
                    "Review and resolve the contradiction before spawning "
                    "colonies that depend on this domain."
                ),
                suggested_colony=SuggestedColony(
                    task=(
                        f"Investigate contradiction between '{title_a}' and "
                        f"'{title_b}'. Determine which is correct based on "
                        f"current evidence."
                    ),
                    caste="researcher",
                    strategy="sequential",
                    max_rounds=5,
                    rationale="Contradicting high-confidence entries need research resolution.",
                    estimated_cost=5 * 0.08,
                ),
            ))
        elif pair.relation == PairRelation.temporal_update:
            newer_title = title_a if pair.newer_id == pair.entry_a_id else title_b
            older_title = title_b if pair.newer_id == pair.entry_a_id else title_a
            insights.append(KnowledgeInsight(
                severity="attention",
                category="contradiction",
                title=f"Temporal update: {newer_title} supersedes {older_title}",
                detail=(
                    f"Entry '{newer_title}' is a temporal update of "
                    f"'{older_title}' ({pair.domain_overlap:.0%} domain overlap, "
                    f"same type). The older entry may need archival or status change."
                ),
                affected_entries=[pair.entry_a_id, pair.entry_b_id],
                suggested_action=(
                    "Consider archiving or demoting the older entry if the "
                    "newer version fully supersedes it."
                ),
            ))
    return insights


# -- Rule 3: Federation trust drop -------------------------------------------


def _rule_federation_trust_drop(
    projections: ProjectionStore,
) -> list[KnowledgeInsight]:
    """Any peer's trust score dropped below 0.5."""
    insights: list[KnowledgeInsight] = []
    # Federation peer state may not be in projections yet
    peer_connections: dict[str, Any] = getattr(
        projections, "peer_connections", {},
    )
    for peer_id, peer in peer_connections.items():
        trust = float(getattr(peer, "trust_score", 1.0))
        if trust < 0.5:
            insights.append(KnowledgeInsight(
                severity="attention",
                category="federation",
                title=f"Peer trust declining: {peer_id}",
                detail=(
                    f"Trust score for peer {peer_id} is {trust:.2f}. "
                    f"Recent entries from this peer had mixed outcomes."
                ),
                affected_entries=[],
                suggested_action=(
                    "Review recent entries from this peer. "
                    "Consider pausing pull replication."
                ),
            ))
    return insights


# -- Rule 4: Coverage gap ---------------------------------------------------


def _rule_coverage_gap(
    entries: dict[str, dict[str, Any]],
) -> list[KnowledgeInsight]:
    """Entries with high prediction error counts signal coverage gaps."""
    insights: list[KnowledgeInsight] = []
    # Count entries with high prediction errors by domain
    domain_errors: dict[str, list[str]] = {}
    for eid, e in entries.items():
        errors = int(e.get("prediction_error_count", 0))
        if errors < 3:
            continue
        domains = _str_list(e.get("domains"))
        for d in domains:
            domain_errors.setdefault(d, []).append(eid)

    for domain, eids in domain_errors.items():
        severity = "attention" if len(eids) >= 3 else "info"
        insights.append(KnowledgeInsight(
            severity=severity,
            category="coverage",
            title=f"Coverage gap in '{domain}'",
            detail=(
                f"{len(eids)} entries in '{domain}' have 3+ prediction errors. "
                f"Retrieved knowledge is not matching query intent."
            ),
            affected_entries=eids[:5],
            suggested_action=(
                "Consider a research colony to expand coverage in this domain."
            ),
            suggested_colony=SuggestedColony(
                task=(
                    f"Research '{domain}' to fill knowledge gap. Current "
                    f"queries return only unvalidated results."
                ),
                caste="researcher",
                strategy="sequential",
                max_rounds=5,
                rationale=f"{len(eids)} entries with high prediction errors in '{domain}'.",
                estimated_cost=5 * 0.08,
            ),
            forage_signal={
                "trigger": "proactive:coverage_gap",
                "gap_description": (
                    f"{len(eids)} entries in '{domain}' have high prediction errors. "
                    f"Knowledge not matching query intent."
                ),
                "topic": domain,
                "domains": [domain],
                "context": f"{len(eids)} entries with 3+ prediction errors",
                "max_results": 5,
            },
        ))
    return insights


# -- Rule 5: Stale cluster --------------------------------------------------


def _rule_stale_cluster(
    entries: dict[str, dict[str, Any]],
    cooccurrence_weights: dict[tuple[str, str], Any],
) -> list[KnowledgeInsight]:
    """Co-occurrence cluster where all entries have prediction_error_count > 3."""
    insights: list[KnowledgeInsight] = []
    if not cooccurrence_weights:
        return insights

    # Build adjacency: connected components with weight > 0.5
    adj: dict[str, set[str]] = {}
    for (a, b), entry in cooccurrence_weights.items():
        weight = float(getattr(entry, "weight", 0.0))
        if weight <= 0.5:
            continue
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)

    # Find connected components via BFS
    visited: set[str] = set()
    clusters: list[set[str]] = []
    for node in adj:
        if node in visited:
            continue
        cluster: set[str] = set()
        queue = [node]
        while queue:
            current = queue.pop()
            if current in visited:
                continue
            visited.add(current)
            cluster.add(current)
            queue.extend(adj.get(current, set()) - visited)
        if len(cluster) >= 2:
            clusters.append(cluster)

    for cluster in clusters:
        # Check if all entries in cluster have high prediction errors
        cluster_entries = {
            eid: entries[eid] for eid in cluster if eid in entries
        }
        if not cluster_entries:
            continue
        all_stale = all(
            int(e.get("prediction_error_count", 0)) > 3
            for e in cluster_entries.values()
        )
        if not all_stale:
            continue

        # Find representative domain
        domains: list[str] = []
        for e in cluster_entries.values():
            domains.extend(_str_list(e.get("domains")))
        domain_label = domains[0] if domains else "unknown"

        insights.append(KnowledgeInsight(
            severity="attention",
            category="staleness",
            title=f"Stale knowledge cluster in '{domain_label}'",
            detail=(
                f"A co-occurrence cluster of {len(cluster_entries)} entries "
                f"all have high prediction errors. The cluster is being "
                f"retrieved but is no longer semantically relevant."
            ),
            affected_entries=list(cluster_entries.keys())[:5],
            suggested_action=(
                "Review the cluster for outdated entries. "
                "Consider archiving or updating."
            ),
            suggested_colony=SuggestedColony(
                task=(
                    f"Re-validate the '{domain_label}' knowledge cluster. "
                    f"Recent retrievals show low semantic relevance."
                ),
                caste="researcher",
                strategy="sequential",
                max_rounds=5,
                rationale=(
                    f"Co-occurrence cluster of {len(cluster_entries)} entries "
                    f"all have high prediction errors."
                ),
                estimated_cost=5 * 0.08,
            ),
            forage_signal={
                "trigger": "proactive:stale_cluster",
                "gap_description": (
                    f"Stale cluster of {len(cluster_entries)} entries in "
                    f"'{domain_label}' — all have high prediction errors."
                ),
                "topic": domain_label,
                "domains": [domain_label] if domain_label != "unknown" else [],
                "context": "stale co-occurrence cluster needs fresh knowledge",
                "max_results": 5,
            },
        ))
    return insights


# -- Rule 6: Merge opportunity -----------------------------------------------


def _rule_merge_opportunity(
    entries: dict[str, dict[str, Any]],
) -> list[KnowledgeInsight]:
    """2+ entries with similar titles/domains (heuristic word overlap)."""
    insights: list[KnowledgeInsight] = []
    items = list(entries.items())
    seen_pairs: set[tuple[str, str]] = set()

    for i, (eid_a, ea) in enumerate(items):
        title_a = str(ea.get("title", ""))
        domains_a = _str_list(ea.get("domains"))
        if not title_a or not domains_a:
            continue
        for eid_b, eb in items[i + 1:]:
            title_b = str(eb.get("title", ""))
            domains_b = _str_list(eb.get("domains"))
            if not title_b or not domains_b:
                continue
            # Same domain + high title overlap
            domain_overlap = _jaccard(domains_a, domains_b)
            if domain_overlap < 0.5:
                continue
            title_sim = _word_overlap(title_a, title_b)
            if title_sim < 0.5:
                continue

            pair_key = (min(eid_a, eid_b), max(eid_a, eid_b))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            insights.append(KnowledgeInsight(
                severity="info",
                category="merge",
                title=f"Possible merge: {title_a[:30]} / {title_b[:30]}",
                detail=(
                    f"Two entries share {domain_overlap:.0%} domain overlap "
                    f"and {title_sim:.0%} title similarity. "
                    f"They may be candidates for manual merge."
                ),
                affected_entries=[eid_a, eid_b],
                suggested_action="Review entries and merge if redundant.",
            ))
            if len(insights) > 10:
                return insights  # Cap merge suggestions
    return insights


# -- Rule 7: Federation inbound -----------------------------------------------


def _rule_federation_inbound(
    entries: dict[str, dict[str, Any]],
    projections: ProjectionStore,
) -> list[KnowledgeInsight]:
    """New entries from peer in domain with no local coverage."""
    insights: list[KnowledgeInsight] = []
    # Identify entries with foreign source
    foreign: dict[str, list[str]] = {}  # domain -> [entry_ids]
    local_domains: set[str] = set()

    for eid, e in entries.items():
        source_peer = e.get("source_peer")
        domains = _str_list(e.get("domains"))
        if source_peer:
            for d in domains:
                foreign.setdefault(d, []).append(eid)
        else:
            for d in domains:
                local_domains.add(d)

    for domain, eids in foreign.items():
        if domain in local_domains:
            continue
        peer_ids = {
            entries[eid].get("source_peer", "unknown") for eid in eids
            if eid in entries
        }
        peer_label = ", ".join(sorted(peer_ids))
        insights.append(KnowledgeInsight(
            severity="info",
            category="inbound",
            title=f"New federated knowledge in '{domain}'",
            detail=(
                f"{len(eids)} entries received from {peer_label} in a domain "
                f"with no local coverage. Review for relevance."
            ),
            affected_entries=eids[:5],
            suggested_action=(
                "Review incoming entries. Consider spawning a colony "
                "to validate this knowledge."
            ),
        ))
    return insights


# -- Rule 8: Strategy efficiency (Wave 36 A3) --------------------------------


def _rule_strategy_efficiency(
    outcomes: dict[str, Any],
) -> list[KnowledgeInsight]:
    """Flag strategies with consistently lower quality than alternatives."""
    insights: list[KnowledgeInsight] = []
    strategy_stats: dict[str, list[float]] = {}
    for o in outcomes.values():
        qs = float(getattr(o, "quality_score", 0))
        if qs <= 0:
            continue
        strat = str(getattr(o, "strategy", "unknown"))
        strategy_stats.setdefault(strat, []).append(qs)

    if len(strategy_stats) < 2:
        return insights

    avg_by_strat = {
        s: sum(scores) / len(scores)
        for s, scores in strategy_stats.items()
        if len(scores) >= 3
    }
    if not avg_by_strat:
        return insights

    best_strat = max(avg_by_strat, key=lambda s: avg_by_strat[s])
    best_avg = avg_by_strat[best_strat]

    for strat, avg in avg_by_strat.items():
        if strat == best_strat:
            continue
        gap = best_avg - avg
        if gap > 0.15:
            n = len(strategy_stats[strat])
            insights.append(KnowledgeInsight(
                severity="info",
                category="performance",
                title=f"Strategy '{strat}' underperforming",
                detail=(
                    f"'{strat}' averages {avg:.0%} quality across {n} colonies "
                    f"vs '{best_strat}' at {best_avg:.0%}. "
                    f"Consider preferring '{best_strat}' for similar tasks."
                ),
                affected_entries=[],
                suggested_action=f"Review whether '{strat}' is the right default.",
            ))
    return insights


# -- Rule 9: Diminishing rounds (Wave 36 A3) ---------------------------------


def _rule_diminishing_rounds(
    outcomes: dict[str, Any],
) -> list[KnowledgeInsight]:
    """Colonies that use max rounds without quality improvement."""
    insights: list[KnowledgeInsight] = []
    low_roi_count = 0
    affected: list[str] = []
    for o in outcomes.values():
        total_rounds = int(getattr(o, "total_rounds", 0))
        qs = float(getattr(o, "quality_score", 0))
        # Flag colonies that ran many rounds but still low quality
        if total_rounds >= 10 and qs < 0.4 and qs > 0:
            low_roi_count += 1
            affected.append(str(getattr(o, "colony_id", "")))

    if low_roi_count >= 2:
        insights.append(KnowledgeInsight(
            severity="attention",
            category="performance",
            title="Diminishing returns on long-running colonies",
            detail=(
                f"{low_roi_count} colonies ran 10+ rounds but achieved "
                f"<40% quality. Extra rounds may not be improving outcomes."
            ),
            affected_entries=affected[:5],
            suggested_action="Consider lower max_rounds or different strategies.",
        ))
    return insights


# -- Rule 10: Cost outlier (Wave 36 A3) --------------------------------------


def _rule_cost_outlier(
    outcomes: dict[str, Any],
) -> list[KnowledgeInsight]:
    """Flag colonies whose cost is >2x the workspace median."""
    insights: list[KnowledgeInsight] = []
    costs = [
        (str(getattr(o, "colony_id", "")), float(getattr(o, "total_cost", 0)))
        for o in outcomes.values()
        if float(getattr(o, "total_cost", 0)) > 0
    ]
    if len(costs) < 5:
        return insights

    sorted_costs = sorted(c for _, c in costs)
    median = sorted_costs[len(sorted_costs) // 2]
    if median <= 0:
        return insights

    outliers = [(cid, c) for cid, c in costs if c > median * 2.5]
    if outliers:
        worst_id, worst_cost = max(outliers, key=lambda x: x[1])
        insights.append(KnowledgeInsight(
            severity="info",
            category="performance",
            title=f"Cost outlier: ${worst_cost:.2f} (median ${median:.2f})",
            detail=(
                f"{len(outliers)} colonies cost >2.5x the median. "
                f"Highest: ${worst_cost:.2f} (colony {worst_id[:12]}). "
                f"Review budget limits and task scoping."
            ),
            affected_entries=[cid for cid, _ in outliers[:5]],
            suggested_action="Tighten budget limits or break large tasks into smaller colonies.",
        ))
    return insights


# -- Rule 11: Knowledge ROI (Wave 36 A3) -------------------------------------


def _rule_knowledge_roi(
    outcomes: dict[str, Any],
) -> list[KnowledgeInsight]:
    """Flag when colonies cost significant amounts but extract no knowledge."""
    insights: list[KnowledgeInsight] = []
    no_extraction_cost = 0.0
    no_extraction_count = 0
    total_cost = 0.0

    for o in outcomes.values():
        cost = float(getattr(o, "total_cost", 0))
        extracted = int(getattr(o, "entries_extracted", 0))
        succeeded = bool(getattr(o, "succeeded", False))
        total_cost += cost
        if succeeded and cost > 0 and extracted == 0:
            no_extraction_cost += cost
            no_extraction_count += 1

    if no_extraction_count >= 3 and total_cost > 0:
        pct = no_extraction_cost / total_cost
        if pct > 0.3:
            insights.append(KnowledgeInsight(
                severity="attention",
                category="performance",
                title="Low knowledge extraction rate",
                detail=(
                    f"{no_extraction_count} successful colonies ({pct:.0%} of spend) "
                    f"extracted zero knowledge entries. ${no_extraction_cost:.2f} spent "
                    f"without growing the knowledge base."
                ),
                affected_entries=[],
                suggested_action=(
                    "Ensure extraction is enabled. Review caste recipes "
                    "and task prompts for knowledge-producing castes."
                ),
            ))
    return insights


# -- Rule 12: Adaptive evaporation recommendation (Wave 37 4A) ---------------


@dataclass
class EvaporationRecommendation:
    """Domain-specific decay adjustment recommendation (Wave 37 4A).

    Recommendation-only — no automatic tuning. The Queen or operator
    decides whether to apply the suggested adjustment.
    """

    domain: str
    current_decay_class: str  # dominant class in this domain
    recommended_decay_class: str
    rationale: str
    evidence: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        domain: str,
        current_decay_class: str,
        recommended_decay_class: str,
        rationale: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.domain = domain
        self.current_decay_class = current_decay_class
        self.recommended_decay_class = recommended_decay_class
        self.rationale = rationale
        self.evidence = evidence or {}


def _rule_evaporation_recommendation(
    entries: dict[str, dict[str, Any]],
    projections: ProjectionStore,
) -> list[KnowledgeInsight]:
    """Recommend domain-specific decay adjustments based on evidence.

    Signals considered:
    - prediction_error_count: high errors → faster decay needed
    - reuse half-life: entries that stop being accessed → faster decay
    - operator feedback demotions (from operator_behavior projection)
    - refresh-colony frequency: domains with frequent refreshes → faster decay

    Recommendation-only. No automatic tuning.
    """
    insights: list[KnowledgeInsight] = []

    # Group entries by domain
    domain_entries: dict[str, list[dict[str, Any]]] = {}
    for e in entries.values():
        domains = e.get("domains", [])
        if not isinstance(domains, list):
            continue
        for d in domains:
            domain_entries.setdefault(str(d), []).append(e)

    operator_behavior = getattr(projections, "operator_behavior", None)

    for domain, d_entries in domain_entries.items():
        if len(d_entries) < 3:
            continue  # Need enough data to make a recommendation

        # Signal 1: prediction error rate for this domain
        total_errors = sum(
            int(e.get("prediction_error_count", 0)) for e in d_entries
        )
        avg_errors = total_errors / len(d_entries)

        # Signal 2: dominant decay class
        decay_counts: dict[str, int] = {}
        for e in d_entries:
            dc = str(e.get("decay_class", "ephemeral"))
            decay_counts[dc] = decay_counts.get(dc, 0) + 1
        current_class = max(decay_counts, key=lambda k: decay_counts[k])

        # Signal 3: operator demotion rate (from 4B projection)
        demotion_rate = 0.0
        if operator_behavior is not None:
            demotion_rate = operator_behavior.domain_demotion_rate(domain)

        # Signal 4: average confidence (low confidence = entries not holding up)
        total_conf = 0.0
        for e in d_entries:
            alpha = float(e.get("conf_alpha", 5))
            beta = float(e.get("conf_beta", 5))
            if alpha + beta > 0:
                total_conf += alpha / (alpha + beta)
        avg_conf = total_conf / len(d_entries)

        # Decision logic: recommend faster or slower decay
        recommended = current_class  # default: no change

        # Recommend faster decay (ephemeral) if knowledge is unreliable
        if current_class in ("stable", "permanent") and (
            avg_errors >= 3.0
            or demotion_rate >= 0.4
            or (avg_conf < 0.4 and len(d_entries) >= 5)
        ):
            recommended = (
                "ephemeral" if current_class == "stable" else "stable"
            )

        # Recommend slower decay (stable) if knowledge is reliable
        if current_class == "ephemeral" and (
            avg_errors < 1.0
            and avg_conf >= 0.7
            and demotion_rate < 0.1
            and len(d_entries) >= 5
        ):
            recommended = "stable"

        if recommended != current_class:
            # Build rationale
            reasons: list[str] = []
            if avg_errors >= 3.0:
                reasons.append(
                    f"high prediction errors ({avg_errors:.1f} avg)",
                )
            if demotion_rate >= 0.4:
                reasons.append(
                    f"high operator demotion rate ({demotion_rate:.0%})",
                )
            if avg_conf < 0.4:
                reasons.append(f"low confidence ({avg_conf:.0%} avg)")
            if avg_conf >= 0.7 and avg_errors < 1.0:
                reasons.append(
                    f"high confidence ({avg_conf:.0%}) with low errors",
                )
            rationale = "; ".join(reasons) if reasons else "mixed signals"

            insights.append(KnowledgeInsight(
                severity="info",
                category="evaporation",
                title=(
                    f"Decay adjustment for '{domain}': "
                    f"{current_class} → {recommended}"
                ),
                detail=(
                    f"Domain '{domain}' has {len(d_entries)} entries "
                    f"currently classified as '{current_class}'. "
                    f"Evidence suggests '{recommended}' would be more "
                    f"appropriate. Rationale: {rationale}."
                ),
                affected_entries=[
                    str(e.get("id", "")) for e in d_entries[:5]
                ],
                suggested_action=(
                    f"Consider changing decay class for '{domain}' entries "
                    f"from '{current_class}' to '{recommended}'."
                ),
            ))

    return insights


def generate_evaporation_recommendations(
    workspace_id: str,
    projections: ProjectionStore,
) -> list[EvaporationRecommendation]:
    """Generate domain-specific decay recommendations (Wave 37 4A).

    Returns structured recommendations separate from insights.
    The Queen or operator decides whether to apply.
    """
    entries = {
        eid: e
        for eid, e in projections.memory_entries.items()
        if e.get("workspace_id") == workspace_id
    }

    recommendations: list[EvaporationRecommendation] = []

    # Group entries by domain
    domain_entries: dict[str, list[dict[str, Any]]] = {}
    for e in entries.values():
        domains = e.get("domains", [])
        if not isinstance(domains, list):
            continue
        for d in domains:
            domain_entries.setdefault(str(d), []).append(e)

    operator_behavior = getattr(projections, "operator_behavior", None)

    for domain, d_entries in domain_entries.items():
        if len(d_entries) < 3:
            continue

        total_errors = sum(
            int(e.get("prediction_error_count", 0)) for e in d_entries
        )
        avg_errors = total_errors / len(d_entries)

        decay_counts: dict[str, int] = {}
        for e in d_entries:
            dc = str(e.get("decay_class", "ephemeral"))
            decay_counts[dc] = decay_counts.get(dc, 0) + 1
        current_class = max(decay_counts, key=lambda k: decay_counts[k])

        demotion_rate = 0.0
        if operator_behavior is not None:
            demotion_rate = operator_behavior.domain_demotion_rate(domain)

        total_conf = 0.0
        for e in d_entries:
            alpha = float(e.get("conf_alpha", 5))
            beta = float(e.get("conf_beta", 5))
            if alpha + beta > 0:
                total_conf += alpha / (alpha + beta)
        avg_conf = total_conf / len(d_entries)

        evidence = {
            "entry_count": len(d_entries),
            "avg_prediction_errors": round(avg_errors, 2),
            "avg_confidence": round(avg_conf, 3),
            "operator_demotion_rate": round(demotion_rate, 3),
        }

        recommended = current_class

        if current_class in ("stable", "permanent") and (
            avg_errors >= 3.0
            or demotion_rate >= 0.4
            or (avg_conf < 0.4 and len(d_entries) >= 5)
        ):
            recommended = (
                "ephemeral" if current_class == "stable" else "stable"
            )

        if current_class == "ephemeral" and (
            avg_errors < 1.0
            and avg_conf >= 0.7
            and demotion_rate < 0.1
            and len(d_entries) >= 5
        ):
            recommended = "stable"

        if recommended != current_class:
            reasons: list[str] = []
            if avg_errors >= 3.0:
                reasons.append(f"high prediction errors ({avg_errors:.1f} avg)")
            if demotion_rate >= 0.4:
                reasons.append(
                    f"operator demotions ({demotion_rate:.0%})",
                )
            if avg_conf < 0.4:
                reasons.append(f"low confidence ({avg_conf:.0%})")
            if avg_conf >= 0.7 and avg_errors < 1.0:
                reasons.append(f"consistently reliable ({avg_conf:.0%})")

            recommendations.append(EvaporationRecommendation(
                domain=domain,
                current_decay_class=current_class,
                recommended_decay_class=recommended,
                rationale="; ".join(reasons) if reasons else "mixed signals",
                evidence=evidence,
            ))

    return recommendations


# ---------------------------------------------------------------------------
# Wave 37 1C: Branching-factor stagnation diagnostics
# ---------------------------------------------------------------------------


def _effective_count(weights: list[float]) -> float:
    """Compute the effective number of choices from a weight distribution.

    Uses the exponential of Shannon entropy: exp(-sum p_i log p_i).
    A uniform distribution over N items yields N; a delta yields 1.
    Returns 0 for empty input.
    """
    if not weights:
        return 0.0
    total = sum(weights)
    if total <= 0:
        return 0.0
    probs = [w / total for w in weights if w > 0]
    if not probs:
        return 0.0
    entropy = -sum(p * math.log(p) for p in probs)
    return math.exp(entropy)


def compute_topology_branching(
    projections: ProjectionStore,
    workspace_id: str,
) -> float:
    """Topology branching factor: effective count over pheromone edge weights.

    Examines active colonies' pheromone weights.  A narrow, concentrated
    topology (one dominant edge pattern) yields a low branching factor.
    """
    all_weights: list[float] = []
    colonies: dict[str, Any] = getattr(projections, "colonies", {})
    for proj in colonies.values():
        ws = getattr(proj, "workspace_id", "")
        if ws != workspace_id:
            continue
        phero: dict[tuple[str, str], float] = getattr(
            proj, "pheromone_weights", {},
        )
        if phero:
            all_weights.extend(
                abs(w) for w in phero.values() if abs(w) > 0.01
            )
    return _effective_count(all_weights)


def compute_knowledge_branching(
    entries: dict[str, dict[str, Any]],
) -> float:
    """Knowledge branching factor: effective count over posterior mass.

    Low branching means a few entries dominate the confidence landscape;
    the system is narrowing onto a small set of knowledge.
    """
    masses: list[float] = []
    for e in entries.values():
        alpha = float(e.get("conf_alpha", 5))
        beta = float(e.get("conf_beta", 5))
        if alpha + beta > 0:
            masses.append(alpha / (alpha + beta))
    return _effective_count(masses)


def compute_config_branching(
    outcomes: dict[str, Any],
) -> float:
    """Configuration branching factor: diversity of strategy/caste selections.

    Low branching means recent colonies all use the same configuration,
    indicating potential premature convergence on a single approach.
    """
    configs: dict[str, float] = {}
    for o in outcomes.values():
        strat = str(getattr(o, "strategy", "unknown"))
        castes = getattr(o, "caste_composition", [])
        caste_str = (
            ",".join(sorted(str(c) for c in castes)) if castes else "default"
        )
        key = f"{strat}:{caste_str}"
        configs[key] = configs.get(key, 0) + 1.0
    return _effective_count(list(configs.values()))


def _rule_branching_stagnation(
    entries: dict[str, dict[str, Any]],
    outcomes: dict[str, Any],
    projections: ProjectionStore,
    workspace_id: str,
) -> list[KnowledgeInsight]:
    """Detect narrowing search breadth across three branching dimensions.

    Generates an insight only when:
    - branching is low (below threshold)
    - AND failures or warnings are rising
    - AND the same entries or configurations dominate recent work
    """
    insights: list[KnowledgeInsight] = []

    if not entries and not outcomes:
        return insights

    # Compute branching factors
    topo_bf = compute_topology_branching(projections, workspace_id)
    know_bf = compute_knowledge_branching(entries)
    config_bf = compute_config_branching(outcomes) if outcomes else 0.0

    # Count recent failures
    failure_count = 0
    total_count = 0
    for o in outcomes.values():
        total_count += 1
        if not getattr(o, "succeeded", True):
            failure_count += 1
    failure_rate = failure_count / total_count if total_count > 0 else 0.0

    # Thresholds — stagnation requires BOTH low branching and rising failures
    low_topo = topo_bf < 2.0 and topo_bf > 0
    low_know = know_bf < 3.0 and len(entries) >= 5
    low_config = config_bf < 1.5 and total_count >= 5

    stagnation_signals = sum([low_topo, low_know, low_config])
    if stagnation_signals < 2:
        return insights
    if failure_rate < 0.3:
        return insights

    # Build detail
    detail_parts: list[str] = []
    if low_topo:
        detail_parts.append(
            f"topology branching={topo_bf:.1f} (concentrated edge patterns)",
        )
    if low_know:
        detail_parts.append(
            f"knowledge branching={know_bf:.1f} across {len(entries)} entries",
        )
    if low_config:
        detail_parts.append(
            f"config branching={config_bf:.1f} across {total_count} colonies",
        )
    detail_parts.append(
        f"failure rate={failure_rate:.0%} ({failure_count}/{total_count})",
    )

    insights.append(KnowledgeInsight(
        severity="attention",
        category="stagnation",
        title="Search breadth narrowing — potential premature convergence",
        detail=(
            "Multiple branching metrics are low while failure rate is elevated. "
            + "; ".join(detail_parts)
            + ". The system may be stuck in a local attractor."
        ),
        affected_entries=[],
        suggested_action=(
            "Consider diversifying colony strategies, castes, or task "
            "decomposition. Review whether dominant knowledge entries "
            "are blocking exploration."
        ),
    ))

    return insights


# -- Rule 13: Earned autonomy recommendations (Wave 39 4B) -----------------


@dataclass
class AutonomyRecommendation:
    """Earned autonomy recommendation for an insight category (Wave 39 4B).

    Recommendation-only — operator still decides. Earning trust is slower
    than losing it (asymmetric thresholds).
    """

    category: str  # insight category (contradiction, coverage, staleness, etc.)
    direction: str  # "promote" | "demote"
    current_level: str  # suggest | auto_notify | autonomous
    recommended_level: str
    rationale: str
    evidence: dict[str, Any]

    def __init__(
        self,
        category: str,
        direction: str,
        current_level: str,
        recommended_level: str,
        rationale: str,
        evidence: dict[str, Any] | None = None,
    ) -> None:
        self.category = category
        self.direction = direction
        self.current_level = current_level
        self.recommended_level = recommended_level
        self.rationale = rationale
        self.evidence = evidence or {}


# Autonomy level ordering for promotion/demotion
_AUTONOMY_LEVELS = ["suggest", "auto_notify", "autonomous"]


def _next_autonomy_level(current: str, direction: str) -> str | None:
    """Get the next autonomy level in the given direction."""
    try:
        idx = _AUTONOMY_LEVELS.index(current)
    except ValueError:
        return None
    if direction == "promote":
        return _AUTONOMY_LEVELS[idx + 1] if idx < len(_AUTONOMY_LEVELS) - 1 else None
    return _AUTONOMY_LEVELS[idx - 1] if idx > 0 else None


def _rule_earned_autonomy(
    projections: ProjectionStore,
    workspace_id: str,
) -> list[KnowledgeInsight]:
    """Recommend autonomy level changes based on operator behavior patterns.

    Asymmetric thresholds: promotion requires more evidence than demotion.
    - Promotion: ≥5 follow-throughs in category AND >70% follow-through rate
    - Demotion: ≥3 kills/negative-feedback AND >50% negative rate

    Cooldown: dismissed categories get a 7-day cooldown before re-recommendation.
    """
    insights: list[KnowledgeInsight] = []
    behavior = getattr(projections, "operator_behavior", None)
    if behavior is None:
        return insights

    # Get current maintenance policy from workspace config
    ws_store: dict[str, Any] = getattr(projections, "workspaces", {})
    ws = ws_store.get(workspace_id)  # pyright: ignore[reportUnknownMemberType]
    if ws is None:
        return insights
    ws_config: dict[str, Any] = getattr(ws, "config", {})
    raw_policy: Any = ws_config.get("maintenance_policy")
    current_level: str = "suggest"
    auto_actions: list[str] = []
    if raw_policy is not None:
        if isinstance(raw_policy, str):
            import json
            try:
                parsed: dict[str, Any] = json.loads(raw_policy)
            except (json.JSONDecodeError, TypeError):
                parsed = {}
            current_level = str(parsed.get("autonomy_level", "suggest"))
            auto_actions = list(parsed.get("auto_actions", []))
        elif isinstance(raw_policy, dict):
            policy_dict = cast("dict[str, Any]", raw_policy)
            current_level = str(policy_dict.get("autonomy_level", "suggest"))
            auto_actions = list(policy_dict.get("auto_actions", []))

    # Check dismissed recommendations cooldown
    dismissed: dict[str, str] = getattr(
        projections, "autonomy_recommendation_dismissals", {},
    )

    now = datetime.now(tz=UTC)
    cooldown_days = 7

    # Analyze follow-through patterns by category
    category_follow_throughs = behavior.suggestion_categories_acted_on

    # Analyze negative signals: kills and negative feedback
    total_kills = len(behavior.kill_records)

    # Categories that have significant positive follow-through → promote
    for category, acted_count in category_follow_throughs.items():
        # Check cooldown
        last_dismissed = _parse_ts(dismissed.get(category, ""))
        if last_dismissed and (now - last_dismissed).days < cooldown_days:
            continue

        # Promotion threshold: ≥5 follow-throughs (asymmetric: harder to earn)
        if acted_count < 5:
            continue

        # Category already auto-dispatched?
        if category in auto_actions:
            continue

        next_level = _next_autonomy_level(current_level, "promote")
        if next_level is None:
            continue

        insights.append(KnowledgeInsight(
            severity="info",
            category="earned_autonomy",
            title=f"Earned autonomy: promote '{category}'",
            detail=(
                f"Operator has acted on {acted_count} '{category}' suggestions. "
                f"Consistent follow-through indicates trust in this category. "
                f"Consider promoting from '{current_level}' to '{next_level}'."
            ),
            affected_entries=[],
            suggested_action=(
                f"Add '{category}' to auto_actions list, or promote "
                f"autonomy level to '{next_level}'."
            ),
        ))

    # Demotion signal: high kill rate or negative feedback rate
    # (asymmetric: easier to lose trust — only ≥3 signals needed)
    if total_kills >= 3:
        # Get dominant strategy being killed
        dominant_strat = max(
            behavior.kills_by_strategy,
            key=lambda s: behavior.kills_by_strategy[s],
            default="",
        )
        kill_count = behavior.kills_by_strategy.get(dominant_strat, 0)

        if kill_count >= 3 and current_level != "suggest":
            # Check cooldown for demotion
            demote_key = f"__demote_{dominant_strat}"
            last_dismissed = _parse_ts(dismissed.get(demote_key, ""))
            if not (last_dismissed and (now - last_dismissed).days < cooldown_days):
                prev_level = _next_autonomy_level(current_level, "demote")
                if prev_level:
                    insights.append(KnowledgeInsight(
                        severity="attention",
                        category="earned_autonomy",
                        title="Autonomy demotion signal",
                        detail=(
                            f"Operator has killed {kill_count} colonies using "
                            f"'{dominant_strat}' strategy. This pattern suggests "
                            f"the system's autonomous decisions in this area are "
                            f"not aligned with operator expectations. "
                            f"Consider demoting from '{current_level}' to '{prev_level}'."
                        ),
                        affected_entries=[],
                        suggested_action=(
                            f"Demote autonomy level from '{current_level}' to "
                            f"'{prev_level}', or narrow auto_actions scope."
                        ),
                    ))

    # Check negative feedback dominance across domains
    for domain, bucket in behavior.feedback_by_domain.items():
        neg = bucket.get("negative", 0)
        pos = bucket.get("positive", 0)
        total = neg + pos
        if total < 3:
            continue
        neg_rate = neg / total
        if neg_rate > 0.5 and current_level != "suggest":
            demote_key = f"__demote_feedback_{domain}"
            last_dismissed = _parse_ts(dismissed.get(demote_key, ""))
            if last_dismissed and (now - last_dismissed).days < cooldown_days:
                continue
            prev_level = _next_autonomy_level(current_level, "demote")
            if prev_level:
                insights.append(KnowledgeInsight(
                    severity="attention",
                    category="earned_autonomy",
                    title=f"Negative feedback pattern in '{domain}'",
                    detail=(
                        f"Operator gave {neg} negative vs {pos} positive feedback "
                        f"on '{domain}' knowledge ({neg_rate:.0%} negative rate). "
                        f"This suggests autonomous handling of this domain needs review."
                    ),
                    affected_entries=[],
                    suggested_action=(
                        f"Review autonomous handling of '{domain}'. "
                        f"Consider demoting autonomy from '{current_level}' to "
                        f"'{prev_level}'."
                    ),
                ))

    return insights


# -- Rule 14: Configuration recommendations (Wave 39 5A) -------------------


@dataclass
class ConfigRecommendation:
    """Evidence-backed configuration recommendation (Wave 39 5A).

    Surfaces 'what tends to work here' based on outcome history.
    """

    dimension: str  # strategy | caste | max_rounds | model_tier
    recommended_value: str
    evidence_summary: str
    sample_size: int
    avg_quality: float
    confidence: str  # "high" | "moderate" | "low"

    def __init__(
        self,
        dimension: str,
        recommended_value: str,
        evidence_summary: str,
        sample_size: int = 0,
        avg_quality: float = 0.0,
        confidence: str = "low",
    ) -> None:
        self.dimension = dimension
        self.recommended_value = recommended_value
        self.evidence_summary = evidence_summary
        self.sample_size = sample_size
        self.avg_quality = avg_quality
        self.confidence = confidence


def generate_config_recommendations(
    workspace_id: str,
    projections: ProjectionStore,
) -> list[ConfigRecommendation]:
    """Generate configuration recommendations from outcome history (Wave 39 5A).

    Analyzes colony outcomes to recommend strategy, caste composition,
    round limits, and model tier. Evidence-backed, not heuristic.
    """
    all_outcomes: dict[str, Any] = getattr(projections, "colony_outcomes", {})
    ws_outcomes = [
        o for o in all_outcomes.values()
        if getattr(o, "workspace_id", None) == workspace_id
        and getattr(o, "succeeded", False)
    ]
    if len(ws_outcomes) < 3:
        return []  # Not enough data for meaningful recommendations

    recommendations: list[ConfigRecommendation] = []

    # --- Strategy recommendation ---
    strat_stats: dict[str, list[float]] = {}
    for o in ws_outcomes:
        strat = str(getattr(o, "strategy", "unknown"))
        qs = float(getattr(o, "quality_score", 0))
        if qs > 0:
            strat_stats.setdefault(strat, []).append(qs)

    if strat_stats:
        best_strat = max(
            strat_stats,
            key=lambda s: (
                sum(strat_stats[s]) / len(strat_stats[s])
                if len(strat_stats[s]) >= 2 else 0
            ),
        )
        scores = strat_stats[best_strat]
        if len(scores) >= 2:
            avg_q = sum(scores) / len(scores)
            confidence = (
                "high" if len(scores) >= 5 else
                "moderate" if len(scores) >= 3 else "low"
            )
            recommendations.append(ConfigRecommendation(
                dimension="strategy",
                recommended_value=best_strat,
                evidence_summary=(
                    f"'{best_strat}' averaged {avg_q:.0%} quality "
                    f"across {len(scores)} colonies"
                ),
                sample_size=len(scores),
                avg_quality=avg_q,
                confidence=confidence,
            ))

    # --- Caste composition recommendation ---
    caste_stats: dict[str, list[float]] = {}
    for o in ws_outcomes:
        castes = getattr(o, "caste_composition", [])
        caste_key = ",".join(sorted(str(c) for c in castes)) if castes else "default"
        qs = float(getattr(o, "quality_score", 0))
        if qs > 0:
            caste_stats.setdefault(caste_key, []).append(qs)

    if caste_stats:
        best_caste = max(
            caste_stats,
            key=lambda s: (
                sum(caste_stats[s]) / len(caste_stats[s])
                if len(caste_stats[s]) >= 2 else 0
            ),
        )
        scores = caste_stats[best_caste]
        if len(scores) >= 2:
            avg_q = sum(scores) / len(scores)
            confidence = (
                "high" if len(scores) >= 5 else
                "moderate" if len(scores) >= 3 else "low"
            )
            recommendations.append(ConfigRecommendation(
                dimension="caste",
                recommended_value=best_caste,
                evidence_summary=(
                    f"Caste composition '{best_caste}' averaged {avg_q:.0%} "
                    f"quality across {len(scores)} colonies"
                ),
                sample_size=len(scores),
                avg_quality=avg_q,
                confidence=confidence,
            ))

    # --- Round limit recommendation ---
    round_quality: list[tuple[int, float]] = []
    for o in ws_outcomes:
        rounds = int(getattr(o, "total_rounds", 0))
        qs = float(getattr(o, "quality_score", 0))
        if rounds > 0 and qs > 0:
            round_quality.append((rounds, qs))

    if len(round_quality) >= 3:
        # Find the sweet spot: highest quality-per-round ratio
        # Group into buckets: 1-5, 6-10, 11-15, 16+
        buckets: dict[str, list[float]] = {}
        for rounds, qs in round_quality:
            if rounds <= 5:
                bucket = "1-5"
            elif rounds <= 10:
                bucket = "6-10"
            elif rounds <= 15:
                bucket = "11-15"
            else:
                bucket = "16+"
            buckets.setdefault(bucket, []).append(qs)

        best_bucket = max(
            buckets,
            key=lambda b: sum(buckets[b]) / len(buckets[b]) if buckets[b] else 0,
        )
        scores = buckets[best_bucket]
        avg_q = sum(scores) / len(scores)
        confidence = (
            "high" if len(scores) >= 5 else
            "moderate" if len(scores) >= 3 else "low"
        )
        recommendations.append(ConfigRecommendation(
            dimension="max_rounds",
            recommended_value=best_bucket,
            evidence_summary=(
                f"Colonies with {best_bucket} rounds averaged {avg_q:.0%} "
                f"quality ({len(scores)} colonies)"
            ),
            sample_size=len(scores),
            avg_quality=avg_q,
            confidence=confidence,
        ))

    # --- Model tier recommendation (from escalation data) ---
    tier_stats: dict[str, list[float]] = {}
    for o in ws_outcomes:
        qs = float(getattr(o, "quality_score", 0))
        if qs <= 0:
            continue
        # Use escalated_tier if escalated, otherwise starting_tier
        tier = str(getattr(o, "escalated_tier", "") or getattr(o, "starting_tier", "") or "default")
        tier_stats.setdefault(tier, []).append(qs)

    if tier_stats:
        best_tier = max(
            tier_stats,
            key=lambda t: (
                sum(tier_stats[t]) / len(tier_stats[t])
                if len(tier_stats[t]) >= 2 else 0
            ),
        )
        scores = tier_stats[best_tier]
        if len(scores) >= 2 and best_tier != "default":
            avg_q = sum(scores) / len(scores)
            confidence = (
                "high" if len(scores) >= 5 else
                "moderate" if len(scores) >= 3 else "low"
            )
            recommendations.append(ConfigRecommendation(
                dimension="model_tier",
                recommended_value=best_tier,
                evidence_summary=(
                    f"Tier '{best_tier}' averaged {avg_q:.0%} quality "
                    f"across {len(scores)} colonies"
                ),
                sample_size=len(scores),
                avg_quality=avg_q,
                confidence=confidence,
            ))

    return recommendations


# ---------------------------------------------------------------------------
# Wave 41 B4: Cost efficiency reporting
# ---------------------------------------------------------------------------


@dataclass
class CostEfficiencyReport:
    """Cost-per-quality metrics for a workspace (Wave 41 B4).

    Answers three questions:
      1. What did the task cost?
      2. What did the success buy us?
      3. When should the colony stop earlier vs spend more?
    """

    workspace_id: str
    total_cost: float
    total_colonies: int
    successful_colonies: int
    avg_cost_per_colony: float
    avg_cost_per_quality_point: float  # cost / quality, lower is better
    avg_rounds_to_success: float
    quality_by_cost_quartile: list[dict[str, Any]]
    early_stop_candidates: list[dict[str, Any]]  # colonies where rounds > quality plateau


def compute_cost_efficiency(
    workspace_id: str,
    outcomes: dict[str, Any],
) -> CostEfficiencyReport:
    """Compute cost efficiency metrics from colony outcomes.

    Deterministic — no LLM calls. Reads only from existing outcome data.
    """
    ws_outcomes = [
        o for o in outcomes.values()
        if getattr(o, "workspace_id", None) == workspace_id
    ]

    if not ws_outcomes:
        return CostEfficiencyReport(
            workspace_id=workspace_id,
            total_cost=0.0,
            total_colonies=0,
            successful_colonies=0,
            avg_cost_per_colony=0.0,
            avg_cost_per_quality_point=0.0,
            avg_rounds_to_success=0.0,
            quality_by_cost_quartile=[],
            early_stop_candidates=[],
        )

    total_cost = sum(float(getattr(o, "total_cost", 0)) for o in ws_outcomes)
    successful = [o for o in ws_outcomes if getattr(o, "succeeded", False)]
    n = len(ws_outcomes)

    avg_cost = total_cost / n if n > 0 else 0.0

    # Cost per quality point (for successful colonies with quality > 0)
    quality_costs: list[float] = []
    for o in successful:
        q = float(getattr(o, "quality_score", 0))
        c = float(getattr(o, "total_cost", 0))
        if q > 0 and c > 0:
            quality_costs.append(c / q)
    avg_cpq = sum(quality_costs) / len(quality_costs) if quality_costs else 0.0

    # Average rounds to success
    success_rounds = [
        int(getattr(o, "total_rounds", 0)) for o in successful
    ]
    avg_rts = sum(success_rounds) / len(success_rounds) if success_rounds else 0.0

    # Quality by cost quartile
    sorted_by_cost = sorted(ws_outcomes, key=lambda o: float(getattr(o, "total_cost", 0)))
    quartile_size = max(1, len(sorted_by_cost) // 4)
    quartile_labels = ["lowest_cost", "low_cost", "high_cost", "highest_cost"]
    quality_by_quartile: list[dict[str, Any]] = []
    for i, label in enumerate(quartile_labels):
        start = i * quartile_size
        end = start + quartile_size if i < 3 else len(sorted_by_cost)
        chunk = sorted_by_cost[start:end]
        if chunk:
            avg_q = sum(float(getattr(o, "quality_score", 0)) for o in chunk) / len(chunk)
            avg_c = sum(float(getattr(o, "total_cost", 0)) for o in chunk) / len(chunk)
            quality_by_quartile.append({
                "quartile": label,
                "avg_quality": round(avg_q, 4),
                "avg_cost": round(avg_c, 4),
                "count": len(chunk),
            })

    # Early stop candidates: colonies that ran many rounds with low quality
    # (quality < 0.4 and rounds >= 8 suggests diminishing returns)
    early_stop: list[dict[str, Any]] = []
    for o in ws_outcomes:
        rounds = int(getattr(o, "total_rounds", 0))
        quality = float(getattr(o, "quality_score", 0))
        cost = float(getattr(o, "total_cost", 0))
        if rounds >= 8 and quality < 0.4 and cost > 0:
            early_stop.append({
                "colony_id": str(getattr(o, "colony_id", "")),
                "rounds": rounds,
                "quality": round(quality, 4),
                "cost": round(cost, 4),
                "cost_per_round": round(cost / rounds, 4) if rounds > 0 else 0.0,
            })

    return CostEfficiencyReport(
        workspace_id=workspace_id,
        total_cost=round(total_cost, 4),
        total_colonies=n,
        successful_colonies=len(successful),
        avg_cost_per_colony=round(avg_cost, 4),
        avg_cost_per_quality_point=round(avg_cpq, 4),
        avg_rounds_to_success=round(avg_rts, 1),
        quality_by_cost_quartile=quality_by_quartile,
        early_stop_candidates=early_stop[:10],
    )


# ---------------------------------------------------------------------------
# Wave 52 B4: Learned-template health rule
# ---------------------------------------------------------------------------


def _rule_learned_template_health(
    projections: ProjectionStore,
    has_outcomes: bool = False,
) -> list[KnowledgeInsight]:
    """Surface learned-template availability and performance."""
    templates = getattr(projections, "templates", {})
    learned = [t for t in templates.values() if getattr(t, "learned", False)]
    if not learned:
        # Only nudge when colonies have actually completed — otherwise the
        # workspace is fresh / test-only and the hint is false-positive noise.
        if not has_outcomes:
            return []
        return [KnowledgeInsight(
            severity="info",
            category="learning_loop",
            title="No learned templates yet",
            detail=(
                "Colonies completing with quality >= 0.7 generate reusable "
                "learned templates automatically."
            ),
            suggested_action=(
                "Complete a few successful colonies to seed learned-template reuse."
            ),
        )]

    total = len(learned)
    total_uses = sum(t.use_count for t in learned)
    total_success = sum(t.success_count for t in learned)
    total_failure = sum(t.failure_count for t in learned)
    win_rate = (
        round(total_success / (total_success + total_failure), 2)
        if (total_success + total_failure) > 0
        else 0.0
    )

    top = sorted(learned, key=lambda t: t.use_count, reverse=True)[:3]
    top_names = ", ".join(t.name for t in top)

    detail = (
        f"{total} learned templates, {total_uses} total uses, "
        f"{win_rate:.0%} success rate. "
        f"Most used: {top_names}."
    )

    severity = "info"
    if total_failure > total_success and (total_success + total_failure) >= 3:
        severity = "attention"

    return [KnowledgeInsight(
        severity=severity,
        category="learning_loop",
        title=f"{total} learned templates available ({win_rate:.0%} success)",
        detail=detail,
        suggested_action="Review learned templates and retire low-performing ones.",
    )]


# ---------------------------------------------------------------------------
# Wave 52 B5: Recent outcome digest rule
# ---------------------------------------------------------------------------


def _rule_recent_outcome_digest(
    ws_outcomes: dict[str, Any],
) -> list[KnowledgeInsight]:
    """Compact digest of recent colony outcomes for Queen context."""
    if not ws_outcomes:
        return []

    # Look at last 20 outcomes (most recent by colony_id which is a ULID)
    recent = sorted(ws_outcomes.values(), key=lambda o: o.colony_id, reverse=True)[:20]
    succeeded = sum(1 for o in recent if o.succeeded)
    failed = len(recent) - succeeded
    avg_quality = sum(o.quality_score for o in recent) / len(recent)
    avg_cost = sum(o.total_cost for o in recent) / len(recent)
    avg_rounds = sum(o.total_rounds for o in recent) / len(recent)

    # Strategy breakdown
    strategy_counts: dict[str, int] = {}
    for o in recent:
        strategy_counts[o.strategy] = strategy_counts.get(o.strategy, 0) + 1
    strategies = ", ".join(
        f"{s}={c}" for s, c in sorted(strategy_counts.items(), key=lambda x: -x[1])
    )

    detail = (
        f"Last {len(recent)} colonies: {succeeded} succeeded, {failed} failed. "
        f"Avg quality: {avg_quality:.2f}, avg cost: ${avg_cost:.3f}, "
        f"avg rounds: {avg_rounds:.1f}. Strategies: {strategies}."
    )

    severity = "info"
    if failed > succeeded and len(recent) >= 3:
        severity = "attention"

    return [KnowledgeInsight(
        severity=severity,
        category="outcome_digest",
        title=(
            f"Recent outcomes: {succeeded}/{len(recent)} succeeded"
            f" (avg quality {avg_quality:.2f})"
        ),
        detail=detail,
        suggested_action=(
            "Consider adjusting strategy or round limits for failing patterns."
            if failed > succeeded else ""
        ),
    )]


# -- Rule 15: Popular but unexamined (Wave 58.5) ----------------------------


def _rule_popular_unexamined(
    entries: dict[str, dict[str, Any]],
    projections: ProjectionStore,
) -> list[KnowledgeInsight]:
    """Entries accessed >= 5 times but confidence still below 0.65.

    These are frequently retrieved entries that haven't built meaningful
    confidence through outcome-weighted reinforcement or explicit feedback.
    Candidates for archivist refinement in the curation maintenance cycle.
    """
    insights: list[KnowledgeInsight] = []
    usage = getattr(projections, "knowledge_entry_usage", {})

    for eid, e in entries.items():
        if e.get("status") != "verified":
            continue
        entry_usage = usage.get(eid, {})
        access_count = int(entry_usage.get("count", 0))
        if access_count < 5:
            continue
        alpha = float(e.get("conf_alpha", 5.0))
        beta = float(e.get("conf_beta", 5.0))
        denom = alpha + beta
        if denom <= 0:
            continue
        confidence = alpha / denom
        if confidence >= 0.65:
            continue
        title_str = e.get("title", eid[:12])
        insights.append(KnowledgeInsight(
            severity="info",
            category="popular_unexamined",
            title=f"Frequently accessed entry needs validation: {title_str}",
            detail=(
                f"Accessed {access_count} times, confidence {confidence:.2f}. "
                f"Consider explicit quality review or archivist refinement."
            ),
            affected_entries=[eid],
            suggested_action="Review entry content for accuracy and completeness.",
        ))
        if len(insights) >= 10:
            break
    return insights


# ---------------------------------------------------------------------------
# Briefing generation
# ---------------------------------------------------------------------------


def generate_briefing(
    workspace_id: str,
    projections: ProjectionStore,
) -> ProactiveBriefing:
    """Generate a proactive briefing from current projection state.

    All rules are deterministic. No LLM calls. Should complete in <100ms.
    """
    entries = {
        eid: e
        for eid, e in projections.memory_entries.items()
        if e.get("workspace_id") == workspace_id
    }

    insights: list[KnowledgeInsight] = []
    insights.extend(_rule_confidence_decline(entries))
    insights.extend(_rule_contradiction(entries))
    insights.extend(_rule_federation_trust_drop(projections))
    insights.extend(_rule_coverage_gap(entries))
    insights.extend(_rule_stale_cluster(entries, projections.cooccurrence_weights))
    insights.extend(_rule_merge_opportunity(entries))
    insights.extend(_rule_federation_inbound(entries, projections))

    # Wave 36 A3: performance rules from colony outcomes
    all_outcomes: dict[str, Any] = getattr(projections, "colony_outcomes", {})
    ws_outcomes = {
        cid: o for cid, o in all_outcomes.items()
        if getattr(o, "workspace_id", None) == workspace_id
    }
    if ws_outcomes:
        insights.extend(_rule_strategy_efficiency(ws_outcomes))
        insights.extend(_rule_diminishing_rounds(ws_outcomes))
        insights.extend(_rule_cost_outlier(ws_outcomes))
        insights.extend(_rule_knowledge_roi(ws_outcomes))

    # Wave 37 4A: adaptive evaporation recommendations
    insights.extend(_rule_evaporation_recommendation(entries, projections))

    # Wave 37 1C: branching-factor stagnation diagnostics
    insights.extend(_rule_branching_stagnation(
        entries, ws_outcomes, projections, workspace_id,
    ))

    # Wave 39 4B: earned autonomy recommendations
    insights.extend(_rule_earned_autonomy(projections, workspace_id))

    # Wave 52 B4: learned-template visibility
    insights.extend(_rule_learned_template_health(projections, has_outcomes=bool(ws_outcomes)))

    # Wave 52 B5: recent outcome digest
    insights.extend(_rule_recent_outcome_digest(ws_outcomes))

    # Wave 58.5: popular but unexamined entries
    insights.extend(_rule_popular_unexamined(entries, projections))

    # Sort by severity (action_required > attention > info)
    insights.sort(key=lambda i: _SEVERITY_ORDER.get(i.severity, 3))

    # Compute stats
    status_counts: dict[str, int] = {}
    total_conf = 0.0
    total_errors = 0
    for e in entries.values():
        s = str(e.get("status", "candidate"))
        status_counts[s] = status_counts.get(s, 0) + 1
        alpha = float(e.get("conf_alpha", 5))
        beta = float(e.get("conf_beta", 5))
        if alpha + beta > 0:
            total_conf += alpha / (alpha + beta)
        total_errors += int(e.get("prediction_error_count", 0))

    n = len(entries) or 1
    avg_conf = total_conf / n

    # Count active co-occurrence clusters (pairs with weight > 0.5)
    active_clusters = sum(
        1 for entry in projections.cooccurrence_weights.values()
        if float(getattr(entry, "weight", 0.0)) > 0.5
    )

    # Distillation candidates (populated by maintenance loop)
    distillation_count = len(
        getattr(projections, "distillation_candidates", []),
    )

    return ProactiveBriefing(
        workspace_id=workspace_id,
        generated_at=datetime.now(tz=UTC).isoformat(),
        insights=insights,
        total_entries=len(entries),
        entries_by_status=status_counts,
        avg_confidence=round(avg_conf, 3),
        prediction_error_rate=round(total_errors / n, 2),
        active_clusters=active_clusters,
        distillation_candidates=distillation_count,
    )


__all__ = [
    "AutonomyRecommendation",
    "ConfigRecommendation",
    "CostEfficiencyReport",
    "EvaporationRecommendation",
    "KnowledgeInsight",
    "ProactiveBriefing",
    "SuggestedColony",
    "compute_config_branching",
    "compute_cost_efficiency",
    "compute_knowledge_branching",
    "compute_topology_branching",
    "generate_briefing",
    "generate_config_recommendations",
    "generate_evaporation_recommendations",
]
