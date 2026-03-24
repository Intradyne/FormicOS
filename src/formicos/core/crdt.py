# pyright: reportUnknownVariableType=false
"""Conflict-free Replicated Data Types for federated knowledge (Wave 33).

Three primitives: GCounter (grow-only counter), LWWRegister (last-writer-wins),
GSet (grow-only set). Merge operations are commutative, associative, idempotent.

ObservationCRDT: composite type storing raw observation counts and timestamps.
Gamma-decay is applied at query time, not stored in the CRDT.

Design references: Shapiro et al. 2011 (CRDTs comprehensive study),
python3-crdt and ericmoritz/crdt (patterns only, not dependencies).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class GCounter:
    """Grow-only counter. Per-node integer values. Merge = pairwise max.

    Integer-only by design: observation counts must be exact.
    The prior (5.0) and decay are applied at query time, not stored here.
    """

    counts: dict[str, int] = field(default_factory=dict)

    def increment(self, node_id: str, delta: int = 1) -> None:
        if delta < 1:
            raise ValueError("G-Counter delta must be positive")
        self.counts[node_id] = self.counts.get(node_id, 0) + delta

    def merge(self, other: GCounter) -> GCounter:
        """Pairwise max. Commutative, associative, idempotent."""
        all_keys = set(self.counts) | set(other.counts)
        return GCounter(counts={
            k: max(self.counts.get(k, 0), other.counts.get(k, 0))
            for k in all_keys
        })

    def value(self) -> int:
        """Total count across all nodes."""
        return sum(self.counts.values())


@dataclass
class LWWRegister:
    """Last-Writer-Wins Register. Higher timestamp wins. Ties broken by node_id."""

    value: Any = None
    timestamp: float = 0.0
    node_id: str = ""

    def assign(self, value: Any, timestamp: float, node_id: str) -> None:
        if timestamp > self.timestamp or (
            timestamp == self.timestamp and node_id > self.node_id
        ):
            self.value = value
            self.timestamp = timestamp
            self.node_id = node_id

    def merge(self, other: LWWRegister) -> LWWRegister:
        """Higher timestamp wins. Ties broken by node_id (lexicographic)."""
        if other.timestamp > self.timestamp or (
            other.timestamp == self.timestamp and other.node_id > self.node_id
        ):
            return LWWRegister(
                value=other.value, timestamp=other.timestamp, node_id=other.node_id,
            )
        return LWWRegister(
            value=self.value, timestamp=self.timestamp, node_id=self.node_id,
        )


@dataclass
class GSet:
    """Grow-only set. Merge = union. Elements never removed."""

    elements: set[str] = field(default_factory=set)

    def add(self, element: str) -> None:
        self.elements.add(element)

    def merge(self, other: GSet) -> GSet:
        return GSet(elements=self.elements | other.elements)

    def __contains__(self, element: str) -> bool:
        return element in self.elements


@dataclass
class ObservationCRDT:
    """Computational CRDT for federated Bayesian confidence.

    Stores raw observation counts (G-Counters) and timestamps (LWW Registers).
    Gamma-decay is applied at query time, not stored in the CRDT.
    This separation ensures monotonic CRDT operations while preserving
    time-dependent confidence computation.

    Reference: Navalho, Duarte, Preguica (PaPoC 2015) —
    separate monotonic facts from derived computation.
    """

    successes: GCounter = field(default_factory=GCounter)
    failures: GCounter = field(default_factory=GCounter)
    last_obs_ts: dict[str, LWWRegister] = field(default_factory=dict)
    archived_by: GSet = field(default_factory=GSet)
    content: LWWRegister = field(default_factory=LWWRegister)
    entry_type: LWWRegister = field(default_factory=LWWRegister)
    domains: GSet = field(default_factory=GSet)
    decay_class: LWWRegister = field(default_factory=LWWRegister)

    def merge(self, other: ObservationCRDT) -> ObservationCRDT:
        """All components merge independently using their own semantics."""
        merged_ts = dict(self.last_obs_ts)
        for k, v in other.last_obs_ts.items():
            if k in merged_ts:
                merged_ts[k] = merged_ts[k].merge(v)
            else:
                merged_ts[k] = v
        return ObservationCRDT(
            successes=self.successes.merge(other.successes),
            failures=self.failures.merge(other.failures),
            last_obs_ts=merged_ts,
            archived_by=self.archived_by.merge(other.archived_by),
            content=self.content.merge(other.content),
            entry_type=self.entry_type.merge(other.entry_type),
            domains=self.domains.merge(other.domains),
            decay_class=self.decay_class.merge(other.decay_class),
        )

    def query_alpha(
        self,
        now: float,
        gamma_rates: dict[str, float],
        prior_alpha: float,
        max_elapsed_days: float = 180.0,
    ) -> float:
        """Compute effective alpha at query time with per-instance decay.

        Args:
            now: Current epoch seconds.
            gamma_rates: Mapping from decay_class name to gamma rate.
                         Callers pass GAMMA_RATES from knowledge_constants.
            prior_alpha: Prior alpha value (callers pass PRIOR_ALPHA).
            max_elapsed_days: Cap on elapsed days (ADR-041 hardening).
        """
        dc = self.decay_class.value if self.decay_class.value else "ephemeral"
        gamma = gamma_rates.get(dc, 0.98)
        alpha = prior_alpha
        for inst_id, count in self.successes.counts.items():
            ts_reg = self.last_obs_ts.get(inst_id)
            ts = ts_reg.timestamp if ts_reg else now
            elapsed = min((now - ts) / 86400.0, max_elapsed_days)
            alpha += (gamma ** max(elapsed, 0.0)) * count
        return max(alpha, 1.0)

    def query_beta(
        self,
        now: float,
        gamma_rates: dict[str, float],
        prior_beta: float,
        max_elapsed_days: float = 180.0,
    ) -> float:
        """Compute effective beta at query time with per-instance decay."""
        dc = self.decay_class.value if self.decay_class.value else "ephemeral"
        gamma = gamma_rates.get(dc, 0.98)
        beta = prior_beta
        for inst_id, count in self.failures.counts.items():
            ts_reg = self.last_obs_ts.get(inst_id)
            ts = ts_reg.timestamp if ts_reg else now
            elapsed = min((now - ts) / 86400.0, max_elapsed_days)
            beta += (gamma ** max(elapsed, 0.0)) * count
        return max(beta, 1.0)

    def query_confidence(
        self,
        now: float,
        gamma_rates: dict[str, float],
        prior_alpha: float,
        prior_beta: float,
        **kwargs: Any,
    ) -> float:
        """Posterior mean: alpha / (alpha + beta)."""
        a = self.query_alpha(
            now, gamma_rates=gamma_rates, prior_alpha=prior_alpha, **kwargs,
        )
        b = self.query_beta(
            now, gamma_rates=gamma_rates, prior_beta=prior_beta, **kwargs,
        )
        return a / (a + b)


__all__ = [
    "GCounter",
    "GSet",
    "LWWRegister",
    "ObservationCRDT",
]
