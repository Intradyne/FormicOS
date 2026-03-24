"""Wave 48 Team 1: Colony audit Forager enrichment tests.

Covers:
- ForageCycleSummary preserves colony_id and thread_id from ForageRequested
- build_colony_audit_view marks Forager-sourced knowledge entries
- Provenance fields included when available
- Linked forage cycles appear in audit view
- Backward compatible: works without store argument
"""

from __future__ import annotations

from typing import Any

import pytest

from formicos.surface.projections import (
    ColonyProjection,
    ForageCycleSummary,
    ProjectionStore,
    WorkspaceProjection,
    build_colony_audit_view,
)


def _make_colony() -> ColonyProjection:
    """Create a minimal colony projection for testing."""
    return ColonyProjection(
        id="col-test",
        thread_id="thread-1",
        workspace_id="ws-1",
        task="Research auth patterns",
        status="completed",
        round_number=3,
        max_rounds=10,
        cost=0.50,
        quality_score=0.8,
        knowledge_accesses=[
            {
                "round": 1,
                "access_mode": "tool_search",
                "items": [
                    {
                        "id": "mem-normal",
                        "title": "Normal entry",
                        "source_system": "local",
                        "canonical_type": "skill",
                        "confidence": 0.8,
                    },
                    {
                        "id": "mem-forager",
                        "title": "Forager-sourced entry",
                        "source_system": "forager",
                        "canonical_type": "skill",
                        "confidence": 0.6,
                    },
                ],
            },
        ],
    )


class TestForageCycleSummaryLinkage:
    """Verify ForageCycleSummary carries colony_id and thread_id."""

    def test_summary_has_linkage_fields(self) -> None:
        summary = ForageCycleSummary(
            forage_request_seq=42,
            mode="reactive",
            reason="knowledge gap",
            colony_id="col-test",
            thread_id="thread-1",
            gap_domain="python",
            gap_query="authentication patterns",
        )
        assert summary.colony_id == "col-test"
        assert summary.thread_id == "thread-1"
        assert summary.gap_domain == "python"
        assert summary.gap_query == "authentication patterns"

    def test_summary_defaults_empty(self) -> None:
        summary = ForageCycleSummary(
            forage_request_seq=1, mode="proactive", reason="stale",
        )
        assert summary.colony_id == ""
        assert summary.thread_id == ""
        assert summary.gap_domain == ""
        assert summary.gap_query == ""


class TestAuditViewForagerAttribution:
    """Verify build_colony_audit_view marks Forager-sourced knowledge."""

    def test_backward_compatible_without_store(self) -> None:
        colony = _make_colony()
        audit = build_colony_audit_view(colony)
        # Should work without store — no forager_sourced field expected
        assert "knowledge_used" in audit
        assert len(audit["knowledge_used"]) == 2

    def test_forager_sourced_marked_with_store(self) -> None:
        colony = _make_colony()
        store = ProjectionStore()
        store.memory_entries["mem-forager"] = {
            "id": "mem-forager",
            "title": "Forager-sourced entry",
            "source_system": "forager",
            "web_source_url": "https://docs.python.org/auth",
            "web_source_domain": "docs.python.org",
            "credibility_score": 0.75,
        }
        store.memory_entries["mem-normal"] = {
            "id": "mem-normal",
            "title": "Normal entry",
            "source_system": "local",
        }

        audit = build_colony_audit_view(colony, store=store)
        knowledge = audit["knowledge_used"]
        assert len(knowledge) == 2

        forager_item = next(k for k in knowledge if k["id"] == "mem-forager")
        normal_item = next(k for k in knowledge if k["id"] == "mem-normal")

        assert forager_item["forager_sourced"] is True
        assert normal_item["forager_sourced"] is False

    def test_provenance_fields_present(self) -> None:
        colony = _make_colony()
        store = ProjectionStore()
        store.memory_entries["mem-forager"] = {
            "id": "mem-forager",
            "source_system": "forager",
            "web_source_url": "https://example.com/article",
            "web_source_domain": "example.com",
            "credibility_score": 0.65,
        }

        audit = build_colony_audit_view(colony, store=store)
        forager_item = next(
            k for k in audit["knowledge_used"] if k["id"] == "mem-forager"
        )
        assert "provenance" in forager_item
        prov = forager_item["provenance"]
        assert prov["source_url"] == "https://example.com/article"
        assert prov["source_domain"] == "example.com"
        assert prov["source_credibility"] == 0.65

    def test_linked_forage_cycles_in_audit(self) -> None:
        colony = _make_colony()
        store = ProjectionStore()
        store.forage_cycles["ws-1"] = [
            ForageCycleSummary(
                forage_request_seq=1,
                mode="reactive",
                reason="auth gap",
                colony_id="col-test",
                thread_id="thread-1",
                queries_issued=3,
                entries_admitted=1,
                gap_domain="python",
                gap_query="auth patterns",
                timestamp="2026-03-19T10:00:00",
            ),
            ForageCycleSummary(
                forage_request_seq=2,
                mode="proactive",
                reason="stale entry",
                colony_id="col-other",  # different colony
                thread_id="thread-1",
                timestamp="2026-03-19T10:01:00",
            ),
        ]

        audit = build_colony_audit_view(colony, store=store)
        assert "forage_cycles" in audit
        assert len(audit["forage_cycles"]) == 1
        cycle = audit["forage_cycles"][0]
        assert cycle["mode"] == "reactive"
        assert cycle["reason"] == "auth gap"
        assert cycle["gap_domain"] == "python"

    def test_no_forage_cycles_yields_empty_list(self) -> None:
        colony = _make_colony()
        store = ProjectionStore()
        audit = build_colony_audit_view(colony, store=store)
        assert audit["forage_cycles"] == []
