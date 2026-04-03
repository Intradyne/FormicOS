"""Constrained addon template skeleton for colony-authored addons (Wave 89).

Provides the file structure and content templates that host-mode colonies
fill in. Intentionally narrow: one manifest, one package init, one handler
with one async dashboard function.
"""

from __future__ import annotations

from pathlib import Path

import structlog

log = structlog.get_logger()

_MANIFEST_TEMPLATE = """\
name: {name}
version: "1.0.0"
description: "{description}"
author: "formicos-colony"

panels:
  - target: workspace
    display_type: status_card
    path: /overview
    handler: status.py::get_overview
    refresh_interval_s: 30

routes:
  - path: /overview
    handler: status.py::get_overview
"""

_INIT_TEMPLATE = '"""Colony-authored addon: {name}."""\n'

_HANDLER_TEMPLATE = '''\
"""Handler for {name} addon — colony-authored dashboard."""

from __future__ import annotations

from typing import Any


async def get_overview(
    inputs: dict[str, Any],
    workspace_id: str,
    _thread_id: str,
    *,
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a dashboard payload for the {name} addon."""
    ctx = runtime_context or {{}}
    projections = ctx.get("projections")
    data_dir = ctx.get("data_dir", "")

    ws_id = inputs.get("workspace_id", "") or workspace_id or "default"

    items: list[dict[str, Any]] = []

    # Colony metrics
    colonies = []
    if projections:
        try:
            colonies = [
                c for c in projections.colonies.values()
                if getattr(c, "workspace_id", "") == ws_id
                and getattr(c, "status", "") in ("completed", "failed")
            ]
        except Exception:
            pass

    total = len(colonies)
    succeeded = sum(1 for c in colonies if getattr(c, "status", "") == "completed")
    failed = total - succeeded
    qualities = [
        getattr(c, "quality_score", 0.0) or 0.0
        for c in colonies
        if getattr(c, "status", "") == "completed"
        and getattr(c, "quality_score", None)
    ]
    avg_q = round(sum(qualities) / max(len(qualities), 1), 3)

    items.append({{"label": "Colonies", "value": total, "status": "ok" if failed == 0 else "warn"}})
    items.append({{"label": "Succeeded", "value": succeeded}})
    items.append({{"label": "Failed", "value": failed, "status": "error" if failed > 0 else "ok"}})
    items.append({{"label": "Avg Quality", "value": f"{{avg_q:.2f}}", "trend": qualities[-10:]}})

    # Memory entries
    entry_count = 0
    if projections:
        try:
            entry_count = len(getattr(projections, "memory_entries", {{}}))
        except Exception:
            pass
    items.append({{"label": "Memory Entries", "value": entry_count}})

    # Plan patterns
    approved = 0
    candidate = 0
    if data_dir:
        try:
            from formicos.surface.plan_patterns import list_patterns
            patterns = list_patterns(data_dir, ws_id)
            approved = sum(1 for p in patterns if p.get("status", "approved") == "approved")
            candidate = sum(1 for p in patterns if p.get("status") == "candidate")
        except Exception:
            pass
    pat_val = f"{{approved}} approved, {{candidate}} candidate"
    items.append({{"label": "Patterns", "value": pat_val}})

    # --- CUSTOMIZE BELOW: add additional dashboard sections ---
    # Example: items.append({{"label": "Custom Metric", "value": 42}})
    additional_items: list[dict[str, Any]] = []
    # --- CUSTOMIZE ABOVE ---

    items.extend(additional_items)

    return {{
        "display_type": "kpi_card",
        "items": items,
        "refresh_interval_s": 30,
    }}
'''


def scaffold_addon(
    name: str,
    description: str = "",
    *,
    addons_dir: str | Path = "addons",
    src_dir: str | Path = "src/formicos/addons",
) -> dict[str, str]:
    """Create the minimal file skeleton for a new addon.

    Returns a dict mapping relative paths to written content.
    """
    safe_name = name.replace("-", "_")
    addon_dir = Path(addons_dir) / name
    pkg_dir = Path(src_dir) / safe_name

    files: dict[str, str] = {}

    # Manifest
    manifest_path = addon_dir / "addon.yaml"
    manifest_content = _MANIFEST_TEMPLATE.format(
        name=name, description=description or f"{name} addon",
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(manifest_content, encoding="utf-8")
    files[str(manifest_path)] = manifest_content

    # Package init
    init_path = pkg_dir / "__init__.py"
    init_content = _INIT_TEMPLATE.format(name=name)
    init_path.parent.mkdir(parents=True, exist_ok=True)
    init_path.write_text(init_content, encoding="utf-8")
    files[str(init_path)] = init_content

    # Handler module
    handler_path = pkg_dir / "status.py"
    handler_content = _HANDLER_TEMPLATE.format(name=name)
    handler_path.write_text(handler_content, encoding="utf-8")
    files[str(handler_path)] = handler_content

    log.info(
        "addon_template.scaffolded",
        name=name,
        files=list(files.keys()),
    )
    return files
