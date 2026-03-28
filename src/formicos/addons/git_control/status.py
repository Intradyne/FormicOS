"""Git control status endpoint for addon panel rendering."""

from __future__ import annotations

import asyncio
from typing import Any


async def get_status(
    _inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return git workspace status as status_card data."""
    ctx = runtime_context or {}
    workspace_root_fn = ctx.get("workspace_root_fn")

    items = []
    ws_path = workspace_root_fn(workspace_id) if workspace_root_fn else None

    if ws_path and ws_path.is_dir():
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "branch", "--show-current",
                cwd=str(ws_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            branch = stdout.decode().strip() if stdout else "unknown"
            items.append({"label": "Branch", "value": branch})

            proc2 = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=str(ws_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            lines = [ln for ln in (stdout2.decode().splitlines() if stdout2 else []) if ln.strip()]
            items.append({"label": "Modified files", "value": str(len(lines))})
        except Exception:  # noqa: BLE001
            items.append({"label": "Status", "value": "git unavailable"})
    else:
        items.append({"label": "Status", "value": "no workspace"})

    return {
        "display_type": "status_card",
        "items": items,
    }
