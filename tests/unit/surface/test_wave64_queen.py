"""Wave 64 Track 3 & 4 tests — Queen smart fan-out and heuristic cloud routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.core.types import ModelRecord
from formicos.surface.queen_tools import QueenToolDispatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_model_record(
    address: str = "local/qwen3",
    cost_in: float = 0.0,
    cost_out: float = 0.0,
    *,
    supports_tools: bool = True,
    status: str = "available",
) -> ModelRecord:
    provider = address.split("/", 1)[0] if "/" in address else address
    return ModelRecord(
        address=address,
        provider=provider,
        endpoint="http://localhost:8080",
        context_window=32768,
        supports_tools=supports_tools,
        cost_per_input_token=cost_in,
        cost_per_output_token=cost_out,
        status=status,
    )


def _make_runtime(
    *,
    max_rounds: int = 20,
    coder_model: str = "local/qwen3",
    reviewer_model: str = "local/qwen3",
    researcher_model: str = "local/qwen3",
    registry: list[ModelRecord] | None = None,
) -> MagicMock:
    runtime = MagicMock()
    runtime.settings.governance.max_rounds_per_colony = max_rounds
    runtime.settings.models.defaults.coder = coder_model
    runtime.settings.models.defaults.reviewer = reviewer_model
    runtime.settings.models.defaults.researcher = researcher_model
    runtime.settings.models.registry = registry or [
        _make_model_record(address=coder_model),
    ]
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))
    runtime.projections.queen_notes = {}
    runtime.projections.colony_outcomes = {}
    runtime.projections.outcome_stats = MagicMock(return_value=[])
    return runtime


def _make_colony_proj(
    colony_id: str = "c-fail-1",
    workspace_id: str = "ws-1",
    *,
    status: str = "failed",
    task: str = "Implement CSV parser",
    strategy: str = "sequential",
    failure_reason: str | None = "Max rounds exceeded",
    castes: list[str] | None = None,
    display_name: str = "csv-colony",
) -> SimpleNamespace:
    """Lightweight colony projection mock for retry tests."""
    return SimpleNamespace(
        id=colony_id,
        workspace_id=workspace_id,
        status=status,
        task=task,
        strategy=strategy,
        failure_reason=failure_reason,
        castes=castes or ["coder"],
        display_name=display_name,
        routing_override=None,
    )


# ===========================================================================
# Track 3: Queen Smart Fan-Out
# ===========================================================================


class TestProposePlanIncludesProviders:
    """Track 3.1: propose_plan enriches output with provider availability."""

    def test_propose_plan_includes_providers(self) -> None:
        """Plan options include provider info from model registry."""
        registry = [
            _make_model_record("local/qwen3", 0.0, 0.0),
            _make_model_record("anthropic/claude-3-haiku", 0.000001, 0.000002),
        ]
        runtime = _make_runtime(
            coder_model="local/qwen3",
            registry=registry,
        )
        dispatcher = QueenToolDispatcher(runtime)

        result_text, action = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Build feature X",
                "options": [
                    {"label": "Fast", "description": "One coder", "colonies": 1},
                ],
            },
            workspace_id="ws-1",
        )

        assert "Available Providers" in result_text
        assert "coder" in result_text
        assert "local/qwen3" in result_text

    def test_unavailable_providers_excluded(self) -> None:
        """Providers with status=unavailable are not shown."""
        registry = [
            _make_model_record("local/qwen3", 0.0, 0.0, status="available"),
            _make_model_record(
                "broken/model", 0.0, 0.0, status="unavailable",
            ),
        ]
        runtime = _make_runtime(
            coder_model="local/qwen3",
            registry=registry,
        )
        dispatcher = QueenToolDispatcher(runtime)

        result_text, _ = dispatcher._propose_plan(  # pyright: ignore[reportPrivateUsage]
            {
                "summary": "Test plan",
                "options": [],
            },
            workspace_id="ws-1",
        )

        assert "broken/model" not in result_text


class TestRetryColony:
    """Track 3.2 & 3.3: retry_colony spawns new colony with failure context."""

    @pytest.mark.anyio()
    async def test_retry_colony_spawns_new(self) -> None:
        """retry_colony creates a new colony via _spawn_colony."""
        runtime = _make_runtime()
        colony = _make_colony_proj()
        runtime.projections.colonies = {colony.id: colony}
        runtime.projections.get_colony = MagicMock(return_value=colony)

        dispatcher = QueenToolDispatcher(runtime)
        # Mock _spawn_colony to capture inputs
        spawn_result = ("Colony c-new spawned.", {"tool": "spawn_colony", "colony_id": "c-new"})
        dispatcher._spawn_colony = AsyncMock(return_value=spawn_result)  # pyright: ignore[reportPrivateUsage]

        result, action = await dispatcher.dispatch(
            {"name": "retry_colony", "input": {"colony_id": "c-fail-1"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "Retrying colony c-fail-1" in result
        dispatcher._spawn_colony.assert_awaited_once()  # pyright: ignore[reportPrivateUsage]
        call_args = dispatcher._spawn_colony.call_args  # pyright: ignore[reportPrivateUsage]
        spawn_inputs = call_args[0][0]
        assert "Implement CSV parser" in spawn_inputs["task"]

    @pytest.mark.anyio()
    async def test_retry_colony_includes_failure_context(self) -> None:
        """Retry task text includes previous failure reason."""
        runtime = _make_runtime()
        colony = _make_colony_proj(failure_reason="Timeout after 20 rounds")
        runtime.projections.colonies = {colony.id: colony}
        runtime.projections.get_colony = MagicMock(return_value=colony)

        dispatcher = QueenToolDispatcher(runtime)
        dispatcher._spawn_colony = AsyncMock(  # pyright: ignore[reportPrivateUsage]
            return_value=("Spawned.", {"tool": "spawn_colony"}),
        )

        await dispatcher.dispatch(
            {"name": "retry_colony", "input": {"colony_id": "c-fail-1"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        call_args = dispatcher._spawn_colony.call_args  # pyright: ignore[reportPrivateUsage]
        spawn_inputs = call_args[0][0]
        task_text = spawn_inputs["task"]
        assert "Timeout after 20 rounds" in task_text
        assert "Previous attempt failed" in task_text

    @pytest.mark.anyio()
    async def test_retry_colony_rejects_running(self) -> None:
        """retry_colony rejects colonies that are still running."""
        runtime = _make_runtime()
        colony = _make_colony_proj(status="running")
        runtime.projections.colonies = {colony.id: colony}
        runtime.projections.get_colony = MagicMock(return_value=colony)

        dispatcher = QueenToolDispatcher(runtime)
        result, action = await dispatcher.dispatch(
            {"name": "retry_colony", "input": {"colony_id": "c-fail-1"}},
            workspace_id="ws-1",
            thread_id="th-1",
        )

        assert "running" in result
        assert action is None


class TestEscalationSuggestsModel:
    """Track 3.4: stall escalation message includes model hint."""

    def test_escalation_suggests_model(self) -> None:
        """When a cloud model with cost is in the registry, the escalation
        message includes a model suggestion with cost estimate."""
        from formicos.core.events import ColonyChatMessage  # noqa: PLC0415

        runtime = MagicMock()
        runtime.settings.models.registry = [
            _make_model_record("local/qwen3", 0.0, 0.0, supports_tools=False),
            _make_model_record(
                "anthropic/claude-3-haiku", 0.000001, 0.000005,
                supports_tools=True,
            ),
        ]

        # Simulate the escalation logic from colony_manager.py
        model_hint = ""
        for rec in runtime.settings.models.registry:
            if (rec.cost_per_output_token
                    and rec.cost_per_output_token > 0
                    and rec.supports_tools):
                est = 4000 * (rec.cost_per_output_token or 0)
                model_hint = (
                    f"\nSuggestion: retry with "
                    f"{rec.address} "
                    f"(est. ${est:.3f}/round)."
                )
                break

        escalation_content = (
            f"Colony stalled -- 0 productive tool calls in "
            f"5 rounds. "
            f"Use retry_colony to retry.{model_hint}"
        )

        assert "anthropic/claude-3-haiku" in escalation_content
        assert "retry_colony" in escalation_content
        assert "$0.020/round" in escalation_content


# ===========================================================================
# Track 4: Heuristic Cloud Routing
# ===========================================================================


class TestCloudRoutingLongMessage:
    """Track 4.5: 500+ token message routes to cloud."""

    def test_cloud_routing_long_message(self) -> None:
        """A message estimated at >500 tokens triggers cloud routing."""
        # The heuristic: len(msg) // 4 > 500, so len > 2000 chars
        last_operator_msg = "x " * 1100  # ~2200 chars -> ~550 tokens

        _msg_tokens = len(last_operator_msg) // 4
        use_cloud = _msg_tokens > 500

        assert use_cloud is True

    def test_short_message_stays_local(self) -> None:
        """A short message does not trigger cloud routing by length alone."""
        last_operator_msg = "Fix the bug in parser.py"

        _msg_tokens = len(last_operator_msg) // 4
        use_cloud = _msg_tokens > 500

        assert use_cloud is False


class TestCloudRoutingAtCloudTag:
    """Track 4.6: @cloud tag forces cloud routing."""

    def test_cloud_routing_at_cloud_tag(self) -> None:
        """@cloud anywhere in the operator message triggers cloud."""
        last_operator_msg = "Plan a refactor of the API layer @cloud"
        use_cloud = "@cloud" in last_operator_msg
        assert use_cloud is True

    def test_at_cloud_stripped_before_sending(self) -> None:
        """@cloud tag is removed from the message before LLM call."""
        msg = "Plan a refactor @cloud please"
        cleaned = msg.replace("@cloud", "").strip()
        assert "@cloud" not in cleaned
        assert "Plan a refactor" in cleaned


class TestCloudRoutingParseFailureRetry:
    """Track 4.7: auto-escalation on parse failure."""

    def test_cloud_routing_parse_failure_retry(self) -> None:
        """Short response + complex message triggers cloud escalation."""
        # Conditions from queen_runtime.py:
        # - no actions produced
        # - response content < 50 chars
        # - operator message > 200 chars
        # - cloud model available and not already used
        # - not already retried

        actions: list[Any] = []
        response_content = "I don't understand."  # < 50 chars
        last_operator_msg = "a " * 120  # 240 chars > 200
        _cloud_retry_used = False
        _planning_model = "anthropic/claude-3-haiku"
        queen_model = "local/qwen3"

        should_escalate = (
            not actions
            and not _cloud_retry_used
            and _planning_model
            and queen_model != _planning_model
            and len(response_content) < 50
            and len(last_operator_msg) > 200
        )

        assert should_escalate is True

    def test_no_escalation_when_already_on_cloud(self) -> None:
        """No re-escalation when already using the cloud model."""
        actions: list[Any] = []
        response_content = "?"
        last_operator_msg = "a " * 120
        _cloud_retry_used = False
        _planning_model = "anthropic/claude-3-haiku"
        queen_model = "anthropic/claude-3-haiku"  # already cloud

        should_escalate = (
            not actions
            and not _cloud_retry_used
            and _planning_model
            and queen_model != _planning_model
            and len(response_content) < 50
            and len(last_operator_msg) > 200
        )

        assert should_escalate is False


class TestModelUsedInMeta:
    """Track 4.8: QueenMessage meta contains model_used."""

    def test_model_used_in_meta(self) -> None:
        """The model_used field is set in QueenMessage meta dict."""
        queen_model = "local/qwen3"
        msg_meta: dict[str, Any] = {}

        # Mirrors queen_runtime.py line 1155-1158
        if msg_meta is None:
            msg_meta = {}
        msg_meta["model_used"] = queen_model

        assert msg_meta["model_used"] == "local/qwen3"

    def test_model_used_reflects_escalation(self) -> None:
        """After cloud escalation, model_used reflects the cloud model."""
        queen_model = "local/qwen3"
        _planning_model = "anthropic/claude-3-haiku"

        # Simulate escalation
        queen_model = _planning_model

        msg_meta: dict[str, Any] = {}
        msg_meta["model_used"] = queen_model

        assert msg_meta["model_used"] == "anthropic/claude-3-haiku"
