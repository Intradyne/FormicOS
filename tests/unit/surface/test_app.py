"""Unit tests for formicos.surface.app."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from formicos.surface.app import (
    _configure_asyncio_debug_from_env,
    create_app,
    route_model_to_adapter,
)


class TestRouteModelToAdapter:
    """Tests for provider-prefix model routing (algorithms.md §11)."""

    def test_routes_anthropic_prefix(self) -> None:
        mock_adapter = MagicMock()
        adapters = {"anthropic": mock_adapter}
        result = route_model_to_adapter("anthropic/claude-sonnet-4.6", adapters)
        assert result is mock_adapter

    def test_routes_ollama_prefix(self) -> None:
        mock_adapter = MagicMock()
        adapters = {"ollama": mock_adapter}
        result = route_model_to_adapter("ollama/llama3.3", adapters)
        assert result is mock_adapter

    def test_unknown_provider_raises(self) -> None:
        adapters: dict[str, MagicMock] = {"anthropic": MagicMock()}
        with pytest.raises(ValueError, match="No adapter registered"):
            route_model_to_adapter("openai/gpt-4", adapters)

    def test_multiple_providers(self) -> None:
        ant = MagicMock()
        oll = MagicMock()
        adapters = {"anthropic": ant, "ollama": oll}
        assert route_model_to_adapter("anthropic/claude-haiku-4.5", adapters) is ant
        assert route_model_to_adapter("ollama/llama3.3", adapters) is oll


class TestCreateApp:
    """Light structural guards for app wiring."""

    def test_combines_mcp_http_lifespan(self) -> None:
        source = inspect.getsource(create_app)
        assert "combined_lifespan" in source
        assert 'getattr(mcp_http, "lifespan", None)' in source


class TestAsyncioDebugConfig:
    """Asyncio debug instrumentation should be opt-in."""

    def test_asyncio_debug_disabled_by_default(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        monkeypatch.delenv("FORMICOS_ASYNCIO_DEBUG", raising=False)
        monkeypatch.setattr("formicos.surface.app.asyncio.get_running_loop", lambda: loop)

        _configure_asyncio_debug_from_env()

        loop.set_debug.assert_not_called()

    def test_asyncio_debug_enabled_when_flag_set(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        loop = MagicMock(spec=asyncio.AbstractEventLoop)
        loop.slow_callback_duration = 0.0
        monkeypatch.setenv("FORMICOS_ASYNCIO_DEBUG", "1")
        monkeypatch.setattr("formicos.surface.app.asyncio.get_running_loop", lambda: loop)

        _configure_asyncio_debug_from_env()

        loop.set_debug.assert_called_once_with(True)
        assert loop.slow_callback_duration == 0.1
