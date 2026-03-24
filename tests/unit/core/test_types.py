"""Unit tests for formicos.core.types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    CasteSlot,
    ColonyConfig,
    InputSource,
    LLMResponse,
    ModelRecord,
    NodeAddress,
    NodeType,
    VectorDocument,
)

# ---------------------------------------------------------------------------
# NodeAddress
# ---------------------------------------------------------------------------


class TestNodeAddress:
    def test_workspace_id(self) -> None:
        addr = NodeAddress(segments=("ws1",))
        assert addr.workspace_id == "ws1"
        assert addr.thread_id is None
        assert addr.colony_id is None

    def test_thread_id(self) -> None:
        addr = NodeAddress(segments=("ws1", "th1"))
        assert addr.workspace_id == "ws1"
        assert addr.thread_id == "th1"
        assert addr.colony_id is None

    def test_colony_id(self) -> None:
        addr = NodeAddress(segments=("ws1", "th1", "col1"))
        assert addr.workspace_id == "ws1"
        assert addr.thread_id == "th1"
        assert addr.colony_id == "col1"

    def test_parent_returns_parent(self) -> None:
        addr = NodeAddress(segments=("ws1", "th1", "col1"))
        parent = addr.parent()
        assert parent is not None
        assert parent.segments == ("ws1", "th1")

    def test_parent_of_root_is_none(self) -> None:
        addr = NodeAddress(segments=("ws1",))
        assert addr.parent() is None

    def test_parent_of_empty_is_none(self) -> None:
        addr = NodeAddress(segments=())
        assert addr.parent() is None
        assert addr.workspace_id is None

    def test_frozen_rejects_mutation(self) -> None:
        addr = NodeAddress(segments=("ws1",))
        with pytest.raises(ValidationError):
            addr.segments = ("ws2",)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# NodeType enum
# ---------------------------------------------------------------------------


class TestNodeType:
    def test_values(self) -> None:
        assert NodeType.system == "system"
        assert NodeType.workspace == "workspace"
        assert NodeType.thread == "thread"
        assert NodeType.colony == "colony"
        assert NodeType.round == "round"
        assert NodeType.turn == "turn"


# ---------------------------------------------------------------------------
# Frozen models reject mutation
# ---------------------------------------------------------------------------


class TestFrozenModels:
    def test_llm_response_frozen(self) -> None:
        resp = LLMResponse(
            content="hello",
            tool_calls=[],
            input_tokens=10,
            output_tokens=5,
            model="test-model",
            stop_reason="end_turn",
        )
        with pytest.raises(ValidationError):
            resp.content = "changed"  # type: ignore[misc]

    def test_vector_document_frozen(self) -> None:
        doc = VectorDocument(id="d1", content="text", metadata={"k": "v"})
        with pytest.raises(ValidationError):
            doc.id = "d2"  # type: ignore[misc]

    def test_agent_config_frozen(self) -> None:
        recipe = CasteRecipe(
            name="coder",
            system_prompt="You are a coder.",
            temperature=0.0,
            tools=["read_file"],
            max_tokens=4096,
        )
        agent = AgentConfig(
            id="a1", name="Agent 1", caste="coder", model="m1", recipe=recipe
        )
        with pytest.raises(ValidationError):
            agent.name = "Agent 2"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CasteRecipe and ModelRecord validation
# ---------------------------------------------------------------------------


class TestCasteRecipe:
    def test_valid_recipe(self) -> None:
        recipe = CasteRecipe(
            name="coder",
            system_prompt="prompt",
            temperature=0.7,
            tools=["tool1", "tool2"],
            max_tokens=2048,
        )
        assert recipe.name == "coder"
        assert recipe.model_override is None

    def test_recipe_with_override(self) -> None:
        recipe = CasteRecipe(
            name="reviewer",
            system_prompt="prompt",
            temperature=0.0,
            model_override="anthropic/claude-3",
            tools=[],
            max_tokens=1024,
        )
        assert recipe.model_override == "anthropic/claude-3"


class TestModelRecord:
    def test_valid_model_record(self) -> None:
        rec = ModelRecord(
            address="anthropic/claude-3",
            provider="anthropic",
            context_window=200000,
            supports_tools=True,
        )
        assert rec.status == "available"
        assert rec.supports_vision is False
        assert rec.endpoint is None
        assert rec.cost_per_input_token is None

    def test_model_record_all_fields(self) -> None:
        rec = ModelRecord(
            address="ollama/llama3",
            provider="ollama",
            endpoint="http://localhost:11434",
            api_key_env="OLLAMA_KEY",
            context_window=8192,
            supports_tools=False,
            supports_vision=True,
            cost_per_input_token=0.0,
            cost_per_output_token=0.0,
            status="unavailable",
        )
        assert rec.supports_vision is True
        assert rec.status == "unavailable"


class TestColonyConfig:
    def test_valid_config(self) -> None:
        cfg = ColonyConfig(
            task="Do something",
            castes=[
                CasteSlot(caste="coder", tier="standard", count=1),
                CasteSlot(caste="reviewer", tier="standard", count=1),
            ],
            max_rounds=5,
            budget_limit=1.0,
            strategy="stigmergic",
        )
        assert cfg.context_budget_tokens is None
        assert cfg.strategy == "stigmergic"


# ---------------------------------------------------------------------------
# InputSource (ADR-033)
# ---------------------------------------------------------------------------


class TestInputSource:
    def test_create_colony_type(self) -> None:
        src = InputSource(type="colony", colony_id="colony-abc", summary="result text")
        assert src.type == "colony"
        assert src.colony_id == "colony-abc"
        assert src.summary == "result text"

    def test_default_summary_empty(self) -> None:
        src = InputSource(type="colony", colony_id="colony-abc")
        assert src.summary == ""

    def test_frozen(self) -> None:
        src = InputSource(type="colony", colony_id="colony-abc")
        with pytest.raises(ValidationError):
            src.colony_id = "changed"  # type: ignore[misc]
