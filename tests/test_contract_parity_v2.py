"""Manifest-based contract parity tests (ADR-036, Wave 21).

Compares declared manifests across Python events, TypeScript events,
MCP tools, Queen tools, and AG-UI events. Catches drift mechanically.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from formicos.core.events import EVENT_TYPE_NAMES
from formicos.surface.agui_endpoint import AGUI_EVENT_TYPES
from formicos.surface.mcp_server import MCP_TOOL_NAMES

# ---------------------------------------------------------------------------
# TypeScript EVENT_NAMES extraction
# ---------------------------------------------------------------------------

_FRONTEND_TYPES_PATH = Path(__file__).resolve().parents[1] / "frontend" / "src" / "types.ts"


def _extract_ts_event_names() -> list[str]:
    """Parse EVENT_NAMES from the TypeScript source."""
    text = _FRONTEND_TYPES_PATH.read_text(encoding="utf-8")
    # Match the array contents between EVENT_NAMES = [ ... ] as const;
    match = re.search(
        r"export\s+const\s+EVENT_NAMES\s*=\s*\[(.*?)\]\s*as\s+const",
        text,
        re.DOTALL,
    )
    assert match is not None, "EVENT_NAMES not found in types.ts"
    raw = match.group(1)
    # Extract quoted strings
    return re.findall(r"'([^']+)'", raw)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEventManifestParity:
    """Python EVENT_TYPE_NAMES vs TypeScript EVENT_NAMES."""

    def test_python_event_count(self) -> None:
        assert len(EVENT_TYPE_NAMES) == 65

    def test_typescript_event_count(self) -> None:
        ts_names = _extract_ts_event_names()
        assert len(ts_names) == 65

    def test_python_ts_event_names_match(self) -> None:
        ts_names = _extract_ts_event_names()
        assert EVENT_TYPE_NAMES == ts_names, (
            f"Python-TS event name drift.\n"
            f"  Python only: {set(EVENT_TYPE_NAMES) - set(ts_names)}\n"
            f"  TS only: {set(ts_names) - set(EVENT_TYPE_NAMES)}"
        )

    def test_no_duplicates_python(self) -> None:
        assert len(EVENT_TYPE_NAMES) == len(set(EVENT_TYPE_NAMES))

    def test_no_duplicates_typescript(self) -> None:
        ts_names = _extract_ts_event_names()
        assert len(ts_names) == len(set(ts_names))


class TestMCPToolManifest:
    """MCP tool manifest is non-empty and has no duplicates."""

    def test_mcp_tools_non_empty(self) -> None:
        assert len(MCP_TOOL_NAMES) > 0

    def test_mcp_tools_no_duplicates(self) -> None:
        assert len(MCP_TOOL_NAMES) == len(set(MCP_TOOL_NAMES))


class TestQueenToolManifest:
    """Queen tools derived from _queen_tools() are consistent."""

    def test_queen_tools_non_empty(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent
        from unittest.mock import MagicMock

        runtime = MagicMock()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()  # noqa: SLF001
        assert len(tools) > 0

    def test_queen_tools_no_duplicate_names(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent
        from unittest.mock import MagicMock

        runtime = MagicMock()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()  # noqa: SLF001
        names = [t["name"] for t in tools]
        assert len(names) == len(set(names))

    def test_queen_tools_have_new_wave21_tools(self) -> None:
        from formicos.surface.queen_runtime import QueenAgent
        from unittest.mock import MagicMock

        runtime = MagicMock()
        queen = QueenAgent(runtime)
        tools = queen._queen_tools()  # noqa: SLF001
        names = {t["name"] for t in tools}
        expected = {
            "read_colony_output",
            "memory_search",
            "write_workspace_file",
            "queen_note",
        }
        assert expected.issubset(names), f"Missing: {expected - names}"


class TestAGUIEventManifest:
    """AG-UI event types manifest is non-empty."""

    def test_agui_events_non_empty(self) -> None:
        assert len(AGUI_EVENT_TYPES) > 0

    def test_agui_events_count(self) -> None:
        assert len(AGUI_EVENT_TYPES) == 9
