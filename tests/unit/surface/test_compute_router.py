"""Tests for LLMRouter.route() — compute router decision order (ADR-012)."""

from __future__ import annotations

import pytest

from formicos.core.settings import ModelRoutingEntry
from formicos.core.types import ModelRecord
from formicos.surface.runtime import LLMRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_router(
    adapters: dict[str, object] | None = None,
    routing_table: dict[str, ModelRoutingEntry] | None = None,
    registry: list[ModelRecord] | None = None,
) -> LLMRouter:
    """Build an LLMRouter with optional routing table and registry."""
    return LLMRouter(
        adapters=adapters or {},  # type: ignore[arg-type]
        routing_table=routing_table or {},
        registry=registry or [],
    )


def _local_record() -> ModelRecord:
    return ModelRecord(
        address="llama-cpp/gpt-4",
        provider="llama-cpp",
        endpoint="http://localhost:8008",
        context_window=8192,
        supports_tools=True,
        supports_vision=False,
        cost_per_input_token=0.0,
        cost_per_output_token=0.0,
    )


def _cloud_record() -> ModelRecord:
    return ModelRecord(
        address="anthropic/claude-sonnet-4.6",
        provider="anthropic",
        endpoint="https://api.anthropic.com",
        context_window=200000,
        supports_tools=True,
        supports_vision=True,
        cost_per_input_token=0.000003,
        cost_per_output_token=0.000015,
    )


# ---------------------------------------------------------------------------
# Decision Order Tests (ADR-012)
# ---------------------------------------------------------------------------


class TestCascadeDefault:
    """Step 4: cascade default when no routing table or budget gate matches."""

    def test_no_routing_table_returns_default(self) -> None:
        router = _make_router(adapters={"test": object()})
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "test/model"

    def test_empty_routing_table_returns_default(self) -> None:
        router = _make_router(
            adapters={"test": object()},
            routing_table={},
        )
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "test/model"

    def test_phase_not_in_table_returns_default(self) -> None:
        router = _make_router(
            adapters={"test": object()},
            routing_table={
                "goal": ModelRoutingEntry(queen="anthropic/claude-sonnet-4.6"),
            },
        )
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "test/model"

    def test_caste_not_in_phase_returns_default(self) -> None:
        router = _make_router(
            adapters={"test": object(), "anthropic": object()},
            routing_table={
                "execute": ModelRoutingEntry(queen="anthropic/claude-sonnet-4.6"),
            },
        )
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "test/model"


class TestRoutingTable:
    """Step 2: routing table lookup."""

    def test_routing_table_match(self) -> None:
        router = _make_router(
            adapters={"anthropic": object(), "test": object()},
            routing_table={
                "execute": ModelRoutingEntry(
                    coder="anthropic/claude-sonnet-4.6",
                ),
            },
        )
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "anthropic/claude-sonnet-4.6"

    def test_routing_table_reviewer_to_local(self) -> None:
        router = _make_router(
            adapters={"llama-cpp": object(), "anthropic": object()},
            routing_table={
                "execute": ModelRoutingEntry(
                    reviewer="llama-cpp/gpt-4",
                ),
            },
        )
        result = router.route(
            "reviewer", "execute", 1, 5.0, "anthropic/claude-sonnet-4.6",
        )
        assert result == "llama-cpp/gpt-4"

    def test_routing_table_multiple_phases(self) -> None:
        router = _make_router(
            adapters={"anthropic": object(), "test": object()},
            routing_table={
                "execute": ModelRoutingEntry(coder="anthropic/claude-sonnet-4.6"),
                "goal": ModelRoutingEntry(queen="anthropic/claude-sonnet-4.6"),
            },
        )
        assert router.route("queen", "goal", 1, 5.0, "test/model") == "anthropic/claude-sonnet-4.6"
        assert router.route("coder", "execute", 1, 5.0, "test/model") == "anthropic/claude-sonnet-4.6"


