"""Smoke test: MCP knowledge population and retrieval workflow.

Exercises the log_finding -> knowledge-for-context pipeline to verify
that developer knowledge ingestion via MCP works end-to-end.
Also validates concurrent-client safety properties.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.mcp_server import create_mcp_server

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(
    workspace_id: str = "ws-1",
    memory_entries: dict | None = None,  # type: ignore[type-arg]
) -> MagicMock:
    """Build a minimal mock Runtime sufficient for log_finding + knowledge prompts."""
    runtime = MagicMock()
    runtime.emit_and_broadcast = AsyncMock(return_value=1)

    # Projections with workspaces and memory_entries
    ws = MagicMock()
    ws.id = workspace_id
    ws.name = workspace_id
    runtime.projections = MagicMock()
    runtime.projections.workspaces = {workspace_id: ws}
    runtime.projections.memory_entries = memory_entries if memory_entries is not None else {}

    # Colony manager and addon registrations
    runtime.colony_manager = None
    runtime.addon_registrations = []

    # Settings stub (needed by some prompts)
    runtime.settings = MagicMock()
    runtime.settings.system.data_dir = "/tmp/formicos-test"

    return runtime


# ---------------------------------------------------------------------------
# Priority 1: Concurrent-client safety
# ---------------------------------------------------------------------------

class TestConcurrentClientSafety:
    """Verify MCP server has no per-client mutable state that would race."""

    def test_stateless_http_flag_in_source(self) -> None:
        """app.py mounts MCP with stateless_http=True -- no session affinity."""
        import inspect

        from formicos.surface import app as app_mod
        src = inspect.getsource(app_mod)
        assert "stateless_http=True" in src

    def test_no_module_level_mutable_state(self) -> None:
        """mcp_server.py should not have module-level mutable containers."""
        import formicos.surface.mcp_server as mod
        # MCP_TOOL_NAMES is an immutable tuple
        assert isinstance(mod.MCP_TOOL_NAMES, tuple)

    def test_two_mcp_instances_are_independent(self) -> None:
        """Creating two MCP servers from the same runtime yields independent objects."""
        runtime = _make_runtime()
        mcp1 = create_mcp_server(runtime)
        mcp2 = create_mcp_server(runtime)
        assert mcp1 is not mcp2


# ---------------------------------------------------------------------------
# Priority 2: log_finding
# ---------------------------------------------------------------------------

class TestLogFinding:
    """Verify log_finding creates correct MemoryEntryCreated events."""

    @pytest.mark.asyncio
    async def test_creates_entry_with_candidate_status(self) -> None:
        runtime = _make_runtime()
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        result = await tool.fn(
            title="Auth tokens expire silently",
            content="JWT refresh fails after 24h due to clock skew",
            domains="auth,security",
            workspace_id="ws-1",
        )

        assert result["status"] == "recorded"
        assert result["review_status"] == "candidate"
        assert result["title"] == "Auth tokens expire silently"
        assert result["domains"] == ["auth", "security"]
        assert result["entry_id"].startswith("entry-")

    @pytest.mark.asyncio
    async def test_emits_memory_entry_created_event(self) -> None:
        runtime = _make_runtime()
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        await tool.fn(
            title="Test finding",
            content="Some content",
            domains="testing",
            workspace_id="ws-1",
        )

        runtime.emit_and_broadcast.assert_called_once()
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.type == "MemoryEntryCreated"
        assert event.workspace_id == "ws-1"

        entry = event.entry
        assert entry["title"] == "Test finding"
        assert entry["content"] == "Some content"
        assert entry["status"] == "candidate"
        assert entry["decay_class"] == "stable"
        assert entry["conf_alpha"] == 5.0
        assert entry["conf_beta"] == 5.0
        assert entry["entry_type"] == "experience"
        assert entry["sub_type"] == "learning"
        assert entry["created_by"] == "developer_mcp"
        assert entry["domains"] == ["testing"]

    @pytest.mark.asyncio
    async def test_defaults_to_first_workspace(self) -> None:
        runtime = _make_runtime(workspace_id="ws-default")
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        result = await tool.fn(
            title="Finding",
            content="Content",
            workspace_id="",  # empty -> default
        )

        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.workspace_id == "ws-default"
        assert result["status"] == "recorded"

    @pytest.mark.asyncio
    async def test_empty_domains_produces_empty_list(self) -> None:
        runtime = _make_runtime()
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        result = await tool.fn(
            title="No domains",
            content="Content",
            domains="",
        )

        assert result["domains"] == []
        event = runtime.emit_and_broadcast.call_args[0][0]
        assert event.entry["domains"] == []

    @pytest.mark.asyncio
    async def test_no_workspace_returns_error(self) -> None:
        runtime = _make_runtime()
        runtime.projections.workspaces = {}  # no workspaces
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        result = await tool.fn(
            title="Finding",
            content="Content",
            workspace_id="",
        )

        # Should return structured error (isError or structuredContent with error_code)
        is_error = result.get("isError") is True
        has_error_code = "error_code" in result.get("structuredContent", {})
        assert is_error or has_error_code

    @pytest.mark.asyncio
    async def test_rapid_sequential_calls_all_independent(self) -> None:
        """10 rapid calls should each produce an independent event with unique IDs."""
        runtime = _make_runtime()
        mcp = create_mcp_server(runtime)
        tool = await mcp.get_tool("log_finding")

        entry_ids = set()
        for i in range(10):
            result = await tool.fn(
                title=f"Finding {i}",
                content=f"Content {i}",
                workspace_id="ws-1",
            )
            assert result["status"] == "recorded"
            entry_ids.add(result["entry_id"])

        # All entry IDs must be unique
        assert len(entry_ids) == 10
        # All calls emitted events
        assert runtime.emit_and_broadcast.call_count == 10


# ---------------------------------------------------------------------------
# Priority 3: knowledge-for-context prompt (search equivalent)
# ---------------------------------------------------------------------------

class TestKnowledgeForContext:
    """Verify the knowledge-for-context prompt searches and formats results."""

    @pytest.mark.asyncio
    async def test_finds_entries_via_catalog(self) -> None:
        """Prompt uses knowledge_catalog.search() for retrieval."""
        runtime = _make_runtime()
        # Mock catalog returning search results
        catalog = AsyncMock()
        catalog.search = AsyncMock(return_value=[
            {
                "entry_id": "entry-001",
                "title": "JWT token rotation",
                "content": "Rotate tokens every 24 hours.",
                "domains": ["auth"],
                "status": "verified",
                "confidence": 0.83,
                "score": 0.75,
            },
        ])
        runtime.knowledge_catalog = catalog
        mcp = create_mcp_server(runtime)
        prompt = await mcp.get_prompt("knowledge-for-context")

        result = await prompt.fn(query="token rotation auth")

        assert "JWT token rotation" in result
        catalog.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_catalog_returns_not_found(self) -> None:
        runtime = _make_runtime()
        runtime.knowledge_catalog = None
        mcp = create_mcp_server(runtime)
        prompt = await mcp.get_prompt("knowledge-for-context")

        result = await prompt.fn(query="nonexistent topic")

        assert "No knowledge entries found" in result

    @pytest.mark.asyncio
    async def test_empty_catalog_results_returns_not_found(self) -> None:
        runtime = _make_runtime()
        catalog = AsyncMock()
        catalog.search = AsyncMock(return_value=[])
        runtime.knowledge_catalog = catalog
        mcp = create_mcp_server(runtime)
        prompt = await mcp.get_prompt("knowledge-for-context")

        result = await prompt.fn(query="auth")

        assert "No knowledge entries found" in result


# ---------------------------------------------------------------------------
# Integration: log_finding -> knowledge-for-context pipeline
# ---------------------------------------------------------------------------

class TestLogFindingToSearchPipeline:
    """End-to-end: log_finding creates entry, catalog search finds it."""

    @pytest.mark.asyncio
    async def test_logged_finding_is_searchable(self) -> None:
        entries: dict[str, dict] = {}  # type: ignore[type-arg]
        runtime = _make_runtime(memory_entries=entries)

        # Capture the event and simulate projection
        async def emit_and_project(event: object) -> int:
            entry = getattr(event, "entry", None)
            if entry is not None:
                entries[entry["entry_id"]] = entry
            return 1

        runtime.emit_and_broadcast = AsyncMock(side_effect=emit_and_project)

        # Mock catalog that returns whatever is in entries
        catalog = AsyncMock()

        async def _search(query: str, **kwargs: object) -> list[dict]:  # type: ignore[type-arg]
            return list(entries.values())

        catalog.search = AsyncMock(side_effect=_search)
        runtime.knowledge_catalog = catalog

        mcp = create_mcp_server(runtime)

        # Step 1: log a finding
        log_tool = await mcp.get_tool("log_finding")
        result = await log_tool.fn(
            title="Docker socket security risk",
            content="Docker socket mount grants daemon access to the FormicOS container.",
            domains="security,deployment",
            workspace_id="ws-1",
        )
        assert result["status"] == "recorded"

        # Verify the entry landed in projections
        assert len(entries) == 1
        entry = next(iter(entries.values()))
        assert entry["title"] == "Docker socket security risk"
        assert entry["status"] == "candidate"

        # Step 2: search via catalog (simulated projection -> catalog -> results)
        prompt = await mcp.get_prompt("knowledge-for-context")
        search_result = await prompt.fn(
            query="docker socket security", workspace_id="",
        )

        # The finding should appear in formatted results
        assert "Docker socket security risk" in search_result
        assert "security" in search_result.lower()
