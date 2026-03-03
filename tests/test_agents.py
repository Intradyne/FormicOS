"""
Tests for FormicOS v0.6.0 -- Agents

Covers:
  - Structured tool call parsing (delta.tool_calls)
  - Content-based tool call fallback (<tool_call> XML tags)
  - Tool approval blocks/allows
  - Draft-refine success and failure fallback
  - Token budget truncation
  - finish_reason "tool" and "tool_calls" both trigger tool processing
  - generate_intent returns valid key/query dict
  - File operations validate workspace root (symlink escape rejected)
  - Multiple tool calls in single response
  - Agent cancellation
  - AgentFactory.create() resolution chain
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents import (
    Agent,
    AgentFactory,
    AgentOutput,
    ToolCallRecord,
    DEFAULT_APPROVAL_REQUIRED,
)
from src.models import (
    Caste,
    SubcasteTier,
)


# ═════════════════════════════════════════════════════════════════════════════
# Helpers -- mock streaming response objects
# ═════════════════════════════════════════════════════════════════════════════


def _make_delta(
    content: str | None = None,
    tool_calls: list | None = None,
):
    """Create a mock delta object for a streaming chunk."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = tool_calls
    return delta


def _make_chunk(
    delta,
    finish_reason: str | None = None,
    usage=None,
):
    """Create a mock streaming chunk."""
    choice = MagicMock()
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk = MagicMock()
    chunk.choices = [choice]
    chunk.usage = usage
    return chunk


def _make_tool_call_delta(index: int, tc_id: str | None = None, name: str | None = None, arguments: str | None = None):
    """Create a mock tool_call delta fragment."""
    tc = MagicMock()
    tc.index = index
    tc.id = tc_id

    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc.function = func

    return tc


async def _async_iter(items):
    """Convert a list to an async iterator (simulates streaming)."""
    for item in items:
        yield item


def _make_non_streaming_response(content: str = "{}"):
    """Create a mock non-streaming response (for generate_intent)."""
    message = MagicMock()
    message.content = content

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_streaming_response(chunks: list):
    """Wrap a list of chunks into an async iterator that can be awaited (stream=True)."""
    return _async_iter(chunks)


def _build_agent(
    tools: list[dict] | None = None,
    config_overrides: dict | None = None,
    workspace_root: str = "./workspace",
) -> tuple[Agent, AsyncMock]:
    """Build an Agent with a mocked AsyncOpenAI client."""
    mock_client = AsyncMock()

    cfg: dict[str, Any] = {
        "max_tokens": 5000,
        "temperature": 0.0,
        "context_length": 32768,
        "workspace_root": workspace_root,
        "approval_required": list(DEFAULT_APPROVAL_REQUIRED),
    }
    if config_overrides:
        cfg.update(config_overrides)

    agent = Agent(
        id="test-agent-1",
        caste=Caste.CODER,
        system_prompt="You are a test agent.",
        model_client=mock_client,
        model_name="test-model",
        tools=tools or [],
        config=cfg,
    )
    return agent, mock_client


# ═════════════════════════════════════════════════════════════════════════════
# Test: generate_intent returns valid key/query dict
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_generate_intent_returns_key_query():
    """generate_intent should return a dict with 'key' and 'query' fields."""
    agent, mock_client = _build_agent()

    mock_client.chat.completions.create.return_value = _make_non_streaming_response(
        '{"key": "code implementation", "query": "architecture design"}'
    )

    result = await agent.generate_intent(
        task="Build a REST API",
        round_history=[{"round": 1, "summary": "Initial planning done"}],
    )

    assert isinstance(result, dict)
    assert "key" in result
    assert "query" in result
    # Now role-enriched: "As a coder: code implementation"
    assert "code implementation" in result["key"]
    assert "architecture design" in result["query"]
    assert result["key"].startswith("As a coder:")
    assert result["query"].startswith("As a coder:")

    # Verify the LLM was called
    mock_client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_intent_fallback_on_bad_json():
    """generate_intent should return sensible defaults if LLM returns garbage."""
    agent, mock_client = _build_agent()

    mock_client.chat.completions.create.return_value = _make_non_streaming_response(
        "not valid json at all"
    )

    result = await agent.generate_intent(task="Do something")

    assert "key" in result
    assert "query" in result
    # Falls back to caste-based defaults, now role-enriched
    assert "coder output" in result["key"]
    assert "general input" in result["query"]


