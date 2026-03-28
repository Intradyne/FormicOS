"""Codebase index status endpoint for addon panel rendering."""

from __future__ import annotations

from typing import Any


async def get_status(
    _inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return index status as status_card data."""
    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")

    items = []
    if vector_port is not None:
        try:
            info = await vector_port.collection_info("code_index")
            items.append({"label": "Chunks indexed", "value": str(info.get("points_count", "?"))})
            items.append({"label": "Collection", "value": "code_index"})
        except Exception:  # noqa: BLE001
            items.append({"label": "Status", "value": "unavailable"})
    else:
        items.append({"label": "Status", "value": "no vector store"})

    return {
        "display_type": "status_card",
        "items": items,
    }
