"""
Tests for FormicOS v0.8.0 formic_subcall Integration.

End-to-end flow: REPL script calls formic_subcall() →
REPLHarness closure schedules on event loop →
SubcallRouter.route_subcall() creates & executes sub-agent →
result string returns to REPL variable.

Covers:
  - REPL → router → mock agent → return string (happy path)
  - Context isolation (sub-agent receives ONLY task + data, no parent state)
  - Subcall limit circuit breaker
  - Sub-agent timeout handling
  - Sub-agent failure propagation
  - Data slice truncation
  - Router diagnostic log population
  - Multiple subcalls in a single exec block
  - formic_subcall with default and custom target_caste
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.orchestrator.router import SubcallRouter, _MAX_DATA_SLICE_CHARS
from src.core.repl.harness import REPLHarness
from src.core.repl.secured_memory import SecuredTopologicalMemory


# ── Helpers ──────────────────────────────────────────────────────────────


@dataclass
class _MockAgentOutput:
    """Minimal AgentOutput stub."""
    output: str = ""
    tool_calls: list = field(default_factory=list)
    tokens_used: int = 42


def _make_mock_factory(execute_return: str = "sub-agent result"):
    """Build a mock AgentFactory whose agents return the given string."""
    factory = MagicMock()
    mock_agent = AsyncMock()
    mock_agent.execute = AsyncMock(
        return_value=_MockAgentOutput(output=execute_return),
    )
    factory.create.return_value = mock_agent
    return factory, mock_agent


def _make_harness(
    factory: MagicMock,
    loop: asyncio.AbstractEventLoop,
    max_subcalls: int = 10,
) -> REPLHarness:
    """Build a REPLHarness with mocked memory and given factory/loop."""
    memory = MagicMock(spec=SecuredTopologicalMemory)
    memory.read_slice.return_value = b"test data"

    router = SubcallRouter(
        factory=factory,
        workspace_root="./workspace/test-colony",
        colony_id="test-colony",
    )

    return REPLHarness(
        memory=memory,
        router=router,
        loop=loop,
        workspace_root="./workspace/test-colony",
        max_subcalls=max_subcalls,
    )


# ── Happy Path ───────────────────────────────────────────────────────────


class TestSubcallHappyPath:
    """REPL calls formic_subcall, router creates agent, returns output."""

    @pytest.mark.asyncio
    async def test_repl_subcall_returns_agent_output(self):
        """Full integration: exec() script calls formic_subcall and captures result."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("# Fixed bug in line 42\ndef foo(): return True")

        harness = _make_harness(factory, loop)

        # Run the REPL in a thread (as it would in production)
        code = (
            'result = formic_subcall("Fix the bug in foo()", '
            '"def foo(): return False", "coder")\n'
            'print(result)'
        )
        output = await asyncio.to_thread(harness.execute, code)

        assert "Fixed bug in line 42" in output
        assert "def foo(): return True" in output

        # Verify the factory created the right agent
        factory.create.assert_called_once()
        call_kwargs = factory.create.call_args
        assert call_kwargs[1]["caste"] == "coder"
        assert call_kwargs[1]["workspace_root"] == "./workspace/test-colony"

    @pytest.mark.asyncio
    async def test_subcall_default_caste(self):
        """Default target_caste is 'Coder' (lowercased to 'coder')."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("default caste output")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Analyze this", "some data")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "default caste output" in output
        assert factory.create.call_args[1]["caste"] == "coder"

    @pytest.mark.asyncio
    async def test_subcall_custom_caste(self):
        """Custom target_caste is respected."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("architect analysis")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Design API", "spec data", "architect")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "architect analysis" in output
        assert factory.create.call_args[1]["caste"] == "architect"


# ── Context Isolation ────────────────────────────────────────────────────


