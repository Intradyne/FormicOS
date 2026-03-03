"""
FormicOS v0.7.9 -- V1 Workspace Routes

Routes for file operations within colony workspaces:
- GET  /colonies/{colony_id}/workspace/files
- GET  /colonies/{colony_id}/workspace/files/{file_path}
- POST /colonies/{colony_id}/workspace/upload
- GET  /colonies/{colony_id}/workspace/archive
- POST /colonies/{colony_id}/workspace/open
"""

from __future__ import annotations

import io
import logging
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse

from src.api.helpers import api_error_v1, check_colony_ownership
from src.auth import ClientAPIKey, get_current_client
from src.colony_manager import ColonyManager

logger = logging.getLogger("formicos.server")

router = APIRouter()


@router.get("/colonies/{colony_id}/workspace/files")
async def v1_list_workspace_files(
    colony_id: str,
    request: Request,
    path: str = "",
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
    workspace = Path("./workspace") / colony_id
    if not workspace.exists():
        return []
    mgr = SharedWorkspaceManager(workspace)
    try:
        return await mgr.list_files(path)
    except SandboxViolationError:
        return api_error_v1(403, "SANDBOX_VIOLATION", "Path escapes workspace")


@router.get("/colonies/{colony_id}/workspace/files/{file_path:path}")
async def v1_read_workspace_file(
    colony_id: str,
    file_path: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
    workspace = Path("./workspace") / colony_id
    file_path = file_path.replace("\\", "/")
    mgr = SharedWorkspaceManager(workspace)
    try:
        content = await mgr.read_file(file_path)
        return {"path": file_path, "content": content}
    except FileNotFoundError:
        return api_error_v1(404, "FILE_NOT_FOUND", f"File not found: {file_path}")
    except SandboxViolationError:
        return api_error_v1(403, "SANDBOX_VIOLATION", "Path escapes workspace")


@router.post("/colonies/{colony_id}/workspace/upload")
async def v1_upload_workspace_file(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    from src.stigmergy import SharedWorkspaceManager, SandboxViolationError
    workspace = Path("./workspace") / colony_id
    workspace.mkdir(parents=True, exist_ok=True)
    mgr = SharedWorkspaceManager(workspace)

    filename = request.headers.get("X-Filename", "")
    if not filename:
        return api_error_v1(400, "MISSING_FILENAME", "X-Filename header required")

    body_bytes = await request.body()
    try:
        written = await mgr.write_file(filename, body_bytes)
        return {"path": filename, "bytes_written": written}
    except SandboxViolationError:
        return api_error_v1(403, "SANDBOX_VIOLATION", "Path escapes workspace")


@router.get("/colonies/{colony_id}/workspace/archive")
async def v1_download_workspace_archive(
    colony_id: str,
    request: Request,
    path: str = "",
    paths: list[str] | None = Query(default=None),
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    workspace = (Path("./workspace") / colony_id).resolve()
    if not workspace.exists():
        return api_error_v1(404, "COLONY_NOT_FOUND", f"Workspace for colony '{colony_id}' not found")

    def _resolve_inside_workspace(rel_path: str) -> Path:
        p = (workspace / rel_path).resolve()
        try:
            p.relative_to(workspace)
        except ValueError:
            raise PermissionError("Path escapes workspace")
        return p

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        selected_paths = paths or []
        if path and selected_paths:
            return api_error_v1(
                400,
                "INVALID_REQUEST",
                "Use either 'path' or 'paths', not both.",
            )

        if selected_paths:
            selected_files: list[Path] = []
            seen: set[str] = set()

            for rel in selected_paths:
                rel_norm = str(rel or "").replace("\\", "/").strip("/")
                if not rel_norm:
                    continue
                try:
                    target = _resolve_inside_workspace(rel_norm)
                except PermissionError:
                    return api_error_v1(403, "SANDBOX_VIOLATION", "Path escapes workspace")

                if not target.exists():
                    return api_error_v1(404, "FILE_NOT_FOUND", f"Path not found: {rel_norm}")

                if target.is_file():
                    key = str(target)
                    if key not in seen:
                        selected_files.append(target)
                        seen.add(key)
                    continue

                for p in target.rglob("*"):
                    if not p.is_file():
                        continue
                    key = str(p)
                    if key in seen:
                        continue
                    selected_files.append(p)
                    seen.add(key)

            if not selected_files:
                return api_error_v1(
                    400,
                    "NO_FILES_SELECTED",
                    "No workspace files were selected for archive download.",
                )

            for p in selected_files:
                zf.write(p, arcname=str(p.relative_to(workspace)).replace("\\", "/"))

        else:
            try:
                target = _resolve_inside_workspace(path) if path else workspace
            except PermissionError:
                return api_error_v1(403, "SANDBOX_VIOLATION", "Path escapes workspace")
            if not target.exists():
                return api_error_v1(404, "FILE_NOT_FOUND", f"Path not found: {path}")

            if target.is_file():
                zf.write(target, arcname=target.name)
            else:
                for p in target.rglob("*"):
                    if p.is_file():
                        zf.write(p, arcname=str(p.relative_to(target)).replace("\\", "/"))
    buf.seek(0)

    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "-", colony_id).strip("-") or "colony"
    filename = f"{safe_name}-workspace.zip"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)


@router.post("/colonies/{colony_id}/workspace/open")
async def v1_open_workspace_folder(
    colony_id: str,
    request: Request,
    client: ClientAPIKey | None = Depends(get_current_client),
):
    cm: ColonyManager = request.app.state.colony_manager
    ownership_err = check_colony_ownership(colony_id, client, cm)
    if ownership_err:
        return ownership_err
    workspace = (Path("./workspace") / colony_id).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    ws_str = str(workspace)
    ws_norm = ws_str.replace("\\", "/")
    container_ws_root = os.environ.get("FORMICOS_CONTAINER_WORKSPACE", "/app/workspace").replace("\\", "/").rstrip("/")
    host_ws_root = os.environ.get("FORMICOS_HOST_WORKSPACE_ROOT", "workspace").replace("\\", "/").rstrip("/")
    host_path_hint = None
    if ws_norm == container_ws_root:
        host_path_hint = host_ws_root
    elif ws_norm.startswith(container_ws_root + "/"):
        rel = ws_norm[len(container_ws_root) + 1:]
        host_path_hint = f"{host_ws_root}/{rel}"
    response = {
        "status": "unavailable",
        "opened": False,
        "path": ws_str,
        "host_path_hint": host_path_hint,
        "reason": None,
    }
    try:
        if os.name == "nt":
            if hasattr(os, "startfile"):
                os.startfile(ws_str)  # type: ignore[attr-defined]
                return {"status": "opened", "opened": True, "path": ws_str, "host_path_hint": host_path_hint}
            response["reason"] = "startfile_unavailable"
            return response
        elif sys.platform == "darwin":
            opener = "open"
        else:
            opener = "xdg-open"

        if shutil.which(opener) is None:
            response["reason"] = f"{opener}_not_installed"
            return response

        if opener == "xdg-open":
            has_gui = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            if not has_gui:
                response["reason"] = "no_graphical_session"
                return response

        proc = subprocess.Popen(
            [opener, ws_str],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {
            "status": "opened",
            "opened": True,
            "path": ws_str,
            "host_path_hint": host_path_hint,
            "pid": proc.pid,
        }
    except Exception as exc:
        logger.warning("Workspace open failed for colony '%s': %s", colony_id, exc)
        response["reason"] = str(exc)
        return response