# ═════════════════════════════════════════════════════════════════════════════
# Test: Structured tool_calls (delta.tool_calls) parsed and executed
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_structured_tool_calls_parsed_and_executed(tmp_path):
    """Structured delta.tool_calls should be parsed and the tool should execute."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read a file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    # Create a test file in workspace
    test_file = tmp_path / "hello.txt"
    test_file.write_text("Hello World", encoding="utf-8")

    # First call: LLM returns a tool call via structured delta
    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_001",
        name="file_read",
        arguments='{"path": "hello.txt"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    # Second call: LLM returns final response after seeing tool result
    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "read file", "output": "got it"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(
        context="Test context",
        round_goal="Read a file",
    )

    assert isinstance(result, AgentOutput)
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "file_read"
    assert "Hello World" in result.tool_calls[0].result
    assert result.tool_calls[0].approved is True


# ═════════════════════════════════════════════════════════════════════════════
# Test: Content-based tool call fallback (<tool_call> XML tags)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_content_based_tool_call_fallback(tmp_path):
    """<tool_call> XML tags in content text should be parsed via json_repair."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read a file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    # Create test file
    test_file = tmp_path / "data.txt"
    test_file.write_text("Some data here", encoding="utf-8")

    # LLM puts tool call in content text (Qwen/llama.cpp behavior)
    content_with_tool = (
        'Let me read the file.\n'
        '<tool_call>{"name": "file_read", "arguments": {"path": "data.txt"}}</tool_call>'
    )

    # Round 1: content has tool_call tag, finish_reason is "stop" (not "tool_calls")
    chunks_round1 = [
        _make_chunk(_make_delta(content=content_with_tool)),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    # Round 2: after tool execution, final answer
    chunks_round2 = [
        _make_chunk(
            _make_delta(
                content='{"approach": "file read", "output": "read data.txt successfully"}'
            )
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(
        context="Test context",
        round_goal="Read data file",
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "file_read"
    assert "Some data here" in result.tool_calls[0].result


# ═════════════════════════════════════════════════════════════════════════════
# Test: finish_reason "tool" (llama.cpp) triggers tool processing
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_finish_reason_tool_triggers_processing(tmp_path):
    """finish_reason='tool' (llama.cpp divergence) should trigger tool processing."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    test_file = tmp_path / "test.txt"
    test_file.write_text("llama test", encoding="utf-8")

    # Tool call via structured delta, but finish_reason is "tool" not "tool_calls"
    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_llama",
        name="file_read",
        arguments='{"path": "test.txt"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool"),  # llama.cpp style
    ]

    chunks_round2 = [
        _make_chunk(_make_delta(content='{"approach": "read", "output": "done"}')),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="read file")

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "file_read"
    assert "llama test" in result.tool_calls[0].result


# ═════════════════════════════════════════════════════════════════════════════
# Test: finish_reason "tool_calls" (OpenAI standard) triggers tool processing
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_finish_reason_tool_calls_triggers_processing(tmp_path):
    """finish_reason='tool_calls' (OpenAI standard) should trigger tool processing."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    test_file = tmp_path / "openai.txt"
    test_file.write_text("openai standard", encoding="utf-8")

    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_openai",
        name="file_read",
        arguments='{"path": "openai.txt"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),  # OpenAI style
    ]

    chunks_round2 = [
        _make_chunk(_make_delta(content='{"approach": "read", "output": "done"}')),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="read file")

    assert len(result.tool_calls) == 1
    assert "openai standard" in result.tool_calls[0].result


# ═════════════════════════════════════════════════════════════════════════════
# Test: Tool approval blocks execution
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tool_approval_blocks_execution(tmp_path):
    """When approval_callback returns False, the tool should be denied."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_write", "name": "file_write", "description": "Write file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_write",
        name="file_write",
        arguments='{"path": "secret.txt", "content": "secrets"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "tried write", "output": "denied"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    # Approval callback that denies everything
    async def deny_all(agent_id, tool_name, args):
        return False

    result = await agent.execute(
        context="ctx",
        round_goal="write file",
        callbacks={"approval_callback": deny_all},
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].approved is False
    assert "denied" in result.tool_calls[0].result.lower()
    # File should NOT have been created
    assert not (tmp_path / "secret.txt").exists()


@pytest.mark.asyncio
async def test_tool_approval_allows_execution(tmp_path):
    """When approval_callback returns True, the tool should execute normally."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_write", "name": "file_write", "description": "Write file"}],
        config_overrides={"workspace_root": str(tmp_path)},
    )

    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_write",
        name="file_write",
        arguments='{"path": "allowed.txt", "content": "hello"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "write", "output": "wrote file"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    async def approve_all(agent_id, tool_name, args):
        return True

    result = await agent.execute(
        context="ctx",
        round_goal="write file",
        callbacks={"approval_callback": approve_all},
    )

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].approved is True
    assert (tmp_path / "allowed.txt").exists()
    assert (tmp_path / "allowed.txt").read_text() == "hello"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Draft-refine success
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_draft_refine_success():
    """When refine model succeeds, the refined output should be returned."""
    refine_client = AsyncMock()
    agent, mock_client = _build_agent(
        config_overrides={
            "refine_client": refine_client,
            "refine_model": "refine-model",
            "refine_prompt": "Refine this.",
        }
    )

    # Draft LLM response
    chunks = [
        _make_chunk(
            _make_delta(
                content='{"approach": "draft approach", "output": "draft output"}'
            )
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    # Refine response
    refine_client.chat.completions.create.return_value = _make_non_streaming_response(
        '{"approach": "refined approach", "output": "refined output"}'
    )

    result = await agent.execute(context="ctx", round_goal="do work")

    assert result.approach == "refined approach"
    assert result.output == "refined output"
    refine_client.chat.completions.create.assert_awaited_once()


# ═════════════════════════════════════════════════════════════════════════════
# Test: Draft-refine failure falls back to draft
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_draft_refine_failure_falls_back_to_draft():
    """When refine model fails, the original draft output should be kept."""
    refine_client = AsyncMock()
    agent, mock_client = _build_agent(
        config_overrides={
            "refine_client": refine_client,
            "refine_model": "refine-model",
        }
    )

    # Draft LLM response
    chunks = [
        _make_chunk(
            _make_delta(
                content='{"approach": "draft only", "output": "draft content"}'
            )
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    # Refine fails with exception
    refine_client.chat.completions.create.side_effect = Exception("Refine model down")

    result = await agent.execute(context="ctx", round_goal="do work")

    assert result.approach == "draft only"
    assert result.output == "draft content"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Token budget truncates context
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_token_budget_truncates_context():
    """When context exceeds the token budget, the hard circuit breaker fires.

    v0.9.0: ContextExceededError is raised BEFORE soft truncation, preventing
    the LLM request entirely. The Orchestrator catches this and returns a
    [SYSTEM_HALT] message.
    """
    from src.agents import ContextExceededError

    agent, mock_client = _build_agent(
        config_overrides={
            # Very small context_length to force the hard limit
            "context_length": 50,  # 50 tokens * 4 chars = 200 chars max
        }
    )

    # Provide a very long context to trigger the circuit breaker
    long_context = "A" * 5000

    with pytest.raises(ContextExceededError):
        await agent.execute(context=long_context, round_goal="work")

    # Verify the LLM was NOT called (circuit breaker halted before request)
    mock_client.chat.completions.create.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# Test: File operations validate workspace root (symlink escape rejected)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_file_read_rejects_symlink_escape(tmp_path):
    """A symlink pointing outside the workspace should be rejected."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create a file outside workspace
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("TOP SECRET", encoding="utf-8")

    # Create a symlink inside workspace that points outside
    symlink = workspace / "escape.txt"
    try:
        symlink.symlink_to(outside_file)
    except OSError:
        pytest.skip("Cannot create symlinks (requires admin on Windows)")

    agent, mock_client = _build_agent(
        config_overrides={"workspace_root": str(workspace)},
    )

    # Directly test the tool execution
    result = await agent._execute_tool("file_read", {"path": "escape.txt"})
    assert "ERROR" in result or "sandbox" in result.lower()


@pytest.mark.asyncio
async def test_file_read_rejects_path_traversal(tmp_path):
    """Path traversal (../) should be rejected by workspace validation."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Create a file outside workspace
    outside = tmp_path / "outside.txt"
    outside.write_text("PRIVATE", encoding="utf-8")

    agent, mock_client = _build_agent(
        config_overrides={"workspace_root": str(workspace)},
    )

    result = await agent._execute_tool("file_read", {"path": "../outside.txt"})
    assert "ERROR" in result


# ═════════════════════════════════════════════════════════════════════════════
# Test: Multiple tool calls in single response
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_single_response(tmp_path):
    """Multiple tool calls from one LLM response should all be executed."""
    agent, mock_client = _build_agent(
        tools=[
            {"id": "file_write", "name": "file_write", "description": "Write file"},
            {"id": "file_read", "name": "file_read", "description": "Read file"},
        ],
        config_overrides={
            "workspace_root": str(tmp_path),
            "approval_required": [],  # No approval needed for this test
        },
    )

    # Two tool calls in one response
    tc1 = _make_tool_call_delta(
        index=0,
        tc_id="call_1",
        name="file_write",
        arguments='{"path": "a.txt", "content": "file_a"}',
    )
    tc2 = _make_tool_call_delta(
        index=1,
        tc_id="call_2",
        name="file_write",
        arguments='{"path": "b.txt", "content": "file_b"}',
    )

    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc1, tc2])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(
                content='{"approach": "multi-write", "output": "wrote two files"}'
            )
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="write files")

    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].tool_name == "file_write"
    assert result.tool_calls[1].tool_name == "file_write"
    assert (tmp_path / "a.txt").read_text() == "file_a"
    assert (tmp_path / "b.txt").read_text() == "file_b"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Multiple content-based tool calls
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_multiple_content_based_tool_calls(tmp_path):
    """Multiple <tool_call> tags in content should all be parsed."""
    agent, mock_client = _build_agent(
        tools=[
            {"id": "file_write", "name": "file_write", "description": "Write file"},
        ],
        config_overrides={
            "workspace_root": str(tmp_path),
            "approval_required": [],
        },
    )

    content = (
        'Writing two files:\n'
        '<tool_call>{"name": "file_write", "arguments": {"path": "x.txt", "content": "X"}}</tool_call>\n'
        '<tool_call>{"name": "file_write", "arguments": {"path": "y.txt", "content": "Y"}}</tool_call>'
    )

    chunks_round1 = [
        _make_chunk(_make_delta(content=content)),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "wrote", "output": "done"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="write")

    assert len(result.tool_calls) == 2
    assert (tmp_path / "x.txt").read_text() == "X"
    assert (tmp_path / "y.txt").read_text() == "Y"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Stream callback receives tokens
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_duplicate_file_read_suppressed_in_same_workspace_state(tmp_path):
    """Second identical file_read in same state should be suppressed with guardrail message."""
    (tmp_path / "data.txt").write_text("DATA", encoding="utf-8")
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read file"}],
        config_overrides={
            "workspace_root": str(tmp_path),
            "approval_required": [],
        },
    )

    tc1 = _make_tool_call_delta(
        index=0,
        tc_id="call_1",
        name="file_read",
        arguments='{"path": "data.txt"}',
    )
    tc2 = _make_tool_call_delta(
        index=1,
        tc_id="call_2",
        name="file_read",
        arguments='{"path": "data.txt"}',
    )

    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc1, tc2])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]
    chunks_round2 = [
        _make_chunk(_make_delta(content='{"approach":"read","output":"done"}')),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="read file once")
    assert len(result.tool_calls) == 2
    assert result.tool_calls[0].tool_name == "file_read"
    assert "DATA" in result.tool_calls[0].result
    assert "Duplicate read/search call suppressed" in result.tool_calls[1].result


