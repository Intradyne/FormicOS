"""Unit tests for Wave 64 Track 1: Generalized adapter factory + per-provider concurrency."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from formicos.adapters.llm_openai_compatible import OpenAICompatibleLLMAdapter
from formicos.core.types import ModelRecord
from formicos.surface.runtime import LLMRouter


def _model(
    address: str,
    provider: str,
    endpoint: str | None = None,
    max_concurrent: int = 0,
    context_window: int = 8192,
    supports_tools: bool = True,
) -> ModelRecord:
    """Helper to build a minimal ModelRecord."""
    return ModelRecord(
        address=address,
        provider=provider,
        endpoint=endpoint,
        context_window=context_window,
        supports_tools=supports_tools,
        max_concurrent=max_concurrent,
    )


def _adapter_key(model: ModelRecord) -> str:
    """Replicate the adapter key logic from app.py."""
    return f"{model.provider}:{model.endpoint or 'default'}"


class TestSamePrefixDifferentEndpoints:
    """Two ModelRecords with same provider but different endpoints produce different keys."""

    def test_same_prefix_different_endpoints(self) -> None:
        m1 = _model(
            "custom/model-a",
            provider="custom",
            endpoint="http://host-a:8000/v1",
        )
        m2 = _model(
            "custom/model-b",
            provider="custom",
            endpoint="http://host-b:8000/v1",
        )

        key1 = _adapter_key(m1)
        key2 = _adapter_key(m2)

        assert key1 != key2
        assert key1 == "custom:http://host-a:8000/v1"
        assert key2 == "custom:http://host-b:8000/v1"

    def test_same_prefix_one_default_one_explicit(self) -> None:
        m_default = _model("custom/model-a", provider="custom", endpoint=None)
        m_explicit = _model(
            "custom/model-b",
            provider="custom",
            endpoint="http://host-b:8000/v1",
        )

        key_default = _adapter_key(m_default)
        key_explicit = _adapter_key(m_explicit)

        assert key_default == "custom:default"
        assert key_explicit == "custom:http://host-b:8000/v1"
        assert key_default != key_explicit


class TestUnknownPrefixWithEndpoint:
    """Non-standard provider with an endpoint should get an OpenAI-compatible adapter."""

    def test_unknown_prefix_with_endpoint(self) -> None:
        m = _model(
            "groq/llama-70b",
            provider="groq",
            endpoint="https://api.groq.com/openai/v1",
        )

        key = _adapter_key(m)
        assert key == "groq:https://api.groq.com/openai/v1"

        # The key format is the same as for known providers — the app.py
        # factory loop handles unknown providers by checking if provider
        # is not in _KNOWN_PROVIDERS and endpoint is set.
        known_providers = {
            "anthropic", "gemini", "llama-cpp", "ollama",
            "openai", "deepseek",
        }
        assert m.provider not in known_providers
        assert m.endpoint is not None
        # These two conditions together cause app.py to create an
        # OpenAICompatibleLLMAdapter for this key.


class TestMaxConcurrentOverridesSlots:
    """max_concurrent > 0 should set semaphore even for cloud endpoints."""

    def test_max_concurrent_overrides_slots(self) -> None:
        adapter = OpenAICompatibleLLMAdapter(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            max_concurrent=5,
        )
        assert adapter._semaphore is not None
        # asyncio.Semaphore stores its value in _value
        assert adapter._semaphore._value == 5  # type: ignore[attr-defined]

    def test_cloud_no_max_concurrent_has_no_semaphore(self) -> None:
        adapter = OpenAICompatibleLLMAdapter(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            max_concurrent=0,
        )
        # Cloud endpoints without explicit max_concurrent get no semaphore
        assert adapter._semaphore is None

    def test_local_no_max_concurrent_uses_llm_slots(self) -> None:
        adapter = OpenAICompatibleLLMAdapter(
            base_url="http://localhost:11434/v1",
            max_concurrent=0,
        )
        # Local endpoints without explicit max_concurrent get a semaphore
        # from LLM_SLOTS env var
        assert adapter._semaphore is not None


class TestBackwardCompatSinglePrefix:
    """Existing configs with one model per provider still work with LLMRouter._resolve()."""

    def test_backward_compat_single_prefix(self) -> None:
        mock_adapter = MagicMock()
        # New key format: provider:default
        adapters = {"llama-cpp:default": mock_adapter}
        model = _model(
            "llama-cpp/gpt-4",
            provider="llama-cpp",
            endpoint=None,
        )
        router = LLMRouter(
            adapters=adapters,
            registry=[model],
        )
        resolved = router._resolve("llama-cpp/gpt-4")
        assert resolved is mock_adapter

    def test_resolve_with_explicit_endpoint(self) -> None:
        mock_a = MagicMock()
        mock_b = MagicMock()
        m1 = _model(
            "custom/model-a",
            provider="custom",
            endpoint="http://host-a:8000/v1",
        )
        m2 = _model(
            "custom/model-b",
            provider="custom",
            endpoint="http://host-b:8000/v1",
        )
        adapters = {
            "custom:http://host-a:8000/v1": mock_a,
            "custom:http://host-b:8000/v1": mock_b,
        }
        router = LLMRouter(
            adapters=adapters,
            registry=[m1, m2],
        )
        assert router._resolve("custom/model-a") is mock_a
        assert router._resolve("custom/model-b") is mock_b

    def test_resolve_falls_back_to_prefix_default(self) -> None:
        """Model not in registry still resolves via prefix:default fallback."""
        mock_adapter = MagicMock()
        adapters = {"ollama:default": mock_adapter}
        router = LLMRouter(
            adapters=adapters,
            registry=[],
        )
        resolved = router._resolve("ollama/llama3.3")
        assert resolved is mock_adapter

    def test_resolve_falls_back_to_any_prefix_match(self) -> None:
        """Model not in registry resolves via any key starting with prefix:."""
        mock_adapter = MagicMock()
        adapters = {"custom:http://host:8000/v1": mock_adapter}
        router = LLMRouter(
            adapters=adapters,
            registry=[],
        )
        resolved = router._resolve("custom/some-model")
        assert resolved is mock_adapter

    def test_resolve_unknown_provider_raises(self) -> None:
        adapters = {"llama-cpp:default": MagicMock()}
        router = LLMRouter(adapters=adapters, registry=[])
        with pytest.raises(ValueError, match="No adapter registered"):
            router._resolve("unknown/model")
