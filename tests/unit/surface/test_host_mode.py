"""Wave 89 Track B: Host-mode addon-generation tests.

Tests for:
- host-like prompts produce capability_mode == "host"
- host-mode context is injected on colony turns
- non-host requests do NOT inherit addon-generation context
- host context includes deploy_addon instruction
"""

from __future__ import annotations

import pytest

from formicos.surface.planning_policy import (
    PlanningDecision,
    _classify_capability_mode,
    decide_planning_route,
)
from formicos.surface.queen_runtime import _HOST_ADDON_CONTEXT_TEMPLATE

# Generate a concrete context for testing
_HOST_ADDON_CONTEXT = _HOST_ADDON_CONTEXT_TEMPLATE.format(
    addon_name="test-addon", addon_package="test_addon",
)


# ── Capability-mode classification ──


class TestHostModeClassification:
    def test_dashboard_request_is_host(self) -> None:
        mode = _classify_capability_mode(
            "build me a dashboard showing colony quality trends", True, "complex",
        )
        assert mode == "host"

    def test_panel_request_is_host(self) -> None:
        mode = _classify_capability_mode(
            "create a panel for monitoring daily outcomes", True, "complex",
        )
        assert mode == "host"

    def test_addon_request_is_host(self) -> None:
        mode = _classify_capability_mode(
            "build an addon that shows pattern library state", True, "complex",
        )
        assert mode == "host"

    def test_living_dashboard_is_host(self) -> None:
        mode = _classify_capability_mode(
            "give me a living dashboard of quality trends", True, "complex",
        )
        assert mode == "host"

    def test_simple_fix_is_not_host(self) -> None:
        mode = _classify_capability_mode(
            "fix the bug in auth.py", True, "simple",
        )
        assert mode != "host"

    def test_status_query_is_not_host(self) -> None:
        mode = _classify_capability_mode(
            "what is the status?", False, "simple",
        )
        assert mode != "host"

    def test_implement_request_is_execute(self) -> None:
        mode = _classify_capability_mode(
            "implement the auth module", True, "complex",
        )
        assert mode == "execute"


class TestHostModeInPolicyDecision:
    def test_dashboard_routes_with_host_mode(self) -> None:
        d = decide_planning_route(
            "build me a dashboard showing colony quality trends",
        )
        assert d.capability_mode == "host"

    def test_simple_fix_not_host(self) -> None:
        d = decide_planning_route("fix the typo in README.md")
        assert d.capability_mode != "host"

    def test_qa_not_host(self) -> None:
        d = decide_planning_route("hello")
        assert d.capability_mode != "host"


# ── Host context content ──


class TestHostContextContent:
    def test_context_mentions_addon_yaml(self) -> None:
        assert "addon.yaml" in _HOST_ADDON_CONTEXT

    def test_context_mentions_deploy_addon(self) -> None:
        assert "deploy_addon" in _HOST_ADDON_CONTEXT

    def test_context_mentions_kpi_card(self) -> None:
        assert "kpi_card" in _HOST_ADDON_CONTEXT

    def test_context_mentions_runtime_context(self) -> None:
        assert "runtime_context" in _HOST_ADDON_CONTEXT

    def test_context_mentions_refresh_interval(self) -> None:
        assert "refresh_interval_s" in _HOST_ADDON_CONTEXT

    def test_context_prohibits_external_apis(self) -> None:
        assert "No external API" in _HOST_ADDON_CONTEXT

    def test_context_mentions_projections(self) -> None:
        assert "projections" in _HOST_ADDON_CONTEXT

    def test_context_mentions_handler_signature(self) -> None:
        assert "async def get_overview" in _HOST_ADDON_CONTEXT