@pytest.mark.asyncio
async def test_stream_callback_receives_tokens():
    """stream_callback should be called with each token chunk."""
    agent, mock_client = _build_agent()

    chunks = [
        _make_chunk(_make_delta(content="Hello ")),
        _make_chunk(_make_delta(content="World")),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    tokens_received = []

    async def collect_tokens(agent_id, token):
        tokens_received.append(token)

    _result = await agent.execute(
        context="ctx",
        round_goal="greet",
        callbacks={"stream_callback": collect_tokens},
    )

    assert tokens_received == ["Hello ", "World"]


# ═════════════════════════════════════════════════════════════════════════════
# Test: Unknown tool forwards to MCP gateway
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unknown_tool_forwards_to_mcp_gateway():
    """Unknown tool names should forward to the MCP gateway callback."""
    mcp_callback = AsyncMock(return_value="MCP result: success")

    agent, mock_client = _build_agent(
        tools=[{"id": "custom_tool", "name": "custom_tool", "description": "Custom"}],
        config_overrides={
            "mcp_gateway_callback": mcp_callback,
            "approval_required": [],
        },
    )

    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_mcp",
        name="custom_tool",
        arguments='{"param": "value"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "mcp", "output": "used custom tool"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="use custom tool")

    mcp_callback.assert_awaited_once_with("custom_tool", {"param": "value"})
    assert result.tool_calls[0].result == "MCP result: success"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Agent cancellation
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_agent_cancel():
    """cancel() should cause the agent to abort execution gracefully."""
    agent, mock_client = _build_agent()

    # Simulate a long-running stream that we cancel mid-way
    async def slow_stream(**kwargs):
        yield _make_chunk(_make_delta(content="start"))
        agent.cancel()  # Cancel during streaming
        yield _make_chunk(_make_delta(content=" more"))
        yield _make_chunk(_make_delta(), finish_reason="stop")

    mock_client.chat.completions.create.return_value = slow_stream()

    result = await agent.execute(context="ctx", round_goal="work")

    assert "cancelled" in result.output.lower()


# ═════════════════════════════════════════════════════════════════════════════
# Test: AgentFactory.create() basic
# ═════════════════════════════════════════════════════════════════════════════


def test_agent_factory_create(sample_config_path):
    """AgentFactory.create() should produce an Agent with correct properties."""
    from src.models import load_config

    config = load_config(sample_config_path)

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
    )

    agent = factory.create(agent_id="worker-1", caste=Caste.MANAGER)

    assert agent.id == "worker-1"
    assert agent.caste == Caste.MANAGER
    assert agent.model_name == config.inference.model
    assert agent.max_tokens == config.inference.max_tokens_per_agent
    assert agent.system_prompt  # Should have some prompt


