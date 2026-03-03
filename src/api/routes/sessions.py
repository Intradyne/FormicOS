"""
FormicOS v0.7.9 -- V1 Session & Approval Routes

Routes: /sessions GET, /{session_id} GET/DELETE, /{session_id}/recover,
        /approvals/pending, /approvals/{request_id}/resolve
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.api.helpers import api_error_v1, safe_serialize
from src.approval import ApprovalGate
from src.context import AsyncContextTree
from src.models import ApproveRequestV1
from src.session import SessionManager

router = APIRouter()


# -- Sessions --

@router.get("/sessions")
async def v1_list_sessions(request: Request):
    sm: SessionManager = request.app.state.session_manager
    sessions = await sm.list_sessions()
    return [safe_serialize(s) for s in sessions]


@router.get("/sessions/{session_id}")
async def v1_get_session(session_id: str, request: Request):
    sm: SessionManager = request.app.state.session_manager
    sessions = await sm.list_sessions()
    for s in sessions:
        sid = s.session_id if hasattr(s, "session_id") else (s.get("session_id") if isinstance(s, dict) else None)
        if sid == session_id:
            return safe_serialize(s)
    return api_error_v1(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")


@router.delete("/sessions/{session_id}")
async def v1_delete_session(session_id: str, request: Request):
    sm: SessionManager = request.app.state.session_manager
    ctx_s: AsyncContextTree = request.app.state.ctx
    try:
        await sm.delete_session(session_id)
        active_sid = ctx_s.get("colony", "session_id")
        if active_sid == session_id:
            await ctx_s.clear_colony()
        return {"status": "deleted", "session_id": session_id}
    except FileNotFoundError:
        return api_error_v1(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")
    except Exception as exc:
        return api_error_v1(500, "SESSION_DELETE_FAILED", str(exc))


@router.post("/sessions/{session_id}/recover")
async def v1_recover_session(session_id: str, request: Request):
    """Attempt recovery of a session."""
    sm: SessionManager = request.app.state.session_manager
    try:
        session = await sm.get_session(session_id)
        return {"session_id": session_id, "status": "recovered", "data": safe_serialize(session)}
    except FileNotFoundError:
        return api_error_v1(404, "SESSION_NOT_FOUND", f"Session '{session_id}' not found")


# -- Approvals --

@router.get("/approvals/pending")
async def v1_pending_approvals(request: Request):
    gate: ApprovalGate = request.app.state.approval_gate
    pending = gate.get_pending()
    return [safe_serialize(p) for p in pending]


@router.post("/approvals/{request_id}/resolve")
async def v1_resolve_approval(request_id: str, body: ApproveRequestV1, request: Request):
    gate: ApprovalGate = request.app.state.approval_gate
    try:
        gate.respond(request_id, body.approved)
        return {"request_id": request_id, "approved": body.approved, "status": "resolved"}
    except KeyError:
        return api_error_v1(404, "APPROVAL_NOT_FOUND", f"No pending approval '{request_id}'")
