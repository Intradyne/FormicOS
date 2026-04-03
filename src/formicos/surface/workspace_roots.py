"""Workspace root resolution — separates project, library, and runtime paths (Wave 81).

Three root concepts:

- **Library root**: ``{data_dir}/workspaces/{id}/files`` — shared file surface
  for uploads, colony output artifacts, and document ingestion.
- **Project root**: ``/project`` (or ``PROJECT_DIR`` env) when mounted — the
  operator's real source code. Falls back to the library root when unbound.
- **Runtime root**: Project root when available, library root otherwise. This
  is what colony tools and code analysis should use for reads/writes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def workspace_library_root(data_dir: str, workspace_id: str) -> Path:
    """Return the workspace library root (uploads, shared files)."""
    return Path(data_dir) / "workspaces" / workspace_id / "files"


def workspace_project_root(workspace_id: str) -> Path | None:
    """Return the bound project root, or None if unbound.

    The project root is determined by the ``PROJECT_DIR`` environment
    variable, which defaults to ``/project`` in the Docker container.
    Returns None when the path doesn't exist or isn't a directory.
    """
    project_dir = os.environ.get("PROJECT_DIR", "/project")
    path = Path(project_dir)
    if path.is_dir():
        return path
    return None


def workspace_runtime_root(data_dir: str, workspace_id: str) -> Path:
    """Return the effective runtime root for colony execution.

    Returns the project root when bound, otherwise the library root.
    """
    project = workspace_project_root(workspace_id)
    if project is not None:
        return project
    return workspace_library_root(data_dir, workspace_id)


def workspace_binding_status(data_dir: str, workspace_id: str) -> dict[str, Any]:
    """Return binding status payload for API consumers."""
    library = workspace_library_root(data_dir, workspace_id)
    project = workspace_project_root(workspace_id)
    runtime = workspace_runtime_root(data_dir, workspace_id)
    return {
        "library_root": str(library),
        "project_root": str(project) if project else None,
        "runtime_root": str(runtime),
        "project_bound": project is not None,
        "bound": project is not None,  # Wave 81 Track D compat alias
    }
