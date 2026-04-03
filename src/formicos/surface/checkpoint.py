"""Shadow Git checkpoints for file safety (Wave 78 Track 1).

Creates shadow git repos that track workspace file state without touching
the operator's own ``.git`` directory. Uses ``GIT_DIR`` + ``GIT_WORK_TREE``
env vars so no ``.git`` folder is created inside the workspace.

Shadow repos live at ``{data_dir}/.formicos/checkpoints/{dir_hash}/``.
"""

from __future__ import annotations

import contextlib
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import structlog

log = structlog.get_logger()

_GIT_TIMEOUT = 5  # seconds per git operation


@dataclass(frozen=True)
class Checkpoint:
    """A single shadow checkpoint record."""

    hash: str
    message: str
    timestamp: str


def _shadow_dir(data_dir: str, workspace_dir: str) -> Path:
    """Compute the shadow git repo path for a workspace directory."""
    dir_hash = hashlib.sha256(
        str(Path(workspace_dir).resolve()).encode(),
    ).hexdigest()[:16]
    return Path(data_dir) / ".formicos" / "checkpoints" / dir_hash


def _git(
    shadow: Path,
    work_tree: str,
    *args: str,
) -> subprocess.CompletedProcess[str]:
    """Run a git command against a shadow repo."""
    import os as _os  # noqa: PLC0415

    # Merge with current env so git can find its binaries
    env = {**_os.environ}
    env.update({
        "GIT_DIR": str(shadow),
        "GIT_WORK_TREE": work_tree,
        "GIT_AUTHOR_NAME": "FormicOS",
        "GIT_AUTHOR_EMAIL": "formicos@localhost",
        "GIT_COMMITTER_NAME": "FormicOS",
        "GIT_COMMITTER_EMAIL": "formicos@localhost",
    })
    return subprocess.run(  # noqa: S603
        ["git", *args],
        capture_output=True,
        text=True,
        timeout=_GIT_TIMEOUT,
        env=env,
        check=False,
    )


