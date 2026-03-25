"""Git control addon tools — smart commit, branch analysis, branch creation, stash."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from pathlib import Path

log = structlog.get_logger()

# Safety: forbidden subcommand + flag pairs (checked as consecutive args)
_FORBIDDEN_GIT_OPS: list[tuple[str, ...]] = [
    ("push", "--force"),
    ("push", "-f"),
    ("reset", "--hard"),
    ("clean", "-f"),
    ("clean", "-fd"),
]


def _is_forbidden(args: list[str]) -> str | None:
    """Return a description if args match a forbidden operation, else None."""
    for forbidden in _FORBIDDEN_GIT_OPS:
        # Check that forbidden tokens appear as consecutive elements in args
        flen = len(forbidden)
        for i in range(len(args) - flen + 1):
            if tuple(args[i:i + flen]) == forbidden:
                return " ".join(forbidden)
    return None


def _run_git(
    args: list[str], cwd: Path, *, timeout: int = 30,
) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    blocked = _is_forbidden(args)
    if blocked:
        return -1, "", f"Forbidden git operation: git {blocked}"
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "git command timed out"
    except FileNotFoundError:
        return -1, "", "git not found"


def _resolve_workspace_path(
    workspace_id: str,
    runtime_context: dict[str, Any] | None,
) -> Path | None:
    """Get the workspace filesystem root from runtime context."""
    ctx = runtime_context or {}
    workspace_root_fn = ctx.get("workspace_root_fn")
    if workspace_root_fn is None:
        return None
    path = workspace_root_fn(workspace_id)
    return path if path.is_dir() else None


async def handle_smart_commit(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Two-phase smart commit: inspect staged changes or execute commit.

    Phase 1 (no message): Returns staged diff and recent commit style.
    Phase 2 (with message): Executes the commit.
    """
    ws_path = _resolve_workspace_path(workspace_id, runtime_context)
    if ws_path is None:
        return "Error: workspace path not found. Ensure runtime context is configured."

    message = inputs.get("message", "")
    amend = inputs.get("amend", False)
    message_hint = inputs.get("message_hint", "")

    # Phase 2: execute commit
    if message:
        args = ["commit", "-m", message]
        if amend:
            args.append("--amend")
        rc, stdout, stderr = _run_git(args, ws_path)
        if rc != 0:
            return f"Commit failed (exit {rc}):\n{stderr.strip()}"
        return f"Commit successful:\n{stdout.strip()}"

    # Phase 1: gather context for Queen to generate commit message
    lines: list[str] = ["## Git Smart Commit Context\n"]

    if amend:
        lines.append("**Mode:** Amend last commit\n")
    else:
        lines.append("**Mode:** New commit\n")

    if message_hint:
        lines.append(f"**Hint:** {message_hint}\n")

    # Get staged diff
    rc, diff_out, _ = _run_git(["diff", "--cached", "--stat"], ws_path)
    if rc == 0 and diff_out.strip():
        lines.append("### Staged changes (summary)")
        lines.append(f"```\n{diff_out.strip()}\n```\n")

        # Get detailed diff (truncated for context window)
        rc2, full_diff, _ = _run_git(["diff", "--cached"], ws_path)
        if rc2 == 0 and full_diff.strip():
            truncated = full_diff[:3000]
            if len(full_diff) > 3000:
                truncated += "\n... (truncated)"
            lines.append("### Staged diff (detail)")
            lines.append(f"```diff\n{truncated}\n```\n")
    else:
        lines.append("**No staged changes.** Use `git add` to stage files first.\n")

    # Get recent commit style
    rc, log_out, _ = _run_git(["log", "--oneline", "-5"], ws_path)
    if rc == 0 and log_out.strip():
        lines.append("### Recent commits (style reference)")
        lines.append(f"```\n{log_out.strip()}\n```\n")

    lines.append(
        "*Generate a commit message based on the staged changes above, "
        "then call `git_smart_commit` again with `message` to execute.*"
    )
    return "\n".join(lines)


