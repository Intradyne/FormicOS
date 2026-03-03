"""
FormicOS v0.6.0 -- DyTopo Semantic Router

Pure computation module that transforms agent intent embeddings into a
directed acyclic graph (DAG), determining execution order for a round.

Pipeline: encode descriptors -> similarity matrix -> threshold + k_in cap
          -> cycle breaking -> Kahn's topological sort -> Topology

This module is a pure function layer -- no I/O, no state, no side effects.
The only external dependency is NumPy (and optionally sentence-transformers
for the encode step).

Matrix conventions (critical -- getting these wrong inverts routing):
    S[i][j] = cosine_sim(query_i, key_j)
              "How well does agent j's offering match agent i's need?"

    A[i][j] = 1 means agent j sends output to agent i (edge j -> i)
              First index = receiver, second index = sender.

    In-degree of node i:  sum(A[i, :])   -- row i
    Out-degree of node j: sum(A[:, j])   -- column j
"""

from __future__ import annotations

import heapq
from typing import Any, Protocol, runtime_checkable

import numpy as np

from src.models import Topology, TopologyEdge


# ---------------------------------------------------------------------------
# Embedder protocol -- anything with an .encode() method works
# ---------------------------------------------------------------------------

@runtime_checkable
class Embedder(Protocol):
    """Minimal interface for a sentence embedding model."""

    def encode(
        self,
        sentences: list[str],
        *,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
    ) -> np.ndarray: ...


# ---------------------------------------------------------------------------
# Step 1: Encode descriptors
# ---------------------------------------------------------------------------

