"""Shared thread-plan parser/helper (Wave 71.0 Track 7).

Canonical helper for reading ``.formicos/plans/{thread_id}.md``.
Follows the same pattern as ``project_plan.py``.

The step-line format matches ``_STEP_RE`` in ``queen_tools.py``::

    - [0] [pending] Description text
    - [1] [completed] Another step
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STEP_RE = re.compile(
    r"^- \[(\d+)\] \[(\w+)\] (.*)$",
)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def thread_plan_path(data_dir: str, thread_id: str) -> Path:
    """Return the canonical thread plan path."""
    return Path(data_dir) / ".formicos" / "plans" / f"{thread_id}.md"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_thread_plan(text: str) -> dict[str, Any]:
    """Parse a thread plan markdown file into structured data.

    Returns::

        {
            "exists": True,
            "goal": "...",
            "thread_id": "...",
            "steps": [
                {"index": 0, "status": "pending", "description": "..."},
                ...
            ],
            "summary": {
                "total": 5,
                "completed": 2,
                "pending": 3,
                "failed": 0,
            },
        }
    """
    goal = ""
    thread_id = ""
    steps: list[dict[str, Any]] = []

    for line in text.splitlines():
        stripped = line.strip()

        # Goal line: "# Thread Plan: <goal>" or "# Plan: <goal>"
        if stripped.startswith("# Thread Plan:") or stripped.startswith("# Plan:"):
            prefix = "# Thread Plan:" if stripped.startswith("# Thread Plan:") else "# Plan:"
            goal = stripped[len(prefix):].strip()
            continue

        # Thread ID line: "Thread: <id>"
        if stripped.startswith("Thread:"):
            thread_id = stripped[len("Thread:"):].strip()
            continue

        # Step line: "- [0] [pending] description"
        m = _STEP_RE.match(stripped)
        if m:
            idx_str, status, desc = m.groups()
            steps.append({
                "index": int(idx_str),
                "status": status,
                "description": desc,
            })

    # Compute summary counts
    status_counts: dict[str, int] = {}
    for step in steps:
        s = step["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    return {
        "exists": True,
        "goal": goal,
        "thread_id": thread_id,
        "steps": steps,
        "summary": {
            "total": len(steps),
            "completed": status_counts.get("completed", 0),
            "pending": status_counts.get("pending", 0),
            "failed": status_counts.get("failed", 0),
        },
    }


def load_thread_plan(data_dir: str, thread_id: str) -> dict[str, Any]:
    """Load and parse a thread plan from disk.

    Returns ``{"exists": False}`` when the plan file does not exist.
    """
    if not data_dir or not thread_id:
        return {"exists": False}

    path = thread_plan_path(data_dir, thread_id)
    if not path.is_file():
        return {"exists": False}

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"exists": False}

    plan = parse_thread_plan(text)
    if not plan.get("thread_id"):
        plan["thread_id"] = thread_id
    return plan


def load_all_thread_plans(data_dir: str) -> list[dict[str, Any]]:
    """Load all thread plans from the plans directory.

    Returns a list of parsed plan dicts (each with ``exists: True``).
    """
    if not data_dir:
        return []

    plans_dir = Path(data_dir) / ".formicos" / "plans"
    if not plans_dir.is_dir():
        return []

    plans: list[dict[str, Any]] = []
    try:
        for plan_file in sorted(plans_dir.glob("*.md")):
            thread_id = plan_file.stem
            plan = load_thread_plan(data_dir, thread_id)
            if plan.get("exists"):
                plans.append(plan)
    except OSError:
        pass

    return plans


# ---------------------------------------------------------------------------
# Rendering — compact context for coordinator / Queen injection
# ---------------------------------------------------------------------------


def render_for_queen(plan: dict[str, Any]) -> str:
    """Render a parsed thread plan into compact text.

    Returns an empty string when the plan does not exist or has no steps.
    """
    if not plan.get("exists"):
        return ""

    steps = plan.get("steps", [])
    if not steps:
        return ""

    goal = plan.get("goal", "")
    summary = plan.get("summary", {})
    tid = plan.get("thread_id", "?")

    parts: list[str] = []
    header = f"[Plan:{tid[:12]}]"
    if goal:
        header += f" {goal}"
    parts.append(header)

    completed = summary.get("completed", 0)
    total = summary.get("total", 0)
    if total:
        parts.append(f"  Progress: {completed}/{total}")

    # Show pending/failed steps only (completed are noise for the Queen)
    for step in steps:
        if step["status"] != "completed":
            marker = "\u2717" if step["status"] == "failed" else "\u25cb"
            parts.append(
                f"  {marker} [{step['index']}] [{step['status']}] "
                f"{step['description']}"
            )

    return "\n".join(parts)