def test_agent_factory_with_model_override(sample_config_path):
    """AgentFactory should use the model_override when provided."""
    from src.models import load_config

    config = load_config(sample_config_path)
    mock_client = AsyncMock()

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
        model_clients={"test/model": mock_client},
    )

    agent = factory.create(
        agent_id="coder-1",
        caste=Caste.CODER,
        model_override="test/model",
    )

    assert agent.model_client is mock_client


def test_agent_factory_with_subcaste_tier(sample_config_path):
    """AgentFactory should resolve models via subcaste_map."""
    from src.models import load_config

    config = load_config(sample_config_path)
    mock_client = AsyncMock()

    factory = AgentFactory(
        model_registry=config.model_registry,
        config=config,
        model_clients={"test/model": mock_client},
    )

    agent = factory.create(
        agent_id="arch-1",
        caste=Caste.ARCHITECT,
        subcaste_tier=SubcasteTier.HEAVY,
    )

    # Should resolve through subcaste_map -> "test/model"
    assert agent.model_client is mock_client


# ═════════════════════════════════════════════════════════════════════════════
# Test: AgentOutput dataclass
# ═════════════════════════════════════════════════════════════════════════════


def test_agent_output_defaults():
    """AgentOutput should have sensible defaults."""
    output = AgentOutput()
    assert output.approach == ""
    assert output.alternatives_rejected == ""
    assert output.output == ""
    assert output.tool_calls == []
    assert output.tokens_used == 0