def encode_descriptors(
    agent_ids: list[str],
    descriptors: dict[str, dict[str, str]],
    embedder: Embedder,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Batch-encode all keys and queries in two calls.

    Args:
        agent_ids: Ordered list of agent identifiers.
        descriptors: {agent_id: {"key": str, "query": str}}
        embedder: Object with an encode() method (e.g. SentenceTransformer).

    Returns:
        key_vectors:   (N, D) float32, L2-normalized
        query_vectors: (N, D) float32, L2-normalized
    """
    keys = [descriptors[aid]["key"] for aid in agent_ids]
    queries = [descriptors[aid]["query"] for aid in agent_ids]

    key_vectors = embedder.encode(
        keys, convert_to_numpy=True, normalize_embeddings=True,
    )
    query_vectors = embedder.encode(
        queries, convert_to_numpy=True, normalize_embeddings=True,
    )

    key_vectors = np.asarray(key_vectors, dtype=np.float32)
    query_vectors = np.asarray(query_vectors, dtype=np.float32)

    # Safety: re-normalize in case the embedder didn't honor the flag
    key_vectors = _safe_normalize(key_vectors)
    query_vectors = _safe_normalize(query_vectors)

    return key_vectors, query_vectors


# ---------------------------------------------------------------------------
# Step 2: Cosine similarity matrix
# ---------------------------------------------------------------------------

def cosine_similarity_matrix(
    query_vectors: np.ndarray,
    key_vectors: np.ndarray,
) -> np.ndarray:
    """
    Compute pairwise cosine similarity between all query-key pairs.

    S[i][j] = cos_sim(query_i, key_j)

    When inputs are L2-normalized, this is a single matmul.
    The diagonal is zeroed (an agent cannot route to itself).

    Args:
        query_vectors: (N, D) pre-normalized float32
        key_vectors:   (N, D) pre-normalized float32

    Returns:
        S: (N, N) float32 with values in [-1, 1], diagonal = 0
    """
    S = query_vectors @ key_vectors.T  # (N, D) @ (D, N) -> (N, N)
    np.fill_diagonal(S, 0.0)
    return S.astype(np.float32)


# ---------------------------------------------------------------------------
# Step 3: Threshold + in-degree cap -> binary adjacency
# ---------------------------------------------------------------------------

def build_adjacency(
    S: np.ndarray,
    tau: float = 0.35,
    k_in: int = 3,
) -> np.ndarray:
    """
    Build a binary adjacency matrix from the similarity matrix.

    A[i][j] = 1 means agent j sends output to agent i (edge j -> i).

    Steps:
        1. Hard threshold at tau
        2. Zero the diagonal (no self-loops)
        3. For each row, keep only top k_in entries by similarity

    Args:
        S:     (N, N) cosine similarity matrix
        tau:   minimum similarity for an edge
        k_in:  maximum incoming edges per agent

    Returns:
        A: (N, N) binary int32 adjacency matrix
    """
    N = S.shape[0]

    # Step 1: Threshold
    A = (S >= tau).astype(np.float32)

    # Step 2: No self-loops
    np.fill_diagonal(A, 0.0)

    # Step 3: Enforce k_in per receiver (per row)
    for i in range(N):
        active = np.where(A[i] > 0)[0]
        if len(active) > k_in:
            sims = S[i, active]
            # argsort descending, take top k_in
            ranked = active[np.argsort(-sims)]
            # Zero out everything beyond top k_in
            A[i, ranked[k_in:]] = 0

    return A.astype(np.int32)


# ---------------------------------------------------------------------------
# Step 4: Cycle detection (DFS with coloring)
# ---------------------------------------------------------------------------

def find_cycle(A: np.ndarray) -> list[int] | None:
    """
    Find one cycle in the directed graph represented by adjacency matrix A.

    Uses DFS with WHITE/GRAY/BLACK coloring.  Returns the cycle as an
    ordered list of node indices [v, ..., u] such that the edges form
    v -> ... -> u -> v, or None if the graph is acyclic.

    Convention: A[i][j] = 1 means edge j -> i.
    Outgoing edges FROM node u: {v : A[v][u] == 1}  (column u)
    """
    N = A.shape[0]
    WHITE, GRAY, BLACK = 0, 1, 2
    color = np.zeros(N, dtype=np.int32)
    parent = np.full(N, -1, dtype=np.int32)

    def dfs(u: int) -> list[int] | None:
        color[u] = GRAY
        neighbors = np.where(A[:, u] == 1)[0]
        for v in neighbors:
            if color[v] == GRAY:
                # Back edge u -> v found; reconstruct cycle
                return _extract_cycle(u, v, parent)
            elif color[v] == WHITE:
                parent[v] = u
                result = dfs(v)
                if result is not None:
                    return result
        color[u] = BLACK
        return None

    for start in range(N):
        if color[start] == WHITE:
            result = dfs(start)
            if result is not None:
                return result
    return None


def _extract_cycle(
    u: int,
    v: int,
    parent: np.ndarray,
) -> list[int]:
    """
    Given back edge u -> v (v is ancestor of u in DFS tree),
    reconstruct the cycle v -> ... -> u.

    Returns ordered list [v, ..., u].  The implied closing edge is u -> v.
    """
    cycle = []
    node = u
    while node != v:
        cycle.append(node)
        node = int(parent[node])
    cycle.append(v)
    cycle.reverse()  # Now [v, ..., u]
    return cycle


# ---------------------------------------------------------------------------
# Step 5: Cycle breaking (greedy weakest-edge removal)
# ---------------------------------------------------------------------------

def break_cycle(
    A: np.ndarray,
    S: np.ndarray,
    cycle: list[int],
) -> tuple[int, int, float]:
    """
    Remove the weakest edge in the given cycle.

    The cycle is [v0, v1, ..., vk] representing path:
        v0 -> v1 -> ... -> vk -> v0

    Edge vi -> vi+1 means A[vi+1][vi] = 1 (A[receiver][sender]).

    Tiebreaker for identical similarities: lowest sender index,
    then lowest receiver index.

    Returns (sender, receiver, similarity) of the removed edge.
    """
    edges = []
    for idx in range(len(cycle)):
        sender = cycle[idx]
        receiver = cycle[(idx + 1) % len(cycle)]
        sim = float(S[receiver, sender])
        edges.append((sender, receiver, sim))

    # Weakest edge; tiebreak by sender index, then receiver index
    weakest = min(edges, key=lambda e: (e[2], e[0], e[1]))
    sender, receiver, sim = weakest

    # Remove it from adjacency
    A[receiver, sender] = 0

    return weakest


def break_all_cycles(
    A: np.ndarray,
    S: np.ndarray,
    max_iterations: int = 50,
) -> list[tuple[int, int, float]]:
    """
    Iteratively find and break cycles until the graph is a DAG.

    For N <= 10, the maximum possible edges is 90, so cycles can be
    broken in at most 90 iterations (in practice, 0-3).

    Args:
        A: (N, N) binary adjacency matrix (modified in-place)
        S: (N, N) similarity matrix (read-only, for edge weights)
        max_iterations: safety limit

    Returns:
        List of removed edges as (sender_idx, receiver_idx, similarity).

    Raises:
        RuntimeError: If cycle breaking does not converge.
    """
    removed: list[tuple[int, int, float]] = []

    for _ in range(max_iterations):
        cycle = find_cycle(A)
        if cycle is None:
            break
        edge = break_cycle(A, S, cycle)
        removed.append(edge)
    else:
        raise RuntimeError(
            f"Cycle breaking did not converge after {max_iterations} iterations. "
            f"This indicates a bug -- N={A.shape[0]} agents can have at most "
            f"{A.shape[0] * (A.shape[0] - 1)} edges."
        )

    return removed


# ---------------------------------------------------------------------------
# Step 6: Topological sort (Kahn's with alphabetical tie-breaking)
# ---------------------------------------------------------------------------

def topological_sort(
    A: np.ndarray,
    agent_ids: list[str],
) -> list[str]:
    """
    Kahn's algorithm with alphabetical tie-breaking for deterministic order.

    Convention: A[i][j] = 1 means edge j -> i.
    In-degree of node i = sum(A[i, :])  (row i).
    Outgoing edges from j: all i where A[i][j] = 1 (column j).

    Args:
        A: (N, N) binary DAG adjacency matrix (must be acyclic)
        agent_ids: ordered list of agent identifier strings

    Returns:
        Execution order as list of agent_id strings.

    Raises:
        ValueError: If the graph contains a cycle.
    """
    N = A.shape[0]
    in_degree = A.sum(axis=1).astype(int)  # row sums

    # Min-heap on agent_id string for alphabetical tie-breaking
    heap: list[tuple[str, int]] = []
    for i in range(N):
        if in_degree[i] == 0:
            heapq.heappush(heap, (agent_ids[i], i))

    order: list[str] = []

    while heap:
        aid, u = heapq.heappop(heap)
        order.append(aid)

        # Outgoing edges from u: all v where A[v][u] == 1
        targets = np.where(A[:, u] == 1)[0]
        for v in targets:
            in_degree[v] -= 1
            if in_degree[v] == 0:
                heapq.heappush(heap, (agent_ids[v], v))

    if len(order) != N:
        remaining = set(agent_ids) - set(order)
        raise ValueError(
            f"Topological sort failed: {remaining} still have unsatisfied "
            f"dependencies. The graph contains a cycle that was not broken."
        )

    return order


# ---------------------------------------------------------------------------
# Step 7: Graph health diagnostics
# ---------------------------------------------------------------------------

def check_graph_health(
    A: np.ndarray,
    agent_ids: list[str],
) -> dict[str, Any]:
    """
    Diagnostic checks on the adjacency matrix.

    Returns dict with keys:
        total_edges, density, isolated_agents, warnings
    """
    N = A.shape[0]
    total_possible = N * (N - 1)
    total_edges = int(A.sum())
    density = total_edges / total_possible if total_possible > 0 else 0.0

    isolated = [
        agent_ids[i]
        for i in range(N)
        if A[i].sum() == 0 and A[:, i].sum() == 0
    ]

    warnings: list[str] = []
    if total_edges == 0:
        warnings.append(
            "EMPTY_GRAPH: No edges above threshold. Consider lowering tau."
        )
    if density > 0.80:
        warnings.append(
            f"DENSE_GRAPH: {density:.0%} density. "
            f"Routing adds little value over broadcast."
        )
    if isolated:
        warnings.append(f"ISOLATED_AGENTS: {isolated} have no connections.")

    return {
        "total_edges": total_edges,
        "density": density,
        "isolated_agents": isolated,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Internal: safe L2 normalization
# ---------------------------------------------------------------------------

def _safe_normalize(vectors: np.ndarray) -> np.ndarray:
    """L2-normalize rows, handling zero vectors gracefully."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-8)
    return (vectors / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _validate_inputs(
    agent_ids: list[str],
    descriptors: dict[str, dict[str, str]],
    tau: float,
    k_in: int,
) -> list[str]:
    """
    Validate build_topology inputs.  Returns list of warnings
    (empty if all OK).  Raises ValueError on fatal errors.
    """
    warnings: list[str] = []

    if tau < 0.0 or tau > 1.0:
        raise ValueError(f"tau must be in [0, 1], got {tau}")
    if k_in < 1:
        raise ValueError(f"k_in must be >= 1, got {k_in}")

    for aid in agent_ids:
        if aid not in descriptors:
            raise ValueError(
                f"Agent '{aid}' listed in agent_ids but missing from descriptors"
            )
        d = descriptors[aid]
        if "key" not in d or "query" not in d:
            raise ValueError(
                f"Agent '{aid}' descriptor must have 'key' and 'query' fields"
            )
        key_text = d["key"].strip()
        query_text = d["query"].strip()
        if len(key_text) < 10:
            warnings.append(
                f"{aid}: key too short ({len(key_text)} chars). "
                f"Will likely be isolated."
            )
        if len(query_text) < 10:
            warnings.append(
                f"{aid}: query too short ({len(query_text)} chars). "
                f"Will likely be isolated."
            )

    return warnings


# ===========================================================================
# Public API: build_topology
# ===========================================================================

def build_topology(
    agent_ids: list[str],
    descriptors: dict[str, dict[str, str]],
    embedder: Embedder,
    tau: float = 0.35,
    k_in: int = 3,
    pheromone_weights: dict[tuple[str, str], float] | None = None,
) -> Topology:
    """
    Full DyTopo routing pipeline: descriptors -> execution order.

    Pure function -- no I/O, no state, no side effects (beyond the
    embedder.encode() call which is treated as a pure transform).

    Steps:
        1. Validate inputs
        2. Encode descriptors (batch)
        3. Compute cosine similarity matrix
        4. Build adjacency (threshold + k_in cap)
        5. Check graph health
        6. Break all cycles (greedy weakest-edge)
        7. Topological sort (Kahn's, alphabetical tie-breaking)
        8. Package into Topology model

    Args:
        agent_ids:    Ordered list of agent IDs.
        descriptors:  {agent_id: {"key": str, "query": str}} for each agent.
        embedder:     Object with encode() method (e.g. SentenceTransformer).
        tau:          Cosine similarity threshold for edge creation (0.0-1.0).
        k_in:         Maximum incoming edges per agent (>= 1).

    Returns:
        Topology with edges, execution_order, density, isolated_agents.

    Raises:
        ValueError: On invalid inputs (bad tau, k_in, missing descriptors,
                    non-square matrix, etc.).
    """
    N = len(agent_ids)

    # --- Always validate params (even for trivial cases) ---
    if tau < 0.0 or tau > 1.0:
        raise ValueError(f"tau must be in [0, 1], got {tau}")
    if k_in < 1:
        raise ValueError(f"k_in must be >= 1, got {k_in}")

    # --- Edge case: 0 agents ---
    if N == 0:
        return Topology(
            edges=[],
            execution_order=[],
            density=0.0,
            isolated_agents=[],
        )

    # --- Edge case: 1 agent ---
    if N == 1:
        return Topology(
            edges=[],
            execution_order=[agent_ids[0]],
            density=0.0,
            isolated_agents=[],
        )

    # --- Validate descriptors (only meaningful for N >= 2) ---
    _validate_inputs(agent_ids, descriptors, tau, k_in)

    # --- Step 1: Embed ---
    key_vecs, query_vecs = encode_descriptors(agent_ids, descriptors, embedder)

    # --- Step 2: Similarity matrix ---
    S = cosine_similarity_matrix(query_vecs, key_vecs)

    # Validate matrix dimensions
    if S.shape[0] != N or S.shape[1] != N:
        raise ValueError(
            f"Similarity matrix shape {S.shape} does not match "
            f"agent count {N}. Expected ({N}, {N})."
        )

    # --- Step 3: Threshold + k_in ---
    A = build_adjacency(S, tau=tau, k_in=k_in)

    # --- Step 4: Health check ---
    health = check_graph_health(A, agent_ids)

    # --- Step 5: Break cycles ---
    break_all_cycles(A, S)

    # --- Step 6: Topological sort ---
    order = topological_sort(A, agent_ids)

    # --- Step 7: Build edge list + Topology ---
    edges: list[TopologyEdge] = []
    for i in range(N):
        for j in range(N):
            if A[i, j] == 1:
                base_weight = float(S[i, j])
                # Apply Janitor pheromone weights (v0.7.7)
                if pheromone_weights:
                    key = (agent_ids[j], agent_ids[i])  # (sender, receiver)
                    base_weight *= pheromone_weights.get(key, 1.0)
                edges.append(
                    TopologyEdge(
                        sender=agent_ids[j],
                        receiver=agent_ids[i],
                        weight=base_weight,
                    )
                )

    density = health["density"]
    isolated = health["isolated_agents"]

    # Re-check isolated after cycle breaking (some may have changed)
    post_health = check_graph_health(A, agent_ids)
    isolated = post_health["isolated_agents"]
    density = post_health["density"]

    return Topology(
        edges=edges,
        execution_order=order,
        density=density,
        isolated_agents=isolated,
    )


# ===========================================================================
# build_topology_from_matrix -- alternative entry point for pre-computed S
# ===========================================================================

def build_topology_from_matrix(
    agent_ids: list[str],
    sim_matrix: np.ndarray,
    tau: float = 0.35,
    k_in: int = 3,
) -> Topology:
    """
    Build topology from a pre-computed similarity matrix.

    This is the lower-level entry point when the caller already has the
    (N, N) cosine similarity matrix (e.g. from a cached or external source).

    Args:
        agent_ids:   Ordered list of agent IDs.
        sim_matrix:  (N, N) cosine similarity matrix.  S[i][j] = similarity
                     of agent j's key to agent i's query.
        tau:         Cosine similarity threshold.
        k_in:        Maximum incoming edges per agent.

    Returns:
        Topology model.

    Raises:
        ValueError: On dimension mismatch or invalid params.
    """
    N = len(agent_ids)

    if N == 0:
        return Topology(
            edges=[],
            execution_order=[],
            density=0.0,
            isolated_agents=[],
        )

    if N == 1:
        return Topology(
            edges=[],
            execution_order=[agent_ids[0]],
            density=0.0,
            isolated_agents=[],
        )

    sim_matrix = np.asarray(sim_matrix, dtype=np.float32)
    if sim_matrix.shape != (N, N):
        raise ValueError(
            f"Similarity matrix shape {sim_matrix.shape} does not match "
            f"agent count {N}. Expected ({N}, {N})."
        )

    if tau < 0.0 or tau > 1.0:
        raise ValueError(f"tau must be in [0, 1], got {tau}")
    if k_in < 1:
        raise ValueError(f"k_in must be >= 1, got {k_in}")

    # Zero diagonal (no self-loops)
    S = sim_matrix.copy()
    np.fill_diagonal(S, 0.0)

    A = build_adjacency(S, tau=tau, k_in=k_in)
    break_all_cycles(A, S)
    order = topological_sort(A, agent_ids)

    edges: list[TopologyEdge] = []
    for i in range(N):
        for j in range(N):
            if A[i, j] == 1:
                edges.append(
                    TopologyEdge(
                        sender=agent_ids[j],
                        receiver=agent_ids[i],
                        weight=float(S[i, j]),
                    )
                )

    health = check_graph_health(A, agent_ids)

    return Topology(
        edges=edges,
        execution_order=order,
        density=health["density"],
        isolated_agents=health["isolated_agents"],
    )