class CheckpointManager:
    """Manages shadow git checkpoints for workspace directories."""

    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    def _ensure_repo(self, workspace_dir: str) -> Path:
        """Initialize shadow repo if needed, return its path."""
        shadow = _shadow_dir(self._data_dir, workspace_dir)
        if not (shadow / "HEAD").exists():
            shadow.mkdir(parents=True, exist_ok=True)
            try:
                result = _git(shadow, workspace_dir, "init")
            except FileNotFoundError:
                log.warning("checkpoint.git_not_found")
                return shadow
            if result.returncode != 0:
                log.warning(
                    "checkpoint.init_failed",
                    stderr=result.stderr[:200],
                )
            else:
                log.info(
                    "checkpoint.init",
                    workspace_dir=workspace_dir,
                    shadow_dir=str(shadow),
                )
        return shadow

    async def create_checkpoint(
        self,
        workspace_dir: str,
        reason: str,
    ) -> str | None:
        """Create a checkpoint of the current workspace state.

        Returns the commit hash, or None if nothing changed.
        """
        if not Path(workspace_dir).is_dir():
            return None

        shadow = self._ensure_repo(workspace_dir)
        work_tree = str(Path(workspace_dir).resolve())

        try:
            # Stage all files
            result = _git(shadow, work_tree, "add", "-A")
            if result.returncode != 0:
                log.warning(
                    "checkpoint.add_failed",
                    stderr=result.stderr[:200],
                )
                return None

            # Check if there's anything to commit
            status = _git(shadow, work_tree, "status", "--porcelain")
            if not status.stdout.strip():
                return None  # Nothing changed

            # Commit
            ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            msg = f"[{ts}] {reason}"
            commit = _git(shadow, work_tree, "commit", "-m", msg)
            if commit.returncode != 0:
                log.warning(
                    "checkpoint.commit_failed",
                    stderr=commit.stderr[:200],
                )
                return None

            # Extract hash
            rev = _git(shadow, work_tree, "rev-parse", "HEAD")
            commit_hash = rev.stdout.strip()

            log.info(
                "checkpoint.created",
                hash=commit_hash[:8],
                reason=reason,
                workspace_dir=workspace_dir,
            )
            return commit_hash

        except subprocess.TimeoutExpired:
            log.warning("checkpoint.timeout", workspace_dir=workspace_dir)
            return None
        except FileNotFoundError:
            log.warning("checkpoint.git_not_found")
            return None

    def list_checkpoints(
        self,
        workspace_dir: str,
        max_count: int = 20,
    ) -> list[Checkpoint]:
        """List recent checkpoints for a workspace directory."""
        shadow = _shadow_dir(self._data_dir, workspace_dir)
        if not (shadow / "HEAD").exists():
            return []

        work_tree = str(Path(workspace_dir).resolve())
        try:
            result = _git(
                shadow, work_tree,
                "log",
                f"--max-count={max_count}",
                "--format=%H|%s|%aI",
            )
            if result.returncode != 0:
                return []

            checkpoints: list[Checkpoint] = []
            for line in result.stdout.strip().splitlines():
                parts = line.split("|", 2)
                if len(parts) == 3:
                    checkpoints.append(Checkpoint(
                        hash=parts[0],
                        message=parts[1],
                        timestamp=parts[2],
                    ))
            return checkpoints

        except (subprocess.TimeoutExpired, FileNotFoundError):
            return []

    async def rollback_to(
        self,
        workspace_dir: str,
        checkpoint_hash: str | None = None,
    ) -> str:
        """Rollback workspace to a checkpoint.

        If *checkpoint_hash* is None, rolls back to the most recent checkpoint.
        Returns a summary of what was restored.
        """
        shadow = _shadow_dir(self._data_dir, workspace_dir)
        if not (shadow / "HEAD").exists():
            return "No checkpoints exist for this directory."

        work_tree = str(Path(workspace_dir).resolve())

        if checkpoint_hash is None:
            # Use HEAD~1 (the state before the last checkpoint)
            result = _git(shadow, work_tree, "rev-parse", "HEAD~1")
            if result.returncode != 0:
                return "Only one checkpoint exists — nothing to roll back to."
            checkpoint_hash = result.stdout.strip()

        try:
            # First create a checkpoint of current state before rolling back
            await self.create_checkpoint(
                workspace_dir, "pre-rollback snapshot",
            )

            # Checkout the target revision
            result = _git(
                shadow, work_tree,
                "checkout", checkpoint_hash, "--", ".",
            )
            if result.returncode != 0:
                return f"Rollback failed: {result.stderr[:200]}"

            return (
                f"Rolled back to checkpoint {checkpoint_hash[:8]}. "
                "A snapshot of the pre-rollback state was saved."
            )

        except subprocess.TimeoutExpired:
            return "Rollback timed out."
        except FileNotFoundError:
            return "Git is not available — cannot rollback."

    def auto_prune(
        self,
        workspace_dir: str,
        max_count: int = 50,
    ) -> int:
        """Keep only the most recent *max_count* checkpoints. Returns pruned count."""
        shadow = _shadow_dir(self._data_dir, workspace_dir)
        if not (shadow / "HEAD").exists():
            return 0

        checkpoints = self.list_checkpoints(workspace_dir, max_count=max_count + 100)
        if len(checkpoints) <= max_count:
            return 0

        # Run gc to reclaim space (shadow repos have no remote)
        work_tree = str(Path(workspace_dir).resolve())
        with contextlib.suppress(subprocess.TimeoutExpired, FileNotFoundError):
            _git(shadow, work_tree, "gc", "--prune=now", "--aggressive")

        pruned = len(checkpoints) - max_count
        log.info(
            "checkpoint.pruned",
            workspace_dir=workspace_dir,
            pruned=pruned,
            remaining=max_count,
        )
        return pruned
