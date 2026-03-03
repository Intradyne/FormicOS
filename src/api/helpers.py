"""
FormicOS v0.7.9 -- Shared V1 API Helpers

Standalone functions extracted from server.py closures.
Route modules call these instead of referencing closure variables.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse

from src.auth import ClientAPIKey
from src.colony_manager import ColonyManager, ColonyNotFoundError
from src.models import (
    AgentInfoV1,
    ArtifactRefsV1,
    ColonyResultV1,
    ColonyStateV1,
    ErrorResponse,
    EventEnvelopeV1,
    EventTrace,
    FailureInfoV1,
    ProblemDetail,
    SUGGESTED_FIXES,
    TeamInfoV1,
    WorkspaceMetaV1,
)


# ── Thread-safe sequence counter ─────────────────────────────────────────

_colony_seq: dict[str, int] = {}


def next_seq(colony_id: str) -> int:
    """Monotonically increasing sequence number per colony."""
    _colony_seq[colony_id] = _colony_seq.get(colony_id, 0) + 1
    return _colony_seq[colony_id]


def cleanup_seq(colony_id: str) -> None:
    """Remove sequence counter for a destroyed colony."""
    _colony_seq.pop(colony_id, None)


# ── Error Helpers ────────────────────────────────────────────────────────


def api_error_v1(
    status_code: int,
    code: str,
    message: str,
    detail: Any = None,
    request_id: str | None = None,
) -> JSONResponse:
    """Build an RFC 7807 ProblemDetail JSONResponse.

    Keeps ``error_code`` for backward compat with pre-v0.7.3 clients.
    """
    rid = request_id or str(uuid.uuid4())
    msg = f"{message} — {detail}" if detail else message
    body = ProblemDetail(
        type=f"https://formicos.dev/errors/{code.lower().replace('_', '-')}",
        title=code.replace("_", " ").title(),
        status=status_code,
        detail=msg,
        instance=f"urn:formicos:request:{rid}",
        suggested_fix=SUGGESTED_FIXES.get(code),
        error_code=code,
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
    )


def error_response(
    status_code: int,
    error_code: str,
    detail: str,
    request_id: str | None = None,
) -> JSONResponse:
    """Build a structured error JSONResponse (legacy format)."""
    rid = request_id or str(uuid.uuid4())
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            error_code=error_code,
            error_detail=detail,
            request_id=rid,
        ).model_dump(),
    )


# ── Event Envelope ───────────────────────────────────────────────────────


def event_envelope(
    type_: str,
    colony_id: str,
    payload: dict[str, Any] | None = None,
    trace: EventTrace | None = None,
) -> dict[str, Any]:
    """Build an EventEnvelopeV1 dict."""
    env = EventEnvelopeV1(
        event_id=str(uuid.uuid4()),
        seq=next_seq(colony_id),
        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        colony_id=colony_id,
        type=type_,
        payload=payload or {},
        trace=trace or EventTrace(),
    )
    return env.model_dump()


# ── State Builders ───────────────────────────────────────────────────────


def build_colony_state_v1(colony_id: str, cm: ColonyManager) -> ColonyStateV1:
    """Assemble ColonyStateV1 from ColonyManager state."""
    info = cm.get_info(colony_id)
    ctx = cm.get_context(colony_id)

    # Build agent info
    agents_raw = ctx.get("colony", "agents", [])
    agent_infos = []
    for a in agents_raw:
        if isinstance(a, str):
            agent_infos.append(AgentInfoV1(agent_id=a, caste="unknown"))
        elif isinstance(a, dict):
            agent_infos.append(AgentInfoV1(
                agent_id=a.get("agent_id", "unknown"),
                caste=a.get("caste", "unknown"),
                model_id=a.get("model_id"),
            ))

    # Build team info
    teams_raw = ctx.get("colony", "teams", [])
    team_infos = []
    for t in teams_raw:
        if isinstance(t, str):
            team_infos.append(TeamInfoV1(team_id=t, name=t))
        elif isinstance(t, dict):
            team_infos.append(TeamInfoV1(
                team_id=t.get("team_id", "unknown"),
                name=t.get("name", "unknown"),
                members=t.get("members", []),
            ))

    # Workspace meta
    ws_path = Path("./workspace") / colony_id
    artifact_count = 0
    if ws_path.exists():
        artifact_count = sum(1 for p in ws_path.rglob("*") if p.is_file())
    workspace = WorkspaceMetaV1(
        root=str(ws_path),
        artifact_count=artifact_count,
    )

    # Live round from context tree (updated by orchestrator each round),
    # falling back to info.round (only synced at completion).
    live_round = ctx.get("colony", "round", info.round)
    if not isinstance(live_round, int):
        live_round = info.round

    return ColonyStateV1(
        colony_id=colony_id,
        status=info.status.value if hasattr(info.status, "value") else str(info.status),
        task=info.task,
        round=live_round,
        max_rounds=info.max_rounds,
        agents=agent_infos,
        teams=team_infos,
        workspace=workspace,
        artifacts=ArtifactRefsV1(
            session_ref=str(Path(".formicos/sessions") / colony_id / "context.json"),
        ),
        created_ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(info.created_at)),
        updated_ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(info.updated_at)),
        origin=info.origin,
        client_id=info.client_id,
    )


def build_colony_result_v1(colony_id: str, cm: ColonyManager) -> ColonyResultV1:
    """Assemble ColonyResultV1 from colony state and workspace."""
    info = cm.get_info(colony_id)
    ctx = cm.get_context(colony_id)

    # Workspace files
    ws_path = Path("./workspace") / colony_id
    files: list[str] = []
    if ws_path.exists():
        files = sorted(
            str(p.relative_to(ws_path)).replace("\\", "/")
            for p in ws_path.rglob("*") if p.is_file()
        )

    final_answer = ctx.get("colony", "final_answer")
    summary_text = None
    try:
        episodes = ctx.get_episodes()
    except Exception:
        episodes = []
    if episodes:
        last_ep = episodes[-1]
        if isinstance(last_ep, dict):
            summary_text = last_ep.get("summary")
        else:
            summary_text = getattr(last_ep, "summary", None)
    if not final_answer and summary_text:
        final_answer = summary_text
    status_val = info.status.value if hasattr(info.status, "value") else str(info.status)

    failure = FailureInfoV1()
    if status_val == "failed":
        failure = FailureInfoV1(
            code="COLONY_FAILED",
            detail=ctx.get("colony", "error_detail"),
        )

    return ColonyResultV1(
        colony_id=colony_id,
        status=status_val,
        final_answer=final_answer,
        summary=summary_text,
        files=files,
        session_ref=str(Path(".formicos/sessions") / colony_id / "context.json"),
        completed_ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(info.updated_at)),
        failure=failure,
    )


# ── Namespace Isolation ──────────────────────────────────────────────────


def check_colony_ownership(
    colony_id: str,
    client: ClientAPIKey | None,
    cm: ColonyManager,
) -> JSONResponse | None:
    """If client is authenticated, verify colony ownership.

    Returns a 403 JSONResponse if unauthorized, None if OK.
    """
    if client is None:
        return None
    try:
        info = cm.get_info(colony_id)
    except ColonyNotFoundError:
        return None  # let caller handle 404
    if (
        info.client_id is not None
        and info.client_id != client.client_id
    ):
        return api_error_v1(
            403, "FORBIDDEN",
            f"Colony '{colony_id}' belongs to a different client",
        )
    return None


# ── Serialisation ────────────────────────────────────────────────────────


def safe_serialize(obj: Any) -> Any:
    """Convert Pydantic models and other objects to JSON-safe dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [safe_serialize(item) for item in obj]
    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}
    return obj
