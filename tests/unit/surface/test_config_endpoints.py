"""Unit tests for formicos.surface.config_endpoints and model_registry_view."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from formicos.core.events import WorkspaceConfigSnapshot, WorkspaceCreated
from formicos.core.settings import (
    EmbeddingConfig,
    GovernanceConfig,
    ModelDefaults,
    ModelsConfig,
    RoutingConfig,
    SystemConfig,
    SystemSettings,
)
from formicos.core.types import ModelRecord
from formicos.surface.config_endpoints import (
    get_workspace_config,
    update_model_assignment,
    update_workspace_config,
)
from formicos.surface.model_registry_view import (
    cloud_endpoints_view,
    model_defaults_view,
    model_registry_view,
)
from formicos.surface.projections import ProjectionStore

NOW = datetime.now(UTC)


def _make_settings(registry: list[ModelRecord] | None = None) -> SystemSettings:
    if registry is None:
        registry = [
            ModelRecord(
                address="anthropic/claude-sonnet-4.6",
                provider="anthropic",
                endpoint="https://api.anthropic.com",
                api_key_env="ANTHROPIC_API_KEY",
                context_window=200000,
                supports_tools=True,
            ),
            ModelRecord(
                address="ollama/llama3.3",
                provider="ollama",
                context_window=128000,
                supports_tools=True,
            ),
        ]
    return SystemSettings(
        system=SystemConfig(host="0.0.0.0", port=8080, data_dir="./data"),
        models=ModelsConfig(
            defaults=ModelDefaults(
                queen="anthropic/claude-sonnet-4.6",
                coder="anthropic/claude-sonnet-4.6",
                reviewer="anthropic/claude-sonnet-4.6",
                researcher="anthropic/claude-sonnet-4.6",
                archivist="anthropic/claude-haiku-4.5",
            ),
            registry=registry,
        ),
        embedding=EmbeddingConfig(model="test-model", dimensions=384),
        governance=GovernanceConfig(
            max_rounds_per_colony=25,
            stall_detection_window=3,
            convergence_threshold=0.95,
            default_budget_per_colony=1.0,
        ),
        routing=RoutingConfig(
            default_strategy="stigmergic",
            tau_threshold=0.35,
            k_in_cap=5,
            pheromone_decay_rate=0.1,
            pheromone_reinforce_rate=0.3,
        ),
    )


def _seed_store() -> ProjectionStore:
    store = ProjectionStore()
    store.apply(WorkspaceCreated(
        seq=1, timestamp=NOW, address="ws1", name="ws1",
        config=WorkspaceConfigSnapshot(budget=10.0, strategy="stigmergic"),
    ))
    return store


class _MockEventStore:
    """Minimal mock implementing EventStorePort.append."""

    def __init__(self) -> None:
        self._seq = 0
        self.events: list[object] = []

    async def append(self, event: object) -> int:
        self._seq += 1
        self.events.append(event)
        return self._seq


class TestUpdateWorkspaceConfig:
    @pytest.mark.anyio()
    async def test_updates_config_field(self) -> None:
        store = _seed_store()
        es = _MockEventStore()
        result = await update_workspace_config("ws1", "budget", "20.0", es, store)
        assert result["status"] == "updated"
        assert store.workspaces["ws1"].config["budget"] == "20.0"

    @pytest.mark.anyio()
    async def test_returns_error_for_missing_workspace(self) -> None:
        store = ProjectionStore()
        es = _MockEventStore()
        result = await update_workspace_config("missing", "budget", "5.0", es, store)
        assert "error" in result

    @pytest.mark.anyio()
    async def test_delete_config_field(self) -> None:
        store = _seed_store()
        store.workspaces["ws1"].config["custom"] = "value"
        es = _MockEventStore()
        result = await update_workspace_config("ws1", "custom", None, es, store)
        assert result["status"] == "updated"
        assert "custom" not in store.workspaces["ws1"].config


class TestUpdateModelAssignment:
    @pytest.mark.anyio()
    async def test_emits_assignment_event(self) -> None:
        store = _seed_store()
        es = _MockEventStore()
        result = await update_model_assignment(
            "ws1", "coder", "ollama/llama3.3", es, store,
            old_model="anthropic/claude-sonnet-4.6",
        )
        assert result["status"] == "updated"
        assert result["caste"] == "coder"
        assert len(es.events) == 1


class TestGetWorkspaceConfig:
    def test_returns_none_for_missing(self) -> None:
        store = ProjectionStore()
        assert get_workspace_config(store, "missing") is None

    def test_returns_config(self) -> None:
        store = _seed_store()
        config = get_workspace_config(store, "ws1")
        assert config is not None
        assert config["id"] == "ws1"


class TestModelRegistryView:
    def test_returns_all_models(self) -> None:
        settings = _make_settings()
        view = model_registry_view(settings)
        assert len(view) == 2
        assert view[0]["address"] == "anthropic/claude-sonnet-4.6"
        assert view[1]["address"] == "ollama/llama3.3"

    def test_derives_no_key_status(self) -> None:
        settings = _make_settings()
        view = model_registry_view(settings)
        # ANTHROPIC_API_KEY likely not set in test env
        anthropic_model = view[0]
        assert anthropic_model["status"] in ("no_key", "available")


class TestCloudEndpointsView:
    def test_groups_by_provider(self) -> None:
        settings = _make_settings()
        endpoints = cloud_endpoints_view(settings)
        providers = [e["provider"] for e in endpoints]
        assert "anthropic" in providers
        assert "ollama" in providers
        assert len(endpoints) == 2


class TestModelDefaultsView:
    def test_returns_defaults(self) -> None:
        settings = _make_settings()
        defaults = model_defaults_view(settings)
        assert defaults["queen"] == "anthropic/claude-sonnet-4.6"
        assert defaults["archivist"] == "anthropic/claude-haiku-4.5"
