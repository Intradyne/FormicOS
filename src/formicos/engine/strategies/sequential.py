"""Sequential coordination strategy — agents execute one at a time in definition order."""

from __future__ import annotations

from collections.abc import Sequence

from formicos.core.ports import PheromoneWeights
from formicos.core.types import AgentConfig, ColonyContext


class SequentialStrategy:
    """Execute agents in definition order, one at a time.

    Each agent forms its own execution group, so no parallelism occurs.
    Routed context accumulates: later agents see outputs from earlier ones.
    """

    async def resolve_topology(
        self,
        agents: Sequence[AgentConfig],
        context: ColonyContext,
        pheromone_weights: PheromoneWeights | None = None,
    ) -> list[list[str]]:
        """Return one agent per group — strict sequential execution."""
        return [[agent.id] for agent in agents]
