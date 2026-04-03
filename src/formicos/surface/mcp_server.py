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
    # Wave 35
    "set_maintenance_policy",
    "get_maintenance_policy",
    "configure_scoring",
    # Wave 73
    "addon_status",
    "toggle_addon",
    "trigger_addon",
    "log_finding",
    "handoff_to_formicos",
    # Wave 75
    "get_task_receipt",
    "search_knowledge",     # Wave 75 Team B
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
    # Wave 73 Track 3: Addon control MCP tools
    # -----------------------------------------------------------------------

    @mcp.tool(annotations=_RO)
    async def addon_status(workspace_id: str = "") -> list[dict[str, Any]]:
        """List installed addons with health status, tool counts, and errors."""
        regs: list[Any] = runtime.addon_registrations or []
        result: list[dict[str, Any]] = []
        for reg in regs:
            manifest = reg.manifest
            if getattr(manifest, "hidden", False):
                continue
            result.append({
                "name": manifest.name,
                "version": getattr(manifest, "version", ""),
                "description": getattr(manifest, "description", ""),
                "status": getattr(reg, "health_status", "unknown"),
                "disabled": getattr(reg, "disabled", False),
                "tool_count": len(getattr(reg, "registered_tools", [])),
                "handler_count": len(getattr(reg, "registered_handlers", [])),
                "total_tool_calls": sum(
                    getattr(reg, "tool_call_counts", {}).values()
                ),
                "last_error": getattr(reg, "last_error", None),
            })
        return result

    @mcp.tool(annotations=_MUT)
    async def toggle_addon(
        addon_name: str,
        disabled: bool,
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Enable or disable an addon. Disabled addons' tools return errors if called."""
        regs: list[Any] = runtime.addon_registrations or []
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return to_mcp_tool_error(KNOWN_ERRORS["ADDON_NOT_FOUND"])
        reg.disabled = disabled
        return {"addon": addon_name, "disabled": reg.disabled}

    @mcp.tool(annotations=_MUT)
    async def trigger_addon(
        addon_name: str,
        handler: str,
        inputs: str = "",
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Trigger an addon handler (e.g., reindex). Same as the REST trigger endpoint."""
        import inspect as _inspect  # noqa: PLC0415

        from formicos.surface.addon_loader import (
            _resolve_handler,  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]
        )

        regs: list[Any] = runtime.addon_registrations or []
        reg = next(
            (r for r in regs if r.manifest.name == addon_name), None,
        )
        if reg is None:
            return to_mcp_tool_error(KNOWN_ERRORS["ADDON_NOT_FOUND"])
        if getattr(reg, "disabled", False):
            return to_mcp_tool_error(KNOWN_ERRORS["ADDON_NOT_FOUND"].model_copy(
                update={"message": f"Addon '{addon_name}' is currently disabled"},
            ))

        try:
            handler_fn = _resolve_handler(addon_name, handler)
        except (ValueError, AttributeError) as exc:
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_PARAMETER"].model_copy(
                update={"message": str(exc)},
            ))

        import json as _json2  # noqa: PLC0415
        parsed_inputs: dict[str, Any] = {}
        if inputs:
            try:
                parsed_inputs = _json2.loads(inputs)
            except (ValueError, TypeError):
                parsed_inputs = {}

        try:
            sig = _inspect.signature(handler_fn)
            accepts_ctx = "runtime_context" in sig.parameters
            positional_params = [
                p for p in sig.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.name not in ("self", "cls", "runtime_context")
            ]
            has_tool_args = len(positional_params) >= 3
        except (ValueError, TypeError):
            accepts_ctx = False
            has_tool_args = False

        try:
            if has_tool_args and accepts_ctx:
                result = await handler_fn(
                    parsed_inputs, workspace_id, "",
                    runtime_context=reg.runtime_context,
                )
            elif has_tool_args:
                result = await handler_fn(parsed_inputs, workspace_id, "")
            elif accepts_ctx:
                result = await handler_fn(
                    runtime_context=reg.runtime_context,
                )
            else:
                result = await handler_fn()
        except Exception as exc:  # noqa: BLE001
            return to_mcp_tool_error(KNOWN_ERRORS["INVALID_STATE"].model_copy(
                update={"message": f"Trigger failed: {exc}"},
            ))

        return {"addon": addon_name, "handler": handler, "result": str(result)}

    # -----------------------------------------------------------------------
    # Wave 73 Track 1e-f: Mutating MCP tools (log_finding, handoff_to_formicos)
    # -----------------------------------------------------------------------

    @mcp.tool(annotations=_MUT)
    async def log_finding(
        title: str,
        content: str,
        domains: str = "",
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Record a developer discovery as a knowledge entry.

        Creates a knowledge entry at 'candidate' status for operator review.
        Domains: comma-separated list (e.g., "auth,security").
        """
        from datetime import UTC, datetime  # noqa: PLC0415
        from uuid import uuid4  # noqa: PLC0415

        from formicos.core.events import MemoryEntryCreated  # noqa: PLC0415

        # Resolve workspace
        if not workspace_id:
            ws_ids = list(runtime.projections.workspaces.keys())
            if not ws_ids:
                return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])
            workspace_id = ws_ids[0]

        domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else []
        entry_id = f"entry-{uuid4().hex[:12]}"
        now = datetime.now(UTC)

        entry_dict: dict[str, Any] = {
            "id": entry_id,
            "entry_id": entry_id,
            "title": title,
            "content": content,
            "entry_type": "experience",
            "sub_type": "learning",
            "category": "experience",
            "domains": domain_list,
            "status": "candidate",
            "conf_alpha": 5.0,
            "conf_beta": 5.0,
            "decay_class": "stable",
            "created_at": now.isoformat(),
            "created_by": "developer_mcp",
            "workspace_id": workspace_id,
            "thread_id": "",
            "tool_refs": [],
            "confidence": 0.5,
        }

        await runtime.emit_and_broadcast(MemoryEntryCreated(
            seq=0, timestamp=now, address=workspace_id,
            entry=entry_dict, workspace_id=workspace_id,
        ))

        return {
            "status": "recorded",
            "entry_id": entry_id,
            "title": title,
            "domains": domain_list,
            "review_status": "candidate",
            "_next_actions": ["approve", "get_status"],
        }

    @mcp.tool(annotations=_MUT)
    async def handoff_to_formicos(
        task: str,
        context: str,
        what_was_tried: str = "",
        files: str = "",
        workspace_id: str = "",
    ) -> dict[str, Any]:
        """Hand off work from the developer to FormicOS.

        Creates a thread and spawns a colony with the developer's full context
        pre-loaded so the colony doesn't repeat failed approaches.
        """
        from formicos.surface.self_maintenance import estimate_blast_radius  # noqa: PLC0415

        # Resolve workspace
        if not workspace_id:
            ws_ids = list(runtime.projections.workspaces.keys())
            if not ws_ids:
                return to_mcp_tool_error(KNOWN_ERRORS["WORKSPACE_NOT_FOUND"])
            workspace_id = ws_ids[0]

        # Build enriched task
        sections = [f"## Task\n{task}"]
        if context:
            sections.append(f"## Developer Context\n{context}")
        if what_was_tried:
            sections.append(f"## What Was Already Tried\n{what_was_tried}")
        if files:
            sections.append(f"## Relevant Files\n{files}")
        enriched_task = "\n\n".join(sections)

        # Suggest team and estimate blast radius
        suggestions = await runtime.suggest_team(task)
        br = estimate_blast_radius(task)

        # Pick castes from suggestion
        from formicos.core.types import CasteSlot  # noqa: PLC0415
        castes: list[CasteSlot] = []
        if suggestions:
            for s in suggestions[:3]:
                castes.append(CasteSlot(
                    caste=s.get("caste", "coder"),
                    count=s.get("count", 1),
                ))
        if not castes:
            castes = [CasteSlot(caste="coder", count=1)]

        # Create thread
        thread_name = f"handoff-{task[:40].replace(' ', '-').lower()}"
        thread_id = await runtime.create_thread(workspace_id, thread_name)

        # Spawn colony
        colony_id = await runtime.spawn_colony(
            workspace_id, thread_id, enriched_task, castes,
        )

        # Start colony in background
        if runtime.colony_manager is not None:
            asyncio.create_task(
                runtime.colony_manager.start_colony(colony_id),
            )

        return {
            "status": "handed_off",
            "colony_id": colony_id,
            "thread_id": thread_id,
            "workspace_id": workspace_id,
            "task": task,
            "blast_radius": {"level": br.level, "score": br.score},
            "_next_actions": ["get_status", "chat_colony"],
            "_context": {"colony_id": colony_id, "workspace_id": workspace_id},
        }

    # -----------------------------------------------------------------------
    # Wave 75: Task receipt tool
    # -----------------------------------------------------------------------

    @mcp.tool(annotations=_RO)
    async def get_task_receipt(task_id: str) -> dict[str, Any]:
        """Get a deterministic receipt for a completed A2A task.

        Returns structured receipt with cost, token totals, quality score,
        transcript hash, and revenue share eligibility.
        """
        from formicos.surface.task_receipts import build_receipt as _build_receipt  # noqa: PLC0415

        receipt = _build_receipt(runtime, task_id)
        if receipt is None:
            return to_mcp_tool_error(KNOWN_ERRORS["TASK_NOT_FOUND"])
        return receipt

    # -----------------------------------------------------------------------
    # Wave 75 B4: retrieval-backed knowledge search
    # -----------------------------------------------------------------------

    @mcp.tool(annotations=_RO)
    async def search_knowledge(
        query: str, workspace_id: str = "", top_k: int = 5,
    ) -> str:
        """Search institutional memory using the full retrieval pipeline.

        Uses semantic search, Thompson sampling, freshness, co-occurrence,
        and graph proximity signals. Returns ranked results as markdown.
        """
        top_k = max(1, min(top_k, 8))

        # Default to first workspace if omitted
        if not workspace_id:
            ws_ids = list(runtime.projections.workspaces.keys())
            workspace_id = ws_ids[0] if ws_ids else ""

        catalog = getattr(runtime, "knowledge_catalog", None)
        if catalog is None:
            return "Knowledge catalog not available."

        try:
            results = await catalog.search(
                query, workspace_id=workspace_id, top_k=top_k,
            )
        except Exception:  # noqa: BLE001
            return f"Search failed for query: {query}"

        if not results:
            return f"No knowledge entries found matching: {query}"

        parts = [f"# Knowledge Search: {query}\n"]
        for r in results:
            title = r.get("title", "Untitled")
            content = str(r.get("content", ""))[:400]
            status = r.get("status", "?")
            domains = r.get("domains", [])
            score = r.get("composite_score", r.get("score", 0))
            alpha = float(r.get("conf_alpha", r.get("alpha", 5.0)))
            beta = float(r.get("conf_beta", r.get("beta", 5.0)))
            conf = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5

            parts.append(f"## {title} (confidence: {conf:.0%}, score: {score:.3f})")
            parts.append(content)
            meta = f"Status: {status}"
            if domains:
                meta += f" | Domains: {', '.join(str(d) for d in domains)}"
            parts.append(meta)
            parts.append("")

        return "\n".join(parts)

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
    # Wave 75 B5: shared knowledge result formatter
    # -----------------------------------------------------------------------

    def _format_knowledge_results(
        query: str, results: list[dict[str, Any]],
    ) -> str:
        parts = [f"# Knowledge Context: {query}\n"]
        for r in results:
            title = r.get("title", "Untitled")
            alpha = float(r.get("conf_alpha", r.get("alpha", 5.0)))
            beta = float(r.get("conf_beta", r.get("beta", 5.0)))
            conf = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
            content_text = str(r.get("content", ""))[:500]
            entry_domains = r.get("domains", [])
            parts.append(f"## {title} (confidence: {conf:.0%})")
            parts.append(content_text)
            meta = f"Status: {r.get('status', '?')}"
            if entry_domains:
                meta += f" | Domains: {', '.join(str(d) for d in entry_domains)}"
            parts.append(meta)
            parts.append("")
        return "\n".join(parts)

    # -----------------------------------------------------------------------
    # Wave 33 B6: MCP prompts (2)
    # -----------------------------------------------------------------------

    @mcp.prompt("knowledge-query")
    async def knowledge_query_prompt(domain: str, question: str) -> str:
        """Build a prompt with relevant knowledge entries and the user's question.

        Uses the real retrieval pipeline (semantic + Thompson sampling + freshness).
        """
        catalog = getattr(runtime, "knowledge_catalog", None)
        if catalog is not None:
            # Default to first workspace
            ws_ids = list(runtime.projections.workspaces.keys())
            ws_id = ws_ids[0] if ws_ids else ""
            try:
                results = await catalog.search(
                    f"{domain} {question}", workspace_id=ws_id, top_k=5,
                )
                context = "\n".join(
                    f"- {r.get('title', 'Untitled')}: {str(r.get('content', ''))[:200]}"
                    for r in results
                )
                return f"Based on this knowledge:\n{context}\n\nAnswer: {question}"
            except Exception:  # noqa: BLE001
                pass
        # Fallback: domain filter over projections
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
    # Wave 73 Track 1a-d: MCP prompts (4 read-only)
    # -----------------------------------------------------------------------

    @mcp.prompt("morning-status")
    async def morning_status_prompt(workspace_id: str) -> str:
        """Get a complete status briefing for a workspace.

        Composes: operational summary, project plan, autonomy score,
        recent colony outcomes, pending actions. Returns natural-language
        markdown suitable for starting a work session.
        """
        from formicos.surface.action_queue import (  # noqa: PLC0415
            list_actions as _list_actions,
        )
        from formicos.surface.operations_coordinator import (  # noqa: PLC0415
            build_operations_summary as _build_ops,
        )
        from formicos.surface.project_plan import (  # noqa: PLC0415
            load_project_plan as _load_plan,
        )
        from formicos.surface.project_plan import (
            render_for_queen as _render_plan,
        )
        from formicos.surface.self_maintenance import (  # noqa: PLC0415
            compute_autonomy_score as _autonomy,
        )

        data_dir = runtime.settings.system.data_dir

        # 1. Operational summary
        ops = _build_ops(data_dir, workspace_id, runtime.projections)

        # 2. Project plan
        plan = _load_plan(data_dir)
        plan_text = _render_plan(plan) or "No project plan set."

        # 3. Autonomy score
        auto = _autonomy(workspace_id, runtime.projections)

        # 4. Pending actions
        pending = _list_actions(
            data_dir, workspace_id, status="pending_review", limit=10,
        )
        pending_actions = pending.get("actions", [])

        # 5. Recent colony outcomes
        ws = runtime.projections.workspaces.get(workspace_id)
        recent_colonies: list[dict[str, Any]] = []
        if ws is not None:
            for thread in ws.threads.values():
                for colony in thread.colonies.values():
                    if colony.status in ("completed", "failed"):
                        recent_colonies.append({
                            "id": colony.id,
                            "status": colony.status,
                            "cost": colony.cost,
                            "round": colony.round_number,
                        })
            recent_colonies = recent_colonies[-5:]

        # Compose
        ws_name = ws.name if ws is not None else workspace_id
        parts = [f"# Status Briefing — {ws_name}\n"]

        parts.append("## Operational Health")
        parts.append(
            f"{ops.get('pending_review_count', 0)} actions pending review | "
            f"{len(ops.get('continuation_candidates', []))} continuations available"
        )
        parts.append(
            f"Autonomy: {auto.grade} ({auto.score}/100)"
            f"{f' — {auto.recommendation}' if auto.recommendation else ''}"
        )

        parts.append(f"\n## Project Plan\n{plan_text}")

        if pending_actions:
            parts.append("\n## Pending Actions")
            for a in pending_actions:
                parts.append(f"- [{a.get('kind', '?')}] {a.get('title', 'Untitled')}")
        else:
            parts.append("\n## Pending Actions\nNone.")

        if recent_colonies:
            parts.append("\n## Recent Colony Outcomes")
            for c in recent_colonies:
                parts.append(f"- {c['id']}: {c['status']} (${c['cost']:.2f})")
        else:
            parts.append("\n## Recent Colony Outcomes\nNone.")

        candidates: list[Any] = ops.get("continuation_candidates", [])
        if candidates:
            parts.append("\n## Continuation Candidates")
            for cand in candidates:
                parts.append(f"- {cand}")

        return "\n".join(parts)

    @mcp.prompt("delegate-task")
    async def delegate_task_prompt(
        task: str,
        context: str = "",
        workspace_id: str = "",
    ) -> str:
        """Plan a colony delegation for a task.

        Resolves workspace, suggests a team, estimates blast radius.
        Returns a delegation plan — the developer confirms before spawning.
        """
        from formicos.surface.self_maintenance import (  # noqa: PLC0415
            estimate_blast_radius as _blast,
        )

        if not workspace_id:
            ws_ids = list(runtime.projections.workspaces.keys())
            workspace_id = ws_ids[0] if ws_ids else "default"

        suggestions = await runtime.suggest_team(task)
        br = _blast(task)

        parts = ["# Delegation Plan\n"]
        parts.append(f"**Task:** {task}")
        parts.append(f"**Workspace:** {workspace_id}")
        if context:
            parts.append(f"**Context:** {context}")

        if suggestions:
            parts.append("\n## Suggested Team")
            for s in suggestions:
                reason = s.get("reason", "")
                line = f"- {s.get('caste', '?')} ×{s.get('count', 1)}"
                if reason:
                    line += f": {reason}"
                parts.append(line)

        parts.append(f"\n## Blast Radius: {br.level} ({br.score:.1f})")
        for f in br.factors:
            parts.append(f"- {f}")

        castes_json = ", ".join(
            f'"{s.get("caste", "coder")}"' for s in (suggestions or [{"caste": "coder"}])
        )
        parts.append("\n## Next Steps")
        parts.append("To spawn this colony, call the `spawn_colony` tool with:")
        parts.append(f"- workspace_id: {workspace_id}")
        parts.append("- thread_id: (create a new thread or use an existing one)")
        parts.append(f"- task: {task}")
        parts.append(f"- castes: [{castes_json}]")

        return "\n".join(parts)

    @mcp.prompt("review-overnight-work")
    async def review_overnight_work_prompt(workspace_id: str) -> str:
        """Review what happened while you were away.

        Shows: recently executed actions, pending review items, new knowledge
        entries, colony outcomes from last 24h.
        """
        from formicos.surface.action_queue import (  # noqa: PLC0415
            list_actions as _list_actions,
        )

        data_dir = runtime.settings.system.data_dir

        executed = _list_actions(
            data_dir, workspace_id, status="executed", limit=20,
        )
        pending = _list_actions(
            data_dir, workspace_id, status="pending_review", limit=20,
        )

        # Recent knowledge entries
        recent_entries: list[dict[str, Any]] = []
        for eid, entry in runtime.projections.memory_entries.items():
            if entry.get("workspace_id") != workspace_id:
                continue
            if entry.get("status") == "rejected":
                continue
            recent_entries.append({"id": eid, **entry})
        recent_entries.sort(
            key=lambda e: e.get("created_at", ""), reverse=True,
        )
        recent_entries = recent_entries[:10]

        parts = [f"# Overnight Review — {workspace_id}\n"]

        # Executed actions
        exec_actions = executed.get("actions", [])
        if exec_actions:
            parts.append("## Recently Executed Actions")
            for a in exec_actions:
                parts.append(f"- [{a.get('kind', '?')}] {a.get('title', 'Untitled')}")
        else:
            parts.append("## Recently Executed Actions\nNone.")

        # Pending review
        pend_actions = pending.get("actions", [])
        if pend_actions:
            parts.append("\n## Pending Review")
            for a in pend_actions:
                parts.append(f"- [{a.get('kind', '?')}] {a.get('title', 'Untitled')}")
        else:
            parts.append("\n## Pending Review\nNone.")

        # New knowledge
        if recent_entries:
            parts.append("\n## New Knowledge Entries")
            for e in recent_entries:
                alpha = float(e.get("conf_alpha", 5.0))
                beta = float(e.get("conf_beta", 5.0))
                conf = alpha / (alpha + beta) if (alpha + beta) > 0 else 0.5
                parts.append(
                    f"- **{e.get('title', 'Untitled')}** "
                    f"({e.get('status', '?')}, conf: {conf:.0%})"
                )
        else:
            parts.append("\n## New Knowledge Entries\nNone.")

        return "\n".join(parts)

    @mcp.prompt("knowledge-for-context")
    async def knowledge_for_context_prompt(
        query: str,
        workspace_id: str = "",
    ) -> str:
        """Search institutional memory and return relevant entries as prose.

        Uses the real retrieval pipeline (semantic + Thompson sampling +
        freshness + co-occurrence + graph proximity). Returns top-5 entries
        formatted for context injection.
        """
        # Default to first workspace if omitted
        if not workspace_id:
            ws_ids = list(runtime.projections.workspaces.keys())
            workspace_id = ws_ids[0] if ws_ids else ""

        catalog = getattr(runtime, "knowledge_catalog", None)
        if catalog is not None:
            try:
                results = await catalog.search(
                    query, workspace_id=workspace_id, top_k=5,
                )
                if results:
                    return _format_knowledge_results(query, results)
            except Exception:  # noqa: BLE001
                log.warning("knowledge_for_context.retrieval_failed", query=query)

        return f"No knowledge entries found matching: {query}"

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

    # -----------------------------------------------------------------------
    # Wave 73 Track 2: MCP resources (3 new)
    # -----------------------------------------------------------------------

    @mcp.resource("formicos://plan")
    async def plan_resource() -> str:
        """Project plan formatted as markdown. Global to the FormicOS instance."""
        from formicos.surface.project_plan import (  # noqa: PLC0415
            load_project_plan as _load_plan,
        )
        from formicos.surface.project_plan import (
            render_for_queen as _render_plan,
        )
        data_dir = runtime.settings.system.data_dir
        plan = _load_plan(data_dir)
        rendered = _render_plan(plan)
        return rendered or "No project plan configured."

    @mcp.resource("formicos://procedures/{workspace_id}")
    async def procedures_resource(workspace_id: str) -> str:
        """Operating procedures for a workspace, formatted as markdown."""
        from formicos.surface.operational_state import (  # noqa: PLC0415
            render_procedures_for_queen as _render_procs,
        )
        data_dir = runtime.settings.system.data_dir
        text = _render_procs(data_dir, workspace_id)
        return text or "No operating procedures configured."

    @mcp.resource("formicos://journal/{workspace_id}")
    async def journal_resource(workspace_id: str) -> str:
        """Recent journal entries for a workspace, formatted as markdown."""
        from formicos.surface.operational_state import (  # noqa: PLC0415
            render_journal_for_queen as _render_journal,
        )
        data_dir = runtime.settings.system.data_dir
        text = _render_journal(data_dir, workspace_id, max_lines=30)
        return text or "No journal entries yet."

    # -----------------------------------------------------------------------
    # Wave 75 Track 5: Economic MCP resources
    # -----------------------------------------------------------------------

    @mcp.resource("formicos://billing")
    async def billing_resource() -> str:
        """Current-period billing status for this FormicOS instance.

        Reads the event store directly (not projections). Total tokens
        includes reasoning tokens per METERING.md specification.
        """
        from formicos.surface.metering import (  # noqa: PLC0415
            aggregate_period as _agg,
        )
        from formicos.surface.metering import (
            current_period as _cur,
        )
        from formicos.surface.metering import (
            format_billing_status as _fmt,
        )

        event_store = getattr(runtime, "_event_store", None)
        if event_store is None:
            return "Billing data unavailable (event store not accessible)."
        start, end = _cur()
        agg = await _agg(event_store, start, end)
        return _fmt(agg)

    @mcp.resource("formicos://receipt/{task_id}")
    async def receipt_resource(task_id: str) -> str:
        """Get a deterministic receipt for a completed colony/task.

        Returns cost, quality, rounds, tokens, and status.
        """
        colony = runtime.projections.colonies.get(task_id)
        if colony is None:
            return f"No colony found with ID: {task_id}"

        budget = colony.budget_truth
        total_tokens = (
            budget.total_input_tokens
            + budget.total_output_tokens
            + budget.total_reasoning_tokens
        )
        quality_str = (
            f"{colony.quality_score:.0%}"
            if colony.quality_score > 0
            else "pending"
        )
        lines = [
            f"# Task Receipt — {colony.display_name or task_id}",
            "",
            f"**Task ID:** {task_id}",
            f"**Status:** {colony.status}",
            f"**Rounds:** {colony.round_number}/{colony.max_rounds}",
            f"**Quality:** {quality_str}",
            f"**Total Cost:** ${budget.total_cost:.4f}",
            f"**Total Tokens:** {total_tokens:,}",
            f"  - Input: {budget.total_input_tokens:,}",
            f"  - Output: {budget.total_output_tokens:,}",
            f"  - Reasoning: {budget.total_reasoning_tokens:,}",
            f"  - Cache-read: {budget.total_cache_read_tokens:,} (informational)",
            "",
        ]
        if budget.model_usage:
            lines.append("**Models Used:**")
            for model, stats in sorted(budget.model_usage.items()):
                m_total = (
                    int(stats.get("input_tokens", 0))
                    + int(stats.get("output_tokens", 0))
                    + int(stats.get("reasoning_tokens", 0))
                )
                cost = float(stats.get("cost", 0))
                lines.append(
                    f"  - {model}: {m_total:,} tokens, ${cost:.4f}"
                )
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Wave 75 Track 6: Economic MCP prompts
    # -----------------------------------------------------------------------

    @mcp.prompt("economic-status")
    async def economic_status_prompt() -> str:
        """Get a complete economic overview of this FormicOS instance.

        Shows billing status, token breakdown, computed fee, and tier status.
        Use this to understand current usage costs and billing position.
        """
        from formicos.surface.metering import (  # noqa: PLC0415
            aggregate_period as _agg,
        )
        from formicos.surface.metering import (
            current_period as _cur,
        )
        from formicos.surface.metering import (
            format_billing_status as _fmt,
        )
        event_store = getattr(runtime, "_event_store", None)
        if event_store is None:
            return "Billing data unavailable (event store not accessible)."
        start, end = _cur()
        agg = await _agg(event_store, start, end)
        status = _fmt(agg)
        return (
            "You are reviewing the economic status of a FormicOS instance.\n\n"
            + status
            + "\n\nSummarize the billing position and flag anything notable "
            "(high spend, approaching tier boundaries, cost concentration)."
        )

    @mcp.prompt("review-task-receipt")
    async def review_task_receipt_prompt(task_id: str) -> str:
        """Review the economic receipt for a completed colony/task.

        Shows cost breakdown, quality score, token usage, and models.
        """
        colony = runtime.projections.colonies.get(task_id)
        if colony is None:
            return f"No colony found with ID: {task_id}. Check the task ID."

        budget = colony.budget_truth
        total_tokens = (
            budget.total_input_tokens
            + budget.total_output_tokens
            + budget.total_reasoning_tokens
        )
        return (
            f"Review this task receipt and assess value-for-cost:\n\n"
            f"Task: {colony.display_name or task_id}\n"
            f"Status: {colony.status}\n"
            f"Rounds: {colony.round_number}/{colony.max_rounds}\n"
            f"Quality: {colony.quality_score:.0%}\n"
            f"Cost: ${budget.total_cost:.4f}\n"
            f"Tokens: {total_tokens:,} "
            f"(input: {budget.total_input_tokens:,}, "
            f"output: {budget.total_output_tokens:,}, "
            f"reasoning: {budget.total_reasoning_tokens:,})\n\n"
            f"Assess whether cost was proportionate to outcome quality "
            f"and suggest optimization if applicable."
        )

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
