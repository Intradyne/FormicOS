"""Tests for cost function construction and budget enforcement (ADR-009)."""

from __future__ import annotations

from unittest.mock import MagicMock

from formicos.core.types import ModelRecord
from formicos.surface.app import _build_cost_fn


class TestBuildCostFn:
    """Verify _build_cost_fn produces correct cost calculations."""

    def test_local_model_zero_cost(self) -> None:
        registry = [
            ModelRecord(
                address="llama-cpp/gpt-4",
                provider="llama-cpp",
                context_window=8192,
                supports_tools=True,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
            ),
        ]
        cost_fn = _build_cost_fn(registry)
        assert cost_fn("llama-cpp/gpt-4", 1000, 500) == 0.0

    def test_cloud_model_cost(self) -> None:
        registry = [
            ModelRecord(
                address="anthropic/claude-sonnet-4.6",
                provider="anthropic",
                context_window=200000,
                supports_tools=True,
                cost_per_input_token=0.000003,
                cost_per_output_token=0.000015,
            ),
        ]
        cost_fn = _build_cost_fn(registry)
        result = cost_fn("anthropic/claude-sonnet-4.6", 1000, 500)
        expected = (1000 * 0.000003) + (500 * 0.000015)
        assert abs(result - expected) < 1e-10

    def test_unknown_model_returns_zero(self) -> None:
        cost_fn = _build_cost_fn([])
        assert cost_fn("unknown/model", 5000, 2000) == 0.0

    def test_multiple_models(self) -> None:
        registry = [
            ModelRecord(
                address="llama-cpp/gpt-4",
                provider="llama-cpp",
                context_window=8192,
                supports_tools=True,
                cost_per_input_token=0.0,
                cost_per_output_token=0.0,
            ),
            ModelRecord(
                address="anthropic/claude-haiku-4.5",
                provider="anthropic",
                context_window=200000,
                supports_tools=True,
                cost_per_input_token=0.0000008,
                cost_per_output_token=0.000004,
            ),
        ]
        cost_fn = _build_cost_fn(registry)
        assert cost_fn("llama-cpp/gpt-4", 1000, 1000) == 0.0
        haiku_cost = cost_fn("anthropic/claude-haiku-4.5", 1000, 1000)
        expected = (1000 * 0.0000008) + (1000 * 0.000004)
        assert abs(haiku_cost - expected) < 1e-10

    def test_none_rates_default_to_zero(self) -> None:
        registry = [
            ModelRecord(
                address="llama-cpp/local",
                provider="llama-cpp",
                context_window=4096,
                supports_tools=False,
                cost_per_input_token=None,
                cost_per_output_token=None,
            ),
        ]
        cost_fn = _build_cost_fn(registry)
        assert cost_fn("llama-cpp/local", 10000, 5000) == 0.0
