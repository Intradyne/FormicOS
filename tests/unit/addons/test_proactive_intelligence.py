"""Tests for proactive intelligence addon handlers."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from formicos.addons.proactive_intelligence.handlers import (
    handle_proactive_configure,
    handle_query_briefing,
    on_scheduled_briefing,
)


def _make_projections(
    *,
    workspaces: dict[str, Any] | None = None,
    workspace_configs: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock projections object."""
    proj = MagicMock()
    proj.workspaces = workspaces or {"ws1": MagicMock()}
    proj.workspace_configs = workspace_configs or {}
    return proj


def _make_insight(
    category: str = "knowledge_health",
    title: str = "Test insight",
    detail: str = "Something needs attention",
    suggested_colony: Any = None,
) -> MagicMock:
    """Build a mock KnowledgeInsight."""
    insight = MagicMock()
    insight.category = category
    insight.title = title
    insight.detail = detail
    insight.suggested_colony = suggested_colony
    return insight


def _make_briefing(insights: list[Any] | None = None) -> MagicMock:
    """Build a mock ProactiveBriefing."""
    briefing = MagicMock()
    briefing.insights = insights or []
    return briefing


# ---------------------------------------------------------------------------
# handle_query_briefing
# ---------------------------------------------------------------------------


class TestHandleQueryBriefing:
    """Test the query_briefing tool handler."""

    def test_no_projections_returns_unavailable(self) -> None:
        result = asyncio.run(
            handle_query_briefing({}, "ws1", "th1", runtime_context={})
        )
        assert "unavailable" in result.lower()

    def test_returns_briefing_with_insights(self) -> None:
        insights = [
            _make_insight(category="knowledge_health", title="Confidence decline"),
            _make_insight(category="performance", title="Cost outlier"),
        ]
        briefing = _make_briefing(insights)
        projections = _make_projections()

        with _patch_generate_briefing(briefing):
            result = asyncio.run(
                handle_query_briefing(
                    {}, "ws1", "th1",
                    runtime_context={"projections": projections},
                )
            )
        assert "2 insights" in result
        assert "Confidence decline" in result
        assert "Cost outlier" in result

    def test_filters_by_categories(self) -> None:
        insights = [
            _make_insight(category="knowledge_health", title="Decline"),
            _make_insight(category="performance", title="Outlier"),
            _make_insight(category="knowledge_health", title="Stale"),
        ]
        briefing = _make_briefing(insights)
        projections = _make_projections()

        with _patch_generate_briefing(briefing):
            result = asyncio.run(
                handle_query_briefing(
                    {"categories": ["performance"]},
                    "ws1", "th1",
                    runtime_context={"projections": projections},
                )
            )
        assert "Outlier" in result
        # knowledge_health insights should be filtered out
        assert "Decline" not in result
        assert "Stale" not in result

    def test_no_insights_returns_message(self) -> None:
        briefing = _make_briefing([])
        projections = _make_projections()

        with _patch_generate_briefing(briefing):
            result = asyncio.run(
                handle_query_briefing(
                    {}, "ws1", "th1",
                    runtime_context={"projections": projections},
                )
            )
        assert "No proactive insights" in result

    def test_suggested_colony_shown(self) -> None:
        colony = MagicMock()
        colony.task = "Investigate stale knowledge cluster"
        insights = [_make_insight(suggested_colony=colony)]
        briefing = _make_briefing(insights)
        projections = _make_projections()

        with _patch_generate_briefing(briefing):
            result = asyncio.run(
                handle_query_briefing(
                    {}, "ws1", "th1",
                    runtime_context={"projections": projections},
                )
            )
        assert "Suggested colony" in result
        assert "stale knowledge" in result.lower()

    def test_uses_target_workspace_from_inputs(self) -> None:
        briefing = _make_briefing([])
        projections = _make_projections()
        captured_ws: list[str] = []

        with _patch_generate_briefing(briefing, capture_ws=captured_ws):
            asyncio.run(
                handle_query_briefing(
                    {"workspace_id": "ws-other"},
                    "ws1", "th1",
                    runtime_context={"projections": projections},
                )
            )
        assert "ws-other" in captured_ws


# ---------------------------------------------------------------------------
# on_scheduled_briefing (cron wrapper)
# ---------------------------------------------------------------------------


