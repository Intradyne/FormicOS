"""Shared operational-state helper (Wave 71.0 Track 1).

Single source of truth for workspace-scoped operational files:
- ``.formicos/operations/{workspace_id}/queen_journal.md``
- ``.formicos/operations/{workspace_id}/operating_procedures.md``

Operational state is file-backed working memory, NOT institutional memory.
Do not route through ``memory_entries``.
"""

from __future__ import annotations

import json as _json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from formicos.surface.projections import ProjectionStore

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_OPS_DIR = "operations"


def _ops_dir(data_dir: str, workspace_id: str) -> Path:
    """Return the workspace-scoped operations directory."""
    return Path(data_dir) / ".formicos" / _OPS_DIR / workspace_id


def journal_path(data_dir: str, workspace_id: str) -> Path:
    """Return the canonical journal path for a workspace."""
    return _ops_dir(data_dir, workspace_id) / "queen_journal.md"


def procedures_path(data_dir: str, workspace_id: str) -> Path:
    """Return the canonical operating procedures path for a workspace."""
    return _ops_dir(data_dir, workspace_id) / "operating_procedures.md"


# ---------------------------------------------------------------------------
# Operating procedures — editable, overwritable
# ---------------------------------------------------------------------------


def load_procedures(data_dir: str, workspace_id: str) -> str:
    """Load operating procedures text. Returns empty string if absent."""
    path = procedures_path(data_dir, workspace_id)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def save_procedures(data_dir: str, workspace_id: str, content: str) -> None:
    """Write operating procedures (full overwrite)."""
    path = procedures_path(data_dir, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_procedure_rule(
    data_dir: str,
    workspace_id: str,
    heading: str,
    rule: str,
) -> str:
    """Append a rule under a markdown heading, creating section if needed.

    Returns the updated full text.
    """
    text = load_procedures(data_dir, workspace_id)
    lines = text.split("\n") if text else []

    heading_line = f"## {heading}"
    heading_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == heading_line:
            heading_idx = i
            break

    if heading_idx == -1:
        # Add heading at end
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(heading_line)
        lines.append(f"- {rule}")
    else:
        # Insert after last bullet under this heading
        insert_at = heading_idx + 1
        for i in range(heading_idx + 1, len(lines)):
            stripped = lines[i].strip()
            if stripped.startswith("#"):
                break
            if stripped.startswith("- ") or stripped == "":
                insert_at = i + 1
            else:
                break
        lines.insert(insert_at, f"- {rule}")

    result = "\n".join(lines)
    save_procedures(data_dir, workspace_id, result)
    return result


# ---------------------------------------------------------------------------
# Queen journal — append-only working log
# ---------------------------------------------------------------------------


def append_journal_entry(
    data_dir: str,
    workspace_id: str,
    source: str,
    message: str,
    *,
    heading: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a timestamped journal entry.

    Parameters
    ----------
    source:
        Short label: ``session``, ``queen``, ``maintenance``, ``operator``.
    message:
        Compact one-line summary (not chat transcript).
    heading:
        Optional heading for display-board entries. When provided, format
        becomes ``- [ts] [source] [heading] message``.
    metadata:
        Optional JSON metadata written as an HTML comment on the next line.
        Stripped from Queen prompt context by ``read_journal_tail()``.
    """
    path = journal_path(data_dir, workspace_id)
    path.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    if heading:
        line = f"- [{ts}] [{source}] [{heading}] {message}\n"
    else:
        line = f"- [{ts}] [{source}] {message}\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        if metadata is not None:
            f.write(f"  <!-- {_json.dumps(metadata)} -->\n")


def read_journal_tail(
    data_dir: str,
    workspace_id: str,
    max_lines: int = 30,
) -> str:
    """Read the most recent journal entries. Returns empty string if absent.

    Metadata comment lines (``<!-- ... -->``) are stripped so they don't
    leak into Queen prompt context.
    """
    path = journal_path(data_dir, workspace_id)
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    lines = text.strip().splitlines()
    # Strip metadata comment lines for clean Queen context
    clean = [ln for ln in lines if not _METADATA_COMMENT_RE.match(ln)]
    tail = clean[-max_lines:] if len(clean) > max_lines else clean
    return "\n".join(tail)


def read_journal_full(data_dir: str, workspace_id: str) -> str:
    """Read the full journal text. Returns empty string if absent."""
    path = journal_path(data_dir, workspace_id)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


# ---------------------------------------------------------------------------
# Structured journal parse (for API endpoint)
# ---------------------------------------------------------------------------

_JOURNAL_ENTRY_RE = re.compile(
    r"^- \[([^\]]+)\] \[([^\]]+)\](?: \[([^\]]+)\])? (.*)$",
)
_METADATA_COMMENT_RE = re.compile(r"^\s*<!--\s*(\{.*\})\s*-->$")


def parse_journal_entries(text: str) -> list[dict[str, Any]]:
    """Parse journal text into structured entries.

    Returns dicts with keys: ``timestamp``, ``source``, ``heading`` (or None),
    ``message``, and ``metadata`` (parsed JSON dict or None).
    """
    entries: list[dict[str, Any]] = []
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        m = _JOURNAL_ENTRY_RE.match(line.strip())
        if not m:
            continue
        entry: dict[str, Any] = {
            "timestamp": m.group(1),
            "source": m.group(2),
            "heading": m.group(3),  # None if legacy format
            "message": m.group(4),
        }
        # Check next line for metadata comment
        meta: dict[str, Any] | None = None
        if i + 1 < len(lines):
            mm = _METADATA_COMMENT_RE.match(lines[i + 1])
            if mm:
                try:
                    meta = _json.loads(mm.group(1))
                except (ValueError, TypeError):
                    pass
        entry["metadata"] = meta
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Queen context rendering — compact injection text
# ---------------------------------------------------------------------------


def render_procedures_for_queen(data_dir: str, workspace_id: str) -> str:
    """Render procedures as compact Queen context block.

    Returns empty string when no procedures file exists.
    """
    text = load_procedures(data_dir, workspace_id)
    if not text.strip():
        return ""
    return f"# Operating Procedures\n{text}"


def render_journal_for_queen(
    data_dir: str,
    workspace_id: str,
    max_lines: int = 20,
) -> str:
    """Render recent journal entries as compact Queen context block.

    Returns empty string when no journal exists.
    """
    tail = read_journal_tail(data_dir, workspace_id, max_lines=max_lines)
    if not tail.strip():
        return ""
    return f"# Queen Journal (recent)\n{tail}"


# ---------------------------------------------------------------------------
# Public API for structured reads
# ---------------------------------------------------------------------------


def get_journal_summary(
    data_dir: str,
    workspace_id: str,
    max_entries: int = 50,
) -> dict[str, Any]:
    """Return structured journal data for the REST endpoint."""
    text = read_journal_full(data_dir, workspace_id)
    if not text.strip():
        return {"exists": False, "entries": []}

    entries = parse_journal_entries(text)
    tail = entries[-max_entries:] if len(entries) > max_entries else entries
    # Map to frontend-expected shape: heading + body
    mapped = [
        {
            "timestamp": e["timestamp"],
            "heading": e.get("heading") or e["source"],
            "body": e["message"],
            "source": e["source"],
            "metadata": e.get("metadata"),
        }
        for e in tail
    ]
    return {
        "exists": True,
        "totalEntries": len(entries),
        "entries": mapped,
    }


def get_procedures_summary(
    data_dir: str,
    workspace_id: str,
) -> dict[str, Any]:
    """Return structured procedures data for the REST endpoint."""
    text = load_procedures(data_dir, workspace_id)
    if not text.strip():
        return {"exists": False, "content": ""}
    return {"exists": True, "content": text}


# ---------------------------------------------------------------------------
# Sweep auto-posting — display board population
# ---------------------------------------------------------------------------


def post_sweep_observations(
    data_dir: str,
    workspace_id: str,
    summary: dict[str, Any],
    projections: ProjectionStore,
) -> int:
    """Post notable findings from the operational sweep to the display board.

    Returns the number of observations posted. Keeps it conservative (2-5 items).
    """
    posted = 0

    # 1. Ready continuations
    candidates = summary.get("continuation_candidates", [])
    ready = [c for c in candidates if isinstance(c, dict) and c.get("ready_for_autonomy")]
    if ready:
        append_journal_entry(
            data_dir, workspace_id, source="maintenance",
            message=f"{len(ready)} continuation(s) ready for autonomous execution",
            heading="status:normal — Continuations ready",
            metadata={"display_board": True, "type": "status", "priority": "normal"},
        )
        posted += 1

    # 2. Pending review count
    pending = summary.get("pending_review_count", 0)
    if pending > 0:
        append_journal_entry(
            data_dir, workspace_id, source="maintenance",
            message=f"{pending} action(s) awaiting operator review",
            heading="status:attention — Pending reviews",
            metadata={"display_board": True, "type": "status", "priority": "attention"},
        )
        posted += 1

    # 3. Stalled threads
    stalled = summary.get("stalled_thread_count", 0)
    if stalled > 0:
        append_journal_entry(
            data_dir, workspace_id, source="maintenance",
            message=f"{stalled} thread(s) appear stalled — consider reviewing or archiving",
            heading="concern:attention — Stalled threads",
            metadata={"display_board": True, "type": "concern", "priority": "attention"},
        )
        posted += 1

    # 4. Failed colonies (from recent outcomes)
    ws = projections.workspaces.get(workspace_id)
    if ws is not None:
        failed_count = 0
        for thread in ws.threads.values():
            for colony in thread.colonies.values():
                if colony.status == "failed":
                    failed_count += 1
        if failed_count > 0:
            append_journal_entry(
                data_dir, workspace_id, source="maintenance",
                message=f"{failed_count} colony/colonies in failed state",
                heading="concern:attention — Failed colonies",
                metadata={"display_board": True, "type": "concern", "priority": "attention"},
            )
            posted += 1

    return posted
