"""Unit tests for colony file upload and export endpoints (ADR-029)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from starlette.testclient import TestClient

if TYPE_CHECKING:
    from starlette.requests import Request

_ALLOWED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv"}


@dataclass
class _FakeColony:
    id: str = "col-1"
    workspace_id: str = "default"
    status: str = "running"
    round_records: list = field(default_factory=list)
    chat_messages: list = field(default_factory=list)


@dataclass
class _FakeRound:
    round_number: int = 1
    agent_outputs: dict = field(default_factory=dict)


@dataclass
class _FakeChat:
    sender: str = "coder-0"
    content: str = "hello"
    timestamp: str = "2026-03-15T12:00:00Z"


def _make_upload_app(
    projections: MagicMock,
    runtime: MagicMock,
    data_dir: Path,
) -> Starlette:
    """Build a minimal Starlette app with just the upload endpoint."""

    async def list_colony_files(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        col = projections.get_colony(colony_id)
        if col is None:
            return JSONResponse({"error": "colony not found"}, status_code=404)

        upload_dir = (
            data_dir / "workspaces" / col.workspace_id
            / "colonies" / colony_id / "uploads"
        )
        files: list[dict[str, Any]] = []
        if upload_dir.exists():
            for path in sorted(upload_dir.iterdir()):
                if path.is_file():
                    files.append({"name": path.name, "bytes": path.stat().st_size})
        return JSONResponse({"files": files})

    async def upload_colony_files(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        col = projections.get_colony(colony_id)
        if col is None:
            return JSONResponse({"error": "colony not found"}, status_code=404)

        form = await request.form()
        upload_dir = (
            data_dir / "workspaces" / col.workspace_id
            / "colonies" / colony_id / "uploads"
        )
        upload_dir.mkdir(parents=True, exist_ok=True)

        uploaded: list[dict[str, Any]] = []
        total_bytes = 0
        for value in form.values():
            if not hasattr(value, "read"):
                continue
            content = await value.read()
            if len(content) > 10 * 1024 * 1024:
                continue
            total_bytes += len(content)
            if total_bytes > 50 * 1024 * 1024:
                break
            filename = Path(value.filename or "file").name
            suffix = Path(filename).suffix.lower()
            if suffix not in _ALLOWED_EXTENSIONS:
                continue
            path = upload_dir / filename
            path.write_bytes(content)
            uploaded.append({"name": filename, "bytes": len(content)})

            if col.status == "running" and runtime.colony_manager is not None:
                text = content.decode("utf-8", errors="replace")
                await runtime.colony_manager.inject_message(
                    colony_id,
                    f"[Uploaded Document: {filename}]\n{text[:8000]}",
                )

        await form.close()
        return JSONResponse({"uploaded": uploaded})

    return Starlette(routes=[
        Route("/api/v1/colonies/{colony_id:str}/files", list_colony_files, methods=["GET"]),
        Route("/api/v1/colonies/{colony_id:str}/files", upload_colony_files, methods=["POST"]),
    ])


def _make_export_app(
    projections: MagicMock,
    data_dir: Path,
) -> Starlette:
    """Build a minimal Starlette app with just the export endpoint."""

    async def export_colony(request: Request) -> Response:
        colony_id = request.path_params["colony_id"]
        col = projections.get_colony(colony_id)
        if col is None:
            return JSONResponse({"error": "colony not found"}, status_code=404)

        items = set(request.query_params.get("items", "uploads,outputs,chat").split(","))
        selected_uploads = {
            name for name in request.query_params.get("uploads", "").split(",") if name
        }
        selected_ws_files = {
            name for name in request.query_params.get("workspace_files", "").split(",") if name
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if "uploads" in items:
                udir = (
                    data_dir / "workspaces" / col.workspace_id
                    / "colonies" / colony_id / "uploads"
                )
                if udir.exists():
                    for path in sorted(udir.iterdir()):
                        if selected_uploads and path.name not in selected_uploads:
                            continue
                        if path.is_file():
                            zf.writestr(f"uploads/{path.name}", path.read_bytes())

            if "workspace_files" in items:
                ws_dir = data_dir / "workspaces" / col.workspace_id / "files"
                if ws_dir.exists():
                    for path in sorted(ws_dir.iterdir()):
                        if selected_ws_files and path.name not in selected_ws_files:
                            continue
                        if path.is_file():
                            zf.writestr(f"workspace/{path.name}", path.read_bytes())

            if "outputs" in items:
                for rec in col.round_records:
                    for agent_id, output in rec.agent_outputs.items():
                        zf.writestr(
                            f"outputs/round-{rec.round_number}/{agent_id}.txt",
                            output,
                        )

            if "chat" in items:
                lines = [
                    f"[{msg.timestamp}] {msg.sender}: {msg.content}"
                    for msg in col.chat_messages
                ]
                if lines:
                    zf.writestr("chat.md", "\n\n".join(lines))

        return Response(
            content=buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{colony_id}-export.zip"'},
        )

    return Starlette(routes=[
        Route("/api/v1/colonies/{colony_id:str}/export", export_colony),
    ])


def _make_workspace_app(
    workspaces: dict[str, object],
    data_dir: Path,
) -> Starlette:
    """Build a minimal Starlette app with workspace file routes."""

    async def list_workspace_files(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        if workspace_id not in workspaces:
            return JSONResponse({"error": "workspace not found"}, status_code=404)
        ws_dir = data_dir / "workspaces" / workspace_id / "files"
        files: list[dict[str, Any]] = []
        if ws_dir.exists():
            for path in sorted(ws_dir.iterdir()):
                if path.is_file():
                    files.append({"name": path.name, "bytes": path.stat().st_size})
        return JSONResponse({"files": files})

    async def preview_workspace_file(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        file_name = Path(request.path_params["file_name"]).name
        if workspace_id not in workspaces:
            return JSONResponse({"error": "workspace not found"}, status_code=404)
        path = data_dir / "workspaces" / workspace_id / "files" / file_name
        if not path.is_file():
            return JSONResponse({"error": "file not found"}, status_code=404)
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        max_chars = 20_000
        return JSONResponse({
            "name": file_name,
            "bytes": len(raw),
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        })

    async def upload_workspace_files(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        if workspace_id not in workspaces:
            return JSONResponse({"error": "workspace not found"}, status_code=404)
        form = await request.form()
        ws_dir = data_dir / "workspaces" / workspace_id / "files"
        ws_dir.mkdir(parents=True, exist_ok=True)
        uploaded: list[dict[str, Any]] = []
        for value in form.values():
            if not hasattr(value, "read"):
                continue
            content = await value.read()
            filename = Path(value.filename or "file").name
            suffix = Path(filename).suffix.lower()
            if suffix not in _ALLOWED_EXTENSIONS:
                continue
            path = ws_dir / filename
            path.write_bytes(content)
            uploaded.append({"name": filename, "bytes": len(content)})
        await form.close()
        return JSONResponse({"uploaded": uploaded})

    return Starlette(routes=[
        Route("/api/v1/workspaces/{workspace_id:str}/files", list_workspace_files, methods=["GET"]),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/files/{file_name:str}",
            preview_workspace_file,
            methods=["GET"],
        ),
        Route(
            "/api/v1/workspaces/{workspace_id:str}/files",
            upload_workspace_files,
            methods=["POST"],
        ),
    ])


class TestUploadEndpoint:
    """Tests for POST /api/v1/colonies/{id}/files."""

    @pytest.mark.anyio()
    async def test_upload_stores_file(self, tmp_path: Path) -> None:
        colony = _FakeColony()
        projections = MagicMock()
        projections.get_colony.return_value = colony

        colony_manager = MagicMock()
        colony_manager.inject_message = AsyncMock()
        runtime = MagicMock()
        runtime.colony_manager = colony_manager

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        app = _make_upload_app(projections, runtime, data_dir)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/colonies/col-1/files",
            files={"test.txt": ("test.txt", b"hello world", "text/plain")},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["uploaded"]) == 1
        assert body["uploaded"][0]["name"] == "test.txt"

        # Verify file was stored
        stored = data_dir / "workspaces" / "default" / "colonies" / "col-1" / "uploads" / "test.txt"
        assert stored.exists()
        assert stored.read_bytes() == b"hello world"

        # Verify inject was called for running colony
        colony_manager.inject_message.assert_awaited_once()

    @pytest.mark.anyio()
    async def test_upload_rejects_binary(self, tmp_path: Path) -> None:
        colony = _FakeColony()
        projections = MagicMock()
        projections.get_colony.return_value = colony

        runtime = MagicMock()
        runtime.colony_manager = None

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        app = _make_upload_app(projections, runtime, data_dir)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/colonies/col-1/files",
            files={"image.png": ("image.png", b"\x89PNG\r\n", "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["uploaded"] == []

    @pytest.mark.anyio()
    async def test_upload_404_unknown_colony(self, tmp_path: Path) -> None:
        projections = MagicMock()
        projections.get_colony.return_value = None

        runtime = MagicMock()
        data_dir = tmp_path / "data"
        data_dir.mkdir()

        app = _make_upload_app(projections, runtime, data_dir)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/colonies/missing/files",
            files={"test.txt": ("test.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 404

    def test_list_uploaded_files(self, tmp_path: Path) -> None:
        colony = _FakeColony()
        projections = MagicMock()
        projections.get_colony.return_value = colony

        runtime = MagicMock()
        data_dir = tmp_path / "data"
        upload_dir = data_dir / "workspaces" / "default" / "colonies" / "col-1" / "uploads"
        upload_dir.mkdir(parents=True)
        (upload_dir / "notes.md").write_text("# notes", encoding="utf-8")

        app = _make_upload_app(projections, runtime, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/colonies/col-1/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == [{"name": "notes.md", "bytes": 7}]


class TestExportEndpoint:
    """Tests for GET /api/v1/colonies/{id}/export."""

    def test_export_chat(self, tmp_path: Path) -> None:
        colony = _FakeColony(
            status="completed",
            chat_messages=[
                _FakeChat(sender="coder-0", content="hello", timestamp="2026-03-15T12:00:00Z"),
                _FakeChat(
                    sender="reviewer-0",
                    content="looks good",
                    timestamp="2026-03-15T12:01:00Z",
                ),
            ],
        )
        projections = MagicMock()
        projections.get_colony.return_value = colony

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        app = _make_export_app(projections, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/colonies/col-1/export?items=chat")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        zf = zipfile.ZipFile(BytesIO(resp.content))
        assert "chat.md" in zf.namelist()
        chat_text = zf.read("chat.md").decode()
        assert "coder-0" in chat_text
        assert "hello" in chat_text

    def test_export_outputs(self, tmp_path: Path) -> None:
        colony = _FakeColony(
            status="completed",
            round_records=[
                _FakeRound(round_number=1, agent_outputs={"coder-0": "def foo(): pass"}),
            ],
        )
        projections = MagicMock()
        projections.get_colony.return_value = colony

        data_dir = tmp_path / "data"
        data_dir.mkdir()

        app = _make_export_app(projections, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/colonies/col-1/export?items=outputs")
        assert resp.status_code == 200

        zf = zipfile.ZipFile(BytesIO(resp.content))
        assert "outputs/round-1/coder-0.txt" in zf.namelist()
        assert zf.read("outputs/round-1/coder-0.txt").decode() == "def foo(): pass"

    def test_export_uploads(self, tmp_path: Path) -> None:
        colony = _FakeColony(status="completed")
        projections = MagicMock()
        projections.get_colony.return_value = colony

        data_dir = tmp_path / "data"
        upload_dir = data_dir / "workspaces" / "default" / "colonies" / "col-1" / "uploads"
        upload_dir.mkdir(parents=True)
        (upload_dir / "spec.md").write_text("# Spec\ndetails here")

        app = _make_export_app(projections, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/colonies/col-1/export?items=uploads")
        assert resp.status_code == 200

        zf = zipfile.ZipFile(BytesIO(resp.content))
        assert "uploads/spec.md" in zf.namelist()
        assert "# Spec" in zf.read("uploads/spec.md").decode()

    def test_export_workspace_files(self, tmp_path: Path) -> None:
        colony = _FakeColony(status="completed")
        projections = MagicMock()
        projections.get_colony.return_value = colony

        data_dir = tmp_path / "data"
        ws_dir = data_dir / "workspaces" / "default" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "readme.md").write_text("# Readme")

        app = _make_export_app(projections, data_dir)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/colonies/col-1/export?items=workspace_files",
        )
        assert resp.status_code == 200

        zf = zipfile.ZipFile(BytesIO(resp.content))
        assert "workspace/readme.md" in zf.namelist()
        assert "# Readme" in zf.read("workspace/readme.md").decode()

    def test_export_selected_workspace_files(self, tmp_path: Path) -> None:
        colony = _FakeColony(status="completed")
        projections = MagicMock()
        projections.get_colony.return_value = colony

        data_dir = tmp_path / "data"
        ws_dir = data_dir / "workspaces" / "default" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "a.md").write_text("A")
        (ws_dir / "b.md").write_text("B")

        app = _make_export_app(projections, data_dir)
        client = TestClient(app)
        resp = client.get(
            "/api/v1/colonies/col-1/export"
            "?items=workspace_files&workspace_files=a.md",
        )
        assert resp.status_code == 200

        zf = zipfile.ZipFile(BytesIO(resp.content))
        assert "workspace/a.md" in zf.namelist()
        assert "workspace/b.md" not in zf.namelist()


class TestWorkspaceFileEndpoints:
    """Tests for workspace-scoped file routes."""

    def test_list_empty(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/workspaces/default/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == []

    def test_list_with_files(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        ws_dir = data_dir / "workspaces" / "default" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "notes.md").write_text("# Notes")
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/workspaces/default/files")
        assert resp.status_code == 200
        assert resp.json()["files"] == [{"name": "notes.md", "bytes": 7}]

    def test_upload(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/workspaces/default/files",
            files={"doc.txt": ("doc.txt", b"hello workspace", "text/plain")},
        )
        assert resp.status_code == 200
        assert len(resp.json()["uploaded"]) == 1
        stored = data_dir / "workspaces" / "default" / "files" / "doc.txt"
        assert stored.exists()
        assert stored.read_bytes() == b"hello workspace"

    def test_upload_rejects_binary(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/workspaces/default/files",
            files={"img.png": ("img.png", b"\x89PNG", "image/png")},
        )
        assert resp.status_code == 200
        assert resp.json()["uploaded"] == []

    def test_404_unknown_workspace(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = _make_workspace_app({}, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/workspaces/nope/files")
        assert resp.status_code == 404

    def test_preview_workspace_file(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        ws_dir = data_dir / "workspaces" / "default" / "files"
        ws_dir.mkdir(parents=True)
        (ws_dir / "notes.md").write_text("# Notes\nhello", encoding="utf-8")
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/workspaces/default/files/notes.md")
        assert resp.status_code == 200
        assert resp.json()["name"] == "notes.md"
        assert "hello" in resp.json()["content"]

    def test_preview_workspace_file_404(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        app = _make_workspace_app({"default": True}, data_dir)
        client = TestClient(app)
        resp = client.get("/api/v1/workspaces/default/files/missing.md")
        assert resp.status_code == 404