def test_agent_output_with_tool_records():
    """AgentOutput should store tool call records."""
    record = ToolCallRecord(
        tool_name="file_write",
        arguments={"path": "test.txt", "content": "hi"},
        result="Written 2 chars to test.txt",
        approved=True,
    )
    output = AgentOutput(
        approach="write",
        output="wrote a file",
        tool_calls=[record],
        tokens_used=150,
    )
    assert len(output.tool_calls) == 1
    assert output.tool_calls[0].tool_name == "file_write"
    assert output.tokens_used == 150


# ═════════════════════════════════════════════════════════════════════════════
# Test: fetch tool (mocked httpx)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_fetch_tool():
    """fetch tool should make an HTTP GET and return content."""
    agent, _ = _build_agent()

    mock_response = MagicMock()
    mock_response.text = "<html>Hello</html>"
    mock_response.raise_for_status = MagicMock()

    with patch("src.agents.httpx.AsyncClient") as mock_httpx:
        mock_ctx = AsyncMock()
        mock_ctx.get.return_value = mock_response
        mock_httpx.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
        mock_httpx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await agent._execute_tool("fetch", {"url": "https://example.com"})

    assert "Hello" in result


@pytest.mark.asyncio
async def test_fetch_tool_invalid_scheme():
    """fetch tool should reject non-HTTP URLs."""
    agent, _ = _build_agent()
    result = await agent._execute_tool("fetch", {"url": "ftp://example.com"})
    assert "ERROR" in result


