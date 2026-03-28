"""Unit tests for Wave 65 Queen autonomous agency tools:
batch_command, summarize_thread, draft_document, list_addons."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from formicos.surface.queen_tools import QueenToolDispatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_runtime(
    ws_dir: str | None = None,
    *,
    thread: SimpleNamespace | None = None,
) -> MagicMock:
    """Build a minimal mock runtime for Wave 65 tool tests."""
    runtime = MagicMock()
    runtime.parse_tool_input = MagicMock(side_effect=lambda tc: tc.get("input", {}))
    runtime.projections.queen_notes = {}
    runtime.projections.colony_outcomes = {}
    runtime.projections.colonies = {}
    runtime.projections.memory_entries = {}
    runtime.projections.cooccurrence_weights = {}
    runtime.projections.distillation_candidates = []
    runtime.projections.operator_behavior = MagicMock()
    runtime.projections.get_colony = MagicMock(
        side_effect=lambda cid: runtime.projections.colonies.get(cid),
    )
    runtime.settings.governance.max_rounds_per_colony = 20
    runtime.settings.models.defaults.coder = "local/qwen3"
    runtime.settings.models.registry = []

    if ws_dir is not None or thread is not None:
        threads = {}
        if thread is not None:
            threads[thread.id] = thread
        ws = SimpleNamespace(
            directory=ws_dir,
            repo_path=ws_dir,
            config={},
            threads=threads,
        )
        runtime.projections.workspaces = {"ws1": ws}
    else:
        runtime.projections.workspaces = {}

    return runtime


def _make_thread() -> SimpleNamespace:
    """Build a mock thread with two colonies."""
    colony1 = SimpleNamespace(
        id="c1",
        display_name="impl",
        status="completed",
        round_number=3,
        cost=0.15,
        quality_score=0.8,
        castes=["coder"],
        skills_extracted=2,
    )
    colony2 = SimpleNamespace(
        id="c2",
        display_name="review",
        status="failed",
        round_number=5,
        cost=0.25,
        quality_score=0.2,
        castes=["reviewer"],
        skills_extracted=0,
    )
    return SimpleNamespace(
        id="t1",
        name="Feature branch",
        goal="Implement OAuth",
        status="active",
        colonies={"c1": colony1, "c2": colony2},
        completed_colony_count=1,
        failed_colony_count=1,
        workflow_steps=[{"description": "Implement auth", "status": "completed"}],
        active_plan=None,
        parallel_groups=None,
    )


# ---------------------------------------------------------------------------
# batch_command tests
# ---------------------------------------------------------------------------


class TestBatchCommand:
    @pytest.mark.anyio()
    async def test_batch_command_runs_multiple(self) -> None:
        """batch_command executes all commands and returns combined results."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        dispatcher._run_command = AsyncMock(  # pyright: ignore[reportPrivateUsage]
            return_value=("Exit code: 0\nstdout:\nok", None),
        )

        result, meta = await dispatcher._batch_command(  # pyright: ignore[reportPrivateUsage]
            {"commands": ["git status", "ruff check src/"]},
            "ws1",
        )

        assert "git status" in result
        assert "ruff check src/" in result
        assert result.count("Exit code: 0") == 2
        assert meta is not None
        assert meta["tool"] == "batch_command"

    @pytest.mark.anyio()
    async def test_batch_command_stops_on_error(self) -> None:
        """batch_command stops after a non-zero exit code when stop_on_error is True."""
        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)

        call_count = 0

        async def _mock_run_command(
            inputs: dict[str, Any], workspace_id: str,
        ) -> tuple[str, dict[str, Any] | None]:
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                return ("Exit code: 1\nstdout:\nfailure", None)
            return ("Exit code: 0\nstdout:\nok", None)

        dispatcher._run_command = _mock_run_command  # type: ignore[assignment]

        result, _ = await dispatcher._batch_command(  # pyright: ignore[reportPrivateUsage]
            {"commands": ["cmd1", "cmd2", "cmd3"]},
            "ws1",
        )

        assert "stopped" in result
        # Only 2 commands should have run (not the third)
        assert call_count == 2
        assert "cmd3" not in result


