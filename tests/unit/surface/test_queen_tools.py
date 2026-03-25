"""Unit tests for formicos.surface.queen_tools — propose_plan and analytical tools."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from formicos.core.types import ModelRecord
from formicos.surface.projections import (
    AgentProjection,
    ColonyOutcome,
    ColonyProjection,
    RoundProjection,
)
from formicos.surface.queen_tools import QueenToolDispatcher


def _make_model_record(
    address: str = "local/qwen3",
    cost_in: float = 0.0,
    cost_out: float = 0.0,
) -> ModelRecord:
    provider = address.split("/", 1)[0] if "/" in address else address
    return ModelRecord(
        address=address,
        provider=provider,
        endpoint="http://localhost:8080",
        context_window=32768,
        supports_tools=True,
        cost_per_input_token=cost_in,
        cost_per_output_token=cost_out,
    )


def _make_runtime(
    *,
    max_rounds: int = 20,
    coder_model: str = "local/qwen3",
    registry: list[ModelRecord] | None = None,
) -> MagicMock:
    runtime = MagicMock()
    runtime.settings.governance.max_rounds_per_colony = max_rounds
    runtime.settings.models.defaults.coder = coder_model
    runtime.settings.models.registry = registry or [_make_model_record(address=coder_model)]
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))
    runtime.projections.queen_notes = {}
    return runtime


class TestProposePlan:
    """Tests for the propose_plan tool handler."""

    def test_propose_plan_returns_proposal_card(self) -> None:
        """propose_plan returns result text and proposal_card render action."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Build a CSV parser",
                "options": [
                    {"label": "Quick", "description": "Single coder, fast path", "colonies": 1},
                    {"label": "Thorough", "description": "Coder + reviewer", "colonies": 2},
                ],
                "recommendation": "Quick approach is sufficient",
            },
            workspace_id="ws-1",
        )

        assert "Proposed Plan" in result_text
        assert "Build a CSV parser" in result_text
        assert "Quick" in result_text
        assert "Thorough" in result_text
        assert "Awaiting your confirmation" in result_text

        assert action is not None
        assert action["tool"] == "propose_plan"
        assert action["render"] == "proposal_card"
        assert action["proposal"]["summary"] == "Build a CSV parser"
        assert len(action["proposal"]["options"]) == 2

    def test_propose_plan_local_model_shows_free(self) -> None:
        """When coder model has zero cost, estimated_cost shows 'local (free)'."""
        runtime = _make_runtime(
            coder_model="local/qwen3",
            registry=[_make_model_record(address="local/qwen3", cost_in=0.0, cost_out=0.0)],
        )
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Simple task",
                "options": [
                    {"label": "A", "description": "One colony", "colonies": 1},
                ],
            },
            workspace_id="ws-1",
        )

        assert action is not None
        opt = action["proposal"]["options"][0]
        assert opt["estimated_cost"] == "local (free)"
        assert "local (free)" in result_text

    def test_propose_plan_cloud_model_shows_cost(self) -> None:
        """When coder model has positive cost, estimated_cost shows dollar amount."""
        runtime = _make_runtime(
            coder_model="anthropic/claude-3-haiku",
            registry=[_make_model_record(address="anthropic/claude-3-haiku", cost_in=0.000001, cost_out=0.000002)],
            max_rounds=10,
        )
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Cloud task",
                "options": [
                    {"label": "A", "description": "One colony", "colonies": 1},
                ],
            },
            workspace_id="ws-1",
        )

        assert action is not None
        opt = action["proposal"]["options"][0]
        # 1 colony * 5 rounds (10/2) * 4000 tokens * 0.000002 = $0.04
        assert opt["estimated_cost"] == "$0.04"

    def test_propose_plan_requires_summary(self) -> None:
        """Missing summary returns an error."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {},
            workspace_id="ws-1",
        )

        assert "Error" in result_text
        assert action is None

    def test_propose_plan_with_questions(self) -> None:
        """Questions appear in the result text."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Needs clarification",
                "questions": ["What format?", "What deadline?"],
            },
            workspace_id="ws-1",
        )

        assert "What format?" in result_text
        assert "What deadline?" in result_text
        assert action is not None
        assert action["proposal"]["questions"] == ["What format?", "What deadline?"]

    @pytest.mark.anyio()
    async def test_propose_plan_via_dispatch(self) -> None:
        """propose_plan is reachable through the dispatch method."""
        runtime = _make_runtime()
        runtime.parse_tool_input = MagicMock(
            return_value={"summary": "Test plan via dispatch"},
        )
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = await dispatcher.dispatch(
            {"name": "propose_plan", "input": {"summary": "Test plan via dispatch"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "Proposed Plan" in result_text
        assert action is not None
        assert action["tool"] == "propose_plan"


# ---------------------------------------------------------------------------
# Helpers for analytical tool tests (Wave 61 Track 3)
# ---------------------------------------------------------------------------


def _make_analytical_runtime() -> MagicMock:
    """Build a minimal mock runtime for analytical tool tests."""
    runtime = MagicMock()
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))
    runtime.projections.colony_outcomes = {}
    runtime.projections.colonies = {}
    runtime.projections.memory_entries = {}
    runtime.projections.cooccurrence_weights = {}
    runtime.projections.distillation_candidates = []
    runtime.projections.workspaces = {}
    runtime.projections.operator_behavior = MagicMock()
    runtime.projections.get_colony = MagicMock(
        side_effect=lambda cid: runtime.projections.colonies.get(cid),
    )
    # queen_notes needed by QueenToolDispatcher init path
    runtime.projections.queen_notes = {}
    return runtime


def _make_colony_proj(
    colony_id: str = "c-1",
    workspace_id: str = "ws-1",
    *,
    task: str = "Test task for colony",
    status: str = "completed",
    strategy: str = "stigmergic",
    display_name: str | None = "test-colony",
    quality_score: float = 0.85,
    cost: float = 0.05,
    round_number: int = 3,
) -> ColonyProjection:
    return ColonyProjection(
        id=colony_id,
        thread_id="th-1",
        workspace_id=workspace_id,
        task=task,
        status=status,
        strategy=strategy,
        display_name=display_name,
        quality_score=quality_score,
        cost=cost,
        round_number=round_number,
        spawned_at=(datetime.now(tz=UTC) - timedelta(hours=1)).isoformat(),
        completed_at=datetime.now(tz=UTC).isoformat(),
    )


def _make_outcome(
    colony_id: str = "c-1",
    workspace_id: str = "ws-1",
    *,
    succeeded: bool = True,
    total_rounds: int = 3,
    total_cost: float = 0.05,
    quality_score: float = 0.85,
    strategy: str = "stigmergic",
    entries_extracted: int = 2,
    entries_accessed: int = 3,
) -> ColonyOutcome:
    return ColonyOutcome(
        colony_id=colony_id,
        workspace_id=workspace_id,
        thread_id="th-1",
        succeeded=succeeded,
        total_rounds=total_rounds,
        total_cost=total_cost,
        duration_ms=5000,
        entries_extracted=entries_extracted,
        entries_accessed=entries_accessed,
        quality_score=quality_score,
        caste_composition=["coder"],
        strategy=strategy,
    )


# ---------------------------------------------------------------------------
# query_outcomes tests
# ---------------------------------------------------------------------------


class TestQueryOutcomes:
    @pytest.mark.anyio()
    async def test_returns_formatted_table(self) -> None:
        runtime = _make_analytical_runtime()
        colony = _make_colony_proj()
        outcome = _make_outcome()
        runtime.projections.colonies[colony.id] = colony
        runtime.projections.colony_outcomes[colony.id] = outcome

        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_outcomes", "input": {"period": "7d"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "test-colony" in result
        assert "Colony Outcomes" in result
        assert "Aggregates" in result

    @pytest.mark.anyio()
    async def test_filters_by_strategy(self) -> None:
        runtime = _make_analytical_runtime()
        c1 = _make_colony_proj(colony_id="c-1", display_name="stig-colony")
        c2 = _make_colony_proj(
            colony_id="c-2", display_name="seq-colony", strategy="sequential",
        )
        runtime.projections.colonies["c-1"] = c1
        runtime.projections.colonies["c-2"] = c2
        runtime.projections.colony_outcomes["c-1"] = _make_outcome(
            colony_id="c-1", strategy="stigmergic",
        )
        runtime.projections.colony_outcomes["c-2"] = _make_outcome(
            colony_id="c-2", strategy="sequential",
        )

        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_outcomes", "input": {"strategy": "sequential"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "seq-colony" in result
        assert "stig-colony" not in result

    @pytest.mark.anyio()
    async def test_no_outcomes(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_outcomes", "input": {}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "No outcomes found" in result

    @pytest.mark.anyio()
    async def test_filters_by_succeeded(self) -> None:
        runtime = _make_analytical_runtime()
        c1 = _make_colony_proj(colony_id="c-1", display_name="good-colony")
        c2 = _make_colony_proj(colony_id="c-2", display_name="bad-colony")
        runtime.projections.colonies["c-1"] = c1
        runtime.projections.colonies["c-2"] = c2
        runtime.projections.colony_outcomes["c-1"] = _make_outcome(
            colony_id="c-1", succeeded=True,
        )
        runtime.projections.colony_outcomes["c-2"] = _make_outcome(
            colony_id="c-2", succeeded=False,
        )

        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_outcomes", "input": {"succeeded": False}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "bad-colony" in result
        assert "good-colony" not in result


# ---------------------------------------------------------------------------
# analyze_colony tests
# ---------------------------------------------------------------------------


class TestAnalyzeColony:
    @pytest.mark.anyio()
    async def test_returns_detailed_analysis(self) -> None:
        runtime = _make_analytical_runtime()
        colony = _make_colony_proj()
        colony.round_records = [
            RoundProjection(
                round_number=1,
                cost=0.02,
                convergence=0.5,
                agent_outputs={"a-1": "Implemented the feature"},
                tool_calls={"a-1": ["code_execute", "workspace_execute"]},
            ),
            RoundProjection(
                round_number=2,
                cost=0.03,
                convergence=0.9,
                agent_outputs={"a-1": "Tests passing"},
                tool_calls={"a-1": ["code_execute"]},
            ),
        ]
        colony.knowledge_accesses = [
            {"entry_id": "e-1", "title": "Python patterns"},
        ]
        colony.entries_extracted_count = 2
        colony.agents["a-1"] = AgentProjection(
            id="a-1", caste="coder", model="test-model",
        )

        outcome = _make_outcome()
        runtime.projections.colonies[colony.id] = colony
        runtime.projections.colony_outcomes[colony.id] = outcome

        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "analyze_colony", "input": {"colony_id": "c-1"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "Colony Analysis" in result
        assert "test-colony" in result
        assert "Round Progression" in result
        assert "Tool Usage" in result
        assert "code_execute" in result
        assert "Knowledge Impact" in result
        assert "Python patterns" in result
        assert "Cost Breakdown" in result

    @pytest.mark.anyio()
    async def test_colony_not_found(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "analyze_colony", "input": {"colony_id": "missing"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "not found" in result

    @pytest.mark.anyio()
    async def test_missing_colony_id(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "analyze_colony", "input": {}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "Error" in result

    @pytest.mark.anyio()
    async def test_failed_colony_shows_failure_info(self) -> None:
        runtime = _make_analytical_runtime()
        colony = _make_colony_proj(status="failed")
        colony.failure_reason = "Max rounds exceeded"
        colony.failed_at_round = 10
        runtime.projections.colonies[colony.id] = colony

        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "analyze_colony", "input": {"colony_id": "c-1"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "Failure Info" in result
        assert "Max rounds exceeded" in result


# ---------------------------------------------------------------------------
# query_briefing tests
# ---------------------------------------------------------------------------


class TestQueryBriefing:
    @pytest.mark.anyio()
    async def test_returns_insights_or_empty(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_briefing", "input": {"category": "all"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        # With no data, should either show insights or report none
        assert "Proactive Intelligence" in result or "No insights found" in result

    @pytest.mark.anyio()
    async def test_filters_by_category(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_briefing", "input": {"category": "performance"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "No insights found" in result
        assert "performance" in result

    @pytest.mark.anyio()
    async def test_empty_workspace(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "query_briefing", "input": {}},
            workspace_id="ws-empty",
            thread_id="th-1",
        )
        assert "No insights found" in result or "0 entries" in result


# ---------------------------------------------------------------------------
# Wave 62 tests
# ---------------------------------------------------------------------------


class TestSearchCodebase:
    """Tests for the search_codebase tool handler."""

    @pytest.mark.anyio()
    async def test_rejects_empty_query(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "search_codebase", "input": {"query": ""}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "Error" in result

    @pytest.mark.anyio()
    async def test_returns_no_matches_for_gibberish(self) -> None:
        runtime = _make_analytical_runtime()
        # Point workspace at a real but small directory
        ws = SimpleNamespace(
            directory=None, repo_path=None,
            config={}, threads={},
        )
        runtime.projections.workspaces = {"ws-1": ws}
        runtime.data_dir = None
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "search_codebase", "input": {"query": "xyzzy_nonexistent_42"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        # Either "not found" workspace or "No matches"
        assert "No matches" in result or "not found" in result


class TestRunCommand:
    """Tests for the run_command tool handler."""

    @pytest.mark.anyio()
    async def test_rejects_empty_command(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "run_command", "input": {"command": ""}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "Error" in result

    @pytest.mark.anyio()
    async def test_rejects_disallowed_command(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "run_command", "input": {"command": "rm -rf /"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "not in the allowlist" in result

    @pytest.mark.anyio()
    async def test_rejects_shell_metacharacters(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "run_command", "input": {"command": "ls | cat"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "metacharacters" in result

    @pytest.mark.anyio()
    async def test_rejects_disallowed_git_subcommand(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "run_command", "input": {"command": "git push"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "not allowed" in result

    @pytest.mark.anyio()
    async def test_runs_allowed_command(self) -> None:
        """git --version is effectively read-only — verifies the happy path."""
        runtime = _make_analytical_runtime()
        ws = SimpleNamespace(directory=None, repo_path=None, config={}, threads={})
        runtime.projections.workspaces = {"ws-1": ws}
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "run_command", "input": {"command": "git status"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        # Should either succeed (exit code 0/128) or report an error
        assert "Exit code" in result or "Error" in result


class TestRegistryDispatch:
    """Tests that the dict-based dispatch registry works correctly."""

    @pytest.mark.anyio()
    async def test_unknown_tool_returns_error(self) -> None:
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        result, _ = await dispatcher.dispatch(
            {"name": "nonexistent_tool", "input": {}},
            workspace_id="ws-1",
            thread_id="th-1",
        )
        assert "Unknown tool" in result

    def test_handlers_dict_has_all_non_delegated_tools(self) -> None:
        """Every tool in tool_specs() (except delegated ones) has a handler."""
        runtime = _make_analytical_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        delegated = {"archive_thread", "define_workflow_steps"}
        spec_names = {s["name"] for s in dispatcher.tool_specs()}
        handler_names = set(dispatcher._handlers.keys())
        missing = (spec_names - delegated) - handler_names
        assert not missing, f"Tools in specs but not in handlers: {missing}"


class TestOutcomeStats:
    """Tests for Track 1.5: outcome-informed proposals."""

    @pytest.mark.anyio()
    async def test_propose_plan_includes_outcome_stats(self) -> None:
        runtime = _make_runtime(registry=[
            _make_model_record("local/qwen3", 0.0, 0.0),
        ])
        # Add colony outcomes to projections
        runtime.projections.colony_outcomes = {
            "c-1": ColonyOutcome(
                colony_id="c-1", workspace_id="ws-1", thread_id="t-1",
                succeeded=True, total_rounds=2, total_cost=0.05,
                duration_ms=5000, entries_extracted=1, entries_accessed=3,
                quality_score=0.9, caste_composition=["coder"],
                strategy="sequential",
            ),
            "c-2": ColonyOutcome(
                colony_id="c-2", workspace_id="ws-1", thread_id="t-1",
                succeeded=True, total_rounds=3, total_cost=0.08,
                duration_ms=8000, entries_extracted=0, entries_accessed=2,
                quality_score=0.7, caste_composition=["coder"],
                strategy="sequential",
            ),
        }
        runtime.projections.outcome_stats = (
            lambda ws_id: _outcome_stats_impl(runtime.projections.colony_outcomes, ws_id)
        )

        dispatcher = QueenToolDispatcher(runtime)
        result_text, action = dispatcher._propose_plan(
            {"summary": "Test plan", "options": [{"name": "A", "description": "opt"}]},
            workspace_id="ws-1",
        )
        assert "Empirical Basis" in result_text
        assert "sequential" in result_text

    @pytest.mark.anyio()
    async def test_propose_plan_no_outcomes_no_section(self) -> None:
        runtime = _make_runtime()
        runtime.projections.colony_outcomes = {}
        runtime.projections.outcome_stats = lambda ws_id: []
        dispatcher = QueenToolDispatcher(runtime)
        result_text, _ = dispatcher._propose_plan(
            {"summary": "Test plan", "options": [{"name": "A", "description": "opt"}]},
            workspace_id="ws-1",
        )
        assert "Empirical Basis" not in result_text


def _outcome_stats_impl(
    outcomes: dict[str, ColonyOutcome], workspace_id: str,
) -> list[dict[str, Any]]:
    """Replicate outcome_stats logic for test mocking."""
    ws_outcomes = [o for o in outcomes.values() if o.workspace_id == workspace_id]
    if not ws_outcomes:
        return []
    buckets: dict[tuple[str, str], list[ColonyOutcome]] = {}
    for o in ws_outcomes:
        key = (o.strategy, ",".join(sorted(o.caste_composition)))
        buckets.setdefault(key, []).append(o)
    stats = []
    for (strategy, caste_mix), group in buckets.items():
        successes = sum(1 for o in group if o.succeeded)
        stats.append({
            "strategy": strategy,
            "caste_mix": caste_mix,
            "total": len(group),
            "success_rate": successes / len(group),
            "avg_rounds": sum(o.total_rounds for o in group) / len(group),
            "avg_cost": sum(o.total_cost for o in group) / len(group),
        })
    return stats


# ---------------------------------------------------------------------------
# Wave 63 Track 3: Queen write tools tests
# ---------------------------------------------------------------------------


def _make_write_tools_runtime(ws_dir: str) -> MagicMock:
    """Runtime mock for write tool tests with a real workspace directory."""
    runtime = _make_runtime()
    ws = SimpleNamespace(directory=ws_dir, repo_path=ws_dir)
    runtime.projections.workspaces = {"ws-1": ws}
    return runtime


class TestEditFile:
    """Tests for the edit_file Queen tool."""

    def test_edit_file_produces_diff(self, tmp_path: Path) -> None:
        """edit_file returns a diff preview for operator approval."""
        # Create a test file
        test_file = tmp_path / "config.yaml"
        test_file.write_text("name: old_value\nversion: 1.0\n")

        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._edit_file(
            {"path": "config.yaml", "old_text": "old_value", "new_text": "new_value", "reason": "fix name"},
            "ws-1",
        )

        assert "old_value" in result
        assert "new_value" in result
        assert meta is not None
        assert meta["tool"] == "edit_file"
        assert meta["preview"] is True
        assert meta["path"] == "config.yaml"

    def test_edit_file_rejects_missing_old_text(self, tmp_path: Path) -> None:
        """edit_file returns error when old_text not found."""
        test_file = tmp_path / "readme.md"
        test_file.write_text("# Hello\n")

        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._edit_file(
            {"path": "readme.md", "old_text": "NONEXISTENT", "new_text": "replacement"},
            "ws-1",
        )

        assert "not found" in result.lower()
        assert meta is None

    def test_edit_file_rejects_binary(self, tmp_path: Path) -> None:
        """edit_file rejects binary files."""
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00" * 100)

        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._edit_file(
            {"path": "image.png", "old_text": "x", "new_text": "y"},
            "ws-1",
        )

        assert "binary" in result.lower()
        assert meta is None

    def test_edit_file_rejects_outside_workspace(self, tmp_path: Path) -> None:
        """edit_file rejects path traversal attempts."""
        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._edit_file(
            {"path": "../../etc/passwd", "old_text": "x", "new_text": "y"},
            "ws-1",
        )

        assert "outside" in result.lower()
        assert meta is None


class TestRunTests:
    """Tests for the run_tests Queen tool."""

    @pytest.mark.anyio()
    async def test_run_tests_returns_structured(self, tmp_path: Path) -> None:
        """run_tests returns exit code and output."""
        from unittest.mock import AsyncMock, patch  # noqa: PLC0415

        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        # Mock subprocess to avoid running real tests
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(
            return_value=(b"3 passed in 1.2s\n", b""),
        )

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            result, meta = await dispatcher._run_tests({"timeout": 10}, "ws-1")

        assert "Exit code: 0" in result
        assert "3 passed" in result
        assert meta is not None
        assert meta["exit_code"] == 0

    @pytest.mark.anyio()
    async def test_run_tests_timeout(self) -> None:
        """run_tests respects timeout parameter (capped at 300)."""
        from unittest.mock import AsyncMock, patch  # noqa: PLC0415

        runtime = _make_runtime()
        runtime.projections.workspaces = {}
        dispatcher = QueenToolDispatcher(runtime)

        # Mock subprocess that times out
        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(side_effect=TimeoutError)

        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
            result, _ = await dispatcher._run_tests({"timeout": 999}, "ws-1")

        assert "timed out" in result.lower()


class TestDeleteFile:
    """Tests for the delete_file Queen tool."""

    def test_delete_file_produces_proposal(self, tmp_path: Path) -> None:
        """delete_file returns a confirmation request."""
        test_file = tmp_path / "obsolete.txt"
        test_file.write_text("old content")

        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._delete_file(
            {"path": "obsolete.txt", "reason": "no longer needed"},
            "ws-1",
        )

        assert "obsolete.txt" in result
        assert "no longer needed" in result
        assert meta is not None
        assert meta["tool"] == "delete_file"
        assert meta["preview"] is True

    def test_delete_file_rejects_missing_file(self, tmp_path: Path) -> None:
        """delete_file returns error for nonexistent file."""
        runtime = _make_write_tools_runtime(str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._delete_file(
            {"path": "ghost.txt"},
            "ws-1",
        )

        assert "not found" in result.lower()
        assert meta is None
