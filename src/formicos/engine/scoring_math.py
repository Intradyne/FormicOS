"""Shared exploration-confidence math for retrieval scoring (Wave 41 A2).

Unifies the exploration term used by both:
  - knowledge_catalog.py (Thompson Sampling — surface-layer retrieval)
  - context.py (UCB exploration bonus — engine-layer skill retrieval)

Both operate on the same Beta(alpha, beta) confidence substrate but
previously used unrelated exploration strategies. This module provides
a single ``exploration_score`` function that both paths now call.

Design: Thompson Sampling remains the primary mechanism (it is the
system of record per CLAUDE.md). The UCB term is folded in as an
optional uncertainty bonus that rewards under-explored entries,
controlled by a weight parameter so callers can dial it up or down.

Wave 57 audit: ``FORMICOS_DETERMINISTIC_SCORING=1`` replaces stochastic
Thompson draws with the Beta expected value ``alpha/(alpha+beta)``.
Use for eval to eliminate the noise floor that makes composite ranking
degenerate to "semantic + random". Production keeps stochastic draws
for exploration.
"""

from __future__ import annotations

import math
import os
import random

_DETERMINISTIC = os.environ.get("FORMICOS_DETERMINISTIC_SCORING", "") == "1"


def exploration_score(
    alpha: float,
    beta: float,
    *,
    total_observations: int = 1,
    ucb_weight: float = 0.0,
) -> float:
    """Unified exploration-confidence score from Beta(alpha, beta).

    Returns a value in [0, 1] combining Thompson Sampling with an
    optional UCB uncertainty bonus.

    Parameters
    ----------
    alpha, beta:
        Beta distribution parameters (conf_alpha, conf_beta).
    total_observations:
        Global observation count (e.g. total colonies). Only used
        when ``ucb_weight > 0`` to compute the UCB exploration term.
    ucb_weight:
        How much UCB exploration bonus to blend in. 0.0 = pure Thompson
        Sampling (default, used by knowledge_catalog). Positive values
        add an uncertainty bonus for under-explored entries (used by
        context.py skill retrieval).
    """
    safe_alpha = max(alpha, 0.1)
    safe_beta = max(beta, 0.1)

    # Thompson Sampling: stochastic draw (production) or expected value (eval)
    if _DETERMINISTIC:
        ts_draw = safe_alpha / (safe_alpha + safe_beta)
    else:
        ts_draw = random.betavariate(safe_alpha, safe_beta)

    if ucb_weight <= 0.0 or total_observations <= 0:
        return ts_draw

    # UCB uncertainty bonus: sqrt(log(N) / n_obs)
    n_obs = max(safe_alpha + safe_beta - 2.0, 1.0)
    big_n = max(total_observations, 1)
    ucb_bonus = math.sqrt(math.log(big_n) / n_obs)

    # Blend: Thompson draw + weighted UCB bonus, clamped to [0, 1]
    return min(ts_draw + ucb_weight * ucb_bonus, 1.0)


__all__ = ["exploration_score"]
