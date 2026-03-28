"""Shared project-plan parser/helper (Wave 70.0 Track 4).

Single source of truth for:
- resolving the project plan path
- parsing markdown into structured milestones
- rendering parsed plan into compact Queen context text
- updating ``Updated:`` timestamps consistently
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_PLAN_FILENAME = "project_plan.md"

_MILESTONE_RE = re.compile(
    r"^- \[(\d+)\] \[(\w+)\] (.*)$",
)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def project_plan_path(data_dir: str) -> Path:
    """Return the canonical project plan path for a data root."""
    return Path(data_dir) / ".formicos" / _PROJECT_PLAN_FILENAME


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_project_plan(text: str) -> dict[str, Any]:
    """Parse project plan markdown into structured data.

    Returns::

        {
            "exists": True,
            "goal": "...",
            "updated": "...",
            "milestones": [
                {
                    "index": 0,
                    "status": "completed",
                    "description": "...",
                    "thread_id": "...",
                    "completed_at": "...",
                    "note": "...",
                }
            ],
        }
    """
    goal = ""
    updated = ""
    milestones: list[dict[str, Any]] = []

    for line in text.splitlines():
        stripped = line.strip()

        # Goal line: "# Project Plan: <goal>"
        if stripped.startswith("# Project Plan:"):
            goal = stripped[len("# Project Plan:"):].strip()
            continue

        # Updated timestamp: "Updated: <iso>"
        if stripped.startswith("Updated:"):
            updated = stripped[len("Updated:"):].strip()
            continue

        # Milestone line: "- [0] [completed] description"
        m = _MILESTONE_RE.match(stripped)
        if m:
            idx_str, status, desc = m.groups()
            milestone: dict[str, Any] = {
                "index": int(idx_str),
                "status": status,
                "description": desc,
            }

            # Parse optional thread ID: (thread <id>)
            thread_match = re.search(r"\(thread\s+(\S+)\)", desc)
            if thread_match:
                milestone["thread_id"] = thread_match.group(1)

            # Parse optional completed_at: [completed_at <iso>]
            completed_match = re.search(
                r"\[completed_at\s+([^\]]+)\]", desc,
            )
            if completed_match:
                milestone["completed_at"] = completed_match.group(1)

            # Parse optional note after em-dash
            if " \u2014 " in desc:
                # Strip metadata suffixes before extracting note
                note_part = desc.split(" \u2014 ", 1)[1]
                # Remove inline metadata from note
                note_part = re.sub(
                    r"\(thread\s+\S+\)", "", note_part,
                ).strip()
                note_part = re.sub(
                    r"\[completed_at\s+[^\]]+\]", "", note_part,
                ).strip()
                if note_part:
                    milestone["note"] = note_part

            milestones.append(milestone)

    return {
        "exists": True,
        "goal": goal,
        "updated": updated,
        "milestones": milestones,
    }


def load_project_plan(data_dir: str) -> dict[str, Any]:
    """Load and parse the project plan from disk.

    Returns ``{"exists": False}`` when the plan file does not exist or
    cannot be read.
    """
    if not data_dir:
        return {"exists": False}

    path = project_plan_path(data_dir)
    if not path.is_file():
        return {"exists": False}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"exists": False}

    return parse_project_plan(text)


# ---------------------------------------------------------------------------
# Rendering — compact context for Queen injection
# ---------------------------------------------------------------------------


def render_for_queen(plan: dict[str, Any]) -> str:
    """Render a parsed plan into compact text suitable for Queen context.

    Returns an empty string when the plan does not exist or has no
    milestones.
    """
    if not plan.get("exists"):
        return ""

    milestones = plan.get("milestones", [])
    goal = plan.get("goal", "")

    if not milestones and not goal:
        return ""

    parts: list[str] = ["# Project Plan (cross-thread)"]
    if goal:
        parts.append(f"Goal: {goal}")

    for ms in milestones:
        status = ms.get("status", "pending")
        desc = ms.get("description", "")
        # Strip inline metadata for compact rendering
        desc = re.sub(r"\(thread\s+\S+\)", "", desc).strip()
        desc = re.sub(r"\[completed_at\s+[^\]]+\]", "", desc).strip()
        marker = "\u2713" if status == "completed" else "\u25cb"
        parts.append(f"  {marker} [{status}] {desc}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------


def _stamp_updated(lines: list[str]) -> list[str]:
    """Insert or update the ``Updated:`` line after the title."""
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    updated_line = f"Updated: {now_iso}"

    for i, line in enumerate(lines):
        if line.strip().startswith("Updated:"):
            lines[i] = updated_line
            return lines

    # Insert after title line (first non-empty line)
    insert_at = 1
    for i, line in enumerate(lines):
        if line.strip().startswith("# Project Plan:"):
            insert_at = i + 1
            break

    lines.insert(insert_at, updated_line)
    return lines


def add_milestone(
    data_dir: str,
    description: str,
    *,
    thread_id: str = "",
    goal: str = "",
) -> dict[str, Any]:
    """Add a milestone to the project plan, creating the file if needed.

    Returns the updated parsed plan.
    """
    path = project_plan_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file():
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
    else:
        title = goal or "Untitled project"
        lines = [f"# Project Plan: {title}", "", "## Milestones"]

    # Update goal if provided and file is new or goal line is empty
    if goal:
        for i, line in enumerate(lines):
            if line.strip().startswith("# Project Plan:"):
                lines[i] = f"# Project Plan: {goal}"
                break

    # Find or create ## Milestones section
    milestones_idx = -1
    for i, line in enumerate(lines):
        if line.strip() == "## Milestones":
            milestones_idx = i
            break
    if milestones_idx == -1:
        lines.append("")
        lines.append("## Milestones")
        milestones_idx = len(lines) - 1

    # Count existing milestones to determine next index
    next_idx = 0
    for line in lines[milestones_idx + 1:]:
        m = _MILESTONE_RE.match(line.strip())
        if m:
            next_idx = max(next_idx, int(m.group(1)) + 1)

    # Build milestone line
    thread_suffix = f" (thread {thread_id})" if thread_id else ""
    new_line = f"- [{next_idx}] [pending] {description}{thread_suffix}"

    # Insert after last milestone or after section header
    insert_at = milestones_idx + 1
    for i in range(milestones_idx + 1, len(lines)):
        if _MILESTONE_RE.match(lines[i].strip()):
            insert_at = i + 1

    lines.insert(insert_at, new_line)
    lines = _stamp_updated(lines)

    path.write_text("\n".join(lines), encoding="utf-8")
    return load_project_plan(data_dir)


def complete_milestone(
    data_dir: str,
    milestone_index: int,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Mark a milestone as completed.

    Returns the updated parsed plan, or ``{"exists": False, "error": ...}``
    on failure.
    """
    path = project_plan_path(data_dir)
    if not path.is_file():
        return {"exists": False, "error": "No project plan file found."}

    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    found = False
    now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    for i, line in enumerate(lines):
        m = _MILESTONE_RE.match(line.strip())
        if m and int(m.group(1)) == milestone_index:
            desc = m.group(3)
            # Strip old status metadata from description
            desc = re.sub(r"\[completed_at\s+[^\]]+\]", "", desc).strip()
            note_suffix = f" \u2014 {note}" if note else ""
            lines[i] = (
                f"- [{milestone_index}] [completed] "
                f"{desc}{note_suffix} "
                f"[completed_at {now_iso}]"
            )
            found = True
            break

    if not found:
        return {
            "exists": True,
            "error": f"Milestone {milestone_index} not found.",
        }

    lines = _stamp_updated(lines)
    path.write_text("\n".join(lines), encoding="utf-8")
    return load_project_plan(data_dir)
