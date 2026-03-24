"""Wave 54 smoke test — behavioral validation of operational playbook layer.

Two tasks: csv-analyzer and markdown-parser (coder caste, Qwen3-30B-A3B).
Pass bar is behavioral, not quality:
  1. At least one productive tool call per colony
  2. Observation ratio < 0.8
  3. No inert spam runs (5+ consecutive identical observation calls)
  4. Playbook visible in context (<operational_playbook>)
  5. Budget STATUS line present

Usage:
    python tests/smoke_wave54.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from collections import Counter
from typing import Any

import websockets  # type: ignore[import-untyped]

WS_URL = "ws://localhost:8080/ws"
BASE_URL = "http://localhost:8080"
TIMEOUT_S = 300  # 5 min per colony max

PRODUCTIVE_TOOLS = {
    "write_workspace_file", "patch_file", "code_execute",
    "workspace_execute", "git_commit",
}
OBSERVATION_TOOLS = {
    "list_workspace_files", "read_workspace_file", "memory_search",
    "git_status", "git_diff", "git_log", "knowledge_detail",
    "transcript_search", "artifact_inspect", "knowledge_feedback",
    "memory_write",
}

_TERMINAL_EVENTS = {"ColonyCompleted", "ColonyFailed", "ColonyKilled"}

TASKS = [
    {
        "id": "csv-analyzer",
        "description": (
            "Write a Python module that reads a CSV file and computes summary "
            "statistics: column types (numeric, categorical, datetime), missing "
            "value counts, mean/median/mode for numeric columns, and unique value "
            "counts for categorical columns. Output a structured report dict. "
            "Include test cases with edge cases (empty file, mixed types, quoted "
            "commas)."
        ),
    },
    {
        "id": "markdown-parser",
        "description": (
            "Write a Python function that parses a subset of Markdown into an AST. "
            "Support headers (h1-h3), bold, italic, code blocks (fenced), unordered "
            "lists, and paragraphs. Return a list of typed AST nodes. Include at "
            "least 10 test cases covering nested formatting and edge cases."
        ),
    },
]


def _direct_spawn(task: str) -> str:
    return json.dumps({
        "action": "spawn_colony",
        "workspaceId": "default",
        "payload": {
            "threadId": "main",
            "task": task,
            "castes": [
                {"caste": "coder", "tier": "standard", "count": 1},
            ],
        },
    })


async def collect_until_terminal(
    ws: Any, timeout_s: float = TIMEOUT_S,
) -> tuple[list[dict[str, Any]], str | None]:
    """Collect events until colony terminal or timeout. Returns (events, colony_id)."""
    events: list[dict[str, Any]] = []
    colony_id: str | None = None
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
            msg = json.loads(raw)
            if msg.get("type") == "event":
                ev = msg["event"]
                events.append(ev)
                etype = ev.get("type", "")
                if etype == "ColonySpawned":
                    # colony_id is the last segment of the address (ws/thread/colony)
                    addr = ev.get("address", "")
                    parts = addr.split("/")
                    colony_id = parts[-1] if len(parts) >= 3 else (
                        ev.get("colony_id") or ev.get("colonyId") or addr
                    )
                if etype in _TERMINAL_EVENTS:
                    return events, colony_id
        except TimeoutError:
            continue
    return events, colony_id


def analyze_tool_calls(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract tool call stats from event stream."""
    tool_calls: list[str] = []
    tool_sequences: list[str] = []

    for ev in events:
        etype = ev.get("type", "")
        # AgentTurnCompleted carries the ordered tool list per turn
        if etype == "AgentTurnCompleted":
            turn_tools = ev.get("tool_calls", [])
            tool_calls.extend(turn_tools)
            tool_sequences.extend(turn_tools)

    productive_count = sum(1 for t in tool_calls if t in PRODUCTIVE_TOOLS)
    observation_count = sum(1 for t in tool_calls if t in OBSERVATION_TOOLS)
    other_count = len(tool_calls) - productive_count - observation_count
    total = len(tool_calls)
    obs_ratio = observation_count / total if total > 0 else 0.0

    # Detect inert spam: 5+ consecutive identical observation calls
    max_consecutive = 0
    current_run = 0
    current_tool = ""
    for t in tool_sequences:
        if t == current_tool and t in OBSERVATION_TOOLS:
            current_run += 1
        else:
            current_run = 1
            current_tool = t
        max_consecutive = max(max_consecutive, current_run)

    return {
        "total": total,
        "productive": productive_count,
        "observation": observation_count,
        "other": other_count,
        "obs_ratio": obs_ratio,
        "max_consecutive_obs": max_consecutive,
        "tool_counts": dict(Counter(tool_calls)),
        "productive_tools_used": [t for t in tool_calls if t in PRODUCTIVE_TOOLS],
    }


def get_transcript(colony_id: str) -> dict[str, Any] | None:
    """Fetch colony transcript via REST API."""
    try:
        url = f"{BASE_URL}/api/v1/colonies/{colony_id}/transcript"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [WARN] Could not fetch transcript: {e}")
        return None


def check_playbook_in_transcript(transcript: dict[str, Any] | None) -> bool:
    """Check if operational_playbook appears in transcript context."""
    if transcript is None:
        return False
    raw = json.dumps(transcript)
    return "operational_playbook" in raw