class TestContextIsolation:
    """Sub-agent receives ONLY task + data, no parent context."""

    @pytest.mark.asyncio
    async def test_agent_receives_blank_context(self):
        """The sub-agent's context contains SUBCALL TASK and DATA, nothing else."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("isolated output")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Parse CSV", "col1,col2\\n1,2")\nprint(result)'
        await asyncio.to_thread(harness.execute, code)

        # Inspect what was passed to agent.execute()
        execute_call = mock_agent.execute.call_args
        context = execute_call[1]["context"]
        round_goal = execute_call[1]["round_goal"]

        assert "SUBCALL TASK: Parse CSV" in context
        assert "DATA:" in context
        assert "col1,col2" in context
        assert round_goal == "Parse CSV"

        # Verify no parent context leaked
        assert execute_call[1]["routed_messages"] is None
        assert execute_call[1]["skill_context"] is None
        assert execute_call[1]["callbacks"] is None

    @pytest.mark.asyncio
    async def test_empty_data_slice(self):
        """Empty data_slice produces context without DATA section."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("no data output")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Do something", "")\nprint(result)'
        await asyncio.to_thread(harness.execute, code)

        context = mock_agent.execute.call_args[1]["context"]
        assert "SUBCALL TASK: Do something" in context
        assert "DATA:" not in context


# ── Data Slice Truncation ────────────────────────────────────────────────


class TestDataSliceTruncation:

    @pytest.mark.asyncio
    async def test_oversized_data_slice_truncated(self):
        """Data slices larger than _MAX_DATA_SLICE_CHARS are capped."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("truncated output")

        harness = _make_harness(factory, loop)

        big_data = "x" * (_MAX_DATA_SLICE_CHARS + 5000)
        code = f'result = formic_subcall("Analyze", """{big_data}""")\nprint(result)'
        await asyncio.to_thread(harness.execute, code)

        context = mock_agent.execute.call_args[1]["context"]
        # Data should be truncated
        assert "truncated" in context.lower()
        assert f"{_MAX_DATA_SLICE_CHARS:,}" in context

    @pytest.mark.asyncio
    async def test_data_within_limit_not_truncated(self):
        """Data slices within the limit are passed through intact."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("ok")

        harness = _make_harness(factory, loop)

        small_data = "y" * 100
        code = f'result = formic_subcall("Check", "{small_data}")\nprint(result)'
        await asyncio.to_thread(harness.execute, code)

        context = mock_agent.execute.call_args[1]["context"]
        assert "truncated" not in context.lower()
        assert small_data in context


# ── Circuit Breaker ──────────────────────────────────────────────────────


class TestSubcallLimit:

    @pytest.mark.asyncio
    async def test_subcall_limit_enforced(self):
        """After max_subcalls, further calls return error string."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("sub result")

        harness = _make_harness(factory, loop, max_subcalls=2)

        code = (
            'r1 = formic_subcall("Task 1", "d1")\n'
            'r2 = formic_subcall("Task 2", "d2")\n'
            'r3 = formic_subcall("Task 3", "d3")\n'
            'print(r3)\n'
        )
        output = await asyncio.to_thread(harness.execute, code)

        # Third call should hit the limit
        assert "ERROR" in output
        assert "limit" in output.lower()

        # Only 2 agents were created, not 3
        assert factory.create.call_count == 2

    @pytest.mark.asyncio
    async def test_subcall_counter_resets_between_execute_calls(self):
        """The subcall budget resets on each execute() call."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("ok")

        harness = _make_harness(factory, loop, max_subcalls=1)

        # First exec: one subcall allowed
        code1 = 'r = formic_subcall("Task A", "data")\nprint(r)'
        output1 = await asyncio.to_thread(harness.execute, code1)
        assert "ok" in output1

        # Second exec: budget resets, one more allowed
        code2 = 'r = formic_subcall("Task B", "data")\nprint(r)'
        output2 = await asyncio.to_thread(harness.execute, code2)
        assert "ok" in output2


# ── Error Handling ───────────────────────────────────────────────────────


