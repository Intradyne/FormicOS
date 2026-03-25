"""Proactive intelligence addon — 17 deterministic briefing rules.

Re-exports all public symbols from the rules module.
"""

from formicos.addons.proactive_intelligence.rules import (
    AutonomyRecommendation,
    ConfigRecommendation,
    CostEfficiencyReport,
    EvaporationRecommendation,
    KnowledgeInsight,
    ProactiveBriefing,
    SuggestedColony,
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
