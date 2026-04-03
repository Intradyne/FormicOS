"""Codebase index status endpoint for addon panel rendering.

Merges vector-store collection info with the persisted reindex sidecar
to give the operator full truth about index state.
"""

from __future__ import annotations

from typing import Any


async def get_status(
    _inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return index status as status_card data.

    Reads from two sources:
    - vector_port.collection_info() for live chunk count
    - persisted sidecar JSON for last-indexed metadata
    """
    from formicos.addons.codebase_index.indexer import read_index_status  # noqa: PLC0415

    ctx = runtime_context or {}
    vector_port = ctx.get("vector_port")
    data_dir = ctx.get("data_dir", "")

    items: list[dict[str, str]] = []

    # Sidecar truth (persisted from last reindex)
    sidecar = read_index_status(data_dir, workspace_id) if data_dir else None

    if sidecar:
        items.append({"label": "Bound root", "value": sidecar.get("workspace_root", "—")})
        items.append({"label": "Last indexed", "value": sidecar.get("last_indexed_at", "—")})
        items.append({
            "label": "Files / Chunks / Errors",
            "value": (
                f"{sidecar.get('file_count', 0)} / "
                f"{sidecar.get('chunk_count', 0)} / "
                f"{sidecar.get('error_count', 0)}"
            ),
        })

    # Live vector-store truth
    if vector_port is not None:
        try:
            info = await vector_port.collection_info("code_index")
            items.append({"label": "Live chunks", "value": str(info.get("points_count", "?"))})
            items.append({"label": "Collection", "value": "code_index"})
        except Exception:  # noqa: BLE001
            items.append({"label": "Vector store", "value": "unavailable"})
    else:
        items.append({"label": "Vector store", "value": "not configured"})

    if not sidecar and not items:
        items.append({"label": "Status", "value": "not indexed"})

    return {
        "display_type": "status_card",
        "items": items,
    }
