"""Tests for git control addon — smart commit, branch analysis, auto-stage."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from formicos.addons.git_control.handlers import on_colony_completed_auto_stage
from formicos.addons.git_control.tools import (
    _is_forbidden,
    _run_git,
    handle_branch_analysis,
    handle_create_branch,
    handle_smart_commit,
    handle_stash,
)


def _make_ctx(tmp_path: Path | None = None) -> dict[str, Any]:
    """Build a runtime_context with a real or mock workspace path."""
    if tmp_path is not None:
        return {"workspace_root_fn": lambda _ws: tmp_path}
    mock_path = MagicMock()
    mock_path.is_dir.return_value = True
    return {"workspace_root_fn": lambda _ws: mock_path}


# ---------------------------------------------------------------------------
# _is_forbidden / _run_git safety checks
# ---------------------------------------------------------------------------


class TestForbiddenOps:
    """Test the forbidden git operations safety check."""

    def test_blocks_push_force(self) -> None:
        assert _is_forbidden(["push", "--force"]) is not None

    def test_blocks_push_f(self) -> None:
        assert _is_forbidden(["push", "-f"]) is not None

    def test_blocks_reset_hard(self) -> None:
        assert _is_forbidden(["reset", "--hard"]) is not None

    def test_blocks_clean_f(self) -> None:
        assert _is_forbidden(["clean", "-f"]) is not None

    def test_blocks_clean_fd(self) -> None:
        assert _is_forbidden(["clean", "-fd"]) is not None

    def test_allows_normal_push(self) -> None:
        assert _is_forbidden(["push", "origin", "main"]) is None

    def test_allows_log_with_force_in_format(self) -> None:
        """'--force' in a different context should not be blocked."""
        assert _is_forbidden(["log", "--format=force"]) is None

    def test_allows_reset_soft(self) -> None:
        assert _is_forbidden(["reset", "--soft", "HEAD~1"]) is None

    def test_run_git_returns_error_for_forbidden(self, tmp_path: Path) -> None:
        rc, _out, err = _run_git(["push", "--force"], tmp_path)
        assert rc == -1
        assert "Forbidden" in err


# ---------------------------------------------------------------------------
# Smart commit
# ---------------------------------------------------------------------------


class TestSmartCommit:
    """Test git_smart_commit handler."""

    def test_no_workspace_returns_error(self) -> None:
        result = asyncio.run(
            handle_smart_commit({"message_hint": "fix auth bug"}, "ws1", "th1")
        )
        assert "Error" in result

    def test_no_workspace_with_empty_context(self) -> None:
        result = asyncio.run(
            handle_smart_commit({}, "ws1", "th1", runtime_context={})
        )
        assert "Error" in result

    def test_phase1_returns_staged_diff(self, tmp_path: Path) -> None:
        """Phase 1 (no message) returns staged diff context."""
        diff_stat = " src/main.py | 3 +++\n 1 file changed, 3 insertions(+)"
        full_diff = "+def new_fn():\n+    return 42"
        log_out = "abc1234 fix: auth\ndef5678 feat: login"
        git_responses = [
            (0, diff_stat, ""),     # diff --cached --stat
            (0, full_diff, ""),     # diff --cached
            (0, log_out, ""),       # log --oneline -5
        ]
        call_idx = {"i": 0}

        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            idx = call_idx["i"]
            call_idx["i"] += 1
            return git_responses[idx] if idx < len(git_responses) else (1, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_smart_commit({}, "ws1", "th1", runtime_context=ctx)
            )
        assert "Staged changes" in result
        assert "new_fn" in result
        assert "Recent commits" in result

    def test_phase1_no_staged_changes(self, tmp_path: Path) -> None:
        """Phase 1 with empty diff returns clear message."""
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_smart_commit({}, "ws1", "th1", runtime_context=ctx)
            )
        assert "No staged changes" in result

    def test_phase2_executes_commit(self, tmp_path: Path) -> None:
        """Phase 2 (with message) calls git commit."""
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            if args[0] == "commit":
                assert "-m" in args
                return (0, "[main abc1234] fix auth\n 1 file changed", "")
            return (1, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_smart_commit(
                    {"message": "fix auth"},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "Commit successful" in result

    def test_phase2_commit_failure(self, tmp_path: Path) -> None:
        """Phase 2 with commit failure returns error."""
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            return (1, "", "nothing to commit, working tree clean")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_smart_commit(
                    {"message": "fix auth"},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "Commit failed" in result


# ---------------------------------------------------------------------------
# Branch analysis
# ---------------------------------------------------------------------------


class TestBranchAnalysis:
    """Test git_branch_analysis handler."""

    def test_missing_branch_returns_error(self) -> None:
        result = asyncio.run(
            handle_branch_analysis({}, "ws1", "th1")
        )
        assert "Error" in result

    def test_no_workspace_returns_error(self) -> None:
        result = asyncio.run(
            handle_branch_analysis(
                {"branch": "feature/auth", "base": "main"},
                "ws1", "th1",
            )
        )
        assert "Error" in result

    def test_returns_ahead_behind_counts(self, tmp_path: Path) -> None:
        """Branch analysis returns commit counts and strategy."""
        responses: dict[str, tuple[int, str, str]] = {}

        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            if args[0] == "merge-base":
                return (0, "abc123def456\n", "")
            if "abc123def4..feature/auth" in args[-1]:
                return (0, "111 feat: login\n222 feat: signup\n333 fix: session\n", "")
            if "abc123def4..main" in args[-1]:
                return (0, "", "")  # zero behind
            if args[0] == "diff" and "--stat" in args:
                return (0, " src/auth.py | 10 ++++\n 1 file changed\n", "")
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_branch_analysis(
                    {"branch": "feature/auth", "base": "main"},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "Commits ahead:" in result
        assert "3" in result  # 3 ahead
        assert "Fast-forward" in result  # zero behind = fast-forward

    def test_merge_strategy_when_behind(self, tmp_path: Path) -> None:
        """Many commits behind = merge commit strategy."""
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            if args[0] == "merge-base":
                return (0, "abc123\n", "")
            if "abc123..feature/x" in " ".join(args):
                return (0, "\n".join(f"{i} commit" for i in range(10)) + "\n", "")
            if "abc123..main" in " ".join(args):
                return (0, "\n".join(f"{i} commit" for i in range(15)) + "\n", "")
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_branch_analysis(
                    {"branch": "feature/x", "base": "main"},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "Merge commit" in result


# ---------------------------------------------------------------------------
# Create branch
# ---------------------------------------------------------------------------


class TestCreateBranch:
    """Test git_create_branch handler."""

    def test_no_workspace_returns_error(self) -> None:
        result = asyncio.run(
            handle_create_branch({"branch_name": "feat/x"}, "ws1", "th1")
        )
        assert "Error" in result

    def test_missing_branch_name_returns_error(self) -> None:
        result = asyncio.run(
            handle_create_branch({}, "ws1", "th1", runtime_context={})
        )
        assert "Error" in result

    def test_creates_and_checks_out(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            assert args == ["checkout", "-b", "feat/new"]
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_create_branch(
                    {"branch_name": "feat/new", "checkout": True},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "created and checked out" in result

    def test_creates_without_checkout(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            assert args == ["branch", "feat/new"]
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_create_branch(
                    {"branch_name": "feat/new", "checkout": False},
                    "ws1", "th1", runtime_context=ctx,
                )
            )
        assert "created" in result
        assert "checked out" not in result


# ---------------------------------------------------------------------------
# Stash
# ---------------------------------------------------------------------------


class TestStash:
    """Test git_stash handler."""

    def test_no_workspace_returns_error(self) -> None:
        result = asyncio.run(
            handle_stash({"action": "save"}, "ws1", "th1")
        )
        assert "Error" in result

    def test_unknown_action_returns_error(self) -> None:
        ctx = _make_ctx()
        result = asyncio.run(
            handle_stash({"action": "explode"}, "ws1", "th1", runtime_context=ctx)
        )
        assert "Unknown" in result

    def test_stash_save(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            assert "stash" in args
            return (0, "Saved working directory", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_stash({"action": "save"}, "ws1", "th1", runtime_context=ctx)
            )
        assert "Stash saved" in result

    def test_stash_pop(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            return (0, "Applied stash@{0}", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_stash({"action": "pop"}, "ws1", "th1", runtime_context=ctx)
            )
        assert "Stash restored" in result

    def test_stash_list(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            return (0, "stash@{0}: WIP on main", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_stash({"action": "list"}, "ws1", "th1", runtime_context=ctx)
            )
        assert "stash@{0}" in result

    def test_stash_list_empty(self, tmp_path: Path) -> None:
        def mock_run_git(args: list[str], cwd: Any, **kw: Any) -> tuple[int, str, str]:
            return (0, "", "")

        ctx = _make_ctx(tmp_path)
        with patch("formicos.addons.git_control.tools._run_git", side_effect=mock_run_git):
            result = asyncio.run(
                handle_stash({"action": "list"}, "ws1", "th1", runtime_context=ctx)
            )
        assert "No stashes" in result


# ---------------------------------------------------------------------------
# Auto-stage
# ---------------------------------------------------------------------------


class TestAutoStage:
    """Test auto-stage handler."""

    def test_auto_stage_no_config_does_nothing(self) -> None:
        """Auto-stage does nothing with no runtime context."""
        asyncio.run(
            on_colony_completed_auto_stage({"type": "ColonyCompleted"})
        )

    def test_auto_stage_disabled_does_nothing(self) -> None:
        """Auto-stage does nothing when git_auto_stage is false."""
        asyncio.run(
            on_colony_completed_auto_stage(
                {"type": "ColonyCompleted"},
                runtime_context={
                    "settings": {"workspace_config": {"git_auto_stage": False}},
                },
            )
        )

    def test_auto_stage_stages_modified_files(self, tmp_path: Path) -> None:
        """Auto-stage detects worktree-modified files and stages them."""
        porcelain_output = " M src/auth.py\nMM src/login.py\n?? untracked.txt\n"
        git_calls: list[list[str]] = []

        def mock_subprocess_run(args: list[str], **kw: Any) -> MagicMock:
            git_calls.append(args)
            result = MagicMock()
            if "status" in args:
                result.returncode = 0
                result.stdout = porcelain_output
            else:
                result.returncode = 0
                result.stdout = ""
            return result

        event = MagicMock()
        event.workspace_id = "ws1"
        event.address = "ws1"

        ctx: dict[str, Any] = {
            "settings": {"workspace_config": {"git_auto_stage": True}},
            "workspace_root_fn": lambda _ws: tmp_path,
        }

        with patch("formicos.addons.git_control.handlers.subprocess.run", side_effect=mock_subprocess_run):
            asyncio.run(
                on_colony_completed_auto_stage(event, runtime_context=ctx)
            )

        # Should have called git status then git add
        assert len(git_calls) == 2
        add_args = git_calls[1]
        assert "add" in add_args
        # Should stage auth.py and login.py (both have M in worktree column)
        assert "src/auth.py" in add_args
        assert "src/login.py" in add_args
        # Should NOT stage untracked files
        assert "untracked.txt" not in add_args

    def test_auto_stage_skips_untracked_only(self, tmp_path: Path) -> None:
        """Auto-stage does nothing when only untracked files exist."""
        def mock_subprocess_run(args: list[str], **kw: Any) -> MagicMock:
            result = MagicMock()
            result.returncode = 0
            result.stdout = "?? new_file.py\n?? another.py\n"
            return result

        event = MagicMock()
        event.workspace_id = "ws1"
        ctx: dict[str, Any] = {
            "settings": {"workspace_config": {"git_auto_stage": True}},
            "workspace_root_fn": lambda _ws: tmp_path,
        }

        with patch("formicos.addons.git_control.handlers.subprocess.run", side_effect=mock_subprocess_run) as mock_run:
            asyncio.run(
                on_colony_completed_auto_stage(event, runtime_context=ctx)
            )
        # Should call git status but NOT git add (nothing to stage)
        assert mock_run.call_count == 1
