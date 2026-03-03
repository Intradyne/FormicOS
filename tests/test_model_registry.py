"""
Tests for FormicOS v0.6.0 Model Registry.

Covers:
- Parse valid config, create registry
- Reject unknown backend type
- Client caching: same ID returns same instance
- Subcaste resolution: heavy -> correct model
- Subcaste resolution: light with refine -> both models resolved
- Health check caching (same result within 30s)
- Unknown model_id raises KeyError
- list_models returns all entries
- VRAM budget calculation
- Anthropic backend: skip if no API key (clear error message)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.model_registry import ModelRegistry, SubcasteResolution, CircuitBreaker, CircuitState
from src.models import (
    FormicOSConfig,
    ModelBackendType,
    ModelRegistryEntry,
    SubcasteMapEntry,
    SubcasteTier,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


def _make_config(
    extra_models: dict | None = None,
    subcaste_overrides: dict | None = None,
    vram_gb: float = 32.0,
) -> FormicOSConfig:
    """Build a minimal FormicOSConfig with customizable model registry."""
    models = {
        "local/qwen3": ModelRegistryEntry(
            model_id="local/qwen3",
            type="autoregressive",
            backend=ModelBackendType.LLAMA_CPP,
            endpoint="http://localhost:8080/v1",
            model_string="Qwen3-30B-A3B",
            context_length=131072,
            vram_gb=25.6,
            supports_tools=True,
            supports_streaming=True,
        ),
        "local/bge-m3": ModelRegistryEntry(
            model_id="local/bge-m3",
            type="embedding",
            backend=ModelBackendType.LLAMA_CPP,
            endpoint="http://localhost:8081/v1",
            model_string="bge-m3",
            context_length=8192,
            vram_gb=2.0,
            supports_tools=False,
            supports_streaming=False,
        ),
        "ollama/mistral": ModelRegistryEntry(
            model_id="ollama/mistral",
            type="autoregressive",
            backend=ModelBackendType.OLLAMA,
            endpoint="http://localhost:11434/v1",
            model_string="mistral:7b",
            context_length=32768,
            vram_gb=4.5,
        ),
    }
    if extra_models:
        for k, v in extra_models.items():
            models[k] = v

    subcaste = subcaste_overrides or {
        "heavy": SubcasteMapEntry(primary="local/qwen3"),
        "balanced": SubcasteMapEntry(primary="local/qwen3"),
        "light": SubcasteMapEntry(primary="ollama/mistral"),
    }

    return FormicOSConfig(
        schema_version="0.6.0",
        identity={"name": "FormicOS", "version": "0.6.0"},
        hardware={"gpu": "rtx5090", "vram_gb": vram_gb, "vram_alert_threshold_gb": 28},
        inference={
            "endpoint": "http://localhost:8080/v1",
            "model": "Qwen3-30B-A3B",
            "model_alias": "gpt-4",
            "max_tokens_per_agent": 5000,
            "temperature": 0,
            "timeout_seconds": 120,
            "context_size": 131072,
        },
        embedding={
            "model": "BAAI/bge-m3",
            "endpoint": "http://localhost:8081/v1",
            "dimensions": 1024,
            "max_tokens": 8192,
            "batch_size": 32,
            "routing_model": "all-MiniLM-L6-v2",
        },
        routing={"tau": 0.35, "k_in": 3, "broadcast_fallback": True},
        convergence={
            "similarity_threshold": 0.95,
            "rounds_before_force_halt": 2,
            "path_diversity_warning_after": 3,
        },
        summarization={
            "epoch_window": 5,
            "max_epoch_tokens": 400,
            "max_agent_summary_tokens": 200,
            "tree_sitter_languages": ["python"],
        },
        temporal={
            "episodic_ttl_hours": 72,
            "stall_repeat_threshold": 3,
            "stall_window_minutes": 20,
            "tkg_max_tuples": 5000,
        },
        castes={"manager": {"system_prompt_file": "manager.md", "tools": []}},
        persistence={"session_dir": ".formicos/sessions", "autosave_interval_seconds": 30},
        approval_required=[],
        qdrant={
            "host": "localhost",
            "port": 6333,
            "grpc_port": 6334,
            "collections": {
                "project_docs": {"embedding": "bge-m3", "dimensions": 1024},
            },
        },
        mcp_gateway={"enabled": False},
        model_registry=models,
        skill_bank={
            "storage_file": ".formicos/skill_bank.json",
            "retrieval_top_k": 3,
            "dedup_threshold": 0.85,
            "evolution_interval": 5,
            "prune_zero_hit_after": 10,
        },
        subcaste_map=subcaste,
        teams={
            "max_teams_per_colony": 4,
            "team_summary_max_tokens": 200,
            "allow_dynamic_spawn": True,
        },
    )


@pytest.fixture
def config() -> FormicOSConfig:
    """Standard test config with 3 local models."""
    return _make_config()


@pytest.fixture
def registry(config: FormicOSConfig) -> ModelRegistry:
    """A freshly constructed ModelRegistry."""
    return ModelRegistry(config)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Parse valid config, create registry
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistryInit:
    def test_loads_all_models(self, registry: ModelRegistry) -> None:
        """Registry should contain every model from the config."""
        assert len(registry.model_ids) == 3
        assert "local/qwen3" in registry.model_ids
        assert "local/bge-m3" in registry.model_ids
        assert "ollama/mistral" in registry.model_ids

    def test_entries_are_model_registry_entry(self, registry: ModelRegistry) -> None:
        entry = registry.get_entry("local/qwen3")
        assert isinstance(entry, ModelRegistryEntry)
        assert entry.backend == ModelBackendType.LLAMA_CPP
        assert entry.context_length == 131072

    def test_model_id_backfilled(self) -> None:
        """If the entry has no model_id, it should be set from the dict key."""
        cfg = _make_config()
        # Wipe model_id on one entry to test backfill
        cfg.model_registry["local/qwen3"] = cfg.model_registry[
            "local/qwen3"
        ].model_copy(update={"model_id": ""})
        reg = ModelRegistry(cfg)
        entry = reg.get_entry("local/qwen3")
        assert entry.model_id == "local/qwen3"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Reject unknown backend type
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownBackend:
    def test_pydantic_rejects_invalid_backend(self) -> None:
        """ModelRegistryEntry should reject an unknown backend string."""
        with pytest.raises(Exception):
            ModelRegistryEntry(
                model_id="bad/model",
                type="autoregressive",
                backend="imaginary_backend",  # type: ignore[arg-type]
                endpoint="http://nowhere",
                context_length=1024,
            )


# ═══════════════════════════════════════════════════════════════════════════
# 3. Client caching: same ID returns same instance
# ═══════════════════════════════════════════════════════════════════════════


class TestClientCaching:
    def test_same_id_returns_same_client(self, registry: ModelRegistry) -> None:
        client_a, model_a = registry.get_client("local/qwen3")
        client_b, model_b = registry.get_client("local/qwen3")
        assert client_a is client_b
        assert model_a == model_b

    def test_different_ids_return_different_clients(
        self, registry: ModelRegistry
    ) -> None:
        client_a, _ = registry.get_client("local/qwen3")
        client_b, _ = registry.get_client("ollama/mistral")
        assert client_a is not client_b


# ═══════════════════════════════════════════════════════════════════════════
# 4. Subcaste resolution: heavy -> correct model
# ═══════════════════════════════════════════════════════════════════════════


class TestSubcasteResolution:
    @pytest.mark.asyncio
    async def test_heavy_resolves_to_qwen3(self, registry: ModelRegistry) -> None:
        subcaste_map = {
            "heavy": SubcasteMapEntry(primary="local/qwen3"),
            "balanced": SubcasteMapEntry(primary="local/qwen3"),
            "light": SubcasteMapEntry(primary="ollama/mistral"),
        }
        result = await registry.resolve_subcaste(SubcasteTier.HEAVY, subcaste_map)

        assert isinstance(result, SubcasteResolution)
        assert result.primary_model == "Qwen3-30B-A3B"
        assert result.primary_client is not None
        assert result.refine_client is None
        assert result.refine_model is None

    # ═══════════════════════════════════════════════════════════════════
    # 5. Subcaste resolution: light with refine -> both models resolved
    # ═══════════════════════════════════════════════════════════════════

    @pytest.mark.asyncio
    async def test_light_with_refine_resolves_both(
        self, registry: ModelRegistry
    ) -> None:
        subcaste_map = {
            "heavy": SubcasteMapEntry(primary="local/qwen3"),
            "balanced": SubcasteMapEntry(primary="local/qwen3"),
            "light": SubcasteMapEntry(
                primary="ollama/mistral",
                refine_with="local/qwen3",
            ),
        }
        result = await registry.resolve_subcaste(SubcasteTier.LIGHT, subcaste_map)

        assert isinstance(result, SubcasteResolution)
        assert result.primary_model == "mistral:7b"
        assert result.primary_client is not None
        assert result.refine_model == "Qwen3-30B-A3B"
        assert result.refine_client is not None
        # Primary and refine should be different client instances
        assert result.primary_client is not result.refine_client

    @pytest.mark.asyncio
    async def test_missing_tier_raises_key_error(
        self, registry: ModelRegistry
    ) -> None:
        subcaste_map = {
            "heavy": SubcasteMapEntry(primary="local/qwen3"),
        }
        with pytest.raises(KeyError, match="light"):
            await registry.resolve_subcaste(SubcasteTier.LIGHT, subcaste_map)

    @pytest.mark.asyncio
    async def test_subcaste_with_raw_dict_entry(
        self, registry: ModelRegistry
    ) -> None:
        """resolve_subcaste should accept raw dicts in the map."""
        subcaste_map = {
            "heavy": {"primary": "local/qwen3"},
        }
        result = await registry.resolve_subcaste(
            SubcasteTier.HEAVY, subcaste_map  # type: ignore[arg-type]
        )
        assert result.primary_model == "Qwen3-30B-A3B"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Health check caching (same result within 30s)
# ═══════════════════════════════════════════════════════════════════════════


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_returns_result(
        self, registry: ModelRegistry
    ) -> None:
        mock_response = httpx.Response(200)
        with patch("src.model_registry.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await registry.health_check("local/qwen3")

        assert result["healthy"] is True
        assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_health_check_closed_always_probes(
        self, registry: ModelRegistry
    ) -> None:
        """In CLOSED state (v0.7.3 circuit breaker), every call probes."""
        mock_response = httpx.Response(200)
        with patch("src.model_registry.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result1 = await registry.health_check("local/qwen3")
            result2 = await registry.health_check("local/qwen3")

        # Both calls probe (circuit breaker CLOSED allows all through)
        assert MockClient.call_count == 2
        assert result1["healthy"] == result2["healthy"]

    @pytest.mark.asyncio
    async def test_health_check_unhealthy_on_error(
        self, registry: ModelRegistry
    ) -> None:
        with patch("src.model_registry.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await registry.health_check("local/qwen3")

        assert result["healthy"] is False

    @pytest.mark.asyncio
    async def test_health_check_circuit_breaker_open_blocks_probe(
        self, registry: ModelRegistry
    ) -> None:
        """When circuit breaker is OPEN, health check should fail-fast."""
        # Force the breaker to OPEN state
        breaker = registry._breakers.get("local/qwen3")
        if breaker is None:
            breaker = CircuitBreaker()
            registry._breakers["local/qwen3"] = breaker

        # Simulate enough failures to open the breaker
        for _ in range(breaker.failure_threshold):
            breaker.record_failure()
        assert breaker.state == CircuitState.OPEN

        # Health check should return cached unhealthy without making HTTP call
        result = await registry.health_check("local/qwen3")
        assert result["healthy"] is False
        assert result.get("circuit_state") == CircuitState.OPEN


# ═══════════════════════════════════════════════════════════════════════════
# 7. Unknown model_id raises KeyError
# ═══════════════════════════════════════════════════════════════════════════


class TestUnknownModelId:
    def test_get_entry_raises_key_error(self, registry: ModelRegistry) -> None:
        with pytest.raises(KeyError, match="nonexistent/model"):
            registry.get_entry("nonexistent/model")

    def test_get_client_raises_key_error(self, registry: ModelRegistry) -> None:
        with pytest.raises(KeyError, match="nonexistent/model"):
            registry.get_client("nonexistent/model")

    def test_key_error_lists_registered_models(
        self, registry: ModelRegistry
    ) -> None:
        with pytest.raises(KeyError, match="local/qwen3"):
            registry.get_entry("nope")

    @pytest.mark.asyncio
    async def test_health_check_raises_key_error(
        self, registry: ModelRegistry
    ) -> None:
        with pytest.raises(KeyError):
            await registry.health_check("nonexistent/model")

    def test_has_model_false_for_unknown(self, registry: ModelRegistry) -> None:
        assert registry.has_model("nonexistent/model") is False


# ═══════════════════════════════════════════════════════════════════════════
# 8. list_models returns all entries
# ═══════════════════════════════════════════════════════════════════════════


class TestListModels:
    def test_returns_all_entries(self, registry: ModelRegistry) -> None:
        models = registry.list_models()
        assert len(models) == 3
        assert "local/qwen3" in models
        assert "local/bge-m3" in models
        assert "ollama/mistral" in models

    def test_entry_fields(self, registry: ModelRegistry) -> None:
        models = registry.list_models()
        qwen = models["local/qwen3"]
        assert qwen["backend"] == "llama_cpp"
        assert qwen["endpoint"] == "http://localhost:8080/v1"
        assert qwen["context_length"] == 131072
        assert qwen["vram_gb"] == 25.6
        assert qwen["supports_tools"] is True

    def test_default_status_unknown(self, registry: ModelRegistry) -> None:
        """Without a health check, status should be 'unknown'."""
        models = registry.list_models()
        for info in models.values():
            assert info["status"] == "unknown"

    @pytest.mark.asyncio
    async def test_status_reflects_health_check(
        self, registry: ModelRegistry
    ) -> None:
        mock_response = httpx.Response(200)
        with patch("src.model_registry.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(return_value=mock_response)
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            await registry.health_check("local/qwen3")

        models = registry.list_models()
        assert models["local/qwen3"]["status"] == "healthy"
        # Others still unknown
        assert models["local/bge-m3"]["status"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════
# 9. VRAM budget calculation
# ═══════════════════════════════════════════════════════════════════════════


class TestVRAMBudget:
    def test_sums_local_models(self, registry: ModelRegistry) -> None:
        budget = registry.get_vram_budget()
        # local/qwen3=25.6 + local/bge-m3=2.0 + ollama/mistral=4.5
        assert budget["allocated"] == 32.1
        assert budget["total_vram"] == 32.0
        assert budget["available"] == 0.0  # max(0, 32 - 32.1)
        assert len(budget["models"]) == 3

    def test_excludes_cloud_models(self) -> None:
        cfg = _make_config(
            extra_models={
                "cloud/openai": ModelRegistryEntry(
                    model_id="cloud/openai",
                    type="autoregressive",
                    backend=ModelBackendType.OPENAI_COMPATIBLE,
                    endpoint="https://api.openai.com/v1",
                    model_string="gpt-4",
                    context_length=128000,
                    vram_gb=None,
                ),
            }
        )
        reg = ModelRegistry(cfg)
        budget = reg.get_vram_budget()
        # Cloud model should not count toward VRAM
        model_ids = [m["model_id"] for m in budget["models"]]
        assert "cloud/openai" not in model_ids

    def test_available_positive_when_headroom(self) -> None:
        cfg = _make_config(vram_gb=64.0)
        reg = ModelRegistry(cfg)
        budget = reg.get_vram_budget()
        assert budget["total_vram"] == 64.0
        assert budget["available"] == pytest.approx(64.0 - 32.1, abs=0.01)

    def test_no_local_models_zero_allocated(self) -> None:
        """If only cloud models exist, allocated should be 0."""
        cfg = _make_config()
        # Replace all models with a cloud model
        cfg.model_registry.clear()
        cfg.model_registry["cloud/gpt4"] = ModelRegistryEntry(
            model_id="cloud/gpt4",
            type="autoregressive",
            backend=ModelBackendType.OPENAI_COMPATIBLE,
            endpoint="https://api.openai.com/v1",
            model_string="gpt-4",
            context_length=128000,
        )
        reg = ModelRegistry(cfg)
        budget = reg.get_vram_budget()
        assert budget["allocated"] == 0.0
        assert budget["available"] == 32.0


# ═══════════════════════════════════════════════════════════════════════════
# 10. Anthropic backend: skip if no API key (clear error message)
# ═══════════════════════════════════════════════════════════════════════════


class TestAnthropicBackend:
    def test_raises_runtime_error_without_api_key(self) -> None:
        cfg = _make_config(
            extra_models={
                "cloud/claude": ModelRegistryEntry(
                    model_id="cloud/claude",
                    type="autoregressive",
                    backend=ModelBackendType.ANTHROPIC_API,
                    endpoint="https://api.anthropic.com/v1",
                    model_string="claude-sonnet-4-5-20250929",
                    context_length=200000,
                    requires_approval=True,
                ),
            }
        )
        reg = ModelRegistry(cfg)

        # Ensure ANTHROPIC_API_KEY is unset
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
                reg.get_client("cloud/claude")

    def test_creates_client_with_api_key(self) -> None:
        cfg = _make_config(
            extra_models={
                "cloud/claude": ModelRegistryEntry(
                    model_id="cloud/claude",
                    type="autoregressive",
                    backend=ModelBackendType.ANTHROPIC_API,
                    endpoint="https://api.anthropic.com/v1",
                    model_string="claude-sonnet-4-5-20250929",
                    context_length=200000,
                    requires_approval=True,
                ),
            }
        )
        reg = ModelRegistry(cfg)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key-123"}):
            client, model_str = reg.get_client("cloud/claude")

        assert model_str == "claude-sonnet-4-5-20250929"
        assert client is not None

    def test_init_does_not_fail_for_anthropic_without_key(self) -> None:
        """Registry init should succeed even without ANTHROPIC_API_KEY.
        The error should only happen on get_client()."""
        cfg = _make_config(
            extra_models={
                "cloud/claude": ModelRegistryEntry(
                    model_id="cloud/claude",
                    type="autoregressive",
                    backend=ModelBackendType.ANTHROPIC_API,
                    context_length=200000,
                ),
            }
        )
        # This must NOT raise
        reg = ModelRegistry(cfg)
        assert reg.has_model("cloud/claude") is True


# ═══════════════════════════════════════════════════════════════════════════
# Backend dispatch edge cases
# ═══════════════════════════════════════════════════════════════════════════


class TestBackendDispatch:
    def test_llama_cpp_model_string_default(self) -> None:
        """llama_cpp without model_string should default to 'local-model'."""
        cfg = _make_config()
        cfg.model_registry["local/qwen3"] = cfg.model_registry[
            "local/qwen3"
        ].model_copy(update={"model_string": None})
        reg = ModelRegistry(cfg)
        _, model_str = reg.get_client("local/qwen3")
        assert model_str == "local-model"

    def test_llama_cpp_without_endpoint_raises(self) -> None:
        cfg = _make_config()
        cfg.model_registry["local/qwen3"] = cfg.model_registry[
            "local/qwen3"
        ].model_copy(update={"endpoint": None})
        reg = ModelRegistry(cfg)
        with pytest.raises(ValueError, match="requires an endpoint"):
            reg.get_client("local/qwen3")

    def test_ollama_default_endpoint(self) -> None:
        """Ollama without endpoint should use default localhost:11434."""
        cfg = _make_config()
        cfg.model_registry["ollama/mistral"] = cfg.model_registry[
            "ollama/mistral"
        ].model_copy(update={"endpoint": None})
        reg = ModelRegistry(cfg)
        client, model_str = reg.get_client("ollama/mistral")
        assert model_str == "mistral:7b"
        assert client is not None

    def test_openai_compatible_requires_endpoint(self) -> None:
        cfg = _make_config(
            extra_models={
                "cloud/oai": ModelRegistryEntry(
                    model_id="cloud/oai",
                    type="autoregressive",
                    backend=ModelBackendType.OPENAI_COMPATIBLE,
                    endpoint=None,
                    model_string="gpt-4",
                    context_length=128000,
                ),
            }
        )
        reg = ModelRegistry(cfg)
        with pytest.raises(ValueError, match="requires an endpoint"):
            reg.get_client("cloud/oai")

    def test_openai_compatible_with_endpoint(self) -> None:
        cfg = _make_config(
            extra_models={
                "cloud/oai": ModelRegistryEntry(
                    model_id="cloud/oai",
                    type="autoregressive",
                    backend=ModelBackendType.OPENAI_COMPATIBLE,
                    endpoint="https://api.openai.com/v1",
                    model_string="gpt-4",
                    context_length=128000,
                ),
            }
        )
        reg = ModelRegistry(cfg)
        client, model_str = reg.get_client("cloud/oai")
        assert model_str == "gpt-4"
        assert client is not None
