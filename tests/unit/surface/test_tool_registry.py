"""Wave 78 Track 2: Self-describing tool registry tests."""

from __future__ import annotations

import asyncio

from formicos.surface.queen_runtime import classify_complexity
from formicos.surface.registry import QueenToolEntry, queen_tool


# -- QueenToolEntry --

def test_queen_tool_entry_fields() -> None:
    entry = QueenToolEntry(
        name="test_tool",
        toolset="testing",
        schema={"name": "test_tool", "description": "A test tool"},
        handler_name="_handle_test",
    )
    assert entry.name == "test_tool"
    assert entry.toolset == "testing"
    assert entry.handler_name == "_handle_test"
    assert entry.is_async is True
    assert entry.mutates_workspace is False
    assert entry.checkpoint_mode == "none"


def test_queen_tool_entry_frozen() -> None:
    entry = QueenToolEntry(
        name="x", toolset="t", schema={}, handler_name="_x",
    )
    try:
        entry.name = "y"  # type: ignore[misc]
        assert False, "Should be frozen"
    except AttributeError:
        pass


# -- @queen_tool decorator --

def test_queen_tool_decorator_sync() -> None:
    @queen_tool(
        name="my_tool",
        toolset="ops",
        schema={"name": "my_tool"},
        mutates_workspace=True,
        checkpoint_mode="always",
    )
    def handler() -> str:
        return "ok"

    entry: QueenToolEntry = handler._queen_tool_entry  # type: ignore[attr-defined]
    assert entry.name == "my_tool"
    assert entry.toolset == "ops"
    assert entry.is_async is False
    assert entry.mutates_workspace is True
    assert entry.checkpoint_mode == "always"
    assert handler() == "ok"


def test_queen_tool_decorator_async() -> None:
    @queen_tool(
        name="async_tool",
        toolset="colony",
        schema={"name": "async_tool"},
    )
    async def handler() -> str:
        return "ok"

    entry: QueenToolEntry = handler._queen_tool_entry  # type: ignore[attr-defined]
    assert entry.is_async is True
    assert asyncio.run(handler()) == "ok"


# -- classify_complexity --

def test_classify_simple_messages() -> None:
    assert classify_complexity("hi") == "simple"
    assert classify_complexity("hello, how are you?") == "simple"
    assert classify_complexity("what time is it") == "simple"
    assert classify_complexity("show me the status") == "simple"
    assert classify_complexity("ok") == "simple"


def test_classify_complex_by_keyword() -> None:
    assert classify_complexity("spawn a colony to refactor the auth module") == "complex"
    assert classify_complexity("debug the login failure") == "complex"
    assert classify_complexity("implement a new feature") == "complex"
    assert classify_complexity("analyze the colony outcomes") == "complex"


def test_classify_complex_by_length() -> None:
    long_msg = "Please help me with " + "a " * 80 + "task"
    assert classify_complexity(long_msg) == "complex"


def test_classify_complex_by_code_block() -> None:
    assert classify_complexity("Fix this:\n```python\nprint(1)\n```") == "complex"


def test_classify_complex_by_word_count() -> None:
    many_words = " ".join(["word"] * 36)  # Wave 85: threshold raised to 35
    assert classify_complexity(many_words) == "complex"


# -- _TOOL_META registry structure --

def test_tool_meta_no_duplicates() -> None:
    """Verify no duplicate tool names in the registry."""
    from formicos.surface.queen_tools import QueenToolDispatcher
    names = [t[0] for t in QueenToolDispatcher._TOOL_META]
    assert len(names) == len(set(names)), f"Duplicate tool names: {[n for n in names if names.count(n) > 1]}"


def test_tool_meta_valid_toolsets() -> None:
    """Verify all toolset names are from the known set."""
    from formicos.surface.queen_tools import QueenToolDispatcher
    known = {"colony", "knowledge", "workspace", "planning", "operations",
             "documents", "working_memory", "analysis", "safety"}
    for name, toolset, *_ in QueenToolDispatcher._TOOL_META:
        assert toolset in known, f"Tool {name} has unknown toolset {toolset}"


def test_tool_meta_handler_specs_valid() -> None:
    """Verify handler spec format is valid."""
    from formicos.surface.queen_tools import QueenToolDispatcher
    valid_sigs = {"", "i", "iw", "it", "iwt"}
    for name, _, handler_spec, *_ in QueenToolDispatcher._TOOL_META:
        if ":" in handler_spec:
            _, sig = handler_spec.split(":", 1)
            assert sig in valid_sigs, f"Tool {name} has invalid sig '{sig}'"


def test_tool_meta_count() -> None:
    """Verify expected tool count.

    43 tools in _TOOL_META. archive_thread and define_workflow_steps
    are delegated to the thread manager and are NOT in the registry.
    They return DELEGATE_THREAD before the handler dict is consulted.
    """
    from formicos.surface.queen_tools import QueenToolDispatcher
    count = len(QueenToolDispatcher._TOOL_META)
    assert count == 45, f"Expected 45 tools in _TOOL_META, got {count}"
