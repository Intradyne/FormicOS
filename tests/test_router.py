"""
Tests for FormicOS v0.6.0 DyTopo Semantic Router.

Covers:
- Known similarity matrix produces expected DAG
- Cycle breaking works on cyclic input (construct an explicit cycle)
- Deterministic output on repeated calls (same input -> same output)
- Empty input returns empty topology
- Single agent returns single-element execution order
- All agents isolated (tau too high) -> all in execution order, no edges
- Threshold enforcement (edges below tau are removed)
- k_in cap enforcement
- Alphabetical tie-breaking verification
- Input validation (bad tau, k_in, missing descriptors)
- Pre-computed similarity matrix entry point
- Real sentence-transformers model integration (skipif unavailable)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.models import Topology, TopologyEdge
from src.router import (
    _safe_normalize,
    break_all_cycles,
    build_adjacency,
    build_topology,
    build_topology_from_matrix,
    check_graph_health,
    cosine_similarity_matrix,
    encode_descriptors,
    find_cycle,
    topological_sort,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def mock_embedder():
    """
    A mock embedder that returns deterministic, pre-normalized vectors.

    Maps known strings to fixed vectors so tests are fully reproducible
    without requiring sentence-transformers.
    """
    # 4-dimensional vectors for simplicity
    VECTORS = {
        # Agent A: architecture offering, needs implementation feedback
        "I have a system architecture design": np.array(
            [0.8, 0.2, 0.1, 0.0], dtype=np.float32
        ),
        "I need implementation feedback": np.array(
            [0.1, 0.7, 0.3, 0.1], dtype=np.float32
        ),
        # Agent B: code implementation, needs architecture spec
        "I have working code implementations": np.array(
            [0.1, 0.8, 0.2, 0.1], dtype=np.float32
        ),
        "I need the architectural specification": np.array(
            [0.7, 0.2, 0.1, 0.2], dtype=np.float32
        ),
        # Agent C: code review feedback, needs code
        "I have code review feedback": np.array(
            [0.2, 0.6, 0.5, 0.1], dtype=np.float32
        ),
        "I need code to review": np.array(
            [0.1, 0.8, 0.1, 0.2], dtype=np.float32
        ),
        # Agent D: test cases, needs code and spec
        "I have test cases and benchmarks": np.array(
            [0.1, 0.3, 0.2, 0.8], dtype=np.float32
        ),
        "I need code and specs to test against": np.array(
            [0.5, 0.5, 0.2, 0.1], dtype=np.float32
        ),
        # For cycle tests: identical symmetric descriptors
        "offering alpha": np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32),
        "need alpha": np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32),
        "offering beta": np.array([0.1, 0.9, 0.0, 0.0], dtype=np.float32),
        "need beta": np.array([0.1, 0.9, 0.0, 0.0], dtype=np.float32),
        "offering gamma": np.array([0.0, 0.1, 0.9, 0.0], dtype=np.float32),
        "need gamma": np.array([0.0, 0.1, 0.9, 0.0], dtype=np.float32),
        # For isolated tests
        "unrelated offering xyz": np.array(
            [0.0, 0.0, 0.0, 1.0], dtype=np.float32
        ),
        "unrelated need xyz": np.array(
            [0.0, 0.0, 1.0, 0.0], dtype=np.float32
        ),
        "unrelated offering abc": np.array(
            [1.0, 0.0, 0.0, 0.0], dtype=np.float32
        ),
        "unrelated need abc": np.array(
            [0.0, 1.0, 0.0, 0.0], dtype=np.float32
        ),
    }

    def _encode(
        sentences,
        *,
        convert_to_numpy=True,
        normalize_embeddings=True,
    ):
        vecs = []
        for s in sentences:
            if s in VECTORS:
                vecs.append(VECTORS[s].copy())
            else:
                # Unknown string: return a small random-ish but deterministic vec
                rng = np.random.RandomState(hash(s) % (2**31))
                vecs.append(rng.randn(4).astype(np.float32))
        result = np.stack(vecs)
        if normalize_embeddings:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.maximum(norms, 1e-8)
            result = result / norms
        return result.astype(np.float32)

    embedder = MagicMock()
    embedder.encode = MagicMock(side_effect=_encode)
    return embedder


@pytest.fixture
def four_agent_descriptors():
    """Standard 4-agent descriptors for reuse across tests."""
    return {
        "Architect": {
            "key": "I have a system architecture design",
            "query": "I need implementation feedback",
        },
        "Coder": {
            "key": "I have working code implementations",
            "query": "I need the architectural specification",
        },
        "Reviewer": {
            "key": "I have code review feedback",
            "query": "I need code to review",
        },
        "Tester": {
            "key": "I have test cases and benchmarks",
            "query": "I need code and specs to test against",
        },
    }


@pytest.fixture
def four_agent_ids():
    return ["Architect", "Coder", "Reviewer", "Tester"]


# ===========================================================================
# Test: Empty input
# ===========================================================================


class TestEmptyInput:
    """Empty agent list returns empty topology."""

    def test_empty_returns_empty_topology(self, mock_embedder):
        result = build_topology([], {}, mock_embedder)
        assert isinstance(result, Topology)
        assert result.edges == []
        assert result.execution_order == []
        assert result.density == 0.0
        assert result.isolated_agents == []

    def test_empty_from_matrix(self):
        result = build_topology_from_matrix([], np.zeros((0, 0)))
        assert isinstance(result, Topology)
        assert result.execution_order == []
        assert result.edges == []


# ===========================================================================
# Test: Single agent
# ===========================================================================


class TestSingleAgent:
    """Single agent returns single-element execution order, no edges."""

    def test_single_agent_topology(self, mock_embedder):
        descriptors = {
            "Solo": {
                "key": "I have a system architecture design",
                "query": "I need implementation feedback",
            },
        }
        result = build_topology(["Solo"], descriptors, mock_embedder)
        assert result.execution_order == ["Solo"]
        assert result.edges == []
        assert result.density == 0.0

    def test_single_agent_from_matrix(self):
        result = build_topology_from_matrix(["Solo"], np.zeros((1, 1)))
        assert result.execution_order == ["Solo"]
        assert result.edges == []


# ===========================================================================
# Test: Known similarity matrix produces expected DAG
# ===========================================================================


class TestKnownMatrix:
    """Known pre-computed similarity matrix produces expected topology."""

    def test_known_dag(self):
        """
        Construct a similarity matrix where:
            A's query matches B's key strongly (0.7)
            B's query matches C's key strongly (0.6)
            No other edges above tau=0.5

        Expected DAG: B -> A, C -> B
        Execution order: C, B, A  (C has no deps, then B, then A)
        """
        agent_ids = ["AgentA", "AgentB", "AgentC"]
        # S[i][j] = how well j's key matches i's query
        S = np.array(
            [
                [0.0, 0.7, 0.1],  # A needs B's key (0.7)
                [0.2, 0.0, 0.6],  # B needs C's key (0.6)
                [0.1, 0.3, 0.0],  # C needs nobody strongly
            ],
            dtype=np.float32,
        )

        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)

        assert result.execution_order == ["AgentC", "AgentB", "AgentA"]
        assert len(result.edges) == 2

        edge_pairs = {(e.sender, e.receiver) for e in result.edges}
        assert ("AgentB", "AgentA") in edge_pairs  # B sends to A
        assert ("AgentC", "AgentB") in edge_pairs  # C sends to B

    def test_known_dag_density(self):
        """Density = 2 edges / 6 possible = 0.333..."""
        agent_ids = ["A", "B", "C"]
        S = np.array(
            [
                [0.0, 0.7, 0.1],
                [0.2, 0.0, 0.6],
                [0.1, 0.3, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        assert abs(result.density - 2.0 / 6.0) < 1e-6


# ===========================================================================
# Test: Threshold enforcement
# ===========================================================================


class TestThresholdEnforcement:
    """Edges below tau are removed."""

    def test_all_below_threshold(self):
        """With tau=0.9, no edges should survive low similarities."""
        agent_ids = ["A", "B", "C"]
        S = np.array(
            [
                [0.0, 0.5, 0.3],
                [0.4, 0.0, 0.6],
                [0.2, 0.5, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.9, k_in=3)
        assert result.edges == []
        assert len(result.execution_order) == 3
        assert result.density == 0.0

    def test_only_strong_edges_survive(self):
        """Only edges >= tau survive."""
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [0.0, 0.6],  # A needs B (0.6)
                [0.3, 0.0],  # B needs A (0.3) -- below tau
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        assert len(result.edges) == 1
        assert result.edges[0].sender == "B"
        assert result.edges[0].receiver == "A"

    def test_threshold_exact_boundary(self):
        """An edge exactly at tau should be kept (>= comparison)."""
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [0.0, 0.35],
                [0.1, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.35, k_in=3)
        assert len(result.edges) == 1


# ===========================================================================
# Test: k_in cap enforcement
# ===========================================================================


class TestKInCap:
    """Each agent receives at most k_in incoming edges."""

    def test_k_in_limits_incoming(self):
        """
        Agent A has high similarity from B, C, D (all above tau).
        With k_in=1, only the strongest incoming edge survives.
        """
        agent_ids = ["A", "B", "C", "D"]
        # A's row: needs from B(0.9), C(0.7), D(0.5) -- all above tau
        S = np.array(
            [
                [0.0, 0.9, 0.7, 0.5],  # A receives from B,C,D
                [0.1, 0.0, 0.1, 0.1],
                [0.1, 0.1, 0.0, 0.1],
                [0.1, 0.1, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.4, k_in=1)

        # A should only receive from B (strongest)
        incoming_to_a = [e for e in result.edges if e.receiver == "A"]
        assert len(incoming_to_a) == 1
        assert incoming_to_a[0].sender == "B"

    def test_k_in_2_keeps_top_2(self):
        """With k_in=2, A keeps top 2 incoming edges."""
        agent_ids = ["A", "B", "C", "D"]
        S = np.array(
            [
                [0.0, 0.9, 0.7, 0.5],
                [0.1, 0.0, 0.1, 0.1],
                [0.1, 0.1, 0.0, 0.1],
                [0.1, 0.1, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.4, k_in=2)

        incoming_to_a = [e for e in result.edges if e.receiver == "A"]
        assert len(incoming_to_a) == 2
        senders = {e.sender for e in incoming_to_a}
        assert senders == {"B", "C"}

    def test_k_in_no_effect_when_under_limit(self):
        """k_in=5 has no effect when only 2 edges exist."""
        agent_ids = ["A", "B", "C"]
        S = np.array(
            [
                [0.0, 0.6, 0.5],
                [0.1, 0.0, 0.1],
                [0.1, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.4, k_in=5)
        incoming_to_a = [e for e in result.edges if e.receiver == "A"]
        assert len(incoming_to_a) == 2


# ===========================================================================
# Test: Cycle breaking
# ===========================================================================


class TestCycleBreaking:
    """Cycle breaking works on cyclic input."""

    def test_simple_2_cycle(self):
        """
        Construct explicit 2-cycle: A -> B -> A.
        S[0][1] = 0.6 (B sends to A), S[1][0] = 0.5 (A sends to B).
        Weaker edge (0.5) should be removed.
        """
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [0.0, 0.6],  # A needs B (0.6)
                [0.5, 0.0],  # B needs A (0.5) -- weaker
            ],
            dtype=np.float32,
        )

        result = build_topology_from_matrix(agent_ids, S, tau=0.4, k_in=3)

        # Only one edge should survive (the stronger one)
        assert len(result.edges) == 1
        assert result.edges[0].sender == "B"
        assert result.edges[0].receiver == "A"
        assert result.edges[0].weight == pytest.approx(0.6)

        # B executes first (no deps), then A
        assert result.execution_order == ["B", "A"]

    def test_3_cycle_breaks_weakest(self):
        """
        3-cycle: A -> B -> C -> A.
        Edge weights: A->B (0.7), B->C (0.5), C->A (0.6).
        Weakest is B->C (0.5), should be removed.
        """
        # A[i][j] = 1 means j -> i
        # A -> B: A[B_idx][A_idx] = A[1][0]
        # B -> C: A[C_idx][B_idx] = A[2][1]
        # C -> A: A[A_idx][C_idx] = A[0][2]
        A = np.array(
            [
                [0, 0, 1],  # A receives from C
                [1, 0, 0],  # B receives from A
                [0, 1, 0],  # C receives from B
            ],
            dtype=np.int32,
        )
        S = np.array(
            [
                [0.0, 0.0, 0.6],  # C->A weight 0.6
                [0.7, 0.0, 0.0],  # A->B weight 0.7
                [0.0, 0.5, 0.0],  # B->C weight 0.5 (weakest)
            ],
            dtype=np.float32,
        )

        removed = break_all_cycles(A, S)
        assert len(removed) == 1
        sender, receiver, sim = removed[0]
        # Weakest edge is B->C: sender=B(1), receiver=C(2), sim=0.5
        assert sender == 1 and receiver == 2
        assert sim == pytest.approx(0.5)

        # After removal, graph should be acyclic
        assert find_cycle(A) is None

    def test_no_cycles_in_dag(self):
        """A DAG produces no removed edges."""
        A = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],  # A -> B
                [0, 1, 0],  # B -> C
            ],
            dtype=np.int32,
        )
        S = np.array(
            [
                [0.0, 0.0, 0.0],
                [0.6, 0.0, 0.0],
                [0.0, 0.7, 0.0],
            ],
            dtype=np.float32,
        )
        removed = break_all_cycles(A, S)
        assert removed == []

    def test_find_cycle_returns_none_for_dag(self):
        """find_cycle returns None for an acyclic graph."""
        A = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [1, 1, 0],
            ],
            dtype=np.int32,
        )
        assert find_cycle(A) is None

    def test_find_cycle_detects_cycle(self):
        """find_cycle returns a cycle for a cyclic graph."""
        # 2-cycle: 0 -> 1 -> 0
        A = np.array(
            [
                [0, 1],  # 0 receives from 1 (edge 1->0)
                [1, 0],  # 1 receives from 0 (edge 0->1)
            ],
            dtype=np.int32,
        )
        cycle = find_cycle(A)
        assert cycle is not None
        assert len(cycle) >= 2


# ===========================================================================
# Test: Topological sort
# ===========================================================================


class TestTopologicalSort:
    """Kahn's algorithm with alphabetical tie-breaking."""

    def test_linear_chain(self):
        """A -> B -> C produces order [A, B, C]."""
        # A sends to B: A[1][0] = 1
        # B sends to C: A[2][1] = 1
        A = np.array(
            [
                [0, 0, 0],
                [1, 0, 0],
                [0, 1, 0],
            ],
            dtype=np.int32,
        )
        order = topological_sort(A, ["A", "B", "C"])
        assert order == ["A", "B", "C"]

    def test_all_independent(self):
        """No edges -> alphabetical order."""
        A = np.zeros((3, 3), dtype=np.int32)
        order = topological_sort(A, ["Charlie", "Alice", "Bob"])
        assert order == ["Alice", "Bob", "Charlie"]

    def test_alphabetical_tiebreaking(self):
        """
        When multiple agents have in-degree 0 simultaneously,
        alphabetically first wins.
        """
        # D depends on both A and B. C is independent.
        # A, B, C all start with in-degree 0.
        A = np.array(
            [
                [0, 0, 0, 0],  # A: no deps
                [0, 0, 0, 0],  # B: no deps
                [0, 0, 0, 0],  # C: no deps
                [1, 1, 0, 0],  # D: depends on A and B
            ],
            dtype=np.int32,
        )
        order = topological_sort(A, ["Alpha", "Beta", "Charlie", "Delta"])
        # Alpha, Beta, Charlie are all roots -- alphabetical order
        assert order[:3] == ["Alpha", "Beta", "Charlie"]
        assert order[3] == "Delta"

    def test_raises_on_cycle(self):
        """Topological sort raises ValueError on a cyclic graph."""
        A = np.array(
            [
                [0, 1],
                [1, 0],
            ],
            dtype=np.int32,
        )
        with pytest.raises(ValueError, match="cycle"):
            topological_sort(A, ["A", "B"])

    def test_reverse_alpha_agents(self):
        """
        Agents named Z, Y, X with no edges.
        Execution order should be alphabetical: X, Y, Z.
        """
        A = np.zeros((3, 3), dtype=np.int32)
        order = topological_sort(A, ["Z", "Y", "X"])
        assert order == ["X", "Y", "Z"]


