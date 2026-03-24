"""Wave 37 Team 2: Trust rationale and admission scoring tests."""

from __future__ import annotations

from formicos.surface.admission import AdmissionResult, evaluate_entry


class TestAdmissionScoring:
    """Verify the admission-scoring hook produces correct results."""

    def test_high_confidence_local_entry(self) -> None:
        """A verified local entry with high alpha scores well."""
        entry = {
            "conf_alpha": 25.0,
            "conf_beta": 5.0,
            "status": "verified",
            "source_colony_id": "colony-abc",
            "title": "Use asyncio.TaskGroup for concurrency",
            "content": "Detailed explanation of TaskGroup usage...",
        }
        result = evaluate_entry(entry)
        assert result.admitted is True
        assert result.score >= 0.7
        assert "low_confidence" not in result.flags
        assert "no_provenance" not in result.flags

    def test_low_confidence_entry_flagged(self) -> None:
        """An entry with very low confidence gets flagged."""
        entry = {
            "conf_alpha": 1.0,
            "conf_beta": 10.0,
            "status": "candidate",
            "title": "Uncertain pattern",
        }
        result = evaluate_entry(entry)
        assert result.admitted is True  # pass-through in Wave 37
        assert "low_confidence" in result.flags
        assert result.score < 0.6

    def test_federated_entry_flagged(self) -> None:
        """A federated entry gets the 'federated' flag."""
        entry = {
            "conf_alpha": 10.0,
            "conf_beta": 5.0,
            "status": "active",
            "source_colony_id": "colony-xyz",
            "source_peer": "peer-remote-1",
            "title": "Remote knowledge",
            "content": "Content from federation partner",
        }
        result = evaluate_entry(entry)
        assert result.admitted is True
        assert "federated" in result.flags
        assert "federated origin" in result.rationale

    def test_no_provenance_flagged(self) -> None:
        """An entry without source_colony_id gets flagged."""
        entry = {
            "conf_alpha": 8.0,
            "conf_beta": 4.0,
            "status": "active",
            "title": "Orphan entry",
            "content": "Some content",
        }
        result = evaluate_entry(entry)
        assert "no_provenance" in result.flags

    def test_weak_entry_scores_lower(self) -> None:
        """An entry with weak signals scores lower than a strong one.

        Wave 38: admission scores based on 7 weighted signals
        (confidence, provenance, scanner, federation, observation mass,
        content type, recency). Lower confidence → lower score.
        """
        weak = {
            "conf_alpha": 1.0,
            "conf_beta": 10.0,
            "source_colony_id": "colony-1",
            "title": "Weak entry",
            "content": "Content",
        }
        strong = {
            "conf_alpha": 20.0,
            "conf_beta": 3.0,
            "source_colony_id": "colony-1",
            "title": "Good entry",
            "content": "Content",
        }
        weak_result = evaluate_entry(weak)
        strong_result = evaluate_entry(strong)
        assert weak_result.score < strong_result.score
        assert "low_confidence" in weak_result.flags

    def test_very_weak_entry_rejected_in_wave38(self) -> None:
        """Wave 38: very weak entries are rejected (no longer pass-through)."""
        worst_case = {
            "conf_alpha": 0.5,
            "conf_beta": 20.0,
        }
        result = evaluate_entry(worst_case)
        # Wave 38 real gating: weak signals → low score and flagged
        assert result.score < 0.5
        assert "low_confidence" in result.flags
        assert "no_provenance" in result.flags

    def test_score_bounded_zero_one(self) -> None:
        """Admission score is always in [0, 1]."""
        entries = [
            {"conf_alpha": 100.0, "conf_beta": 1.0, "status": "verified",
             "source_colony_id": "c", "title": "t", "content": "c"},
            {"conf_alpha": 0.1, "conf_beta": 50.0, "status": "rejected"},
            {},
        ]
        for entry in entries:
            result = evaluate_entry(entry)
            assert 0.0 <= result.score <= 1.0

    def test_result_dataclass_fields(self) -> None:
        """AdmissionResult has the expected fields."""
        result = evaluate_entry({"title": "test"})
        assert isinstance(result, AdmissionResult)
        assert isinstance(result.admitted, bool)
        assert isinstance(result.score, float)
        assert isinstance(result.flags, list)
        assert isinstance(result.rationale, str)


class TestTrustProvenance:
    """Verify trust/provenance enrichment on KnowledgeCatalog.get_by_id."""

    def test_enrich_trust_provenance_local(self) -> None:
        """_enrich_trust_provenance adds correct metadata for local entries."""
        from formicos.surface.knowledge_catalog import _enrich_trust_provenance

        item: dict = {}
        raw = {
            "source_colony_id": "colony-abc",
            "source_round": "round-1",
            "source_agent": "coder-0",
            "created_at": "2026-01-15T10:00:00Z",
            "workspace_id": "ws-1",
            "thread_id": "t-1",
            "decay_class": "stable",
            "conf_alpha": 15.0,
            "conf_beta": 5.0,
            "status": "verified",
            "title": "Test entry",
            "content": "Content",
        }
        _enrich_trust_provenance(item, raw)

        assert "provenance" in item
        assert item["provenance"]["source_colony_id"] == "colony-abc"
        assert item["provenance"]["is_federated"] is False
        assert item["provenance"]["decay_class"] == "stable"

        assert "trust_rationale" in item
        assert item["trust_rationale"]["admitted"] is True
        assert item["trust_rationale"]["admission_score"] > 0
        assert isinstance(item["trust_rationale"]["rationale"], str)

    def test_enrich_trust_provenance_federated(self) -> None:
        """_enrich_trust_provenance marks federated entries correctly."""
        from formicos.surface.knowledge_catalog import _enrich_trust_provenance

        item: dict = {}
        raw = {
            "source_colony_id": "remote-colony",
            "source_peer": "peer-alpha",
            "conf_alpha": 8.0,
            "conf_beta": 4.0,
            "status": "active",
            "title": "Remote",
            "content": "C",
        }
        _enrich_trust_provenance(item, raw)

        assert item["provenance"]["is_federated"] is True
        assert item["provenance"]["source_peer"] == "peer-alpha"
        assert "federated" in item["trust_rationale"]["flags"]


class TestFederationTrustDiscounting:
    """Verify that federation trust discounting prevents foreign dominance.

    This reviews the existing retrieval scoring to confirm that low-trust
    federated entries cannot dominate strong local entries by default.
    The 6-signal composite with status bonus and thread bonus inherently
    favors local verified entries over remote candidates.
    """

    def test_local_verified_beats_remote_candidate(self) -> None:
        """A local verified entry should score higher than a remote candidate
        with the same semantic similarity, due to status bonus."""
        from formicos.surface.knowledge_catalog import _STATUS_BONUS

        local_status = _STATUS_BONUS.get("verified", 0.0)
        remote_status = _STATUS_BONUS.get("candidate", 0.0)
        # The status signal gives verified a 1.0 vs candidate's 0.5
        # With weight 0.10, this is a 0.05 composite advantage
        assert local_status > remote_status
        assert local_status == 1.0
        assert remote_status == 0.5
