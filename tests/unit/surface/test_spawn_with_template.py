"""Tests for colony spawn with template_id (ADR-016, Phase B T2)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.core.types import CasteSlot
from formicos.surface.commands import handle_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime() -> MagicMock:
    runtime = MagicMock()
    runtime.spawn_colony = AsyncMock(return_value="colony-test123")
    runtime.emit_and_broadcast = AsyncMock(return_value=1)
    runtime.colony_manager = MagicMock()
    runtime.colony_manager.start_colony = AsyncMock()
    return runtime


def _make_template(
    *,
    template_id: str = "tmpl-abc12345",
    castes: list[str] | None = None,
    strategy: str = "stigmergic",
    budget_limit: float = 1.0,
    max_rounds: int = 15,
) -> MagicMock:
    tmpl = MagicMock()
    tmpl.template_id = template_id
    slots = [CasteSlot(caste=c) for c in (castes or ["coder", "reviewer"])]
    tmpl.castes = slots
    tmpl.strategy = strategy
    tmpl.budget_limit = budget_limit
    tmpl.max_rounds = max_rounds
    return tmpl


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSpawnWithTemplate:
    @pytest.mark.asyncio
    async def test_template_defaults_applied(self) -> None:
        """Spawn with templateId should use template defaults."""
        runtime = _make_runtime()
        tmpl = _make_template(
            castes=["coder", "reviewer", "researcher"],
            budget_limit=2.0,
            max_rounds=20,
        )

        with patch(
            "formicos.surface.template_manager.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ):
            result = await handle_command(
                "spawn_colony", "ws-1",
                {
                    "threadId": "th-1",
                    "task": "Build feature",
                    "templateId": "tmpl-abc12345",
                },
                runtime,
            )

        assert result["colonyId"] == "colony-test123"
        assert result["templateId"] == "tmpl-abc12345"

        # Verify template defaults were passed to spawn_colony
        call_args = runtime.spawn_colony.call_args
        castes_arg = call_args[0][3]
        assert [s.caste for s in castes_arg] == ["coder", "reviewer", "researcher"]
        assert call_args[1]["budget_limit"] == 2.0
        assert call_args[1]["max_rounds"] == 20

    @pytest.mark.asyncio
    async def test_template_overrides(self) -> None:
        """Explicit payload fields should override template defaults."""
        runtime = _make_runtime()
        tmpl = _make_template(budget_limit=1.0, max_rounds=15)

        with patch(
            "formicos.surface.template_manager.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ):
            result = await handle_command(
                "spawn_colony", "ws-1",
                {
                    "threadId": "th-1",
                    "task": "Build feature",
                    "templateId": "tmpl-abc12345",
                    "budgetLimit": 3.0,
                    "castes": [{"caste": "coder"}],
                },
                runtime,
            )

        assert result["colonyId"] == "colony-test123"
        call_args = runtime.spawn_colony.call_args
        assert [s.caste for s in call_args[0][3]] == ["coder"]  # overridden
        assert call_args[1]["budget_limit"] == 3.0  # overridden
        assert call_args[1]["max_rounds"] == 15  # from template

    @pytest.mark.asyncio
    async def test_template_used_event_emitted(self) -> None:
        """ColonyTemplateUsed event should be emitted when template is used."""
        runtime = _make_runtime()
        tmpl = _make_template()

        with patch(
            "formicos.surface.template_manager.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ):
            await handle_command(
                "spawn_colony", "ws-1",
                {
                    "threadId": "th-1",
                    "task": "Build feature",
                    "templateId": "tmpl-abc12345",
                },
                runtime,
            )

        # emit_and_broadcast called for ColonyTemplateUsed
        assert runtime.emit_and_broadcast.await_count >= 1
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.template_id == "tmpl-abc12345"
        assert event.colony_id == "colony-test123"

    @pytest.mark.asyncio
    async def test_unknown_template_returns_error(self) -> None:
        """Spawning with a nonexistent template_id should return an error."""
        runtime = _make_runtime()

        with patch(
            "formicos.surface.template_manager.get_template",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await handle_command(
                "spawn_colony", "ws-1",
                {
                    "threadId": "th-1",
                    "task": "Build feature",
                    "templateId": "nonexistent",
                },
                runtime,
            )

        assert "error" in result
        assert "nonexistent" in result["error"]
        runtime.spawn_colony.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_spawn_without_template_unchanged(self) -> None:
        """Spawn without templateId should work as before."""
        runtime = _make_runtime()

        result = await handle_command(
            "spawn_colony", "ws-1",
            {
                "threadId": "th-1",
                "task": "Build feature",
                "castes": [{"caste": "coder"}],
            },
            runtime,
        )

        assert result["colonyId"] == "colony-test123"
        assert result.get("templateId") is None
        runtime.spawn_colony.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_castes_from_template(self) -> None:
        """When template provides castes, they become the default."""
        runtime = _make_runtime()
        tmpl = _make_template(castes=["researcher", "archivist"])

        with patch(
            "formicos.surface.template_manager.get_template",
            new_callable=AsyncMock,
            return_value=tmpl,
        ):
            await handle_command(
                "spawn_colony", "ws-1",
                {
                    "threadId": "th-1",
                    "task": "Research JWT",
                    "templateId": "tmpl-abc12345",
                },
                runtime,
            )

        call_args = runtime.spawn_colony.call_args
        assert [s.caste for s in call_args[0][3]] == ["researcher", "archivist"]
