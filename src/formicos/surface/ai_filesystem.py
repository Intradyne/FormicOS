"""AI Filesystem — state/artifact separation + amnesiac forking (ADR-052).

File-backed working memory tier. Two workspace-scoped roots:
- ``runtime/{workspace_id}/`` — intermediate state, ephemeral
- ``artifacts/{workspace_id}/`` — final deliverables, stable

Colonies do NOT write during round execution. Writes happen only at:
- Post-colony hooks (reflection on failure)
- Queen tool invocation (write_working_note, promote_to_artifact)
"""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog

log = structlog.get_logger()

# Approximate chars-per-token ratio for budget estimation.
_CHARS_PER_TOKEN = 4


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _runtime_root(data_dir: str, workspace_id: str) -> Path:
    return Path(data_dir) / ".formicos" / "runtime" / workspace_id


def _artifacts_root(data_dir: str, workspace_id: str) -> Path:
    return Path(data_dir) / ".formicos" / "artifacts" / workspace_id


def _colony_reflection_path(
    data_dir: str, workspace_id: str, colony_id: str,
) -> Path:
    return _runtime_root(data_dir, workspace_id) / "colonies" / colony_id / "reflection.md"


# ---------------------------------------------------------------------------
# Queen working notes
# ---------------------------------------------------------------------------


def write_working_note(
    data_dir: str,
    workspace_id: str,
    filename: str,
    content: str,
    *,
    mode: str = "append",
) -> str:
    """Write/append to runtime/queen/{filename}. Returns the written path."""
    safe_name = Path(filename).name  # strip directory traversal
    if not safe_name:
        return "Error: invalid filename"
    path = _runtime_root(data_dir, workspace_id) / "queen" / safe_name
    path.parent.mkdir(parents=True, exist_ok=True)

    if mode == "overwrite":
        path.write_text(content, encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(content + "\n")

    log.debug("ai_fs.write_note", path=str(path), mode=mode, size=len(content))
    return str(path)


# ---------------------------------------------------------------------------
# Artifact promotion
# ---------------------------------------------------------------------------


def promote_to_artifact(
    data_dir: str,
    workspace_id: str,
    runtime_filename: str,
    target_subdir: str = "deliverables",
) -> str:
    """Move a runtime file to artifacts/. Returns the new path or error."""
    # Wave 79.5 C2: path-safe promotion (accepts relative paths, not just basename)
    rel = Path(runtime_filename)
    if rel.is_absolute() or ".." in rel.parts:
        return "Error: path must be relative with no '..' components"

    runtime = _runtime_root(data_dir, workspace_id)
    src = runtime / rel
    if not src.is_file():
        # Fallback: basename search for backward compat
        safe_name = rel.name
        if not safe_name:
            return "Error: invalid filename"
        candidates = list(runtime.rglob(safe_name))
        if not candidates:
            return f"Error: '{runtime_filename}' not found under runtime/"
        src = candidates[0]

    safe_subdir = Path(target_subdir).name or "deliverables"
    dest = _artifacts_root(data_dir, workspace_id) / safe_subdir / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))

    log.info("ai_fs.promoted", src=str(src), dest=str(dest))
    return str(dest)


def preview_file(
    data_dir: str,
    workspace_id: str,
    scope: str,
    rel_path: str,
    max_chars: int = 4000,
) -> str:
    """Read preview text from a runtime or artifacts file.

    *scope* must be ``"runtime"`` or ``"artifacts"``.
    Returns file content (truncated) or an error string.
    """
    rel = Path(rel_path)
    if rel.is_absolute() or ".." in rel.parts:
        return "Error: path must be relative with no '..' components"

    if scope == "runtime":
        root = _runtime_root(data_dir, workspace_id)
    elif scope == "artifacts":
        root = _artifacts_root(data_dir, workspace_id)
    else:
        return f"Error: invalid scope '{scope}'"

    target = root / rel
    if not target.is_file():
        return f"Error: file not found: {rel_path}"

    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Error reading file: {exc}"

    if len(content) > max_chars:
        return content[:max_chars] + "\n...(truncated)"
    return content


# ---------------------------------------------------------------------------
# Reflection (amnesiac forking)
# ---------------------------------------------------------------------------


def write_reflection(
    data_dir: str,
    workspace_id: str,
    colony_id: str,
    *,
    task: str = "",
    failure_reason: str = "",
    rounds_completed: int = 0,
    quality: float = 0.0,
    stall_count: int = 0,
    last_round_summary: str = "",
    strategy: str = "",
    castes: str = "",
) -> str:
    """Write reflection.md for a failed colony. Returns the path."""
    path = _colony_reflection_path(data_dir, workspace_id, colony_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"## Reflection: {colony_id}",
        f"Task: {task[:500]}",
        f"Failure: {failure_reason}",
        f"Rounds completed: {rounds_completed}, Quality: {quality:.2f}",
        f"Stalls: {stall_count}",
        f"Strategy: {strategy}, Castes: {castes}",
    ]
    if last_round_summary:
        lines.append(f"Last round summary: {last_round_summary[:500]}")

    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    log.info("ai_fs.reflection_written", colony_id=colony_id, path=str(path))
    return str(path)


def read_reflection(
    data_dir: str, workspace_id: str, colony_id: str,
) -> str:
    """Read reflection.md for a colony. Returns content or empty string."""
    path = _colony_reflection_path(data_dir, workspace_id, colony_id)
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Budget slot: read working memory for Queen context injection
# ---------------------------------------------------------------------------


def read_working_memory(
    data_dir: str,
    workspace_id: str,
    token_budget: int,
) -> str:
    """Read runtime/queen/ and runtime/shared/ for Queen context injection.

    Returns a manifest + content string, truncated tail-biased to fit
    the token budget.
    """
    runtime = _runtime_root(data_dir, workspace_id)
    dirs = [runtime / "queen", runtime / "shared"]

    files: list[tuple[str, str]] = []
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.iterdir()):
            if f.is_file() and f.suffix in (".md", ".txt", ".yaml", ".json"):
                content = f.read_text(encoding="utf-8", errors="replace")
                rel = f.relative_to(runtime)
                files.append((str(rel), content))

    if not files:
        return ""

    # Build manifest + content
    parts: list[str] = ["# Working Memory"]
    for rel_path, content in files:
        parts.append(f"\n## {rel_path} ({len(content)} chars)")
        parts.append(content)

    combined = "\n".join(parts)

    # Truncate tail-biased: keep the last N chars within budget
    char_budget = token_budget * _CHARS_PER_TOKEN
    if len(combined) > char_budget:
        combined = "...(truncated)\n" + combined[-char_budget:]

    return combined


# ---------------------------------------------------------------------------
# Utility: parse [retry_of:...] prefix from colony task
# ---------------------------------------------------------------------------


def parse_retry_of(task: str) -> tuple[str, str]:
    """Parse ``[retry_of:{colony_id}]`` prefix from task text.

    Returns ``(original_colony_id, clean_task)`` if prefix found,
    otherwise ``("", task)``.
    """
    if not task.startswith("[retry_of:"):
        return ("", task)
    end = task.find("]")
    if end < 0:
        return ("", task)
    original_id = task[len("[retry_of:"):end]
    clean_task = task[end + 1:].lstrip()
    return (original_id, clean_task)
