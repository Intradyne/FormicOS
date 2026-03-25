"""Proactive intelligence — shim delegating to formicos.addons.proactive_intelligence.

Wave 64 Track 6b: the 17 deterministic briefing rules were extracted to the
proactive-intelligence addon package.  This shim preserves backward
compatibility for all existing callers (queen_runtime, self_maintenance,
mcp_server, routes/api, tests).
"""

# Private symbols re-exported for backward-compatible test imports.
# These will be removed once tests import from the addon directly.
from formicos.addons.proactive_intelligence.rules import (  # noqa: F401
    AutonomyRecommendation,
    ConfigRecommendation,
    CostEfficiencyReport,
    EvaporationRecommendation,
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
    _effective_count,  # type: ignore[attr-defined]  # noqa: F401
    _next_autonomy_level,  # type: ignore[attr-defined]  # noqa: F401
    _rule_branching_stagnation,  # type: ignore[attr-defined]  # noqa: F401
    _rule_confidence_decline,  # type: ignore[attr-defined]  # noqa: F401
    _rule_contradiction,  # type: ignore[attr-defined]  # noqa: F401
    _rule_earned_autonomy,  # type: ignore[attr-defined]  # noqa: F401
    _rule_learned_template_health,  # type: ignore[attr-defined]  # noqa: F401
    _rule_recent_outcome_digest,  # type: ignore[attr-defined]  # noqa: F401
    compute_config_branching,
    compute_cost_efficiency,
    compute_knowledge_branching,
    compute_topology_branching,
    generate_briefing,
    generate_config_recommendations,
    generate_evaporation_recommendations,
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
