"""
Tests for FormicOS v0.9.0 Context Window Circuit Breaker.

Validates the hard pre-execution token check that prevents LLM requests
when assembled messages exceed the agent's context_length.

Covers:
  - ContextExceededError raised for oversized messages
  - 10,000-word string triggers halt without LLM request
  - Messages within limit pass through to LLM
  - Orchestrator converts ContextExceededError into [SYSTEM_HALT] output
  - _check_context_limit integration with _enforce_token_budget
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents import Agent, ContextExceededError


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_agent(
    context_length: int = 8192,
    agent_id: str = "test-agent",
) -> Agent:
    """Build a minimal Agent with a mock LLM client."""
    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock()

    agent = Agent(
        id=agent_id,
        caste="coder",
        system_prompt="You are a test agent.",
        model_client=mock_client,
        model_name="test-model",
        tools=[],
        config={
            "context_length": context_length,
            "workspace_root": "./workspace/test",
            "max_tokens": 2000,
        },
    )
    return agent


# ── ContextExceededError ─────────────────────────────────────────────────


class TestContextExceededError:
    """ContextExceededError is a proper exception class."""

    def test_is_exception(self):
        assert issubclass(ContextExceededError, Exception)

    def test_carries_message(self):
        err = ContextExceededError("too many tokens")
        assert "too many tokens" in str(err)


# ── _check_context_limit ─────────────────────────────────────────────────


class TestCheckContextLimit:
    """Unit tests for Agent._check_context_limit()."""

    def test_within_limit_passes(self):
        """Messages within the context window do not raise."""
        agent = _make_agent(context_length=8192)
        messages = [
            {"role": "system", "content": "Short system prompt."},
            {"role": "user", "content": "Short user message."},
        ]
        # Should not raise
        agent._check_context_limit(messages)

    def test_exceeds_limit_raises(self):
        """Messages exceeding the context window raise ContextExceededError."""
        agent = _make_agent(context_length=100)  # 100 tokens = ~400 chars
        messages = [
            {"role": "system", "content": "x" * 200},
            {"role": "user", "content": "y" * 300},  # total 500 chars = ~125 tokens > 100
        ]
        with pytest.raises(ContextExceededError) as exc_info:
            agent._check_context_limit(messages)

        assert "125" in str(exc_info.value)  # estimated tokens
        assert "100" in str(exc_info.value)  # context_length

    def test_exact_limit_passes(self):
        """Messages exactly at the context window pass (not strictly greater)."""
        agent = _make_agent(context_length=100)  # 100 tokens = 400 chars
        messages = [
            {"role": "system", "content": "a" * 400},  # exactly 100 tokens
        ]
        # Should not raise (100 <= 100)
        agent._check_context_limit(messages)

    def test_empty_content_treated_as_zero(self):
        """Messages with None or empty content are counted as zero."""
        agent = _make_agent(context_length=100)
        messages = [
            {"role": "system", "content": None},
            {"role": "user", "content": ""},
        ]
        agent._check_context_limit(messages)

    def test_error_includes_agent_id(self):
        """Error message includes the agent's ID."""
        agent = _make_agent(context_length=10, agent_id="breaker-agent")
        messages = [
            {"role": "user", "content": "x" * 1000},
        ]
        with pytest.raises(ContextExceededError, match="breaker-agent"):
            agent._check_context_limit(messages)


# ── 10,000-Word String Integration ──────────────────────────────────────


