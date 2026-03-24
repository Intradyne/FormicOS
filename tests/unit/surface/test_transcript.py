"""Tests for transcript builder (Wave 20 Track A)."""

from __future__ import annotations

import pytest

from formicos.core.types import CasteSlot, InputSource, SubcasteTier
from formicos.surface.projections import (
    AgentProjection,
    ColonyProjection,
    RoundProjection,
)
from formicos.surface.transcript import build_transcript


def _make_colony(
    *,
    status: str = "completed",
    rounds: int = 2,
    with_redirect: bool = False,
) -> ColonyProjection:
    colony = ColonyProjection(
        id="colony-abc",
        thread_id="main",
        workspace_id="default",
        task="Write a haiku about ants",
        active_goal="Write a haiku about ants",
        status=status,
        round_number=rounds,
        display_name="Ant Haiku",
        quality_score=0.82,
        skills_extracted=1,
        cost=0.005,
        castes=[CasteSlot(caste="coder", tier=SubcasteTier.standard, count=2)],
        model_assignments={"coder": "llama-cpp/gpt-4"},
    )
    colony.agents["agent-1"] = AgentProjection(
        id="agent-1", caste="coder", model="llama-cpp/gpt-4",
    )
    for r in range(1, rounds + 1):
        rp = RoundProjection(
            round_number=r,
            convergence=0.5 * r,
            cost=0.002,
        )
        rp.agent_outputs["agent-1"] = f"Round {r} output about ants."
        rp.tool_calls["agent-1"] = ["memory_search"] if r == 1 else []
        colony.round_records.append(rp)

    if with_redirect:
        colony.active_goal = "Write a poem about butterflies"
        colony.redirect_history.append({
            "redirect_index": 0,
            "new_goal": "Write a poem about butterflies",
            "reason": "Topic change",
            "trigger": "queen_inspection",
            "round": 1,
            "timestamp": "2026-01-01T00:00:00+00:00",
        })

    return colony


class TestBuildTranscript:
    def test_basic_fields(self) -> None:
        colony = _make_colony()
        t = build_transcript(colony)
        assert t["colony_id"] == "colony-abc"
        assert t["display_name"] == "Ant Haiku"
        assert t["original_task"] == "Write a haiku about ants"
        assert t["active_goal"] == "Write a haiku about ants"
        assert t["status"] == "completed"
        assert t["quality_score"] == 0.82
        assert t["skills_extracted"] == 1
        assert t["cost"] == 0.005
        assert t["rounds_completed"] == 2

    def test_round_summaries(self) -> None:
        colony = _make_colony(rounds=2)
        t = build_transcript(colony)
        assert len(t["round_summaries"]) == 2
        r1 = t["round_summaries"][0]
        assert r1["round"] == 1
        assert len(r1["agents"]) == 1
        assert r1["agents"][0]["caste"] == "coder"
        assert r1["agents"][0]["tool_calls"] == ["memory_search"]
        r2 = t["round_summaries"][1]
        assert r2["agents"][0]["tool_calls"] == []

    def test_team_composition(self) -> None:
        colony = _make_colony()
        t = build_transcript(colony)
        assert len(t["team"]) == 1
        assert t["team"][0]["caste"] == "coder"
        assert t["team"][0]["tier"] == "standard"
        assert t["team"][0]["count"] == 2
        assert t["team"][0]["model"] == "llama-cpp/gpt-4"

    def test_input_sources_default_and_passthrough(self) -> None:
        colony = _make_colony()
        assert build_transcript(colony)["input_sources"] == []

        colony.input_sources = [InputSource(type="colony", colony_id="col-prev", summary="prior result")]  # type: ignore[attr-defined]
        t = build_transcript(colony)
        assert len(t["input_sources"]) == 1
        assert t["input_sources"][0].colony_id == "col-prev"

    def test_final_output(self) -> None:
        colony = _make_colony(rounds=2)
        t = build_transcript(colony)
        assert "Round 2 output" in t["final_output"]

    def test_redirect_history_present(self) -> None:
        colony = _make_colony(with_redirect=True)
        t = build_transcript(colony)
        assert t["active_goal"] == "Write a poem about butterflies"
        assert t["original_task"] == "Write a haiku about ants"
        assert len(t["redirect_history"]) == 1
        assert t["redirect_history"][0]["trigger"] == "queen_inspection"

    def test_running_colony(self) -> None:
        colony = _make_colony(status="running", rounds=1)
        t = build_transcript(colony)
        assert t["status"] == "running"
        assert len(t["round_summaries"]) == 1

    def test_failed_colony(self) -> None:
        colony = _make_colony(status="failed", rounds=0)
        colony.round_records.clear()
        t = build_transcript(colony)
        assert t["status"] == "failed"
        assert t["round_summaries"] == []
        assert t["final_output"] == ""

    def test_killed_colony(self) -> None:
        colony = _make_colony(status="killed", rounds=1)
        t = build_transcript(colony)
        assert t["status"] == "killed"

    def test_display_name_fallback(self) -> None:
        colony = _make_colony()
        colony.display_name = None
        t = build_transcript(colony)
        assert t["display_name"] == "colony-abc"

    def test_no_agents_graceful(self) -> None:
        colony = ColonyProjection(
            id="empty", thread_id="t", workspace_id="ws",
            task="nothing", status="completed",
        )
        t = build_transcript(colony)
        assert t["team"] == []
        assert t["round_summaries"] == []
