"""Tests for MCP resources and prompts (Wave 33 B5/B6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from formicos.surface.mcp_server import create_mcp_server


def _make_mock_runtime() -> MagicMock:
    """Build a mock runtime with minimal projection state."""
    runtime = MagicMock()

    # Mock projections
    runtime.projections.memory_entries = {
        "entry-1": {
            "title": "Test entry",
            "content": "Some content",
            "entry_type": "skill",
            "status": "verified",
            "domains": ["python", "testing"],
            "conf_alpha": 10.0,
            "conf_beta": 2.0,
            "workspace_id": "default",
            "thread_id": "main",
            "created_at": "2026-03-01T00:00:00Z",
        },
        "entry-2": {
            "title": "Rejected entry",
            "content": "Bad content",
            "entry_type": "experience",
            "status": "rejected",
            "domains": ["security"],
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "workspace_id": "default",
            "thread_id": "",
            "created_at": "2026-03-02T00:00:00Z",
        },
    }

    # Mock workspace with threads
    mock_thread = MagicMock()
    mock_thread.id = "main"
    mock_thread.name = "Main Thread"
    mock_thread.status = "active"
    mock_thread.goal = "Test goal"
    mock_thread.workflow_steps = []
    mock_thread.colonies = {}

    mock_ws = MagicMock()
    mock_ws.id = "default"
    mock_ws.name = "default"
    mock_ws.threads = {"main": mock_thread}

    runtime.projections.workspaces = {"default": mock_ws}
    runtime.projections.get_colony.return_value = None

    # Colony manager
    runtime.colony_manager = MagicMock()
    runtime.colony_manager.service_router = MagicMock()

    # Queen
    runtime.queen = MagicMock()

    return runtime


class TestMCPServerCreation:
    """Verify MCP server can be created with resources and prompts."""

    def test_create_server_does_not_raise(self) -> None:
        runtime = _make_mock_runtime()
        mcp = create_mcp_server(runtime)
        assert mcp is not None
        assert mcp.name == "FormicOS"