class TestTenThousandWordHalt:
    """The critical test: a 10,000-word string triggers SYSTEM_HALT
    without ever calling the LLM backend."""

    @pytest.mark.asyncio
    async def test_10k_word_string_raises_without_llm_call(self):
        """A 10,000-word payload exceeds 8192-token context and raises
        ContextExceededError before the LLM request is sent."""
        agent = _make_agent(context_length=8192)

        # 10,000 words at ~5 chars/word + spaces ≈ 60,000 chars ≈ 15,000 tokens
        giant_text = " ".join(["overflowed"] * 10_000)

        with pytest.raises(ContextExceededError):
            await agent.execute(
                context=giant_text,
                round_goal="Process this massive dataset",
            )

        # The LLM client should NEVER have been called
        agent.model_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_normal_payload_calls_llm(self):
        """A normal-sized payload does NOT raise and DOES call the LLM."""
        agent = _make_agent(context_length=8192)

        # Set up mock streaming response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta.content = "Hello from LLM"
        mock_chunk.choices[0].delta.tool_calls = None
        mock_chunk.choices[0].finish_reason = "stop"
        mock_chunk.usage = MagicMock()
        mock_chunk.usage.total_tokens = 50
        mock_chunk.usage.prompt_tokens = 30
        mock_chunk.usage.completion_tokens = 20

        async def mock_stream(**kwargs):
            yield mock_chunk

        agent.model_client.chat.completions.create = MagicMock(
            return_value=mock_stream()
        )

        output = await agent.execute(
            context="Brief context for the task.",
            round_goal="Do a small thing",
        )

        assert output.output  # Got some output
        # LLM was actually called (not blocked by circuit breaker)


# ── Orchestrator Integration ─────────────────────────────────────────────


class TestOrchestratorContextHalt:
    """Orchestrator._execute_agent catches ContextExceededError and
    returns the [SYSTEM_HALT] message."""

    @pytest.mark.asyncio
    async def test_orchestrator_returns_system_halt(self):
        """When an agent raises ContextExceededError, the orchestrator
        returns [SYSTEM_HALT] in the AgentOutput."""
        from src.orchestrator import Orchestrator
        from src.models import Topology

        # Build a minimal orchestrator with mocked internals
        mock_ctx = MagicMock()
        mock_ctx.assemble_agent_context.return_value = "x" * 200_000  # huge context

        orch = Orchestrator.__new__(Orchestrator)
        orch.ctx = mock_ctx
        orch._session_id = "test-session"
        orch._round_history = []
        orch._agent_timeout = 60
        orch.audit = None

        # Create agent that will breach the limit
        agent = _make_agent(context_length=8192, agent_id="overflow-agent")

        topology = Topology(
            edges=[],
            execution_order=["overflow-agent"],
            density=0.0,
            isolated_agents=[],
        )

        agent_id, output = await orch._execute_agent(
            agent=agent,
            topology=topology,
            agent_outputs={},
            round_goal="Test the breaker",
            skill_context=None,
            callbacks=None,
        )

        assert agent_id == "overflow-agent"
        assert "[SYSTEM_HALT]" in output.output
        assert "Truncate your slice requests" in output.output

        # LLM was never called
        agent.model_client.chat.completions.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_orchestrator_logs_context_exceeded(self):
        """Orchestrator logs the context_exceeded event to audit."""
        from src.orchestrator import Orchestrator
        from src.models import Topology

        mock_ctx = MagicMock()
        mock_ctx.assemble_agent_context.return_value = "x" * 200_000

        mock_audit = MagicMock()

        orch = Orchestrator.__new__(Orchestrator)
        orch.ctx = mock_ctx
        orch._session_id = "test-session"
        orch._round_history = []
        orch._agent_timeout = 60
        orch.audit = mock_audit

        agent = _make_agent(context_length=8192, agent_id="audit-agent")

        topology = Topology(
            edges=[],
            execution_order=["audit-agent"],
            density=0.0,
            isolated_agents=[],
        )

        await orch._execute_agent(
            agent=agent,
            topology=topology,
            agent_outputs={},
            round_goal="Test audit logging",
            skill_context=None,
            callbacks=None,
        )

        mock_audit.log_error.assert_called_once()
        call_args = mock_audit.log_error.call_args
        assert call_args[0][1] == "context_exceeded"
        assert "audit-agent" in call_args[0][2]