class TestSubcallErrors:

    @pytest.mark.asyncio
    async def test_agent_creation_failure(self):
        """If AgentFactory.create() raises, error string is returned."""
        loop = asyncio.get_running_loop()
        factory = MagicMock()
        factory.create.side_effect = KeyError("Model 'bad/model' not found")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Test", "data")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "ERROR" in output
        assert "Failed to create" in output

    @pytest.mark.asyncio
    async def test_agent_execution_failure(self):
        """If agent.execute() raises, error string is returned."""
        loop = asyncio.get_running_loop()
        factory = MagicMock()
        mock_agent = AsyncMock()
        mock_agent.execute = AsyncMock(side_effect=RuntimeError("LLM crashed"))
        factory.create.return_value = mock_agent

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Test", "data")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "ERROR" in output

    @pytest.mark.asyncio
    async def test_agent_timeout(self):
        """Sub-agent exceeding timeout returns error string."""
        loop = asyncio.get_running_loop()
        factory = MagicMock()

        async def slow_execute(**kwargs):
            await asyncio.sleep(999)

        mock_agent = AsyncMock()
        mock_agent.execute = slow_execute
        factory.create.return_value = mock_agent

        router = SubcallRouter(
            factory=factory,
            workspace_root="./workspace",
            colony_id="test",
            agent_timeout=0.1,  # very short timeout
        )

        memory = MagicMock(spec=SecuredTopologicalMemory)
        memory.read_slice.return_value = b""

        harness = REPLHarness(
            memory=memory, router=router, loop=loop,
        )

        code = 'result = formic_subcall("Slow task", "data")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "ERROR" in output
        assert "timed out" in output.lower()

    @pytest.mark.asyncio
    async def test_no_output_from_agent(self):
        """Agent returning empty output gives placeholder message."""
        loop = asyncio.get_running_loop()
        factory, mock_agent = _make_mock_factory("")
        mock_agent.execute.return_value = _MockAgentOutput(output="")

        harness = _make_harness(factory, loop)

        code = 'result = formic_subcall("Empty task", "data")\nprint(result)'
        output = await asyncio.to_thread(harness.execute, code)

        assert "no output" in output.lower()


# ── Router Diagnostic Log ────────────────────────────────────────────────


class TestRouterLog:

    @pytest.mark.asyncio
    async def test_subcall_log_populated(self):
        """SubcallRouter.subcall_log records each subcall."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("logged result")

        memory = MagicMock(spec=SecuredTopologicalMemory)
        memory.read_slice.return_value = b""

        router = SubcallRouter(
            factory=factory,
            workspace_root="./workspace",
            colony_id="test",
        )
        harness = REPLHarness(memory=memory, router=router, loop=loop)

        code = 'r = formic_subcall("Log this task", "data")\nprint(r)'
        await asyncio.to_thread(harness.execute, code)

        log = router.subcall_log
        assert len(log) == 1
        assert log[0]["caste"] == "coder"
        assert "Log this task" in log[0]["task"]
        assert log[0]["tokens_used"] == 42
        assert log[0]["tool_calls"] == 0

    @pytest.mark.asyncio
    async def test_multiple_subcalls_all_logged(self):
        """All subcalls are recorded in the log."""
        loop = asyncio.get_running_loop()
        factory, _ = _make_mock_factory("result")

        memory = MagicMock(spec=SecuredTopologicalMemory)
        memory.read_slice.return_value = b""

        router = SubcallRouter(
            factory=factory,
            workspace_root="./workspace",
            colony_id="test",
        )
        harness = REPLHarness(memory=memory, router=router, loop=loop)

        code = (
            'r1 = formic_subcall("Task A", "d1")\n'
            'r2 = formic_subcall("Task B", "d2", "reviewer")\n'
            'print(r1, r2)\n'
        )
        await asyncio.to_thread(harness.execute, code)

        log = router.subcall_log
        assert len(log) == 2
        assert log[0]["caste"] == "coder"
        assert log[1]["caste"] == "reviewer"


# ── Multiple Subcalls ────────────────────────────────────────────────────


class TestMultipleSubcalls:

    @pytest.mark.asyncio
    async def test_sequential_subcalls_in_single_exec(self):
        """Multiple formic_subcall invocations in one exec() block."""
        call_count = 0

        async def counting_execute(**kwargs):
            nonlocal call_count
            call_count += 1
            return _MockAgentOutput(output=f"output-{call_count}")

        loop = asyncio.get_running_loop()
        factory = MagicMock()
        mock_agent = AsyncMock()
        mock_agent.execute = counting_execute
        factory.create.return_value = mock_agent

        harness = _make_harness(factory, loop)

        code = (
            'a = formic_subcall("First", "d1")\n'
            'b = formic_subcall("Second", "d2")\n'
            'print(a)\nprint(b)\n'
        )
        output = await asyncio.to_thread(harness.execute, code)

        assert "output-1" in output
        assert "output-2" in output
        assert factory.create.call_count == 2
