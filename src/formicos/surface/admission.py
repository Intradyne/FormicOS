"""Admission scoring for knowledge entry ingestion (Wave 38).

Real gating policy that combines scanner findings, confidence, provenance,
federation origin, content-type prior, temporal recency, and observation mass
to decide whether an entry should be admitted, demoted, or rejected.

The policy is conservative: suspicious or very low-value entries are blocked
or status-demoted. Every decision includes an inspectable rationale.

Called at:
  1. Ingestion time (colony_manager) — gates entry creation
  2. Retrieval time (KnowledgeCatalog) — annotates already-ingested entries
"""

from __future__ import annotations

import math
import time as _time_mod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AdmissionResult:
    """Result of evaluating a knowledge entry for admission."""

    admitted: bool
    score: float  # [0.0, 1.0] — higher is more trustworthy
    status_override: str  # "" = no override, or "rejected" / "candidate"
    flags: list[str]  # human-readable flags
    rationale: str  # one-line explanation
    signal_scores: dict[str, float]  # per-signal breakdown for inspectability


# Signal weights (sum to 1.0)
_WEIGHTS: dict[str, float] = {
    "confidence": 0.20,
    "provenance": 0.15,
    "scanner": 0.25,
    "federation": 0.10,
    "observation_mass": 0.10,
    "content_type": 0.10,
    "recency": 0.10,
}

# Content-type priors: some entry types are inherently more trustworthy
_CONTENT_TYPE_PRIOR: dict[str, float] = {
    "skill": 0.7,
    "experience": 0.6,
    "technique": 0.75,
    "pattern": 0.7,
    "anti_pattern": 0.65,
    "decision": 0.6,
    "convention": 0.8,
    "learning": 0.5,
    "bug": 0.55,
}

# Scanner tier → score mapping (inverted: safe=1.0, critical=0.0)
_SCANNER_TIER_SCORE: dict[str, float] = {
    "safe": 1.0,
    "low": 0.7,
    "medium": 0.4,
    "high": 0.1,
    "critical": 0.0,
    "pending": 0.6,  # not yet scanned
}


def evaluate_entry(
    entry: dict[str, Any],
    *,
    scanner_result: dict[str, Any] | None = None,
    peer_trust_score: float | None = None,
) -> AdmissionResult:
    """Evaluate a knowledge entry's admission worthiness.

    Wave 38: real gating policy. Suspicious or very low-value entries
    are rejected or demoted. Decision is explainable via signal_scores.

    Args:
        entry: The knowledge entry dict.
        scanner_result: Output of memory_scanner.scan_entry() if available.
        peer_trust_score: Peer trust score (0-1) for federated entries.
    """
    flags: list[str] = []
    signal_scores: dict[str, float] = {}

    # --- Signal 1: Bayesian confidence posterior mean ---
    alpha = float(entry.get("conf_alpha", entry.get("confidence", 0.5)))
    beta_val = float(entry.get("conf_beta", 1.0))
    posterior_mean = alpha / (alpha + beta_val) if alpha > 0 and beta_val > 0 else 0.5
    signal_scores["confidence"] = posterior_mean
    if posterior_mean < 0.3:
        flags.append("low_confidence")

    # --- Signal 2: Provenance completeness ---
    has_source = bool(entry.get("source_colony_id"))
    has_content = bool(entry.get("content") or entry.get("content_preview"))
    has_title = bool(entry.get("title"))
    provenance_score = sum([
        0.4 if has_source else 0.0,
        0.3 if has_content else 0.0,
        0.3 if has_title else 0.0,
    ])
    # Source credibility adjustment (Wave 45): forager entries carry a
    # credibility score from the domain tier system. Blend it into provenance
    # when present — authoritative sources boost, unknown sources penalize.
    forager_prov = entry.get("forager_provenance")
    if isinstance(forager_prov, dict):
        credibility = float(forager_prov.get("source_credibility", 0.5))
        # Blend: 60% structural provenance, 40% source credibility
        provenance_score = provenance_score * 0.6 + credibility * 0.4
        if credibility < 0.4:
            flags.append("low_source_credibility")
    signal_scores["provenance"] = provenance_score
    if not has_source:
        flags.append("no_provenance")

    # --- Signal 3: Scanner findings ---
    scan_tier = "pending"
    if scanner_result is not None:
        scan_tier = str(scanner_result.get("tier", "pending"))
    elif entry.get("scan_status"):
        scan_tier = str(entry["scan_status"])
    scanner_score = _SCANNER_TIER_SCORE.get(scan_tier, 0.5)
    signal_scores["scanner"] = scanner_score
    if scan_tier in ("high", "critical"):
        flags.append(f"scanner_{scan_tier}")
    if scanner_result and scanner_result.get("findings"):
        for finding in scanner_result["findings"][:3]:
            flags.append(f"scan:{finding}")

    # --- Signal 4: Federation origin + peer trust ---
    source_peer = entry.get("source_peer", "")
    is_federated = bool(source_peer)
    if is_federated:
        # Unknown peer gets conservative 0.3; known peers discounted by 0.8
        fed_score = peer_trust_score * 0.8 if peer_trust_score is not None else 0.3
        flags.append("federated")
        if fed_score < 0.3:
            flags.append("low_peer_trust")
    else:
        fed_score = 1.0  # local entries get full trust
    signal_scores["federation"] = fed_score

    # --- Signal 5: Observation mass ---
    raw_alpha = float(entry.get("conf_alpha", 5.0))
    raw_beta = float(entry.get("conf_beta", 5.0))
    total_obs = raw_alpha + raw_beta
    certainty = 1.0 - math.exp(-0.05 * total_obs) if total_obs > 0 else 0.0
    signal_scores["observation_mass"] = certainty
    if certainty < 0.2:
        flags.append("low_observation_mass")

    # --- Signal 6: Content-type prior ---
    entry_type = str(entry.get("entry_type", entry.get("category", "skill")))
    sub_type = str(entry.get("sub_type", ""))
    type_key = sub_type if sub_type in _CONTENT_TYPE_PRIOR else entry_type
    content_type_score = _CONTENT_TYPE_PRIOR.get(type_key, 0.5)
    signal_scores["content_type"] = content_type_score

    # --- Signal 7: Temporal recency ---
    recency_score = _compute_recency(entry.get("created_at", ""))
    signal_scores["recency"] = recency_score

    # --- Weighted composite ---
    composite = sum(
        _WEIGHTS[k] * signal_scores[k] for k in _WEIGHTS
    )
    composite = round(composite, 3)

    # --- Admission decision ---
    admitted, status_override = _admission_decision(
        composite, scan_tier, is_federated,
    )

    return AdmissionResult(
        admitted=admitted,
        score=composite,
        status_override=status_override,
        flags=flags,
        rationale=_build_rationale(composite, flags, is_federated, status_override),
        signal_scores=signal_scores,
    )


