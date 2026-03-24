"""Stigmergic (DyTopo) coordination strategy — algorithms.md §2.

Builds an adjacency matrix from embedded agent descriptors weighted
by pheromone trails, then derives execution groups via topological sort.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Awaitable, Callable, Sequence

from formicos.core.ports import PheromoneWeights
from formicos.core.types import AgentConfig, ColonyContext

# Type alias for async embed function (ADR-025)
AsyncEmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


class StigmergicStrategy:
    """DyTopo stigmergic routing from algorithms.md §2.

    Supports both sync ``embed_fn`` and async ``async_embed_fn`` (ADR-025).
    The async path is preferred when available.
    """

    def __init__(
        self,
        embed_fn: Callable[[list[str]], list[list[float]]] | None = None,
        async_embed_fn: AsyncEmbedFn | None = None,
        tau: float = 0.35,
        k_in: int = 5,
    ) -> None:
        self._embed_fn = embed_fn
        self._async_embed_fn = async_embed_fn
        self._tau = tau
        self._k_in = k_in
        self.active_edges: list[tuple[str, str]] = []

    async def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Unified embedding helper: async > sync (ADR-025)."""
        if self._async_embed_fn is not None:
            return await self._async_embed_fn(texts)
        if self._embed_fn is not None:
            return self._embed_fn(texts)
        msg = "StigmergicStrategy requires either embed_fn or async_embed_fn"
        raise RuntimeError(msg)

    async def resolve_topology(
        self,
        agents: Sequence[AgentConfig],
        context: ColonyContext,
        pheromone_weights: PheromoneWeights | None = None,
    ) -> list[list[str]]:
        """Build adjacency matrix, apply pheromones, threshold, toposort.

        Wave 37 1A: Knowledge priors are merged into pheromone_weights by the
        runner before calling this method, keeping the protocol signature
        unchanged.
        """
        n = len(agents)
        if n == 0:
            return []
        if n == 1:
            return [[agents[0].id]]

        # Generate simple descriptors from caste info (Phase 2 skipped)
        queries = [f"I need help with: {a.recipe.name} tasks" for a in agents]
        keys = [
            f"I can help with: {a.recipe.name} - {a.recipe.description}"
            for a in agents
        ]

        # Embed all texts
        all_texts = queries + keys
        embeddings = await self._get_embeddings(all_texts)
        query_vecs = embeddings[:n]
        key_vecs = embeddings[n:]

        # Build similarity matrix
        sim_matrix = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i != j:
                    sim_matrix[i][j] = _dot(query_vecs[i], key_vecs[j])

        # Apply pheromone weights BEFORE thresholding
        if pheromone_weights:
            for (src, tgt), weight in pheromone_weights.items():
                i = _agent_index(src, agents)
                j = _agent_index(tgt, agents)
                if i is not None and j is not None:
                    sim_matrix[i][j] *= weight

        # Hard threshold at tau
        adjacency = [
            [1 if sim_matrix[i][j] >= self._tau else 0 for j in range(n)]
            for i in range(n)
        ]
        for i in range(n):
            adjacency[i][i] = 0

        # Cap inbound edges at k_in
        for j in range(n):
            inbound = [
                (sim_matrix[i][j], i) for i in range(n) if adjacency[i][j] == 1
            ]
            if len(inbound) > self._k_in:
                inbound.sort(reverse=True)
                keep = {i for _, i in inbound[: self._k_in]}
                for i in range(n):
                    if adjacency[i][j] == 1 and i not in keep:
                        adjacency[i][j] = 0

        # Extract active edges from the adjacency matrix
        self.active_edges = [
            (agents[i].id, agents[j].id)
            for i in range(n) for j in range(n)
            if adjacency[i][j] == 1
        ]

        # Topological sort with cycle breaking
        order = _topological_sort(adjacency, n, sim_matrix)
        groups = _collapse_into_groups(adjacency, order, n)
        return [[agents[i].id for i in group] for group in groups]


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _dot(a: list[float], b: list[float]) -> float:
    """Dot product of two vectors."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def _agent_index(agent_id: str, agents: Sequence[AgentConfig]) -> int | None:
    """Find the index of an agent by id, or None."""
    for i, a in enumerate(agents):
        if a.id == agent_id:
            return i
    return None


def _topological_sort(
    adjacency: list[list[int]],
    n: int,
    sim_matrix: list[list[float]],
) -> list[int]:
    """Kahn's algorithm with cycle breaking via lowest-weight edge removal."""
    adj = [row[:] for row in adjacency]
    in_degree = [sum(adj[i][j] for i in range(n)) for j in range(n)]
    queue: deque[int] = deque()
    for i in range(n):
        if in_degree[i] == 0:
            queue.append(i)

    order: list[int] = []
    while len(order) < n:
        if not queue:
            # Cycle detected — break lowest-weight edge among remaining nodes
            remaining = [i for i in range(n) if i not in set(order)]
            min_weight = math.inf
            min_edge: tuple[int, int] = (remaining[0], remaining[0])
            for i in remaining:
                for j in remaining:
                    if adj[i][j] == 1 and sim_matrix[i][j] < min_weight:
                        min_weight = sim_matrix[i][j]
                        min_edge = (i, j)
            src, tgt = min_edge
            adj[src][tgt] = 0
            in_degree[tgt] -= 1
            if in_degree[tgt] == 0:
                queue.append(tgt)
            continue

        node = queue.popleft()
        order.append(node)
        for j in range(n):
            if adj[node][j] == 1:
                in_degree[j] -= 1
                if in_degree[j] == 0:
                    queue.append(j)

    return order


def _collapse_into_groups(
    adjacency: list[list[int]],
    order: list[int],
    n: int,
) -> list[list[int]]:
    """Group nodes by topological level — nodes whose predecessors are all
    in earlier groups can run in parallel within the same group.
    """
    level: dict[int, int] = {}
    for node in order:
        preds = [i for i in range(n) if adjacency[i][node] == 1 and i in level]
        if preds:
            level[node] = max(level[p] for p in preds) + 1
        else:
            level[node] = 0

    max_level = max(level.values()) if level else 0
    groups: list[list[int]] = [[] for _ in range(max_level + 1)]
    for node in order:
        groups[level[node]].append(node)
    return [g for g in groups if g]
