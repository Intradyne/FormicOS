"""Colony and workspace file I/O routes (ADR-029, ADR-037)."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from formicos.core.types import VectorDocument
from formicos.surface.credential_scan import redact_credentials
from formicos.surface.structured_error import KNOWN_ERRORS, to_http_error
from formicos.surface.transcript import build_transcript

if TYPE_CHECKING:
    from starlette.requests import Request

    from formicos.core.ports import VectorPort
    from formicos.surface.projections import ProjectionStore
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()

_ALLOWED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv"}
_MAX_FILE_BYTES = 10 * 1024 * 1024   # 10 MB per file
_MAX_COLONY_BYTES = 50 * 1024 * 1024  # 50 MB total per colony
_INJECT_TRUNCATE = 8000               # chars injected into running colony
_CHUNK_SIZE = 1000                    # chars per chunk for knowledge ingestion
_CHUNK_OVERLAP = 200                  # overlap between chunks


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks for embedding."""
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def routes(
    *,
    runtime: Runtime,
    projections: ProjectionStore,
    data_dir: Path,
    vector_store: VectorPort | None = None,
    **_unused: Any,
) -> list[Route]:
    """Build colony/workspace file I/O routes."""

    def _err_response(err_key: str, **overrides: Any) -> JSONResponse:
        err = KNOWN_ERRORS[err_key]
        if overrides:
            err = err.model_copy(update=overrides)
        status, body, headers = to_http_error(err)
        return JSONResponse(body, status_code=status, headers=headers)

    async def list_colony_files(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")

        upload_dir = (
            data_dir / "workspaces" / colony.workspace_id
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
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")

        form = await request.form()
        upload_dir = (
            data_dir / "workspaces" / colony.workspace_id
            / "colonies" / colony_id / "uploads"
        )
        upload_dir.mkdir(parents=True, exist_ok=True)

        uploaded: list[dict[str, Any]] = []
        total_bytes = 0

        for value in form.values():
            if not hasattr(value, "read"):
                continue
            content = await value.read()  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue]
            if len(content) > _MAX_FILE_BYTES:  # pyright: ignore[reportUnknownArgumentType]
                continue
            total_bytes += len(content)  # pyright: ignore[reportUnknownArgumentType]
            if total_bytes > _MAX_COLONY_BYTES:
                break

            filename = Path(value.filename or "file").name  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportAttributeAccessIssue]
            suffix = Path(filename).suffix.lower()
            if suffix not in _ALLOWED_EXTENSIONS:
                continue

            path = upload_dir / filename
            path.write_bytes(content)
            uploaded.append({"name": filename, "bytes": len(content)})  # pyright: ignore[reportUnknownArgumentType]

            # Inject into running colony via colony_manager
            if colony.status == "running" and runtime.colony_manager is not None:
                text = content.decode("utf-8", errors="replace")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
                await runtime.colony_manager.inject_message(
                    colony_id,
                    f"[Uploaded Document: {filename}]\n{text[:_INJECT_TRUNCATE]}",
                )

        await form.close()
        return JSONResponse({"uploaded": uploaded})

    async def export_colony(request: Request) -> Response:
        colony_id = request.path_params["colony_id"]
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")

        items = set(
            request.query_params.get("items", "uploads,outputs,chat").split(","),
        )
        selected_uploads = {
            name
            for name in request.query_params.get("uploads", "").split(",")
            if name
        }
        selected_workspace_files = {
            name
            for name in request.query_params.get("workspace_files", "").split(",")
            if name
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if "uploads" in items:
                udir = (
                    data_dir / "workspaces" / colony.workspace_id
                    / "colonies" / colony_id / "uploads"
                )
                if udir.exists():
                    for path in sorted(udir.iterdir()):
                        if selected_uploads and path.name not in selected_uploads:
                            continue
                        if path.is_file():
                            zf.writestr(f"uploads/{path.name}", path.read_bytes())

            if "workspace_files" in items:
                ws_dir = data_dir / "workspaces" / colony.workspace_id / "files"
                if ws_dir.exists():
                    for path in sorted(ws_dir.iterdir()):
                        if selected_workspace_files and path.name not in selected_workspace_files:
                            continue
                        if path.is_file():
                            zf.writestr(f"workspace/{path.name}", path.read_bytes())

            if "outputs" in items:
                for rec in colony.round_records:
                    for agent_id, output in rec.agent_outputs.items():
                        zf.writestr(
                            f"outputs/round-{rec.round_number}/{agent_id}.txt",
                            output,
                        )

            if "chat" in items:
                lines = [
                    f"[{msg.timestamp}] {msg.sender}: {msg.content}"
                    for msg in colony.chat_messages
                ]
                if lines:
                    zf.writestr("chat.md", "\n\n".join(lines))

        zip_bytes = buf.getvalue()
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{colony_id}-export.zip"',
            },
        )

    # -- Workspace file I/O --

    async def list_workspace_files(request: Request) -> JSONResponse:
        workspace_id = request.path_params["workspace_id"]
        ws = projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

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
        ws = projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        path = data_dir / "workspaces" / workspace_id / "files" / file_name
        if not path.is_file():
            return _err_response("FILE_NOT_FOUND")

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
        ws = projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")

        form = await request.form()
        ws_dir = data_dir / "workspaces" / workspace_id / "files"
        ws_dir.mkdir(parents=True, exist_ok=True)

        uploaded: list[dict[str, Any]] = []
        total_bytes = 0

        for value in form.values():
            if not hasattr(value, "read"):
                continue
            content = await value.read()  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue]
            if len(content) > _MAX_FILE_BYTES:  # pyright: ignore[reportUnknownArgumentType]
                continue
            total_bytes += len(content)  # pyright: ignore[reportUnknownArgumentType]
            if total_bytes > _MAX_COLONY_BYTES:
                break

            filename = Path(value.filename or "file").name  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportAttributeAccessIssue]
            suffix = Path(filename).suffix.lower()
            if suffix not in _ALLOWED_EXTENSIONS:
                continue

            path = ws_dir / filename
            path.write_bytes(content)
            uploaded.append({"name": filename, "bytes": len(content)})  # pyright: ignore[reportUnknownArgumentType]

        await form.close()
        return JSONResponse({"uploaded": uploaded})

    # -- Colony transcript (Wave 20 Track A) --

    async def get_transcript(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")
        transcript = build_transcript(colony)
        # Wave 33 B2: redact credentials from transcript exports
        for round_data in transcript.get("round_summaries", []):
            for agent in round_data.get("agents", []):
                summary = agent.get("output_summary", "")
                if summary:
                    agent["output_summary"], _ = redact_credentials(summary)
        final = transcript.get("final_output", "")
        if final:
            transcript["final_output"], _ = redact_credentials(final)
        return JSONResponse(transcript)

    # -- Colony artifact read surfaces (Wave 25.5) --

    _PREVIEW_CHARS = 500

    async def list_colony_artifacts(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")

        previews: list[dict[str, Any]] = []
        for art in colony.artifacts:
            previews.append({
                "id": art.get("id", ""),
                "name": art.get("name", ""),
                "artifact_type": art.get("artifact_type", "generic"),
                "mime_type": art.get("mime_type", "text/plain"),
                "source_agent_id": art.get("source_agent_id", ""),
                "source_round": art.get("source_round", 0),
                "content_preview": art.get("content", "")[:_PREVIEW_CHARS],
            })
        return JSONResponse({"artifacts": previews})

    async def get_colony_artifact(request: Request) -> JSONResponse:
        colony_id = request.path_params["colony_id"]
        artifact_id = request.path_params["artifact_id"]
        colony = projections.get_colony(colony_id)
        if colony is None:
            return _err_response("COLONY_NOT_FOUND")

        for art in colony.artifacts:
            if art.get("id") == artifact_id:
                return JSONResponse({
                    "id": art.get("id", ""),
                    "name": art.get("name", ""),
                    "artifact_type": art.get("artifact_type", "generic"),
                    "mime_type": art.get("mime_type", "text/plain"),
                    "content": art.get("content", ""),
                    "source_colony_id": art.get("source_colony_id", ""),
                    "source_agent_id": art.get("source_agent_id", ""),
                    "source_round": art.get("source_round", 0),
                    "created_at": art.get("created_at", ""),
                    "metadata": art.get("metadata", {}),
                })
        return _err_response("ARTIFACT_NOT_FOUND")

    # -- Workspace knowledge ingestion (Wave 22 Track B, ADR-037) --

    async def ingest_workspace_file(request: Request) -> JSONResponse:
        """Upload a file to workspace library and embed into workspace memory."""
        workspace_id = request.path_params["workspace_id"]
        ws = projections.workspaces.get(workspace_id)
        if ws is None:
            return _err_response("WORKSPACE_NOT_FOUND")
        if vector_store is None:
            return _err_response("VECTOR_STORE_UNAVAILABLE")

        form = await request.form()
        ws_dir = data_dir / "workspaces" / workspace_id / "files"
        ws_dir.mkdir(parents=True, exist_ok=True)

        ingested: list[dict[str, Any]] = []
        for value in form.values():
            if not hasattr(value, "read"):
                continue
            content = await value.read()  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType,reportAttributeAccessIssue]
            if len(content) > _MAX_FILE_BYTES:  # pyright: ignore[reportUnknownArgumentType]
                continue

            filename = Path(value.filename or "file").name  # pyright: ignore[reportUnknownMemberType,reportUnknownArgumentType,reportAttributeAccessIssue]
            suffix = Path(filename).suffix.lower()
            if suffix not in _ALLOWED_EXTENSIONS:
                continue

            # Write file to workspace directory
            path = ws_dir / filename
            path.write_bytes(content)

            # Chunk and embed into workspace memory collection
            text = content.decode("utf-8", errors="replace")  # pyright: ignore[reportUnknownVariableType,reportUnknownMemberType]
            chunks = _chunk_text(text)  # pyright: ignore[reportUnknownArgumentType]
            now_iso = datetime.now(UTC).isoformat()
            docs = [
                VectorDocument(
                    id=f"wsdoc-{workspace_id}-{filename}-{i}-{uuid4().hex[:6]}",
                    content=chunk,
                    metadata={
                        "type": "workspace_doc",
                        "source_file": filename,
                        "chunk_index": i,
                        "workspace_id": workspace_id,
                        "ingested_at": now_iso,
                    },
                )
                for i, chunk in enumerate(chunks)
            ]
            count = await vector_store.upsert(collection=workspace_id, docs=docs)
            log.info(
                "workspace.knowledge_ingested",
                workspace_id=workspace_id,
                filename=filename,
                chunks=len(chunks),
                upserted=count,
            )
            ingested.append({
                "name": filename,
                "bytes": len(content),  # pyright: ignore[reportUnknownArgumentType]
                "chunks": len(chunks),
            })

        await form.close()
        return JSONResponse({"ingested": ingested})

    return [
        Route("/api/v1/colonies/{colony_id:str}/files", list_colony_files, methods=["GET"]),
        Route("/api/v1/colonies/{colony_id:str}/files", upload_colony_files, methods=["POST"]),
        Route("/api/v1/colonies/{colony_id:str}/export", export_colony),
        Route("/api/v1/colonies/{colony_id:str}/transcript", get_transcript, methods=["GET"]),
        Route("/api/v1/colonies/{colony_id:str}/artifacts", list_colony_artifacts, methods=["GET"]),
        Route(
            "/api/v1/colonies/{colony_id:str}/artifacts/{artifact_id:str}",
            get_colony_artifact,
            methods=["GET"],
        ),
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
        Route(
            "/api/v1/workspaces/{workspace_id:str}/ingest",
            ingest_workspace_file,
            methods=["POST"],
        ),
    ]
