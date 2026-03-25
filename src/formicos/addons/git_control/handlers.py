"""Git control addon event handlers — auto-stage colony output."""

from __future__ import annotations

import subprocess
from typing import Any

import structlog

log = structlog.get_logger()


async def on_colony_completed_auto_stage(
    event: Any,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> None:
    """On ColonyCompleted, auto-stage modified files in the workspace.

    Opt-in via workspace config: ``git_auto_stage: true``.
    Uses ``git status --porcelain`` to find modified (not untracked) files,
    then stages them. Never runs ``git add -A``.
    """
    ctx = runtime_context or {}
    settings = ctx.get("settings", {})
    workspace_config = getattr(settings, "workspace_config", {}) if settings else {}
    if isinstance(settings, dict):
        workspace_config = settings.get("workspace_config", {})

    if not workspace_config.get("git_auto_stage", False):
        return

    workspace_root_fn = ctx.get("workspace_root_fn")
    workspace_id = getattr(event, "workspace_id", "") or getattr(event, "address", "")
    if not workspace_root_fn or not workspace_id:
        log.info("git_control.auto_stage_skipped", reason="no_workspace_context")
        return

    ws_path = workspace_root_fn(workspace_id)
    if not ws_path.is_dir():
        log.info("git_control.auto_stage_skipped", reason="workspace_not_found")
        return

    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ws_path),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if result.returncode != 0:
            log.warning("git_control.auto_stage_git_error", stderr=result.stderr)
            return

        # Stage files with worktree modifications (column 2 = M),
        # but skip untracked (??) and ignored (!!) files.
        # Porcelain format: XY filename  (X=index, Y=worktree)
        modified = []
        for line in result.stdout.splitlines():
            if len(line) < 4:
                continue
            index_status, worktree_status = line[0], line[1]
            # Skip untracked and ignored
            if index_status == "?" or index_status == "!":
                continue
            # Stage files modified in the worktree (not already fully staged)
            if worktree_status == "M":
                # Handle quoted paths (git quotes paths with special chars)
                path = line[3:]
                if path.startswith('"') and path.endswith('"'):
                    path = path[1:-1].encode("utf-8").decode("unicode_escape")
                modified.append(path)

        if not modified:
            log.info("git_control.auto_stage_nothing", workspace=workspace_id)
            return

        subprocess.run(
            ["git", "add", *modified],
            cwd=str(ws_path),
            capture_output=True,
            timeout=15,
            check=False,
        )
        log.info(
            "git_control.auto_staged",
            workspace=workspace_id,
            file_count=len(modified),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        log.warning("git_control.auto_stage_failed", exc_info=True)