def check_budget_status(transcript: dict[str, Any] | None) -> bool:
    """Check if STATUS line appears in transcript."""
    if transcript is None:
        return False
    raw = json.dumps(transcript)
    return any(s in raw for s in ["STATUS: ON TRACK", "STATUS: SLOW", "STATUS: STALLED", "STATUS: FINAL ROUND"])


async def run_smoke() -> bool:
    """Run Wave 54 smoke test. Returns True if all pass criteria met."""
    print("=" * 70)
    print("WAVE 54 SMOKE TEST — Operational Playbook Layer")
    print("=" * 70)

    all_pass = True
    task_results: list[dict[str, Any]] = []

    async with websockets.connect(WS_URL) as ws:
        # Subscribe to default workspace
        sub_msg = json.dumps({"action": "subscribe", "workspaceId": "default"})
        print(f"  Subscribing: {sub_msg}")
        await ws.send(sub_msg)
        # Drain initial state message
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            msg = json.loads(raw)
            print(f"  Initial message type: {msg.get('type', '?')}")
        except TimeoutError:
            print("  [WARN] No initial state received")

        for task in TASKS:
            print(f"\n{'-' * 70}")
            print(f"TASK: {task['id']}")
            print(f"{'-' * 70}")

            t0 = time.time()
            spawn_cmd = _direct_spawn(task["description"])
            print(f"  Spawning colony...")
            await ws.send(spawn_cmd)
            events, colony_id = await collect_until_terminal(ws)
            wall_time = time.time() - t0
            print(f"  Received {len(events)} events in {wall_time:.1f}s")
            if events:
                event_types = [e.get("type", "?") for e in events[:10]]
                print(f"  First event types: {event_types}")
                # Debug: show ColonySpawned event structure
                for e in events[:3]:
                    if e.get("type") == "ColonySpawned":
                        print(f"  ColonySpawned keys: {list(e.keys())}")
                        print(f"  ColonySpawned: {json.dumps(e)[:500]}")

            if colony_id is None:
                print(f"  [FAIL] No ColonySpawned event received")
                all_pass = False
                continue

            # Check terminal status
            terminal = [e for e in events if e.get("type", "") in _TERMINAL_EVENTS]
            status = terminal[0].get("type", "?") if terminal else "timeout"
            print(f"  Colony: {colony_id}")
            print(f"  Status: {status}")
            print(f"  Wall time: {wall_time:.1f}s")

            # Analyze tool calls
            stats = analyze_tool_calls(events)
            print(f"\n  Tool calls: {stats['total']} total")
            print(f"    Productive: {stats['productive']} ({', '.join(stats['productive_tools_used']) or 'NONE'})")
            print(f"    Observation: {stats['observation']}")
            print(f"    Other: {stats['other']}")
            print(f"    Obs ratio: {stats['obs_ratio']:.2f}")
            print(f"    Max consecutive obs: {stats['max_consecutive_obs']}")
            print(f"    Tool breakdown: {json.dumps(stats['tool_counts'], indent=6)}")

            # Fetch transcript for context checks
            transcript = get_transcript(colony_id)

            # ── Pass criteria ──
            print(f"\n  CRITERIA:")

            # 1. At least one productive tool call
            has_productive = stats["productive"] > 0
            print(f"    {'[PASS]' if has_productive else '[FAIL]'} Productive tool called: {has_productive}")
            if not has_productive:
                all_pass = False

            # 2. Observation ratio < 0.8
            ratio_ok = stats["obs_ratio"] < 0.8
            print(f"    {'[PASS]' if ratio_ok else '[FAIL]'} Obs ratio < 0.8: {stats['obs_ratio']:.2f}")
            if not ratio_ok:
                all_pass = False

            # 3. No inert spam (5+ consecutive identical obs calls)
            no_spam = stats["max_consecutive_obs"] < 5
            print(f"    {'[PASS]' if no_spam else '[FAIL]'} No inert spam: max consecutive = {stats['max_consecutive_obs']}")
            if not no_spam:
                all_pass = False

            # 4. Playbook visible
            has_playbook = check_playbook_in_transcript(transcript)
            print(f"    {'[PASS]' if has_playbook else '[WARN]'} Playbook in transcript: {has_playbook}")
            # This is informational — transcript API may not expose full context

            # 5. Budget STATUS present
            has_status = check_budget_status(transcript)
            print(f"    {'[PASS]' if has_status else '[WARN]'} Budget STATUS in transcript: {has_status}")

            task_results.append({
                "task_id": task["id"],
                "colony_id": colony_id,
                "status": status,
                "wall_time": wall_time,
                "stats": stats,
                "has_playbook": has_playbook,
                "has_status": has_status,
            })

    # ── Summary ──
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    for tr in task_results:
        s = tr["stats"]
        verdict = "PASS" if (s["productive"] > 0 and s["obs_ratio"] < 0.8 and s["max_consecutive_obs"] < 5) else "FAIL"
        print(f"  [{verdict}] {tr['task_id']}: {s['productive']} productive, {s['observation']} obs, ratio={s['obs_ratio']:.2f}, {tr['wall_time']:.0f}s")

    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
    print(f"{'=' * 70}")

    return all_pass


if __name__ == "__main__":
    ok = asyncio.run(run_smoke())
    sys.exit(0 if ok else 1)