def _admission_decision(
    score: float,
    scan_tier: str,
    is_federated: bool,
) -> tuple[bool, str]:
    """Determine admission and status override.

    Returns (admitted, status_override).
    status_override is "" if no change, "rejected" or "candidate" otherwise.
    """
    # Hard reject: scanner found critical/high risk
    if scan_tier == "critical":
        return False, "rejected"
    if scan_tier == "high":
        return False, "rejected"

    # Hard reject: very low composite score
    if score < 0.25:
        return False, "rejected"

    # Soft demotion: federated with low trust
    if is_federated and score < 0.40:
        return True, "candidate"  # admitted but demoted to candidate

    # Soft demotion: low score but not catastrophic
    if score < 0.35:
        return True, "candidate"

    # Normal admission
    return True, ""


def _compute_recency(created_at: str) -> float:
    """Exponential decay with 90-day half-life. Returns [0, 1]."""
    if not created_at:
        return 0.5  # unknown recency
    try:
        ext_dt = datetime.fromisoformat(created_at)
        age_days = (_time_mod.time() - ext_dt.timestamp()) / 86400.0
    except (ValueError, TypeError):
        return 0.5
    return 2.0 ** (-age_days / 90.0)


def _build_rationale(
    score: float,
    flags: list[str],
    is_federated: bool,
    status_override: str,
) -> str:
    """Build a human-readable one-line rationale."""
    if status_override == "rejected":
        base = "Rejected"
    elif score >= 0.8:
        base = "High trust"
    elif score >= 0.6:
        base = "Moderate trust"
    elif score >= 0.4:
        base = "Low trust"
    else:
        base = "Minimal trust"

    parts = [base]
    if is_federated:
        parts.append("federated origin")
    if "scanner_critical" in flags:
        parts.append("critical security risk")
    elif "scanner_high" in flags:
        parts.append("high security risk")
    if "low_confidence" in flags:
        parts.append("low confidence")
    if "no_provenance" in flags:
        parts.append("missing provenance")
    if "low_peer_trust" in flags:
        parts.append("low peer trust")
    if "low_observation_mass" in flags:
        parts.append("few observations")

    return " — ".join(parts) if len(parts) > 1 else base


__all__ = ["AdmissionResult", "evaluate_entry"]
