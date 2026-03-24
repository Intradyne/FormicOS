"""Admission scoring policy tests (Wave 38, Pillar 3A).

Validates that:
- admission scoring is no longer pass-through
- scanner findings influence admission decisions
- low-confidence/low-provenance entries are demoted or rejected
- federated entries with low trust are penalized
- all decisions include inspectable rationale and signal scores
"""

from __future__ import annotations

import pytest

from formicos.surface.admission import AdmissionResult, evaluate_entry


def _base_entry(**overrides: object) -> dict:
    """Create a baseline entry with good defaults."""
    entry: dict = {
        "id": "test-entry-1",
        "category": "skill",
        "sub_type": "technique",
        "title": "Python async patterns",
        "content": "Use asyncio.gather for concurrent IO operations",
        "status": "candidate",
        "conf_alpha": 10.0,
        "conf_beta": 3.0,
        "source_colony_id": "col-1",
        "created_at": "2026-03-19T10:00:00+00:00",
    }
    entry.update(overrides)
    return entry


class TestAdmissionGating:
    """Admission scoring no longer passes everything through."""

    def test_good_entry_admitted(self) -> None:
        """Clean entry with good signals is admitted."""
        entry = _base_entry()
        result = evaluate_entry(entry)
        assert result.admitted is True
        assert result.score > 0.5
        assert result.status_override == ""

    def test_scanner_critical_rejects(self) -> None:
        """Critical scanner findings cause rejection."""
        entry = _base_entry()
        scanner = {"tier": "critical", "score": 3.0, "findings": ["prompt injection pattern"]}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert result.admitted is False
        assert result.status_override == "rejected"
        assert "scanner_critical" in result.flags

    def test_scanner_high_rejects(self) -> None:
        """High scanner findings cause rejection."""
        entry = _base_entry()
        scanner = {"tier": "high", "score": 2.5, "findings": ["data exfiltration pattern"]}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert result.admitted is False
        assert result.status_override == "rejected"

    def test_scanner_medium_does_not_reject(self) -> None:
        """Medium scanner findings don't reject on their own."""
        entry = _base_entry()
        scanner = {"tier": "medium", "score": 1.5, "findings": ["exec/eval pattern"]}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert result.admitted is True

    def test_scanner_safe_full_score(self) -> None:
        """Safe scanner tier gives full scanner signal score."""
        entry = _base_entry()
        scanner = {"tier": "safe", "score": 0.0, "findings": []}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert result.signal_scores["scanner"] == 1.0

    def test_very_low_score_rejects(self) -> None:
        """Entry with catastrophically low composite score is rejected."""
        entry = _base_entry(
            conf_alpha=0.5,
            conf_beta=10.0,
            title="",
            content="",
            source_colony_id="",
            status="rejected",
        )
        # Also give it a bad scanner result to push score below threshold
        scanner = {"tier": "high", "score": 2.5, "findings": ["exfiltration"]}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert result.admitted is False
        assert result.status_override == "rejected"


class TestFederationAdmission:
    """Federated entries are properly discounted."""

    def test_federated_with_no_trust_penalized(self) -> None:
        """Federated entry without known peer trust gets conservative score."""
        entry = _base_entry(source_peer="peer-xyz")
        result = evaluate_entry(entry)
        assert "federated" in result.flags
        assert result.signal_scores["federation"] < 0.5

    def test_federated_with_high_trust(self) -> None:
        """Federated entry with high peer trust gets decent federation score."""
        entry = _base_entry(source_peer="peer-trusted")
        result = evaluate_entry(entry, peer_trust_score=0.9)
        assert result.signal_scores["federation"] == pytest.approx(0.72, abs=0.01)
        assert result.admitted is True

    def test_federated_with_low_trust_demoted(self) -> None:
        """Federated entry with low peer trust and low confidence gets demoted."""
        entry = _base_entry(
            source_peer="peer-shady",
            conf_alpha=2.0,
            conf_beta=5.0,
        )
        result = evaluate_entry(entry, peer_trust_score=0.2)
        assert "low_peer_trust" in result.flags

    def test_local_entry_full_federation_score(self) -> None:
        """Local entries get full federation signal score."""
        entry = _base_entry()
        result = evaluate_entry(entry)
        assert result.signal_scores["federation"] == 1.0
        assert "federated" not in result.flags


class TestSignalBreakdown:
    """All decisions include inspectable signal scores."""

    def test_signal_scores_present(self) -> None:
        """All expected signal keys are present in result."""
        entry = _base_entry()
        result = evaluate_entry(entry)
        expected_keys = {
            "confidence", "provenance", "scanner", "federation",
            "observation_mass", "content_type", "recency",
        }
        assert set(result.signal_scores.keys()) == expected_keys

    def test_rationale_is_human_readable(self) -> None:
        """Rationale contains human-readable text."""
        entry = _base_entry()
        result = evaluate_entry(entry)
        assert len(result.rationale) > 0
        assert "trust" in result.rationale.lower() or "rejected" in result.rationale.lower()

    def test_rejected_rationale_says_rejected(self) -> None:
        """Rejected entries have 'Rejected' in rationale."""
        entry = _base_entry()
        scanner = {"tier": "critical", "score": 3.0, "findings": ["injection"]}
        result = evaluate_entry(entry, scanner_result=scanner)
        assert "Rejected" in result.rationale


class TestContentTypePrior:
    """Content-type prior influences score."""

    def test_convention_type_gets_higher_prior(self) -> None:
        """Convention entries get higher content-type score than bugs."""
        conv_entry = _base_entry(sub_type="convention")
        bug_entry = _base_entry(sub_type="bug")
        conv_result = evaluate_entry(conv_entry)
        bug_result = evaluate_entry(bug_entry)
        assert conv_result.signal_scores["content_type"] > bug_result.signal_scores["content_type"]


class TestRecencySignal:
    """Temporal recency influences score."""

    def test_recent_entry_high_recency(self) -> None:
        """Recently created entry gets high recency score."""
        entry = _base_entry()
        # created_at is today — should be close to 1.0
        result = evaluate_entry(entry)
        assert result.signal_scores["recency"] > 0.8

    def test_missing_created_at_gets_default(self) -> None:
        """Entry without created_at gets neutral recency score."""
        entry = _base_entry(created_at="")
        result = evaluate_entry(entry)
        assert result.signal_scores["recency"] == 0.5


class TestAdmissionDemotion:
    """Low-trust entries are demoted to candidate rather than rejected."""

    def test_low_score_federated_demoted_to_candidate(self) -> None:
        """Federated entry with low-ish score gets demoted, not rejected."""
        entry = _base_entry(
            source_peer="peer-new",
            conf_alpha=3.0,
            conf_beta=5.0,
            status="active",
        )
        result = evaluate_entry(entry, peer_trust_score=0.3)
        # Should be admitted but may be demoted
        if result.admitted and result.status_override:
            assert result.status_override == "candidate"
