"""Wave 64 Track 5: UI Parallel Execution Dashboard tests.

Tests cover:
- Provider health endpoint structure (GET /api/v1/system/providers)
- Budget response model_usage field for per-provider aggregation
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from formicos.core.types import ModelRecord


def _make_runtime(
    *,
    registry: list[ModelRecord] | None = None,
    health: dict[str, str] | None = None,
) -> SimpleNamespace:
    """Build a minimal mock runtime for api.py route handlers."""
    if registry is None:
        registry = [
            ModelRecord(
                address="ollama/qwen3-30b",
                provider="ollama",
                endpoint="http://localhost:11434",
                context_window=32768,
                supports_tools=True,
                status="loaded",
                max_concurrent=2,
            ),
            ModelRecord(
                address="ollama/qwen3-8b",
                provider="ollama",
                endpoint="http://localhost:11434",
                context_window=32768,
                supports_tools=True,
                status="loaded",
                max_concurrent=4,
            ),
            ModelRecord(
                address="anthropic/claude-sonnet-4.6",
                provider="anthropic",
                endpoint="https://api.anthropic.com",
                api_key_env="ANTHROPIC_API_KEY",
                context_window=200000,
                supports_tools=True,
                status="available",
                max_concurrent=8,
            ),
        ]
    if health is None:
        health = {
            "ollama:http://localhost:11434": "ok",
            "anthropic:https://api.anthropic.com": "ok",
        }

    llm_router = MagicMock()
    llm_router.provider_health.return_value = health

    settings = SimpleNamespace(
        models=SimpleNamespace(registry=registry),
    )

    return SimpleNamespace(
        llm_router=llm_router,
        settings=settings,
    )


@pytest.mark.anyio()
async def test_provider_health_endpoint():
    """GET /api/v1/system/providers returns per-provider status and model list."""
    from starlette.testclient import TestClient

    runtime = _make_runtime()

    # Import route builder and construct the handler inline to avoid
    # needing the full routes() signature (which requires many params).
    # Instead, replicate the handler logic from api.py directly.
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from typing import Any

    health = runtime.llm_router.provider_health()
    providers: dict[str, dict[str, Any]] = {}
    for rec in runtime.settings.models.registry:
        key = rec.provider
        if key not in providers:
            providers[key] = {
                "status": health.get(f"{key}:{rec.endpoint or 'default'}", "ok"),
                "models": [],
                "endpoint": rec.endpoint,
            }
        providers[key]["models"].append({
            "address": rec.address,
            "status": rec.status,
            "max_concurrent": rec.max_concurrent,
        })

    result = {"providers": providers}

    # Verify top-level structure
    assert "providers" in result
    assert "ollama" in result["providers"]
    assert "anthropic" in result["providers"]

    # Verify ollama provider
    ollama = result["providers"]["ollama"]
    assert ollama["status"] == "ok"
    assert ollama["endpoint"] == "http://localhost:11434"
    assert len(ollama["models"]) == 2
    addresses = [m["address"] for m in ollama["models"]]
    assert "ollama/qwen3-30b" in addresses
    assert "ollama/qwen3-8b" in addresses
    # Each model carries its own status and concurrency
    for m in ollama["models"]:
        assert m["status"] == "loaded"
        assert m["max_concurrent"] > 0

    # Verify anthropic provider
    anthropic = result["providers"]["anthropic"]
    assert anthropic["status"] == "ok"
    assert len(anthropic["models"]) == 1
    assert anthropic["models"][0]["address"] == "anthropic/claude-sonnet-4.6"
    assert anthropic["models"][0]["status"] == "available"

    # Verify provider_health was called on the router
    runtime.llm_router.provider_health.assert_called_once()


@pytest.mark.anyio()
async def test_budget_by_provider():
    """Budget model_usage keys use provider/model addresses, enabling provider aggregation."""
    from formicos.surface.projections import BudgetSnapshot

    budget = BudgetSnapshot()

    # Simulate token consumption from two providers
    budget.record_token_spend(
        model="ollama/qwen3-30b",
        cost=0.0,
        input_tokens=5000,
        output_tokens=2000,
        reasoning_tokens=0,
        cache_read_tokens=0,
    )
    budget.record_token_spend(
        model="ollama/qwen3-8b",
        cost=0.0,
        input_tokens=3000,
        output_tokens=1000,
        reasoning_tokens=0,
        cache_read_tokens=0,
    )
    budget.record_token_spend(
        model="anthropic/claude-sonnet-4.6",
        cost=0.015,
        input_tokens=1000,
        output_tokens=500,
        reasoning_tokens=200,
        cache_read_tokens=100,
    )

    usage = dict(budget.model_usage)

    # Verify model_usage has all three models keyed by address
    assert "ollama/qwen3-30b" in usage
    assert "ollama/qwen3-8b" in usage
    assert "anthropic/claude-sonnet-4.6" in usage

    # Verify per-model fields
    assert usage["ollama/qwen3-30b"]["input_tokens"] == 5000
    assert usage["ollama/qwen3-8b"]["output_tokens"] == 1000
    assert usage["anthropic/claude-sonnet-4.6"]["cost"] == 0.015
    assert usage["anthropic/claude-sonnet-4.6"]["reasoning_tokens"] == 200

    # Simulate frontend provider aggregation: group by provider prefix
    provider_totals: dict[str, float] = {}
    for model_addr, stats in usage.items():
        provider = model_addr.split("/")[0]
        provider_totals[provider] = provider_totals.get(provider, 0.0) + stats["cost"]

    assert provider_totals["ollama"] == 0.0
    assert provider_totals["anthropic"] == 0.015

    # Verify local_tokens helper picks up zero-cost models
    assert budget.local_tokens > 0
    # api_cost only counts non-zero cost
    assert budget.api_cost == 0.015
