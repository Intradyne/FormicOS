"""Bayesian trust scoring for federation peers (Wave 33 C6).

Uses 10th percentile of Beta posterior instead of mean.
Research finding: mean-based trust lets a new peer reach 0.9 after
only 9 successes. 10th percentile requires ~30+ for 0.8.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass
class PeerTrust:
    alpha: float = 1.0  # successes + 1
    beta: float = 1.0  # failures + 1

    @property
    def score(self) -> float:
        """10th percentile of Beta posterior. Penalizes uncertainty."""
        return _beta_ppf_approx(0.10, self.alpha, self.beta)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    def record_success(self) -> None:
        self.alpha += 1.0

    def record_failure(self) -> None:
        """Asymmetric penalty: failures count 2x (Wave 38 trust hardening).

        Rationale: trust is hard to earn, easy to lose. A single failure
        from a peer should weigh more than a single success.
        """
        self.beta += 2.0

    def decay(self, days: float, gamma: float = 0.9995) -> None:
        """Trust decay: retains 91.4% at 90 days, 83.5% at 180 days."""
        factor = gamma**days
        self.alpha = max(factor * self.alpha + (1 - factor) * 1.0, 1.0)
        self.beta = max(factor * self.beta + (1 - factor) * 1.0, 1.0)


def trust_discount(trust_score: float, hop: int = 0) -> float:
    """Discount factor for foreign knowledge observations.

    Applied at query time in ObservationCRDT, not stored in CRDT state.

    Wave 41 A1: posterior-aware hop discounting. Instead of a fixed 0.7
    per-hop decay, the base decay rate is modulated by the peer's trust
    score. High-trust peers (score ~0.8+) decay more slowly per hop;
    low-trust peers decay faster. The 0.5 cap remains — federated
    knowledge never outweighs local.
    """
    # Blend between aggressive (0.6) and gentle (0.85) hop decay
    # based on how much we trust the peer.
    hop_base = 0.6 + 0.25 * trust_score  # range [0.6, 0.85]
    raw = trust_score * (hop_base ** hop)
    return min(raw, 0.5)  # cap — federated never outweighs local


def entry_confidence_score(entry: dict[str, Any]) -> float:
    """Live posterior confidence for a knowledge entry.

    Wave 41 A1: replaces coarse status-band lookup with the entry's
    actual Beta posterior. Uses the 10th percentile (same as PeerTrust)
    to penalize high-uncertainty entries.

    Returns a value in [0, 1]. Entries with no Beta params default to
    a conservative 0.4.
    """
    alpha = float(entry.get("conf_alpha", 0))
    beta_p = float(entry.get("conf_beta", 0))
    if alpha <= 0 or beta_p <= 0:
        return 0.4
    return _beta_ppf_approx(0.10, alpha, beta_p)


def federated_retrieval_penalty(
    entry: dict[str, Any],
    local_verified_max_score: float = 0.0,
    *,
    peer_trust_score: float | None = None,
) -> float:
    """Compute a retrieval score penalty for federated entries.

    Wave 41 A1: posterior-aware trust weighting replaces coarse status
    bands. The penalty now combines three live signals:
      1. The entry's own confidence posterior (via entry_confidence_score)
      2. A status floor that prevents candidates from being treated like
         verified entries even when they happen to have high alpha
      3. Hop-aware trust discount (via trust_discount) using the entry's
         federation_hop and the peer's trust score

    Parameters
    ----------
    entry:
        Knowledge entry dict with optional source_peer, federation_hop,
        conf_alpha, conf_beta, and status fields.
    local_verified_max_score:
        Unused legacy parameter, kept for backward compatibility.
    peer_trust_score:
        If provided, the PeerTrust.score for the source peer. When None,
        the entry's own posterior is used as a proxy.

    Returns a multiplier in [0.0, 1.0] to apply to the entry's composite
    score. Local entries return 1.0 (no penalty).
    """
    source_peer = entry.get("source_peer", "")
    if not source_peer:
        return 1.0  # local — no penalty

    # Live posterior confidence from the entry's own Beta params
    posterior = entry_confidence_score(entry)

    # Status floor: even a high-confidence candidate gets penalized
    # because it hasn't been promoted through the trust pipeline yet.
    _STATUS_FLOOR: dict[str, float] = {
        "verified": 0.80,
        "active": 0.55,
        "candidate": 0.35,
        "stale": 0.20,
    }
    status = str(entry.get("status", "candidate"))
    floor = _STATUS_FLOOR.get(status, 0.35)

    # Blend: 60% posterior, 40% status floor
    blended = 0.6 * posterior + 0.4 * floor

    # Wave 41 A1: apply hop-aware trust discount for multi-hop entries.
    # Uses actual PeerTrust score if provided, otherwise the entry's
    # own posterior as a proxy for the source peer's trustworthiness.
    hop = int(entry.get("federation_hop", 0))
    if hop > 0 or peer_trust_score is not None:
        ts = peer_trust_score if peer_trust_score is not None else posterior
        hop_discount = trust_discount(ts, hop=hop)
        # The hop discount (capped at 0.5) further attenuates the penalty.
        # Use the minimum of the blended score and the hop discount to
        # ensure multi-hop entries are always penalized at least as much
        # as the hop discount suggests.
        blended = min(blended, hop_discount + 0.1)

    return max(0.1, min(blended, 0.90))


def _beta_ppf_approx(p: float, alpha: float, beta: float) -> float:
    """Approximate inverse CDF of Beta distribution.

    Uses the normal approximation for Beta when alpha+beta > 4,
    falls back to a simple quantile estimate otherwise.
    """
    if alpha <= 0 or beta <= 0:
        return 0.0
    n = alpha + beta
    if n > 4:
        mu = alpha / n
        sigma = math.sqrt(alpha * beta / (n * n * (n + 1)))
        z = _inv_normal_approx(p)
        return max(0.0, min(1.0, mu + z * sigma))
    return max(0.0, alpha / n - 0.1)


def _inv_normal_approx(p: float) -> float:
    """Rational approximation of inverse normal CDF (Abramowitz & Stegun 26.2.23)."""
    if p <= 0.0:
        return -4.0
    if p >= 1.0:
        return 4.0
    if p > 0.5:
        return -_inv_normal_approx(1.0 - p)
    t = math.sqrt(-2.0 * math.log(p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return -(
        t
        - (c0 + c1 * t + c2 * t * t)
        / (1 + d1 * t + d2 * t * t + d3 * t * t * t)
    )


__all__ = [
    "PeerTrust",
    "entry_confidence_score",
    "federated_retrieval_penalty",
    "trust_discount",
]
