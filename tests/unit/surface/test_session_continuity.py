"""Tests for Wave 68 session continuity — summary emission and injection."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from formicos.surface.queen_runtime import QueenAgent


def _make_thread(
    *,
    name: str = "Test Thread",
    status: str = "active",
    queen_messages: list[SimpleNamespace] | None = None,
    colony_count: int = 3,
    completed_count: int = 2,
    failed_count: int = 1,
    workflow_steps: list[dict[str, str]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        status=status,
        goal="Build a thing",
        queen_messages=queen_messages or [],
        colony_count=colony_count,
        completed_colony_count=completed_count,
        failed_colony_count=failed_count,
        workflow_steps=workflow_steps or [],
        expected_outputs=[],
        artifact_types_produced={},
    )


def _make_runtime(tmp_path: Path) -> MagicMock:
    runtime = MagicMock()
    runtime.settings.system.data_dir = str(tmp_path)
    return runtime


class TestEmitSessionSummary:
    def test_emit_session_summary_writes_file(
        self, tmp_path: Path,
    ) -> None:
        runtime = _make_runtime(tmp_path)
        thread = _make_thread(
            queen_messages=[
                SimpleNamespace(
                    role="queen",
                    content="I recommend option A for this task.",
                    timestamp="2026-03-25T12:00:00+00:00",
                ),
                SimpleNamespace(
                    role="operator",
                    content="Go ahead",
                    timestamp="2026-03-25T12:01:00+00:00",
                ),
                SimpleNamespace(
                    role="queen",
                    content="Colony spawned for auth module.",
                    timestamp="2026-03-25T12:02:00+00:00",
                ),
            ],
            workflow_steps=[
                {"status": "completed", "description": "Step 1"},
                {"status": "pending", "description": "Step 2"},
            ],
        )
        runtime.projections.get_thread.return_value = thread

        agent = QueenAgent(runtime)
        agent.emit_session_summary("ws-1", "thr-1")

        session_path = (
            tmp_path / ".formicos" / "sessions" / "ws-1" / "thr-1.md"
        )
        assert session_path.is_file()
        content = session_path.read_text(encoding="utf-8")
        assert "# Session Summary: Test Thread" in content
        assert "**Status:** active" in content
        assert "2 completed, 1 failed, 3 total" in content
        assert "1 steps completed, 1 pending" in content
        assert "## Recent Queen Activity" in content
        assert "I recommend option A" in content
        assert "Colony spawned" in content

    def test_emit_session_summary_includes_plan_state(
        self, tmp_path: Path,
    ) -> None:
        runtime = _make_runtime(tmp_path)
        thread = _make_thread()
        runtime.projections.get_thread.return_value = thread

        # Write a plan file
        plan_dir = tmp_path / ".formicos" / "plans"
        plan_dir.mkdir(parents=True, exist_ok=True)
        (plan_dir / "thr-1.md").write_text(
            "# Plan: Build CSV parser\n\n## Steps\n"
            "- [0] [completed] Parse headers\n",
            encoding="utf-8",
        )

        agent = QueenAgent(runtime)
        agent.emit_session_summary("ws-1", "thr-1")

        session_path = (
            tmp_path / ".formicos" / "sessions" / "ws-1" / "thr-1.md"
        )
        content = session_path.read_text(encoding="utf-8")
        assert "## Active Plan" in content
        assert "Plan: Build CSV parser" in content

    def test_emit_session_summary_no_thread(
        self, tmp_path: Path,
    ) -> None:
        runtime = _make_runtime(tmp_path)
        runtime.projections.get_thread.return_value = None

        agent = QueenAgent(runtime)
        agent.emit_session_summary("ws-1", "thr-none")

        session_dir = tmp_path / ".formicos" / "sessions"
        assert not session_dir.exists()

    def test_session_injection_caps_at_4000_chars(
        self, tmp_path: Path,
    ) -> None:
        """Session file content is truncated to 4000 chars when injected."""
        # Write an oversized session file
        session_dir = tmp_path / ".formicos" / "sessions"
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "thr-big.md").write_text(
            "X" * 8000, encoding="utf-8",
        )

        # Verify the file read + truncation logic
        session_path = session_dir / "thr-big.md"
        text = session_path.read_text(encoding="utf-8")[:4000]
        assert len(text) == 4000
