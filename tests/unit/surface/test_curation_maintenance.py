"""Tests for curation maintenance handler (Wave 59 Track 3)."""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class _FakeProjections:
    memory_entries: dict[str, dict[str, Any]] = dataclasses.field(default_factory=dict)
    knowledge_entry_usage: dict[str, dict[str, Any]] = dataclasses.field(
        default_factory=dict,
    )


def _entry(
    eid: str,
    *,
    status: str = "verified",
    workspace_id: str = "ws-1",
    conf_alpha: float = 5.0,
    conf_beta: float = 5.0,
    content: str = "Some knowledge content that is long enough to pass validation.",
    title: str = "Test entry",
    domains: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": eid,
        "status": status,
        "workspace_id": workspace_id,
        "conf_alpha": conf_alpha,
        "conf_beta": conf_beta,
        "content": content,
        "title": title,
        "domains": domains or ["code_implementation"],
    }


def _select_candidates(
    proj: _FakeProjections, workspace_id: str,
) -> list[dict[str, Any]]:
    """Mirror the candidate selection logic from make_curation_handler."""
    candidates: list[dict[str, Any]] = []
    usage = getattr(proj, "knowledge_entry_usage", {})
    for eid, entry in proj.memory_entries.items():
        if entry.get("status") != "verified":
            continue
        if entry.get("workspace_id", "") != workspace_id:
            continue
        entry_usage = usage.get(eid, {})
        access_count = int(entry_usage.get("count", 0))
        if access_count < 5:
            continue
        alpha = float(entry.get("conf_alpha", 5.0))
        beta_val = float(entry.get("conf_beta", 5.0))
        denom = alpha + beta_val
        if denom <= 0:
            continue
        confidence = alpha / denom
        if confidence >= 0.65:
            continue
        candidates.append({
            **entry,
            "access_count": access_count,
            "confidence": confidence,
        })
        if len(candidates) >= 10:
            break
    return candidates


class TestCurationCandidateSelection:
    """Test the candidate selection logic (no LLM call needed)."""

    def test_selects_popular_low_conf(self) -> None:
        """Entry with access >= 5 and confidence < 0.65 is selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=5.0, conf_beta=5.0)},
            knowledge_entry_usage={"e1": {"count": 7, "last_accessed": "2026-03-23"}},
        )
        # confidence = 5/(5+5) = 0.50, access = 7 -> selected
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 1
        assert candidates[0]["id"] == "e1"

    def test_skips_low_access(self) -> None:
        """Entry with access < 5 is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=5.0, conf_beta=5.0)},
            knowledge_entry_usage={"e1": {"count": 2}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_skips_high_conf(self) -> None:
        """Entry with confidence >= 0.65 is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=7.0, conf_beta=3.0)},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        # confidence = 7/10 = 0.70 -> skipped
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_skips_wrong_workspace(self) -> None:
        """Entry from different workspace is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", workspace_id="ws-other")},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_skips_non_verified(self) -> None:
        """Entry with status != verified is not selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", status="candidate")},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0

    def test_respects_batch_limit(self) -> None:
        """Max 10 candidates selected."""
        entries = {}
        usage = {}
        for i in range(15):
            eid = f"e{i}"
            entries[eid] = _entry(eid)
            usage[eid] = {"count": 10}
        proj = _FakeProjections(memory_entries=entries, knowledge_entry_usage=usage)
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 10

    def test_boundary_access_count_exactly_5(self) -> None:
        """Entry with exactly 5 accesses is selected."""
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=5.0, conf_beta=5.0)},
            knowledge_entry_usage={"e1": {"count": 5}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 1

    def test_boundary_confidence_exactly_065(self) -> None:
        """Entry with confidence exactly 0.65 is NOT selected (>= threshold)."""
        # 13/20 = 0.65
        proj = _FakeProjections(
            memory_entries={"e1": _entry("e1", conf_alpha=13.0, conf_beta=7.0)},
            knowledge_entry_usage={"e1": {"count": 10}},
        )
        candidates = _select_candidates(proj, "ws-1")
        assert len(candidates) == 0
