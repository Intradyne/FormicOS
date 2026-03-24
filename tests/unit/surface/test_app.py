"""Unit tests for formicos.surface.app."""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest

from formicos.surface.app import create_app, route_model_to_adapter


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
