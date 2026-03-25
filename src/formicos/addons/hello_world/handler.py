"""Hello-world addon handler."""

from __future__ import annotations

from typing import Any


async def handle_hello(
    inputs: dict[str, Any],
    workspace_id: str,
    thread_id: str,
) -> str:
    """Return a greeting from the addon system."""
    greeting = inputs.get("greeting", "Hello")
    return f"{greeting} from addon system!"