# ═════════════════════════════════════════════════════════════════════════════
# Test: qdrant_search placeholder
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_qdrant_search_placeholder():
    """qdrant_search should report unavailability in this runtime."""
    agent, _ = _build_agent()
    result = await agent._execute_tool("qdrant_search", {"query": "test query"})
    assert "QDRANT_UNAVAILABLE" in result
    assert "test query" in result


# ═════════════════════════════════════════════════════════════════════════════
# Test: file_write and file_delete with approval
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_file_write_and_delete(tmp_path):
    """file_write and file_delete should work within workspace."""
    agent, _ = _build_agent(
        config_overrides={"workspace_root": str(tmp_path)},
    )

    # Write
    result = await agent._execute_tool(
        "file_write", {"path": "test.txt", "content": "hello world"}
    )
    assert "Written" in result
    assert (tmp_path / "test.txt").read_text() == "hello world"

    # Read
    result = await agent._execute_tool("file_read", {"path": "test.txt"})
    assert result == "hello world"

    # Delete
    result = await agent._execute_tool("file_delete", {"path": "test.txt"})
    assert "Deleted" in result
    assert not (tmp_path / "test.txt").exists()


@pytest.mark.asyncio
async def test_file_write_rejects_binary_asset_paths(tmp_path):
    """file_write should reject binary asset extensions (text-only tool)."""
    agent, _ = _build_agent(
        config_overrides={"workspace_root": str(tmp_path)},
    )
    result = await agent._execute_tool(
        "file_write",
        {"path": "assets/sounds/eat.wav", "content": ""},
    )
    assert "ERROR" in result
    assert "text-only" in result
    assert not (tmp_path / "assets" / "sounds" / "eat.wav").exists()