# ---------------------------------------------------------------------------
# summarize_thread tests
# ---------------------------------------------------------------------------


class TestSummarizeThread:
    def test_summarize_thread_returns_structured_output(self) -> None:
        """summarize_thread returns formatted markdown with thread details."""
        thread = _make_thread()
        runtime = _make_runtime(thread=thread)
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._summarize_thread(  # pyright: ignore[reportPrivateUsage]
            {"thread_id": "t1"},
            "ws1",
            "t1",
        )

        # Thread name and goal
        assert "Feature branch" in result
        assert "Implement OAuth" in result
        # Colony count header
        assert "Colonies (2)" in result
        # Cost totals (0.15 + 0.25 = 0.40)
        assert "$0.400" in result
        # Colony statuses
        assert "impl" in result
        assert "ok" in result  # completed renders as "ok"
        assert "review" in result
        assert "failed" in result
        # Workflow steps
        assert "Implement auth" in result
        # Knowledge extracted (2 total)
        assert "Knowledge entries extracted: 2" in result


# ---------------------------------------------------------------------------
# draft_document tests
# ---------------------------------------------------------------------------


class TestDraftDocument:
    def test_draft_document_writes_file(self, tmp_path: Path) -> None:
        """draft_document creates a file with the given content."""
        runtime = _make_runtime(ws_dir=str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._draft_document(  # pyright: ignore[reportPrivateUsage]
            {"path": "CHANGELOG.md", "content": "# v1.0", "mode": "overwrite"},
            "ws1",
        )

        target = tmp_path / "CHANGELOG.md"
        assert target.exists()
        assert target.read_text(encoding="utf-8") == "# v1.0"
        assert "Written" in result
        assert "CHANGELOG.md" in result
        assert meta is not None
        assert meta["tool"] == "draft_document"
        assert meta["mode"] == "overwrite"

    def test_draft_document_prepend_mode(self, tmp_path: Path) -> None:
        """draft_document prepend mode inserts content before existing text."""
        existing_file = tmp_path / "notes.md"
        existing_file.write_text("Old content", encoding="utf-8")

        runtime = _make_runtime(ws_dir=str(tmp_path))
        dispatcher = QueenToolDispatcher(runtime)

        result, meta = dispatcher._draft_document(  # pyright: ignore[reportPrivateUsage]
            {"path": "notes.md", "content": "New header", "mode": "prepend"},
            "ws1",
        )

        content = existing_file.read_text(encoding="utf-8")
        # New content should appear before old content
        new_pos = content.index("New header")
        old_pos = content.index("Old content")
        assert new_pos < old_pos
        assert "Written" in result
        assert meta is not None
        assert meta["mode"] == "prepend"


# ---------------------------------------------------------------------------
# list_addons tests
# ---------------------------------------------------------------------------


class TestListAddons:
    def test_list_addons_shows_addon_tools(self) -> None:
        """list_addons reports registered addon manifests with capabilities."""
        from formicos.surface.addon_loader import AddonManifest, AddonToolSpec

        runtime = _make_runtime()
        dispatcher = QueenToolDispatcher(runtime)
        dispatcher._addon_manifests = [  # pyright: ignore[reportPrivateUsage]
            AddonManifest(
                name="codebase-index",
                description="Search code",
                content_kinds=["source_code"],
                search_tool="semantic_search",
                tools=[
                    AddonToolSpec(
                        name="semantic_search",
                        description="Search code",
                        handler="search.py::handle",
                    ),
                ],
            ),
        ]

        result, meta = dispatcher._list_addons()  # pyright: ignore[reportPrivateUsage]

        assert "semantic_search" in result
        assert "codebase-index" in result
        assert "Search code" in result