async def handle_branch_analysis(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Analyze branch divergence with real git data."""
    ws_path = _resolve_workspace_path(workspace_id, runtime_context)
    if ws_path is None:
        return "Error: workspace path not found. Ensure runtime context is configured."

    branch = inputs.get("branch", "")
    base = inputs.get("base", "main")

    if not branch:
        return "Error: 'branch' parameter is required."

    lines: list[str] = [f"## Branch Analysis: `{branch}` vs `{base}`\n"]

    # Find merge base
    rc, merge_base, _ = _run_git(["merge-base", base, branch], ws_path)
    if rc != 0:
        return f"Cannot find merge base between `{base}` and `{branch}`. Are both branches valid?"

    mb = merge_base.strip()
    lines.append(f"**Merge base:** `{mb[:10]}`\n")

    # Branch commits
    rc, branch_log, _ = _run_git(["log", "--oneline", f"{mb}..{branch}"], ws_path)
    ahead = len(branch_log.strip().splitlines()) if branch_log.strip() else 0
    lines.append(f"**Commits ahead:** {ahead}")
    if branch_log.strip():
        lines.append(f"```\n{branch_log.strip()}\n```\n")

    # Base commits since diverge
    rc, base_log, _ = _run_git(["log", "--oneline", f"{mb}..{base}"], ws_path)
    behind = len(base_log.strip().splitlines()) if base_log.strip() else 0
    lines.append(f"**Commits behind:** {behind}")
    if base_log.strip():
        lines.append(f"```\n{base_log.strip()}\n```\n")

    # File change summary
    rc, stat_out, _ = _run_git(["diff", "--stat", f"{mb}..{branch}"], ws_path)
    if rc == 0 and stat_out.strip():
        lines.append("### Changed files")
        lines.append(f"```\n{stat_out.strip()}\n```\n")

    # Suggest strategy
    if behind == 0:
        lines.append("**Suggested strategy:** Fast-forward merge")
    elif ahead <= 3 and behind <= 10:
        lines.append("**Suggested strategy:** Rebase onto base")
    else:
        lines.append("**Suggested strategy:** Merge commit")

    return "\n".join(lines)


async def handle_create_branch(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Create a new git branch and optionally switch to it."""
    ws_path = _resolve_workspace_path(workspace_id, runtime_context)
    if ws_path is None:
        return "Error: workspace path not found."

    branch_name = inputs.get("branch_name", "")
    checkout = inputs.get("checkout", True)

    if not branch_name:
        return "Error: 'branch_name' parameter is required."

    if checkout:
        rc, _, stderr = _run_git(["checkout", "-b", branch_name], ws_path)
    else:
        rc, _, stderr = _run_git(["branch", branch_name], ws_path)

    if rc != 0:
        return f"Failed to create branch '{branch_name}': {stderr.strip()}"
    return f"Branch '{branch_name}' created{' and checked out' if checkout else ''}."


async def handle_stash(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> str:
    """Save or restore stashed changes."""
    ws_path = _resolve_workspace_path(workspace_id, runtime_context)
    if ws_path is None:
        return "Error: workspace path not found."

    action = inputs.get("action", "save")
    stash_message = inputs.get("message", "")

    if action == "save":
        args = ["stash", "push"]
        if stash_message:
            args.extend(["-m", stash_message])
        rc, stdout, stderr = _run_git(args, ws_path)
        if rc != 0:
            return f"Stash save failed: {stderr.strip()}"
        return f"Stash saved: {stdout.strip()}"
    elif action == "pop":
        rc, stdout, stderr = _run_git(["stash", "pop"], ws_path)
        if rc != 0:
            return f"Stash pop failed: {stderr.strip()}"
        return f"Stash restored: {stdout.strip()}"
    elif action == "list":
        rc, stdout, _ = _run_git(["stash", "list"], ws_path)
        if not stdout.strip():
            return "No stashes found."
        return f"Stashes:\n```\n{stdout.strip()}\n```"
    else:
        return f"Unknown stash action '{action}'. Use 'save', 'pop', or 'list'."