# ===========================================================================
# Test: All agents isolated (tau too high)
# ===========================================================================


class TestAllIsolated:
    """When tau is too high, all agents are isolated."""

    def test_high_tau_no_edges(self, mock_embedder, four_agent_ids, four_agent_descriptors):
        result = build_topology(
            four_agent_ids,
            four_agent_descriptors,
            mock_embedder,
            tau=0.99,
            k_in=3,
        )
        assert result.edges == []
        assert result.density == 0.0
        # All agents should still be in execution order
        assert len(result.execution_order) == 4
        assert set(result.execution_order) == set(four_agent_ids)
        # Order should be alphabetical (all have in-degree 0)
        assert result.execution_order == sorted(four_agent_ids)

    def test_high_tau_from_matrix(self):
        """Pre-computed matrix with tau=0.99 yields no edges."""
        agent_ids = ["A", "B", "C"]
        S = np.array(
            [
                [0.0, 0.5, 0.3],
                [0.4, 0.0, 0.6],
                [0.2, 0.5, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.99, k_in=3)
        assert result.edges == []
        assert result.execution_order == ["A", "B", "C"]
        assert set(result.isolated_agents) == {"A", "B", "C"}


# ===========================================================================
# Test: Deterministic output
# ===========================================================================


class TestDeterminism:
    """Same input always produces same output."""

    def test_repeated_calls_identical(
        self, mock_embedder, four_agent_ids, four_agent_descriptors
    ):
        """Run build_topology 5 times; all results must match."""
        results = []
        for _ in range(5):
            r = build_topology(
                four_agent_ids,
                four_agent_descriptors,
                mock_embedder,
                tau=0.35,
                k_in=3,
            )
            results.append(r)

        first = results[0]
        for r in results[1:]:
            assert r.execution_order == first.execution_order
            assert r.density == first.density
            assert len(r.edges) == len(first.edges)
            for e1, e2 in zip(first.edges, r.edges):
                assert e1.sender == e2.sender
                assert e1.receiver == e2.receiver
                assert e1.weight == pytest.approx(e2.weight)

    def test_repeated_matrix_calls(self):
        """build_topology_from_matrix is deterministic."""
        agent_ids = ["X", "Y", "Z"]
        S = np.array(
            [
                [0.0, 0.5, 0.3],
                [0.6, 0.0, 0.4],
                [0.2, 0.7, 0.0],
            ],
            dtype=np.float32,
        )
        results = [
            build_topology_from_matrix(agent_ids, S.copy(), tau=0.35, k_in=2)
            for _ in range(5)
        ]
        first = results[0]
        for r in results[1:]:
            assert r.execution_order == first.execution_order
            assert r.density == pytest.approx(first.density)


# ===========================================================================
# Test: Cosine similarity matrix
# ===========================================================================


class TestCosineSimilarity:
    """cosine_similarity_matrix correctness."""

    def test_identity_vectors(self):
        """Identical normalized vectors have cosine similarity 1 (but diagonal is 0)."""
        v = np.array([[1, 0, 0], [1, 0, 0]], dtype=np.float32)
        S = cosine_similarity_matrix(v, v)
        assert S[0, 0] == 0.0  # diagonal zeroed
        assert S[1, 1] == 0.0
        assert S[0, 1] == pytest.approx(1.0)
        assert S[1, 0] == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        """Orthogonal vectors have cosine similarity 0."""
        q = np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)
        k = np.array([[0, 1, 0], [1, 0, 0]], dtype=np.float32)
        S = cosine_similarity_matrix(q, k)
        assert S[0, 0] == pytest.approx(0.0)  # diagonal zeroed
        assert S[1, 1] == pytest.approx(0.0)
        assert S[0, 1] == pytest.approx(1.0)  # q0 dot k1
        assert S[1, 0] == pytest.approx(1.0)  # q1 dot k0

    def test_diagonal_always_zero(self):
        """Diagonal is always zero regardless of input."""
        rng = np.random.RandomState(42)
        v = rng.randn(5, 10).astype(np.float32)
        norms = np.linalg.norm(v, axis=1, keepdims=True)
        v = v / norms
        S = cosine_similarity_matrix(v, v)
        for i in range(5):
            assert S[i, i] == 0.0


# ===========================================================================
# Test: Build adjacency
# ===========================================================================


class TestBuildAdjacency:
    """build_adjacency threshold + k_in logic."""

    def test_threshold_filters(self):
        """Only entries >= tau survive."""
        S = np.array(
            [
                [0.0, 0.5, 0.2],
                [0.3, 0.0, 0.8],
                [0.1, 0.6, 0.0],
            ],
            dtype=np.float32,
        )
        A = build_adjacency(S, tau=0.5, k_in=10)
        # Surviving: S[0][1]=0.5, S[1][2]=0.8, S[2][1]=0.6
        assert A[0, 1] == 1
        assert A[1, 2] == 1
        assert A[2, 1] == 1
        # Below tau: S[0][2]=0.2, S[1][0]=0.3, S[2][0]=0.1
        assert A[0, 2] == 0
        assert A[1, 0] == 0
        assert A[2, 0] == 0

    def test_k_in_enforcement(self):
        """k_in=1 keeps only strongest incoming per row."""
        S = np.array(
            [
                [0.0, 0.6, 0.8, 0.5],
                [0.1, 0.0, 0.1, 0.1],
                [0.1, 0.1, 0.0, 0.1],
                [0.1, 0.1, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        A = build_adjacency(S, tau=0.4, k_in=1)
        # Row 0: B(0.6), C(0.8), D(0.5) all above tau.
        # k_in=1 keeps only C (strongest at 0.8)
        assert A[0, 2] == 1  # C sends to A
        assert A[0, 1] == 0  # B cut
        assert A[0, 3] == 0  # D cut

    def test_no_self_loops(self):
        """Diagonal is always 0 even if S diagonal is nonzero."""
        S = np.array(
            [
                [1.0, 0.5],
                [0.5, 1.0],
            ],
            dtype=np.float32,
        )
        A = build_adjacency(S, tau=0.4, k_in=3)
        assert A[0, 0] == 0
        assert A[1, 1] == 0


# ===========================================================================
# Test: Graph health
# ===========================================================================


class TestGraphHealth:
    """check_graph_health diagnostics."""

    def test_empty_graph_warning(self):
        A = np.zeros((3, 3), dtype=np.int32)
        health = check_graph_health(A, ["A", "B", "C"])
        assert health["total_edges"] == 0
        assert health["density"] == 0.0
        assert len(health["isolated_agents"]) == 3
        assert any("EMPTY_GRAPH" in w for w in health["warnings"])
        assert any("ISOLATED_AGENTS" in w for w in health["warnings"])

    def test_dense_graph_warning(self):
        """Density > 80% triggers DENSE_GRAPH warning."""
        # 3 agents, 5 out of 6 possible edges
        A = np.array(
            [
                [0, 1, 1],
                [1, 0, 1],
                [1, 0, 0],
            ],
            dtype=np.int32,
        )
        health = check_graph_health(A, ["A", "B", "C"])
        assert health["density"] == pytest.approx(5 / 6)
        assert any("DENSE_GRAPH" in w for w in health["warnings"])

    def test_no_warnings_healthy_graph(self):
        """A moderately connected graph has no warnings."""
        A = np.array(
            [
                [0, 1, 0],
                [0, 0, 0],
                [0, 1, 0],
            ],
            dtype=np.int32,
        )
        health = check_graph_health(A, ["A", "B", "C"])
        assert health["total_edges"] == 2
        # A has connections. B has connections. C has a connection.
        # But A: receives from B. B: sends to A and C. C: receives from B.
        # Isolated = nodes with no in OR out edges.
        # A: in=1, out=0 -> not isolated. B: in=0, out=2 -> not isolated.
        # C: in=1, out=0 -> not isolated.
        assert health["isolated_agents"] == []

    def test_single_node(self):
        """Single node: 0 possible edges, density 0."""
        A = np.zeros((1, 1), dtype=np.int32)
        health = check_graph_health(A, ["Solo"])
        assert health["density"] == 0.0
        # A single node with no edges is technically isolated
        assert health["isolated_agents"] == ["Solo"]


# ===========================================================================
# Test: Safe normalize
# ===========================================================================


class TestSafeNormalize:
    """_safe_normalize handles edge cases."""

    def test_already_normalized(self):
        v = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
        result = _safe_normalize(v)
        np.testing.assert_allclose(result, v, atol=1e-6)

    def test_zero_vector(self):
        """Zero vector should not produce NaN."""
        v = np.array([[0.0, 0.0, 0.0]], dtype=np.float32)
        result = _safe_normalize(v)
        assert not np.any(np.isnan(result))
        # Should be near-zero magnitude
        assert np.linalg.norm(result) < 1e-4

    def test_unnormalized_vectors(self):
        v = np.array([[3.0, 4.0, 0.0]], dtype=np.float32)
        result = _safe_normalize(v)
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-6


# ===========================================================================
# Test: Input validation
# ===========================================================================


class TestInputValidation:
    """build_topology validates inputs correctly."""

    def test_invalid_tau_low(self, mock_embedder):
        with pytest.raises(ValueError, match="tau"):
            build_topology(
                ["A", "B"],
                {
                    "A": {"key": "x" * 20, "query": "y" * 20},
                    "B": {"key": "x" * 20, "query": "y" * 20},
                },
                mock_embedder,
                tau=-0.1,
            )

    def test_invalid_tau_high(self, mock_embedder):
        with pytest.raises(ValueError, match="tau"):
            build_topology(
                ["A", "B"],
                {
                    "A": {"key": "x" * 20, "query": "y" * 20},
                    "B": {"key": "x" * 20, "query": "y" * 20},
                },
                mock_embedder,
                tau=1.5,
            )

    def test_invalid_k_in(self, mock_embedder):
        with pytest.raises(ValueError, match="k_in"):
            build_topology(
                ["A", "B"],
                {
                    "A": {"key": "x" * 20, "query": "y" * 20},
                    "B": {"key": "x" * 20, "query": "y" * 20},
                },
                mock_embedder,
                k_in=0,
            )

    def test_invalid_tau_single_agent(self, mock_embedder):
        """Even with a single agent, bad tau should be rejected."""
        with pytest.raises(ValueError, match="tau"):
            build_topology(
                ["A"],
                {"A": {"key": "x" * 20, "query": "y" * 20}},
                mock_embedder,
                tau=-0.5,
            )

    def test_missing_agent_in_descriptors(self, mock_embedder):
        with pytest.raises(ValueError, match="missing from descriptors"):
            build_topology(
                ["A", "B"],
                {"A": {"key": "x" * 20, "query": "y" * 20}},
                mock_embedder,
            )

    def test_missing_key_field(self, mock_embedder):
        with pytest.raises(ValueError, match="key"):
            build_topology(
                ["A", "B"],
                {
                    "A": {"key": "x" * 20, "query": "y" * 20},
                    "B": {"query": "y" * 20},
                },
                mock_embedder,
            )

    def test_matrix_dimension_mismatch(self):
        """Non-square or wrong-sized matrix raises ValueError."""
        with pytest.raises(ValueError, match="shape"):
            build_topology_from_matrix(
                ["A", "B"],
                np.zeros((3, 3), dtype=np.float32),
            )

    def test_matrix_non_square(self):
        with pytest.raises(ValueError, match="shape"):
            build_topology_from_matrix(
                ["A", "B"],
                np.zeros((2, 3), dtype=np.float32),
            )


# ===========================================================================
# Test: Encode descriptors
# ===========================================================================


class TestEncodeDescriptors:
    """encode_descriptors batch encoding."""

    def test_returns_correct_shapes(self, mock_embedder):
        agent_ids = ["A", "B"]
        descriptors = {
            "A": {"key": "I have a system architecture design", "query": "I need implementation feedback"},
            "B": {"key": "I have working code implementations", "query": "I need the architectural specification"},
        }
        keys, queries = encode_descriptors(agent_ids, descriptors, mock_embedder)
        assert keys.shape[0] == 2
        assert queries.shape[0] == 2
        assert keys.shape[1] == queries.shape[1]

    def test_vectors_are_normalized(self, mock_embedder):
        agent_ids = ["A"]
        descriptors = {
            "A": {"key": "I have a system architecture design", "query": "I need implementation feedback"},
        }
        keys, queries = encode_descriptors(agent_ids, descriptors, mock_embedder)
        key_norm = np.linalg.norm(keys[0])
        query_norm = np.linalg.norm(queries[0])
        assert abs(key_norm - 1.0) < 1e-5
        assert abs(query_norm - 1.0) < 1e-5

    def test_embedder_called_twice(self, mock_embedder):
        """Embedder should be called exactly twice (keys batch + queries batch)."""
        agent_ids = ["A", "B"]
        descriptors = {
            "A": {"key": "I have a system architecture design", "query": "I need implementation feedback"},
            "B": {"key": "I have working code implementations", "query": "I need the architectural specification"},
        }
        encode_descriptors(agent_ids, descriptors, mock_embedder)
        assert mock_embedder.encode.call_count == 2


# ===========================================================================
# Test: Full pipeline (build_topology with mock embedder)
# ===========================================================================


class TestFullPipeline:
    """Integration tests using mock embedder through build_topology."""

    def test_four_agents(
        self, mock_embedder, four_agent_ids, four_agent_descriptors
    ):
        result = build_topology(
            four_agent_ids,
            four_agent_descriptors,
            mock_embedder,
            tau=0.35,
            k_in=3,
        )
        assert isinstance(result, Topology)
        assert len(result.execution_order) == 4
        assert set(result.execution_order) == set(four_agent_ids)
        # Density should be between 0 and 1
        assert 0.0 <= result.density <= 1.0
        # All edges should have valid sender/receiver from agent_ids
        for e in result.edges:
            assert e.sender in four_agent_ids
            assert e.receiver in four_agent_ids
            assert e.sender != e.receiver
            assert e.weight >= 0.0

    def test_topology_is_dag(self, mock_embedder, four_agent_ids, four_agent_descriptors):
        """The returned topology must be a DAG (no cycles)."""
        result = build_topology(
            four_agent_ids,
            four_agent_descriptors,
            mock_embedder,
            tau=0.2,
            k_in=3,
        )
        # Verify execution_order is a valid topological ordering:
        # For every edge (sender -> receiver), sender must appear
        # before receiver in execution_order.
        order_idx = {aid: i for i, aid in enumerate(result.execution_order)}
        for e in result.edges:
            assert order_idx[e.sender] < order_idx[e.receiver], (
                f"Edge {e.sender} -> {e.receiver} violates topological order: "
                f"{e.sender} at position {order_idx[e.sender]}, "
                f"{e.receiver} at position {order_idx[e.receiver]}"
            )

    def test_edge_weights_match_topology_edges(
        self, mock_embedder, four_agent_ids, four_agent_descriptors
    ):
        """All edge weights are non-negative floats."""
        result = build_topology(
            four_agent_ids,
            four_agent_descriptors,
            mock_embedder,
            tau=0.35,
            k_in=3,
        )
        for e in result.edges:
            assert isinstance(e.weight, float)
            assert e.weight >= 0.0


# ===========================================================================
# Test: build_topology_from_matrix
# ===========================================================================


class TestBuildTopologyFromMatrix:
    """Tests for the pre-computed matrix entry point."""

    def test_basic_usage(self):
        agent_ids = ["A", "B", "C"]
        S = np.array(
            [
                [0.0, 0.6, 0.2],
                [0.1, 0.0, 0.7],
                [0.3, 0.1, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        assert isinstance(result, Topology)
        assert len(result.execution_order) == 3

    def test_zeroes_diagonal(self):
        """Even if diagonal has values, they are ignored."""
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [1.0, 0.6],
                [0.1, 1.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        # No self-loops
        for e in result.edges:
            assert e.sender != e.receiver


# ===========================================================================
# Test: Alphabetical tie-breaking in full pipeline
# ===========================================================================


class TestAlphabeticalTieBreaking:
    """Verify alphabetical tie-breaking across the full pipeline."""

    def test_independent_agents_sorted_alphabetically(self):
        """Agents with no edges are sorted alphabetically."""
        agent_ids = ["Delta", "Alpha", "Charlie", "Bravo"]
        S = np.zeros((4, 4), dtype=np.float32)  # no edges
        result = build_topology_from_matrix(agent_ids, S, tau=0.35, k_in=3)
        assert result.execution_order == ["Alpha", "Bravo", "Charlie", "Delta"]

    def test_partial_order_tiebreaking(self):
        """
        B depends on A. C and D are independent of everything.
        Expected: A before B (dependency). C and D in alpha order among roots.
        """
        agent_ids = ["D", "C", "B", "A"]
        # Only edge: A -> B  =>  A[B_idx][A_idx] = A[2][3] = 1
        # agent_ids indexing: D=0, C=1, B=2, A=3
        S = np.zeros((4, 4), dtype=np.float32)
        S[2, 3] = 0.8  # B needs A (A sends to B)
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)

        # A, C, D are roots (in-degree 0). A processed first (alpha).
        # After A is processed, B's in-degree drops to 0.
        # Now B, C, D all have in-degree 0 → alphabetical: B, C, D.
        assert result.execution_order == ["A", "B", "C", "D"]


# ===========================================================================
# Test: TopologyEdge model integration
# ===========================================================================


class TestTopologyEdgeIntegration:
    """Verify edges are proper TopologyEdge Pydantic models."""

    def test_edge_model_fields(self):
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [0.0, 0.7],
                [0.2, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        assert len(result.edges) == 1
        edge = result.edges[0]
        assert isinstance(edge, TopologyEdge)
        assert edge.sender == "B"
        assert edge.receiver == "A"
        assert edge.weight == pytest.approx(0.7)
        assert edge.schema_version == "0.6.0"

    def test_topology_model_serialization(self):
        """Topology can be serialized to dict and back."""
        agent_ids = ["A", "B"]
        S = np.array(
            [
                [0.0, 0.7],
                [0.2, 0.0],
            ],
            dtype=np.float32,
        )
        result = build_topology_from_matrix(agent_ids, S, tau=0.5, k_in=3)
        data = result.model_dump()
        restored = Topology.model_validate(data)
        assert restored.execution_order == result.execution_order
        assert len(restored.edges) == len(result.edges)


# ===========================================================================
# Test: Real sentence-transformers integration (skipped if unavailable)
# ===========================================================================


def _has_sentence_transformers() -> bool:
    """Check if sentence-transformers is installed."""
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(
    not _has_sentence_transformers(),
    reason="sentence-transformers not installed",
)
class TestRealEmbedder:
    """Integration test with the real all-MiniLM-L6-v2 model."""

    def test_real_embedder_four_agents(self):
        from sentence_transformers import SentenceTransformer

        embedder = SentenceTransformer("all-MiniLM-L6-v2")

        agent_ids = ["Architect", "Coder", "Reviewer", "Tester"]
        descriptors = {
            "Architect": {
                "key": "I have a system decomposition with module boundaries and data flow",
                "query": "I need implementation feedback on whether my design is feasible",
            },
            "Coder": {
                "key": "I have working implementations of the core sorting algorithms",
                "query": "I need the architectural specification and module interfaces",
            },
            "Reviewer": {
                "key": "I have code review feedback with correctness and style issues",
                "query": "I need the code implementations to review",
            },
            "Tester": {
                "key": "I have test cases covering edge cases and performance benchmarks",
                "query": "I need both the code and the architectural spec to design tests against",
            },
        }

        result = build_topology(
            agent_ids, descriptors, embedder, tau=0.35, k_in=3
        )

        assert isinstance(result, Topology)
        assert len(result.execution_order) == 4
        assert set(result.execution_order) == set(agent_ids)

        # Must be a valid DAG
        order_idx = {aid: i for i, aid in enumerate(result.execution_order)}
        for e in result.edges:
            assert order_idx[e.sender] < order_idx[e.receiver]

        # Deterministic: run again and compare
        result2 = build_topology(
            agent_ids, descriptors, embedder, tau=0.35, k_in=3
        )
        assert result.execution_order == result2.execution_order
        assert len(result.edges) == len(result2.edges)
