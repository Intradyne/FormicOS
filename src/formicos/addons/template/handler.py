"""Template addon handlers -- copy and customize."""

from __future__ import annotations

from typing import Any


async def handle_greet(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> str:
    """Example tool handler: returns a greeting."""
    name = inputs.get("name", "World")
    return f"Hello, {name}! (from template addon)"


# Uncomment for event handler:
# async def on_colony_completed(
#     event: Any,
#     *,
#     workspace_path: str | None = None,
#     workspace_config: dict[str, Any] | None = None,
# ) -> None:
#     """React to ColonyCompleted events."""
#     pass


# Uncomment for trigger handler:
# async def on_hourly(
#     *,
#     runtime_context: dict[str, Any] | None = None,
# ) -> None:
#     """Called on cron schedule."""
#     pass