class TestBudgetGate:
    """Step 1: budget gate — budget < $0.10 → cheapest model."""

    def test_budget_gate_selects_cheapest(self) -> None:
        router = _make_router(
            adapters={"llama-cpp": object(), "anthropic": object()},
            registry=[_local_record(), _cloud_record()],
            routing_table={
                "execute": ModelRoutingEntry(
                    coder="anthropic/claude-sonnet-4.6",
                ),
            },
        )
        result = router.route("coder", "execute", 1, 0.05, "anthropic/claude-sonnet-4.6")
        assert result == "llama-cpp/gpt-4"

    def test_budget_gate_at_threshold(self) -> None:
        """Budget exactly at $0.10 should NOT trigger the gate."""
        router = _make_router(
            adapters={"anthropic": object(), "llama-cpp": object()},
            registry=[_local_record(), _cloud_record()],
            routing_table={
                "execute": ModelRoutingEntry(
                    coder="anthropic/claude-sonnet-4.6",
                ),
            },
        )
        result = router.route("coder", "execute", 1, 0.10, "test/default")
        assert result == "anthropic/claude-sonnet-4.6"

    def test_budget_gate_no_registry_falls_to_default(self) -> None:
        router = _make_router(adapters={"test": object()})
        result = router.route("coder", "execute", 1, 0.05, "test/model")
        assert result == "test/model"


class TestAdapterFallback:
    """Step 3: adapter check — no adapter for routed model → cascade default."""

    def test_no_adapter_falls_back_to_default(self) -> None:
        router = _make_router(
            adapters={"test": object()},  # no "anthropic" adapter
            routing_table={
                "execute": ModelRoutingEntry(
                    coder="anthropic/claude-sonnet-4.6",
                ),
            },
        )
        result = router.route("coder", "execute", 1, 5.0, "test/model")
        assert result == "test/model"

    def test_budget_gate_cheapest_no_adapter_falls_to_default(self) -> None:
        """Budget gate selects cheapest, but if cheapest has no adapter, fall back."""
        # Registry has a model whose provider has no adapter
        orphan = ModelRecord(
            address="orphan/cheap",
            provider="orphan",
            endpoint="http://localhost:9999",
            context_window=4096,
            supports_tools=False,
            supports_vision=False,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
        )
        router = _make_router(
            adapters={"test": object()},  # no "orphan" adapter
            registry=[orphan],
        )
        # cheapest is None because orphan has no adapter
        result = router.route("coder", "execute", 1, 0.05, "test/model")
        assert result == "test/model"

    def test_cooled_provider_falls_back_to_default(self) -> None:
        router = _make_router(
            adapters={"anthropic": object(), "test": object()},
            routing_table={
                "execute": ModelRoutingEntry(
                    coder="anthropic/claude-sonnet-4.6",
                ),
            },
        )
        router._cooldown.record_failure("anthropic")
        router._cooldown.record_failure("anthropic")
        router._cooldown.record_failure("anthropic")

        result = router.route("coder", "execute", 1, 5.0, "test/model")

        assert result == "test/model"


class TestCheapestModel:
    """Cheapest model precomputation."""

    def test_cheapest_model_is_local(self) -> None:
        router = _make_router(
            adapters={"llama-cpp": object(), "anthropic": object()},
            registry=[_local_record(), _cloud_record()],
        )
        assert router._cheapest == "llama-cpp/gpt-4"

    def test_cheapest_model_filters_missing_adapters(self) -> None:
        router = _make_router(
            adapters={"anthropic": object()},  # no llama-cpp adapter
            registry=[_local_record(), _cloud_record()],
        )
        assert router._cheapest == "anthropic/claude-sonnet-4.6"

    def test_cheapest_model_empty_registry(self) -> None:
        router = _make_router(adapters={"test": object()}, registry=[])
        assert router._cheapest is None
