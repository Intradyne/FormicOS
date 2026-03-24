"""FastMCP tool server — sole programmatic API (ADR-005).

All colony operations delegate to runtime. MCP tools and WS commands
share the same runtime operations — no duplication.
"""
# pyright: reportUnusedFunction=false

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import structlog
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from formicos.surface.structured_error import KNOWN_ERRORS, to_mcp_tool_error

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()

MCP_TOOL_NAMES = (
    "list_workspaces",
    "get_status",
    "create_workspace",
    "create_thread",
    "spawn_colony",
    "list_templates",
    "get_template_detail",
    "suggest_team",
    "code_execute",
    "kill_colony",
    "chat_queen",
    "create_merge",
    "prune_merge",
    "broadcast",
    "approve",
    "deny",
    "query_service",
    "activate_service",
    "chat_colony",
)

_RO = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
_MUT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
_DEST = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True)


def create_mcp_server(runtime: Runtime) -> FastMCP:
    """Build and return the FastMCP server with all FormicOS tools."""
    # Convention: MCP tool returns may include underscore-prefixed metadata:
    #   _next_actions: list[str] — tool names the client should consider calling next
    #   _context: dict — IDs/state the client may need for follow-up calls
    # These are advisory — clients may ignore them.
    mcp = FastMCP("FormicOS")

    @mcp.tool(annotations=_RO)
    async def list_workspaces() -> list[dict[str, str]]:
        """List all workspaces."""
        return [
            {"id": ws.id, "name": ws.name}
            for ws in runtime.projections.workspaces.values()
        ]

    @mcp.tool(annotations=_RO)
    async def get_status(workspace_id: str) -> dict[str, Any]:
        """Get workspace status including threads and colonies."""
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])
        return {
            "id": ws.id,
            "name": ws.name,
            "threads": [
                {
                    "id": t.id,
                    "name": t.name,
                    "colonies": [
                        {"id": c.id, "status": c.status, "round": c.round_number}
                        for c in t.colonies.values()
                    ],
                }
                for t in ws.threads.values()
            ],
        }

    @mcp.tool(annotations=_MUT)
    async def create_workspace(name: str) -> dict[str, Any]:
        """Create a new workspace."""
        await runtime.create_workspace(name)
        return {
            "workspace_id": name,
            "_next_actions": ["create_thread", "list_workspaces"],
            "_context": {"workspace_id": name},
        }

    @mcp.tool(annotations=_MUT)
    async def create_thread(workspace_id: str, name: str) -> dict[str, Any]:
        """Create a new thread in a workspace."""
        await runtime.create_thread(workspace_id, name)
        return {
            "thread_id": name,
            "_next_actions": ["spawn_colony", "chat_queen"],
            "_context": {"workspace_id": workspace_id, "thread_id": name},
        }

    @mcp.tool(annotations=_MUT)
    async def spawn_colony(
        workspace_id: str,
        thread_id: str,
        task: str,
        castes: list[dict[str, Any]],
        strategy: str = "stigmergic",
        max_rounds: int = 25,
        budget_limit: float = 5.0,
        model_assignments: dict[str, str] | None = None,
        template_id: str = "",
    ) -> dict[str, Any]:
        """Spawn a new colony in a thread.

        castes: list of {caste, tier?, count?} dicts (CasteSlot shape).
        """
        from formicos.core.types import CasteSlot
        slots = [CasteSlot(**c) for c in castes]
        colony_id = await runtime.spawn_colony(
            workspace_id, thread_id, task, slots,
            strategy=strategy, max_rounds=max_rounds,
            budget_limit=budget_limit, model_assignments=model_assignments,
            template_id=template_id,
        )
        # Start colony round loop — same behavior as WS path (ADR-005 parity)
        if runtime.colony_manager is not None:
            asyncio.create_task(runtime.colony_manager.start_colony(colony_id))
        return {
            "colony_id": colony_id,
            "_next_actions": ["get_status", "chat_colony"],
            "_context": {"thread_id": thread_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_RO)
    async def list_templates() -> list[dict[str, Any]]:
        """List all colony templates."""
        from formicos.surface.template_manager import list_templates as _list
        return await _list()

    @mcp.tool(annotations=_RO)
    async def get_template_detail(template_id: str) -> dict[str, Any]:
        """Get a single colony template by ID."""
        from formicos.surface.template_manager import get_template as _get
        tmpl = await _get(template_id)
        if tmpl is None:
            return to_mcp_tool_error(KNOWN_ERRORS["TEMPLATE_NOT_FOUND"])
        return tmpl.model_dump()

    @mcp.tool(annotations=_RO)
    async def suggest_team(objective: str) -> list[dict[str, Any]]:
        """Suggest a team composition for a given objective."""
        return await runtime.suggest_team(objective)

    @mcp.tool(annotations=_RO)
    async def code_execute(
        code: str,
        timeout_s: int = 10,
    ) -> dict[str, Any]:
        """Execute Python code in a sandboxed container.

        AST-screened for dangerous patterns. Returns stdout, stderr, exit code.
        """
        from formicos.adapters.ast_security import check_ast_safety
        from formicos.adapters.output_sanitizer import sanitize_output
        from formicos.adapters.sandbox_manager import execute_sandboxed

        ast_result = check_ast_safety(code)
        if not ast_result.safe:
            return {"blocked": True, "reason": ast_result.reason, "exit_code": -1}

        result = await execute_sandboxed(code, timeout_s=min(timeout_s, 30))
        return {
            "blocked": False,
            "stdout": sanitize_output(result.stdout),
            "stderr": sanitize_output(result.stderr),
            "exit_code": result.exit_code,
        }

    @mcp.tool(annotations=_DEST)
    async def kill_colony(
        workspace_id: str, colony_id: str, killed_by: str = "operator",
    ) -> dict[str, Any]:
        """Kill a running colony."""
        await runtime.kill_colony(colony_id, killed_by)
        return {
            "status": "killed",
            "_next_actions": ["spawn_colony", "list_workspaces"],
            "_context": {"colony_id": colony_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_MUT)
    async def chat_queen(
        workspace_id: str, thread_id: str, content: str,
    ) -> dict[str, Any]:
        """Send a message to the Queen in a thread."""
        await runtime.send_queen_message(workspace_id, thread_id, content)
        # Schedule Queen response — same behavior as WS path (ADR-005 parity)
        if runtime.queen is not None:
            asyncio.create_task(runtime.queen.respond(workspace_id, thread_id))
        return {
            "status": "sent",
            "_next_actions": ["spawn_colony", "get_status"],
            "_context": {"workspace_id": workspace_id, "thread_id": thread_id},
        }

    @mcp.tool(annotations=_MUT)
    async def create_merge(
        workspace_id: str, from_colony: str, to_colony: str,
        created_by: str = "operator",
    ) -> dict[str, Any]:
        """Create a merge edge between two colonies."""
        edge_id = await runtime.create_merge(workspace_id, from_colony, to_colony, created_by)
        return {
            "edge_id": edge_id,
            "_next_actions": ["get_status"],
            "_context": {"edge_id": edge_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_DEST)
    async def prune_merge(
        workspace_id: str, edge_id: str, pruned_by: str = "operator",
    ) -> dict[str, Any]:
        """Remove a merge edge."""
        await runtime.prune_merge(workspace_id, edge_id)
        return {
            "status": "pruned",
            "_next_actions": ["get_status"],
            "_context": {"edge_id": edge_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_MUT)
    async def broadcast(
        workspace_id: str, thread_id: str, from_colony: str,
    ) -> dict[str, Any]:
        """Broadcast a colony's output to all siblings in the thread."""
        edges = await runtime.broadcast(workspace_id, thread_id, from_colony)
        return {
            "edges": edges,
            "_next_actions": ["get_status"],
            "_context": {"workspace_id": workspace_id, "from_colony": from_colony},
        }

    @mcp.tool(annotations=_DEST)
    async def approve(workspace_id: str, request_id: str) -> dict[str, Any]:
        """Grant a pending approval request."""
        await runtime.approve(workspace_id, request_id)
        return {
            "status": "approved",
            "_next_actions": ["get_status"],
            "_context": {"request_id": request_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_DEST)
    async def deny(workspace_id: str, request_id: str) -> dict[str, Any]:
        """Deny a pending approval request."""
        await runtime.deny(workspace_id, request_id)
        return {
            "status": "denied",
            "_next_actions": ["get_status"],
            "_context": {"request_id": request_id, "workspace_id": workspace_id},
        }

    @mcp.tool(annotations=_RO)
    async def query_service(
        service_type: str,
        query: str,
        timeout: int = 30,
    ) -> dict[str, Any]:
        """Query a service colony by type.

        Service colonies are completed colonies activated as persistent services.
        They retain their tools, skills, and knowledge.
        """
        if runtime.colony_manager is None:
            return to_mcp_tool_error(KNOWN_ERRORS["COLONY_MANAGER_UNAVAILABLE"])
        router = runtime.colony_manager.service_router
        try:
            response = await router.query(
                service_type=service_type,
                query_text=query,
                timeout_s=float(min(timeout, 60)),
            )
            return {"response": response}
        except ValueError as exc:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_SERVICE_TYPE"].model_copy(
                update={"message": str(exc)},
            ))
        except TimeoutError:
            return to_mcp_tool_error(KNOWN_ERRORS["SERVICE_TIMEOUT"])

    @mcp.tool(annotations=_MUT)
    async def activate_service(
        workspace_id: str,
        colony_id: str,
        service_type: str,
    ) -> dict[str, Any]:
        """Activate a completed colony as a service colony.

        The colony must have status 'completed'. After activation it becomes
        queryable via query_service.
        """
        if runtime.colony_manager is None:
            return to_mcp_tool_error(KNOWN_ERRORS["COLONY_MANAGER_UNAVAILABLE"])
        try:
            await runtime.colony_manager.activate_service(colony_id, service_type)
        except ValueError as exc:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_STATE"].model_copy(
                update={"message": str(exc)},
            ))
        return {
            "status": "activated",
            "service_type": service_type,
            "_next_actions": ["query_service", "get_status"],
            "_context": {"colony_id": colony_id, "service_type": service_type},
        }

    @mcp.tool(annotations=_RO)
    async def chat_colony(
        colony_id: str,
        message: str,
        directive_type: str | None = None,
        directive_priority: str = "normal",
    ) -> dict[str, str]:
        """Send an operator message to a colony's chat.

        The message is stored as a ColonyChatMessage event and injected
        into the colony's context for the next round.

        When directive_type is provided (context_update, priority_shift,
        constraint_add, strategy_change), the message is tagged as an
        operator directive with the given priority (normal or urgent).
        Directives get special framing in the agent's context assembly.
        """
        colony = runtime.projections.get_colony(colony_id)
        if colony is None:
            return to_mcp_tool_error(KNOWN_ERRORS["COLONY_NOT_FOUND"])

        # Validate directive_type if provided (ADR-045 D3)
        _valid_directive_types = {
            "context_update", "priority_shift", "constraint_add", "strategy_change",
        }
        if directive_type is not None and directive_type not in _valid_directive_types:
            valid_str = ", ".join(sorted(_valid_directive_types))
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": f"directive_type must be one of: {valid_str}"},
            ))

        from datetime import UTC, datetime

        from formicos.core.events import ColonyChatMessage as ChatMsg
        address = f"{colony.workspace_id}/{colony.thread_id}/{colony_id}"

        # Build metadata for directive-tagged messages
        metadata: dict[str, Any] | None = None
        event_directive_type: str | None = None
        if directive_type is not None:
            event_directive_type = directive_type
            metadata = {
                "directive_type": directive_type,
                "directive_priority": directive_priority,
            }

        await runtime.emit_and_broadcast(ChatMsg(
            seq=0, timestamp=datetime.now(UTC), address=address,
            colony_id=colony_id, workspace_id=colony.workspace_id,
            sender="operator", content=message,
            directive_type=event_directive_type,
            metadata=metadata,
        ))
        if runtime.colony_manager is not None:
            await runtime.colony_manager.inject_message(
                colony_id, message,
                directive_type=directive_type,
                directive_priority=directive_priority,
            )
        return {"status": "sent", **({"directive_type": directive_type} if directive_type else {})}

    # -----------------------------------------------------------------------
    # Wave 35: Maintenance policy tools (ADR-046)
    # -----------------------------------------------------------------------

    _VALID_AUTO_ACTIONS = frozenset({
        "contradiction", "coverage_gap", "stale_cluster", "distillation",
    })

    @mcp.tool(annotations=_MUT)
    async def set_maintenance_policy(
        workspace_id: str,
        autonomy_level: str = "suggest",
        auto_actions: list[str] | None = None,
        max_maintenance_colonies: int = 2,
        daily_maintenance_budget: float = 1.0,
    ) -> dict[str, Any]:
        """Set the self-maintenance autonomy policy for a workspace."""
        from formicos.core.types import AutonomyLevel, MaintenancePolicy  # noqa: PLC0415

        # Validate autonomy level
        valid_levels = {e.value for e in AutonomyLevel}
        if autonomy_level not in valid_levels:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": f"autonomy_level must be one of {sorted(valid_levels)}"},
            ))

        # Validate auto_actions
        actions = auto_actions or []
        invalid = set(actions) - _VALID_AUTO_ACTIONS
        if invalid:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": (
                    f"Invalid auto_actions: {sorted(invalid)}. "
                    f"Valid: {sorted(_VALID_AUTO_ACTIONS)}"
                )},
            ))

        if daily_maintenance_budget <= 0:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": "daily_maintenance_budget must be > 0"},
            ))

        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])

        policy = MaintenancePolicy(
            autonomy_level=AutonomyLevel(autonomy_level),
            auto_actions=actions,
            max_maintenance_colonies=max_maintenance_colonies,
            daily_maintenance_budget=daily_maintenance_budget,
        )

        from datetime import UTC, datetime

        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415

        policy_json = policy.model_dump_json()
        old_raw = ws.config.get("maintenance_policy")
        old_json = str(old_raw) if old_raw is not None else None
        await runtime.emit_and_broadcast(WorkspaceConfigChanged(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            field="maintenance_policy",
            old_value=old_json,
            new_value=policy_json,
        ))
        return {"status": "updated", "policy": policy.model_dump()}

    @mcp.tool(annotations=_RO)
    async def get_maintenance_policy(workspace_id: str) -> dict[str, Any]:
        """Get the current maintenance policy for a workspace."""
        from formicos.core.types import MaintenancePolicy  # noqa: PLC0415

        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])

        raw = ws.config.get("maintenance_policy")
        if raw is None:
            return MaintenancePolicy().model_dump()
        if isinstance(raw, str):
            import json as _json  # noqa: PLC0415
            try:
                return _json.loads(raw)
            except (ValueError, TypeError):
                return MaintenancePolicy().model_dump()
        if isinstance(raw, dict):
            return dict(raw)  # type: ignore[arg-type]
        return MaintenancePolicy().model_dump()

    # -----------------------------------------------------------------------
    # Wave 35 C2: per-workspace composite weight configuration (ADR-044 D4)
    # -----------------------------------------------------------------------

    @mcp.tool(annotations=_MUT)
    async def configure_scoring(
        workspace_id: str,
        semantic: float | None = None,
        thompson: float | None = None,
        freshness: float | None = None,
        status: float | None = None,
        thread: float | None = None,
        cooccurrence: float | None = None,
    ) -> dict[str, Any]:
        """Adjust composite scoring weights for this workspace.

        Weights must sum to 1.0 (+/- 0.001). All values must be >= 0.0 and <= 0.5.
        Omitted values keep their current setting.
        """
        from formicos.surface.knowledge_constants import get_workspace_weights  # noqa: PLC0415

        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])

        current = get_workspace_weights(workspace_id, runtime.projections)
        updates = {
            "semantic": semantic, "thompson": thompson, "freshness": freshness,
            "status": status, "thread": thread, "cooccurrence": cooccurrence,
        }
        new_weights = dict(current)
        for k, v in updates.items():
            if v is not None:
                new_weights[k] = v

        # Validate bounds
        for k, v in new_weights.items():
            if v < 0.0 or v > 0.5:
                return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                    update={"message": f"Weight '{k}' = {v} is out of bounds [0.0, 0.5]"},
                ))

        # Validate sum
        weight_sum = sum(new_weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": f"Weights sum to {weight_sum:.4f}, must be 1.0 (+/- 0.001)"},
            ))

        import json as _json  # noqa: PLC0415
        from datetime import UTC, datetime  # noqa: PLC0415

        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415

        old_raw = ws.config.get("composite_weights")
        old_value_str = _json.dumps(old_raw) if old_raw is not None else None
        await runtime.emit_and_broadcast(WorkspaceConfigChanged(
            seq=0,
            timestamp=datetime.now(UTC),
            address=workspace_id,
            workspace_id=workspace_id,
            field="composite_weights",
            old_value=old_value_str,
            new_value=_json.dumps(new_weights),
        ))
        return {"status": "updated", "weights": new_weights}

    # -----------------------------------------------------------------------
    # Wave 33 B5: MCP resources (5)
    # -----------------------------------------------------------------------

    @mcp.resource("formicos://knowledge/{workspace}")
    async def knowledge_catalog_resource(
        workspace: str,
    ) -> list[dict[str, Any]]:
        """List knowledge entries for a workspace (use '_all' for all workspaces).

        Supports sub_type filtering via workspace format: 'ws-1:bug' filters to
        sub_type='bug'. Plain workspace ID returns all sub-types.
        """
        # Parse optional sub_type filter from workspace param: "ws-1:bug"
        sub_type_filter = ""
        if ":" in workspace:
            workspace, sub_type_filter = workspace.rsplit(":", 1)

        entries: list[dict[str, Any]] = []
        show_all = workspace == "_all"
        for eid, entry in runtime.projections.memory_entries.items():
            if entry.get("status") == "rejected":
                continue
            if not show_all and entry.get("workspace_id") != workspace:
                continue
            if sub_type_filter and entry.get("sub_type") != sub_type_filter:
                continue
            alpha = float(entry.get("conf_alpha", 5.0))
            beta = float(entry.get("conf_beta", 5.0))
            conf = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
            entries.append({
                "id": eid,
                "title": entry.get("title", ""),
                "entry_type": entry.get("entry_type", ""),
                "sub_type": entry.get("sub_type"),
                "confidence": round(conf, 3),
                "domains": entry.get("domains", []),
                "status": entry.get("status", "candidate"),
            })
            if len(entries) >= 50:
                break
        return entries

    @mcp.resource("formicos://knowledge/{entry_id}")
    async def knowledge_entry_resource(entry_id: str) -> dict[str, Any]:
        """Get a single knowledge entry by ID."""
        entry = runtime.projections.memory_entries.get(entry_id)
        if entry is None:
            return {"error": "entry not found"}
        alpha = float(entry.get("conf_alpha", 5.0))
        beta = float(entry.get("conf_beta", 5.0))
        return {
            "id": entry_id,
            "title": entry.get("title", ""),
            "content": entry.get("content", ""),
            "entry_type": entry.get("entry_type", ""),
            "sub_type": entry.get("sub_type"),
            "status": entry.get("status", "candidate"),
            "confidence": round(alpha / (alpha + beta), 3) if (alpha + beta) > 0 else 0.5,
            "domains": entry.get("domains", []),
            "workspace_id": entry.get("workspace_id", ""),
            "thread_id": entry.get("thread_id", ""),
            "created_at": entry.get("created_at", ""),
        }

    @mcp.resource("formicos://threads/{workspace_id}")
    async def workspace_threads_resource(workspace_id: str) -> list[dict[str, Any]]:
        """List threads in a workspace."""
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return []
        return [
            {
                "id": t.id,
                "name": t.name,
                "status": getattr(t, "status", "active"),
                "colony_count": len(t.colonies),
            }
            for t in ws.threads.values()
        ]

    @mcp.resource("formicos://threads/{workspace_id}/{thread_id}")
    async def thread_detail_resource(
        workspace_id: str, thread_id: str,
    ) -> dict[str, Any]:
        """Get thread detail with workflow steps."""
        ws = runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return {"error": "workspace not found"}
        thread = ws.threads.get(thread_id)
        if thread is None:
            return {"error": "thread not found"}
        return {
            "id": thread.id,
            "name": thread.name,
            "status": getattr(thread, "status", "active"),
            "goal": getattr(thread, "goal", ""),
            "workflow_steps": [
                {
                    "index": s.get("step_index", i),
                    "description": s.get("description", ""),
                    "status": s.get("status", "pending"),
                }
                for i, s in enumerate(getattr(thread, "workflow_steps", []))
            ],
            "colonies": [
                {"id": c.id, "status": c.status, "round": c.round_number}
                for c in thread.colonies.values()
            ],
        }

    @mcp.resource("formicos://colonies/{colony_id}")
    async def colony_detail_resource(colony_id: str) -> dict[str, Any]:
        """Get colony status, stats, and outcome."""
        colony = runtime.projections.get_colony(colony_id)
        if colony is None:
            return {"error": "colony not found"}
        return {
            "id": colony.id,
            "status": colony.status,
            "round_number": colony.round_number,
            "max_rounds": colony.max_rounds,
            "convergence": colony.convergence,
            "cost": colony.cost,
            "quality_score": colony.quality_score,
            "skills_extracted": colony.skills_extracted,
            "workspace_id": colony.workspace_id,
            "thread_id": colony.thread_id,
        }

    # -----------------------------------------------------------------------
    # Wave 33 B6: MCP prompts (2)
    # -----------------------------------------------------------------------

    @mcp.prompt("knowledge-query")
    async def knowledge_query_prompt(domain: str, question: str) -> str:
        """Build a prompt with relevant knowledge entries and the user's question."""
        entries: list[dict[str, Any]] = []
        for entry in runtime.projections.memory_entries.values():
            if entry.get("status") == "rejected":
                continue
            if domain and domain in entry.get("domains", []):
                entries.append(entry)
        entries = entries[:5]
        context = "\n".join(
            f"- {e.get('title', 'Untitled')}: {e.get('content', '')[:200]}"
            for e in entries
        )
        return f"Based on this knowledge:\n{context}\n\nAnswer: {question}"

    @mcp.prompt("plan-task")
    async def plan_task_prompt(goal: str, workspace_id: str) -> str:
        """Build a prompt with workspace context for task planning."""
        ws = runtime.projections.workspaces.get(workspace_id)
        thread_lines = ""
        if ws is not None:
            thread_lines = "\n".join(
                f"  - {t.name} ({len(t.colonies)} colonies)"
                for t in ws.threads.values()
            )
        from formicos.surface.template_manager import load_templates as _load  # noqa: PLC0415
        templates = await _load()
        template_lines = "\n".join(
            f"  - {t.name}: {t.description}" for t in templates
        )
        return (
            f"Goal: {goal}\n\n"
            f"Active threads:\n{thread_lines or '  (none)'}\n\n"
            f"Available templates:\n{template_lines or '  (none)'}"
        )

    # -----------------------------------------------------------------------
    # Wave 34 B2: Proactive intelligence briefing resource
    # -----------------------------------------------------------------------

    @mcp.resource("formicos://briefing/{workspace_id}")
    async def briefing_resource(workspace_id: str) -> dict[str, Any]:
        """Get proactive intelligence briefing with insights for a workspace."""
        from formicos.surface.proactive_intelligence import (
            generate_briefing as _gen,  # noqa: PLC0415
        )
        briefing = _gen(workspace_id, runtime.projections)
        return briefing.model_dump()

    # Activate transforms so @mcp.resource() and @mcp.prompt()
    # definitions are automatically exposed as tools.
    try:
        from fastmcp.server.transforms import PromptsAsTools, ResourcesAsTools
        mcp.add_transform(ResourcesAsTools(mcp))
        mcp.add_transform(PromptsAsTools(mcp))
    except ImportError:
        log.debug(
            "mcp.transforms_unavailable",
            reason="FastMCP <3.1 — upgrade for PromptsAsTools/ResourcesAsTools",
        )

    return mcp


__all__ = ["create_mcp_server"]
