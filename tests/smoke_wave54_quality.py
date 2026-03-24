"""Wave 54.5 quality measurement smoke — verifies productive_ratio signal in quality scores.

Spawns two colonies (simple 1-round + moderate multi-round) and captures quality_score
from ColonyCompleted/ColonyFailed events via WebSocket.  Compares against B1 baseline
where multi-round colonies scored 0.19-0.25.

Usage:
    python tests/smoke_wave54_quality.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import websockets  # type: ignore[import-untyped]

WS_URL = "ws://localhost:8080/ws"
BASE_URL = "http://localhost:8080"
TIMEOUT_S = 300

_TERMINAL_EVENTS = {"ColonyCompleted", "ColonyFailed", "ColonyKilled"}

TASKS = [
    {
        "id": "email-validator",
        "description": (
            "Write a Python function that validates email addresses. It should check "
            "format correctness (RFC 5322 basics), reject obviously invalid inputs, "
            "and return a structured result with the local part, domain, and "
            "validation status. Include at least 8 test cases."
        ),
    },
    {
        "id": "csv-analyzer",
        "description": (
            "Write a Python module that reads a CSV file and computes summary "
            "statistics: column types (numeric, categorical, datetime), missing "
            "value counts, mean/median/mode for numeric columns, and unique value "
            "counts for categorical columns. Output a structured report dict. "
            "Include test cases with edge cases (empty file, mixed types, "
            "large row counts)."
        ),
    },
]


async def run_colony(task: dict[str, str]) -> dict[str, object]:
    """Spawn a colony and collect quality-relevant metrics."""
    async with websockets.connect(WS_URL) as ws:
        await ws.send(json.dumps({"action": "subscribe", "workspaceId": "default"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
        assert msg.get("type") == "state", f"Expected state, got {msg.get('type')}"

        # Spawn via WebSocket
        await ws.send(json.dumps({
            "action": "spawn_colony",
            "workspaceId": "default",
            "payload": {
                "threadId": "main",
                "task": task["description"],
                "castes": [
                    {"caste": "coder", "tier": "standard", "count": 1},
                ],
            },
        }))

        colony_id = None
        terminal_event = None
        quality_score = None
        productive_count = 0
        observation_count = 0
        total_tools = 0
        rounds_seen = 0
        t0 = time.monotonic()

        PRODUCTIVE_TOOLS = {
            "write_workspace_file", "patch_file", "code_execute",
            "workspace_execute", "git_commit",
        }
        OBSERVATION_TOOLS = {
            "list_workspace_files", "read_workspace_file", "memory_search",
            "git_status", "git_diff", "git_log",
        }

        while time.monotonic() - t0 < TIMEOUT_S:
            try:
                raw = await asyncio.wait_for(ws.recv(), 30)
            except asyncio.TimeoutError:
                continue
            msg = json.loads(raw)

            mtype = msg.get("type")

            # Single event (standard WS format)
            if mtype == "event":
                evt = msg.get("event", {})
                etype = evt.get("type", "")

                if etype == "ColonySpawned" and colony_id is None:
                    colony_id = evt.get("address", "").rsplit("/", 1)[-1]

                if etype == "RoundStarted":
                    rounds_seen += 1

                if etype == "AgentTurnCompleted":
                    tools = evt.get("tool_calls", [])
                    for t in tools:
                        total_tools += 1
                        if t in PRODUCTIVE_TOOLS:
                            productive_count += 1
                        elif t in OBSERVATION_TOOLS:
                            observation_count += 1

                if etype in _TERMINAL_EVENTS:
                    terminal_event = etype

            if terminal_event:
                break

        wall_time = time.monotonic() - t0

        # Try to get quality from the colony projection via WS state
        if colony_id:
            try:
                async with websockets.connect(WS_URL) as ws2:
                    await ws2.send(json.dumps({"action": "subscribe", "workspaceId": "default"}))
                    state_msg = json.loads(await asyncio.wait_for(ws2.recv(), 10))
                    if state_msg.get("type") == "state":
                        for c in state_msg.get("colonies", []):
                            if c.get("colony_id") == colony_id:
                                quality_score = c.get("quality_score")
                                break
            except Exception:
                pass

        return {
            "task_id": task["id"],
            "colony_id": colony_id,
            "status": terminal_event or "timeout",
            "quality_score": quality_score,
            "rounds": rounds_seen,
            "productive_calls": productive_count,
            "total_calls": total_tools,
            "observation_calls": observation_count,
            "wall_time_s": round(wall_time, 1),
        }


async def main() -> None:
    print("=" * 70)
    print("WAVE 54.5 QUALITY MEASUREMENT SMOKE")
    print("=" * 70)

    results = []
    for task in TASKS:
        print(f"\n{'-' * 70}")
        print(f"TASK: {task['id']}")
        print(f"{'-' * 70}")
        r = await run_colony(task)
        results.append(r)

        prod_ratio = (
            f"{r['productive_calls']}/{r['total_calls']}"
            if r["total_calls"] > 0 else "n/a"
        )
        print(f"  Colony: {r['colony_id']}")
        print(f"  Status: {r['status']}")
        print(f"  Rounds: {r['rounds']}")
        print(f"  Tools: {prod_ratio} productive ({r['productive_calls']} prod, {r['observation_calls']} obs)")
        print(f"  Quality: {r['quality_score']}")
        print(f"  Wall: {r['wall_time_s']}s")

    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    for r in results:
        q = r["quality_score"]
        q_str = f"{q:.4f}" if isinstance(q, (int, float)) and q is not None else str(q)
        print(f"  {r['task_id']}: quality={q_str}, rounds={r['rounds']}, "
              f"productive={r['productive_calls']}/{r['total_calls']}, "
              f"status={r['status']}, {r['wall_time_s']}s")

    # B2 acceptance: multi-round colony should score > 0.35
    multi_round = [r for r in results if r["rounds"] > 1]
    if multi_round:
        scores = [r["quality_score"] for r in multi_round if isinstance(r.get("quality_score"), (int, float))]
        if scores:
            avg = sum(scores) / len(scores)
            verdict = "PASS" if avg > 0.35 else "FAIL"
            print(f"\n  B2 CHECK: multi-round avg quality = {avg:.4f} [{verdict}]")
            print(f"    (B1 baseline was 0.19-0.25, target > 0.35)")
        else:
            print(f"\n  B2 CHECK: no quality scores captured for multi-round colonies")
    else:
        print(f"\n  B2 CHECK: no multi-round colonies observed")

    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