class TestOnScheduledBriefing:
    """Test the cron trigger wrapper."""

    def test_skips_without_projections(self) -> None:
        """No projections = no crash, just skip."""
        asyncio.run(on_scheduled_briefing(runtime_context={}))

    def test_skips_with_none_context(self) -> None:
        asyncio.run(on_scheduled_briefing(runtime_context=None))

    def test_generates_briefings_for_all_workspaces(self) -> None:
        """Cron wrapper calls generate_briefing for each workspace."""
        projections = _make_projections(
            workspaces={"ws1": MagicMock(), "ws2": MagicMock()},
        )
        call_count = {"n": 0}

        def mock_generate(ws_id: str, _proj: Any) -> MagicMock:
            call_count["n"] += 1
            return _make_briefing([_make_insight()])

        with _patch_generate_briefing_fn(mock_generate):
            asyncio.run(
                on_scheduled_briefing(runtime_context={"projections": projections})
            )
        assert call_count["n"] == 2


# ---------------------------------------------------------------------------
# handle_proactive_configure
# ---------------------------------------------------------------------------


class TestHandleProactiveConfigure:
    """Test rule enable/disable handler."""

    def test_list_action_returns_rules(self) -> None:
        result = asyncio.run(
            handle_proactive_configure(
                {"action": "list"}, "ws1", "th1",
            )
        )
        assert "contradiction" in result
        assert "cost_outlier" in result

    def test_disable_rule_emits_event(self) -> None:
        mock_runtime = MagicMock()
        mock_runtime.emit_and_broadcast = AsyncMock()
        projections = _make_projections()

        result = asyncio.run(
            handle_proactive_configure(
                {"action": "disable", "rule_name": "contradiction"},
                "ws1", "th1",
                runtime_context={
                    "projections": projections,
                    "runtime": mock_runtime,
                },
            )
        )
        assert "disabled" in result.lower()
        mock_runtime.emit_and_broadcast.assert_called_once()
        event = mock_runtime.emit_and_broadcast.call_args[0][0]
        assert event.field == "proactive_disabled_rules"
        assert "contradiction" in event.new_value

    def test_enable_rule_removes_from_disabled(self) -> None:
        mock_runtime = MagicMock()
        mock_runtime.emit_and_broadcast = AsyncMock()
        projections = _make_projections(
            workspace_configs={
                "ws1": {"proactive_disabled_rules": ["contradiction", "cost_outlier"]},
            },
        )

        result = asyncio.run(
            handle_proactive_configure(
                {"action": "enable", "rule_name": "contradiction"},
                "ws1", "th1",
                runtime_context={
                    "projections": projections,
                    "runtime": mock_runtime,
                },
            )
        )
        assert "enabled" in result.lower()
        event = mock_runtime.emit_and_broadcast.call_args[0][0]
        # contradiction should be removed, cost_outlier should remain
        assert "contradiction" not in event.new_value
        assert "cost_outlier" in event.new_value

    def test_missing_rule_name_returns_error(self) -> None:
        result = asyncio.run(
            handle_proactive_configure(
                {"action": "disable"}, "ws1", "th1",
            )
        )
        assert "Error" in result

    def test_unknown_action_returns_error(self) -> None:
        result = asyncio.run(
            handle_proactive_configure(
                {"action": "explode", "rule_name": "foo"}, "ws1", "th1",
            )
        )
        assert "Unknown" in result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_generate_briefing(
    briefing: MagicMock,
    capture_ws: list[str] | None = None,
):  # noqa: ANN202
    """Patch generate_briefing at the source module (lazy import target)."""
    from unittest.mock import patch

    def mock_fn(ws_id: str, _proj: Any) -> MagicMock:
        if capture_ws is not None:
            capture_ws.append(ws_id)
        return briefing

    return patch(
        "formicos.addons.proactive_intelligence.rules.generate_briefing",
        side_effect=mock_fn,
    )


def _patch_generate_briefing_fn(fn):  # noqa: ANN001, ANN202
    """Patch generate_briefing with a custom callable."""
    from unittest.mock import patch

    return patch(
        "formicos.addons.proactive_intelligence.rules.generate_briefing",
        side_effect=fn,
    )