@pytest.mark.asyncio
async def test_file_read_not_found_includes_available_file_hints(tmp_path):
    """file_read not-found should provide nearby available file hints."""
    agent, _ = _build_agent(
        config_overrides={"workspace_root": str(tmp_path)},
    )
    (tmp_path / "snake_game.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "config.py").write_text("x=1", encoding="utf-8")

    result = await agent._execute_tool("file_read", {"path": "missing.py"})
    assert "ERROR: File not found" in result
    assert "Available files:" in result
    assert "snake_game.py" in result or "config.py" in result


@pytest.mark.asyncio
async def test_code_execute_accepts_python_command_string(tmp_path):
    """code_execute should accept command-style python invocations."""
    agent, _ = _build_agent(
        config_overrides={"workspace_root": str(tmp_path)},
    )
    result = await agent._execute_tool(
        "code_execute",
        {"code": "python -m site --user-base"},
    )
    assert "ERROR:" not in result
    assert "SyntaxError" not in result
    assert result.strip() != ""


@pytest.mark.asyncio
async def test_file_delete_nonexistent(tmp_path):
    """file_delete on nonexistent file should return error."""
    agent, _ = _build_agent(
        config_overrides={"workspace_root": str(tmp_path)},
    )
    result = await agent._execute_tool("file_delete", {"path": "nope.txt"})
    assert "ERROR" in result


# ═════════════════════════════════════════════════════════════════════════════
# Test: content-based tool call with malformed JSON uses json_repair
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_content_tool_call_with_json_repair(tmp_path):
    """Content-based tool calls with slightly malformed JSON should be repaired."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_write", "name": "file_write", "description": "Write"}],
        config_overrides={
            "workspace_root": str(tmp_path),
            "approval_required": [],
        },
    )

    # Slightly malformed JSON (trailing comma in arguments)
    content = (
        '<tool_call>{"name": "file_write", "arguments": {"path": "fixed.txt", "content": "repaired",}}</tool_call>'
    )

    chunks_round1 = [
        _make_chunk(_make_delta(content=content)),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    chunks_round2 = [
        _make_chunk(
            _make_delta(content='{"approach": "write", "output": "wrote"}')
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    result = await agent.execute(context="ctx", round_goal="write")

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_name == "file_write"
    # json_repair should have fixed the trailing comma
    assert (tmp_path / "fixed.txt").exists()
    assert (tmp_path / "fixed.txt").read_text() == "repaired"


# ═════════════════════════════════════════════════════════════════════════════
# Test: No tools available -- pure text response
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_pure_text_response_no_tools():
    """Agent without tools should return parsed text output."""
    agent, mock_client = _build_agent(tools=[])

    chunks = [
        _make_chunk(
            _make_delta(
                content='{"approach": "analysis", "alternatives_rejected": "none", "output": "pure text result"}'
            )
        ),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    result = await agent.execute(context="ctx", round_goal="analyze")

    assert result.approach == "analysis"
    assert result.alternatives_rejected == "none"
    assert result.output == "pure text result"
    assert result.tool_calls == []


# ═════════════════════════════════════════════════════════════════════════════
# Test: LLM returns unparseable response
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_unparseable_llm_response():
    """If LLM returns non-JSON, output should wrap raw text."""
    agent, mock_client = _build_agent()

    chunks = [
        _make_chunk(_make_delta(content="This is just plain text, no JSON.")),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    result = await agent.execute(context="ctx", round_goal="work")

    # Should still produce an AgentOutput (not crash)
    assert isinstance(result, AgentOutput)
    assert result.output  # Should contain something


# ═════════════════════════════════════════════════════════════════════════════
# Test: Tool call callback fires
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_tool_call_callback_fires(tmp_path):
    """tool_call_callback should be called for each tool invocation."""
    agent, mock_client = _build_agent(
        tools=[{"id": "file_read", "name": "file_read", "description": "Read"}],
        config_overrides={
            "workspace_root": str(tmp_path),
            "approval_required": [],
        },
    )

    (tmp_path / "cb.txt").write_text("callback test")

    tc_delta = _make_tool_call_delta(
        index=0,
        tc_id="call_cb",
        name="file_read",
        arguments='{"path": "cb.txt"}',
    )
    chunks_round1 = [
        _make_chunk(_make_delta(tool_calls=[tc_delta])),
        _make_chunk(_make_delta(), finish_reason="tool_calls"),
    ]

    chunks_round2 = [
        _make_chunk(_make_delta(content='{"output": "done"}')),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]

    mock_client.chat.completions.create.side_effect = [
        _make_streaming_response(chunks_round1),
        _make_streaming_response(chunks_round2),
    ]

    callback_log = []

    async def log_tool_call(agent_id, tool_name, args):
        callback_log.append((agent_id, tool_name, args))

    _result = await agent.execute(
        context="ctx",
        round_goal="read",
        callbacks={"tool_call_callback": log_tool_call},
    )

    assert len(callback_log) == 1
    assert callback_log[0][0] == "test-agent-1"
    assert callback_log[0][1] == "file_read"


# ═════════════════════════════════════════════════════════════════════════════
# Test: Skill context injected into prompt
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_skill_context_injected():
    """skill_context should appear in the prompt sent to the LLM."""
    agent, mock_client = _build_agent()

    chunks = [
        _make_chunk(_make_delta(content='{"output": "used skills"}')),
        _make_chunk(_make_delta(), finish_reason="stop"),
    ]
    mock_client.chat.completions.create.return_value = _make_streaming_response(chunks)

    await agent.execute(
        context="ctx",
        round_goal="work",
        skill_context="Skill: Always validate inputs before processing.",
    )

    # Verify the skill context was included in the messages
    call_kwargs = mock_client.chat.completions.create.call_args
    messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
    user_content = messages[1]["content"]
    assert "Always validate inputs" in user_content
    assert "RELEVANT SKILLS" in user_content
