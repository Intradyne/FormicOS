"""Queen tool dispatcher — extracted from queen_runtime.py.

Contains tool specs, dispatch routing, and all tool handler methods
except archive_thread and define_workflow_steps (delegated to queen_thread).
"""
# pyright: reportUnknownVariableType=false

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from formicos.core.events import (
    ColonyRedirected,
    ThreadGoalSet,
    ThreadStatusChanged,
)
from formicos.core.types import CasteSlot, InputSource, RedirectTrigger, SubcasteTier
from formicos.surface.config_validator import validate_config_update
from formicos.surface.metacognition import format_nudge, should_nudge
from formicos.surface.queen_shared import (
    PendingConfigProposal,
    _is_experimentable,  # pyright: ignore[reportPrivateUsage]
    _now,  # pyright: ignore[reportPrivateUsage]
)
from formicos.surface.template_manager import load_all_templates

if TYPE_CHECKING:
    from formicos.surface.runtime import Runtime

log = structlog.get_logger()


def _log_task_exception(task: asyncio.Task[Any]) -> None:
    """Error callback for fire-and-forget tasks."""
    if not task.cancelled() and task.exception() is not None:
        log.error(
            "fire_and_forget_failed",
            task_name=task.get_name(),
            error=str(task.exception()),
        )


def build_colony_preview(
    task: str,
    caste_slots: list[CasteSlot],
    strategy: str,
    max_rounds: int,
    budget_limit: float,
    fast_path: bool = False,
    target_files: list[str] | None = None,
) -> dict[str, Any]:
    """Build structured colony preview metadata without dispatching.

    Shared by QueenToolDispatcher._preview_spawn_colony and the REST
    preview-colony endpoint (Wave 48).
    """
    _target_files = target_files or []
    team_desc = ", ".join(
        f"{s.caste}({s.tier.value})" + (f"x{s.count}" if s.count > 1 else "")
        for s in caste_slots
    )
    lines = [
        "[PREVIEW — no colony dispatched]",
        f"Task: {task[:200]}",
        f"Team: {team_desc}",
        f"Strategy: {strategy}",
        f"Rounds: {max_rounds}, Budget: ${budget_limit:.2f}",
    ]
    if fast_path:
        lines.append("Mode: fast_path (skips pheromone/convergence overhead)")
    if _target_files:
        lines.append(f"Target files: {', '.join(_target_files[:5])}")

    return {
        # Internal keys (not part of frontend contract):
        "summary": "\n".join(lines),
        "preview": True,
        # Frontend PreviewCardMeta shape (camelCase):
        "task": task,
        "team": [
            {"caste": s.caste, "tier": s.tier.value, "count": s.count}
            for s in caste_slots
        ],
        "strategy": strategy,
        "maxRounds": max_rounds,
        "budgetLimit": budget_limit,
        "estimatedCost": budget_limit,
        "fastPath": fast_path,
        "targetFiles": _target_files[:10] if _target_files else [],
    }


# Sentinel returned for tools that must be handled by the thread manager.
DELEGATE_THREAD = ("__delegate__", None)


def _parse_caste_slots(raw_castes: list[Any]) -> list[CasteSlot]:
    """Parse raw caste input (strings or dicts) into CasteSlot objects.

    Accepts both ``["coder"]`` and ``[{"caste": "coder", "tier": "heavy"}]``.
    Falls back to ``[CasteSlot(caste="coder")]`` when input is empty.
    """
    caste_slots: list[CasteSlot] = []
    for entry in raw_castes:
        if isinstance(entry, str):
            caste_slots.append(CasteSlot(caste=entry))
        elif isinstance(entry, dict):
            d: dict[str, Any] = entry
            tier_str = str(d.get("tier", "standard"))
            try:
                tier = SubcasteTier(tier_str)
            except ValueError:
                tier = SubcasteTier.standard
            caste_slots.append(CasteSlot(
                caste=str(d.get("caste", "coder")),
                tier=tier,
                count=int(d.get("count", 1)),
            ))
    if not caste_slots:
        caste_slots = [CasteSlot(caste="coder")]
    return caste_slots


class QueenToolDispatcher:
    """Handles Queen tool specs, dispatch, and all non-thread tool handlers.

    Extracted from QueenAgent to reduce queen_runtime.py size.
    """

    # Class-level constants shared with queen_runtime note helpers
    _OUTPUT_TRUNCATE = 4000
    _WS_FILE_ALLOWED_EXT = {".md", ".txt", ".json", ".yaml", ".yml", ".csv"}
    _WS_FILE_MAX_BYTES = 1 * 1024 * 1024  # 1 MB
    _MAX_NOTES = 50
    _MAX_NOTE_CHARS = 500
    _INJECT_NOTES = 10

    def __init__(
        self,
        runtime: Runtime,
        *,
        nudge_cooldowns: dict[str, float] | None = None,
    ) -> None:
        self._runtime = runtime
        # Thread-scoped pending config proposals (one per thread, with TTL)
        self._pending_proposals: dict[str, PendingConfigProposal] = {}
        # Shared reference to nudge cooldown state (owned by QueenAgent)
        self._nudge_cooldowns: dict[str, float] = (
            nudge_cooldowns if nudge_cooldowns is not None else {}
        )

    def _find_colony(self, colony_id: str) -> Any:
        """Look up a colony by ID, falling back to display_name substring match."""
        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            lower = colony_id.lower()
            for c in self._runtime.projections.colonies.values():
                if c.display_name and lower in c.display_name.lower():
                    return c
        return colony

    # ------------------------------------------------------------------ #
    # Tool specs                                                          #
    # ------------------------------------------------------------------ #

    def tool_specs(self) -> list[dict[str, Any]]:
        """Define the tools available to the Queen (ADR-030)."""
        return [
            {
                "name": "spawn_colony",
                "description": "Spawn a new worker colony to execute a task.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Clear task description for the colony.",
                        },
                        "castes": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "caste": {
                                        "type": "string",
                                        "description": (
                                            "Caste name: coder, reviewer,"
                                            " researcher, or archivist."
                                        ),
                                    },
                                    "tier": {
                                        "type": "string",
                                        "enum": [
                                            "light", "standard",
                                            "heavy", "flash",
                                        ],
                                        "description": (
                                            "Compute tier. light=fast/cheap,"
                                            " standard=balanced,"
                                            " heavy=max capability."
                                        ),
                                    },
                                    "count": {
                                        "type": "integer",
                                        "description": (
                                            "Number of agents of this"
                                            " caste (default 1)."
                                        ),
                                    },
                                },
                                "required": ["caste"],
                            },
                            "description": (
                                "Team composition: caste slots"
                                " with optional tier and count."
                            ),
                        },
                        "input_from": {
                            "type": "string",
                            "description": (
                                "Colony ID to chain from. The completed "
                                "colony's output becomes seed context."
                            ),
                        },
                        "max_rounds": {
                            "type": "integer",
                            "description": (
                                "Maximum rounds. Trivial: 2-4. "
                                "Moderate: 5-10. Complex: 10-25."
                            ),
                        },
                        "budget_limit": {
                            "type": "number",
                            "description": (
                                "Budget cap in dollars. "
                                "Keep trivial tasks low (0.10-0.50)."
                            ),
                        },
                        "template_id": {
                            "type": "string",
                            "description": (
                                "Template ID from list_templates "
                                "when a template fits the task."
                            ),
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["stigmergic", "sequential"],
                            "description": (
                                "sequential for simple single-agent tasks, "
                                "stigmergic for multi-agent coordination."
                            ),
                        },
                        "step_index": {
                            "type": "integer",
                            "description": (
                                "Workflow step index this colony fulfils "
                                "(-1 or omit if not part of a workflow)."
                            ),
                        },
                        "target_files": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Files the colony should focus on."
                            ),
                        },
                        "fast_path": {
                            "type": "boolean",
                            "description": (
                                "Use fast path for simple single-agent tasks. "
                                "Skips pheromone updates and convergence scoring. "
                                "Best for trivial or single-caste work."
                            ),
                        },
                        "preview": {
                            "type": "boolean",
                            "description": (
                                "If true, return a plan summary without "
                                "actually dispatching the colony."
                            ),
                        },
                    },
                    "required": ["task", "castes"],
                },
            },
            {
                "name": "spawn_parallel",
                "description": (
                    "Spawn multiple colonies organized as a parallel execution plan. "
                    "Tasks are grouped into parallel execution groups. Groups run "
                    "sequentially; tasks within each group run concurrently."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {
                            "type": "string",
                            "description": (
                                "Why these tasks are decomposed this way. "
                                "Reference knowledge gaps and briefing insights."
                            ),
                        },
                        "tasks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "task_id": {
                                        "type": "string",
                                        "description": "Unique identifier for this task.",
                                    },
                                    "task": {
                                        "type": "string",
                                        "description": "Task description for the colony.",
                                    },
                                    "caste": {
                                        "type": "string",
                                        "description": (
                                            "Primary caste: coder, reviewer, "
                                            "researcher, or archivist."
                                        ),
                                    },
                                    "strategy": {
                                        "type": "string",
                                        "enum": ["sequential", "stigmergic"],
                                        "description": "Coordination strategy.",
                                    },
                                    "max_rounds": {
                                        "type": "integer",
                                        "description": "Maximum rounds for this task.",
                                    },
                                    "budget_limit": {
                                        "type": "number",
                                        "description": "Budget cap in dollars.",
                                    },
                                    "depends_on": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "Task IDs that must complete before this task."
                                        ),
                                    },
                                    "input_from": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "Task IDs whose colony output feeds this task."
                                        ),
                                    },
                                },
                                "required": ["task_id", "task", "caste"],
                            },
                            "description": "List of colony tasks to execute.",
                        },
                        "parallel_groups": {
                            "type": "array",
                            "items": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "description": (
                                "Groups of task_ids. Groups execute sequentially; "
                                "tasks within a group execute concurrently."
                            ),
                        },
                        "estimated_total_cost": {
                            "type": "number",
                            "description": "Estimated total cost in dollars.",
                        },
                        "knowledge_gaps": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Domains where the briefing flagged issues.",
                        },
                        "preview": {
                            "type": "boolean",
                            "description": (
                                "If true, validate the plan and return a "
                                "summary without dispatching colonies."
                            ),
                        },
                    },
                    "required": ["reasoning", "tasks", "parallel_groups"],
                },
            },
            {
                "name": "approve_config_change",
                "description": (
                    "Apply a previously proposed config change. "
                    "Only works if a proposal is pending in this thread."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "get_status",
                "description": "Get workspace status including threads and colonies.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {"type": "string", "description": "Workspace identifier"},
                    },
                    "required": ["workspace_id"],
                },
            },
            {
                "name": "kill_colony",
                "description": "Kill a running colony.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {"type": "string", "description": "Colony to kill"},
                    },
                    "required": ["colony_id"],
                },
            },
            {
                "name": "list_templates",
                "description": (
                    "List available colony templates with their "
                    "descriptions and team compositions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
            {
                "name": "inspect_template",
                "description": "Get full details of a specific colony template by ID or name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "template_id": {
                            "type": "string",
                            "description": "Template ID or name to inspect.",
                        },
                    },
                    "required": ["template_id"],
                },
            },
            {
                "name": "inspect_colony",
                "description": "Get detailed status and results of a colony by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "Colony ID to inspect.",
                        },
                    },
                    "required": ["colony_id"],
                },
            },
            {
                "name": "read_workspace_files",
                "description": "List files in the workspace data directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "workspace_id": {
                            "type": "string",
                            "description": "Workspace ID (default: current workspace).",
                        },
                    },
                    "required": [],
                },
            },
            {
                "name": "suggest_config_change",
                "description": (
                    "Propose a configuration change for operator approval. "
                    "Does NOT apply the change — only formats a proposal. "
                    "The operator must approve before any change takes effect."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param_path": {
                            "type": "string",
                            "description": (
                                "Dot-path to the parameter (e.g., "
                                "'castes.coder.temperature', "
                                "'governance.convergence_threshold')."
                            ),
                        },
                        "proposed_value": {
                            "type": "string",
                            "description": "The proposed new value (will be type-coerced).",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this change would improve performance.",
                        },
                    },
                    "required": ["param_path", "proposed_value", "reason"],
                },
            },
            {
                "name": "redirect_colony",
                "description": (
                    "Redirect a running colony to a new goal. "
                    "The colony keeps its team and topology but "
                    "works toward the new goal from the next round."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "Colony to redirect.",
                        },
                        "new_goal": {
                            "type": "string",
                            "description": "Clear reframed goal.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this redirect is needed.",
                        },
                    },
                    "required": ["colony_id", "new_goal", "reason"],
                },
            },
            {
                "name": "escalate_colony",
                "description": (
                    "Escalate a running colony to a higher compute tier "
                    "for remaining rounds. Does not change the team — "
                    "only routes to more capable models."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "Colony to escalate.",
                        },
                        "tier": {
                            "type": "string",
                            "enum": ["standard", "heavy", "max"],
                            "description": (
                                "Target tier: standard (local), "
                                "heavy (Sonnet), max (Opus)."
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why escalation is needed.",
                        },
                    },
                    "required": ["colony_id", "tier", "reason"],
                },
            },
            {
                "name": "read_colony_output",
                "description": (
                    "Read full agent output for a colony round. "
                    "Includes agent caste, model, and tool calls."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "Colony ID to read output from.",
                        },
                        "round_number": {
                            "type": "integer",
                            "description": (
                                "Round number (default: latest completed round)."
                            ),
                        },
                        "agent_id": {
                            "type": "string",
                            "description": (
                                "Specific agent ID (default: all agents)."
                            ),
                        },
                    },
                    "required": ["colony_id"],
                },
            },
            {
                "name": "memory_search",
                "description": (
                    "Search all system knowledge (institutional memory and "
                    "legacy skill bank) for skills and experiences relevant "
                    "to a query. Returns entries with provenance, trust "
                    "status, and confidence scores."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": (
                                "Search query -- task description, tool name, "
                                "error pattern, etc."
                            ),
                        },
                        "entry_type": {
                            "type": "string",
                            "enum": ["skill", "experience", ""],
                            "description": (
                                "Filter by entry type. "
                                "Empty string for both."
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default 5, max 10).",
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "write_workspace_file",
                "description": (
                    "Write a text file to the workspace files directory. "
                    "Allowed extensions: .md, .txt, .json, .yaml, .yml, .csv."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "File name (e.g. 'summary.md').",
                        },
                        "content": {
                            "type": "string",
                            "description": "File content to write.",
                        },
                    },
                    "required": ["filename", "content"],
                },
            },
            {
                "name": "queen_note",
                "description": (
                    "Save or list persistent operator-preference notes for this thread. "
                    "Notes survive restarts and are injected into Queen context. "
                    "Notes are scoped to the current thread."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["save", "list"],
                            "description": "'save' to add a note, 'list' to show all.",
                        },
                        "content": {
                            "type": "string",
                            "description": "Note text (required for save, max 500 chars).",
                        },
                    },
                    "required": ["action"],
                },
            },
            # Wave 29: thread management tools
            {
                "name": "set_thread_goal",
                "description": (
                    "Set or update the workflow goal and expected "
                    "outputs for the current thread."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string", "description": "Workflow objective."},
                        "expected_outputs": {
                            "type": "array", "items": {"type": "string"},
                            "description": (
                                "Expected artifact types: code, test, "
                                "document, schema, report."
                            ),
                        },
                    },
                    "required": ["goal"],
                },
            },
            {
                "name": "complete_thread",
                "description": "Mark the current thread's workflow as completed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": "Why the workflow is complete.",
                        },
                    },
                    "required": ["reason"],
                },
            },
            {
                "name": "archive_thread",
                "description": (
                    "Archive a completed thread. Archived threads' "
                    "unpromoted knowledge entries receive a confidence "
                    "decay. Use after complete_thread when the workflow "
                    "is no longer active."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reason": {
                            "type": "string",
                            "description": (
                                "Why the thread is being archived."
                            ),
                        },
                    },
                    "required": ["reason"],
                },
            },
            {
                "name": "query_service",
                "description": (
                    "Query an active service (LLM service colony, "
                    "deterministic maintenance service, or external "
                    "specialist). Available services include "
                    "consolidation:dedup, consolidation:stale_sweep, "
                    "and external:nemoclaw:* specialists (when configured)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "service_type": {
                            "type": "string",
                            "description": "Service name to query.",
                        },
                        "query": {
                            "type": "string",
                            "description": "Query text or command.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds (default 30).",
                        },
                    },
                    "required": ["service_type", "query"],
                },
            },
            # Wave 30 (Track B): workflow step tools
            {
                "name": "define_workflow_steps",
                "description": (
                    "Define declarative workflow steps for the current "
                    "thread. Each step describes work for a colony to fulfil."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "steps": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "description": {
                                        "type": "string",
                                        "description": "What this step accomplishes.",
                                    },
                                    "expected_outputs": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Artifact types produced.",
                                    },
                                    "template_id": {
                                        "type": "string",
                                        "description": "Optional colony template.",
                                    },
                                    "strategy": {
                                        "type": "string",
                                        "enum": ["stigmergic", "sequential"],
                                        "description": "Coordination strategy.",
                                    },
                                    "input_from_step": {
                                        "type": "integer",
                                        "description": (
                                            "Step index whose output seeds this step."
                                        ),
                                    },
                                },
                                "required": ["description"],
                            },
                            "description": "Ordered list of workflow steps.",
                        },
                    },
                    "required": ["steps"],
                },
            },
        ]

    # ------------------------------------------------------------------ #
    # Dispatch                                                            #
    # ------------------------------------------------------------------ #

    async def dispatch(
        self,
        tc: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Execute a single tool call. Returns (result_text, action_record_or_None).

        For ``archive_thread`` and ``define_workflow_steps``, returns
        ``DELEGATE_THREAD`` so the caller can route to the thread manager.
        """
        name = tc.get("name", "")
        inputs = self._runtime.parse_tool_input(tc)
        log.info("queen.tool_call", tool=name, inputs=inputs)

        try:
            # Thread-management tools delegated to caller
            if name in ("archive_thread", "define_workflow_steps"):
                return DELEGATE_THREAD  # type: ignore[return-value]

            if name == "spawn_colony":
                return await self._spawn_colony(inputs, workspace_id, thread_id)

            if name == "spawn_parallel":
                return await self._spawn_parallel(inputs, workspace_id, thread_id)

            if name == "kill_colony":
                colony_id = inputs.get("colony_id", "")
                if not colony_id:
                    return ("Error: colony_id is required", None)
                await self._runtime.kill_colony(colony_id)
                return (
                    f"Colony {colony_id} killed.",
                    {"tool": "kill_colony", "colony_id": colony_id},
                )

            if name == "get_status":
                return self._get_status(inputs, workspace_id)

            if name == "list_templates":
                return await self._list_templates()

            if name == "inspect_template":
                return await self._inspect_template(inputs)

            if name == "inspect_colony":
                return self._inspect_colony(inputs)

            if name == "read_workspace_files":
                return self._read_workspace_files(inputs, workspace_id)

            if name == "suggest_config_change":
                return self._suggest_config_change(inputs, thread_id)

            if name == "approve_config_change":
                return await self._approve_config_change(
                    inputs, workspace_id, thread_id,
                )

            if name == "redirect_colony":
                return await self._redirect_colony(
                    inputs, workspace_id, thread_id,
                )

            if name == "escalate_colony":
                return await self._escalate_colony(inputs)

            if name == "read_colony_output":
                return self._read_colony_output(inputs)

            if name == "memory_search":
                return await self._memory_search(inputs, workspace_id, thread_id)

            if name == "write_workspace_file":
                return self._write_workspace_file(inputs, workspace_id)

            if name == "queen_note":
                return await self._queen_note(inputs, workspace_id, thread_id)

            # Wave 29: thread management + service tools
            if name == "set_thread_goal":
                goal = inputs.get("goal", "")
                expected = inputs.get("expected_outputs", [])
                if not goal:
                    return ("Error: goal is required.", None)
                await self._runtime.emit_and_broadcast(ThreadGoalSet(
                    seq=0, timestamp=_now(),
                    address=f"{workspace_id}/{thread_id}",
                    workspace_id=workspace_id, thread_id=thread_id,
                    goal=goal, expected_outputs=expected,
                ))
                return (f"Thread goal set: {goal}", None)

            if name == "complete_thread":
                reason = inputs.get("reason", "")
                ws = self._runtime.projections.workspaces.get(workspace_id)
                old_status = "active"
                if ws is not None:
                    thread = ws.threads.get(thread_id)
                    if thread is not None:
                        old_status = thread.status
                await self._runtime.emit_and_broadcast(ThreadStatusChanged(
                    seq=0, timestamp=_now(),
                    address=f"{workspace_id}/{thread_id}",
                    workspace_id=workspace_id, thread_id=thread_id,
                    old_status=old_status, new_status="completed", reason=reason,
                ))
                return (f"Thread completed: {reason}", None)

            if name == "query_service":
                stype = inputs.get("service_type", "")
                query_text = inputs.get("query", "")
                timeout = min(inputs.get("timeout", 30), 60)
                if not stype or not query_text:
                    return ("Error: service_type and query are required.", None)
                cm = self._runtime.colony_manager
                if cm is None:
                    return ("Error: service routing not available.", None)
                router = cm.service_router
                try:
                    result = await router.query(
                        service_type=stype, query_text=query_text,
                        sender_colony_id=None, timeout_s=float(timeout),
                    )
                    return (result, None)
                except ValueError as exc:
                    return (f"Error: {exc}", None)
                except TimeoutError as exc:
                    return (f"Error: {exc}", None)

            return (f"Unknown tool: {name}", None)
        except Exception as exc:
            log.exception("queen.tool_error", tool=name)
            return (f"Tool {name} failed: {exc}", None)

    # ------------------------------------------------------------------ #
    # Tool handlers                                                       #
    # ------------------------------------------------------------------ #

    async def _spawn_colony(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        task = inputs.get("task", "")
        raw_castes = inputs.get("castes", ["coder"])
        if not task:
            return ("Error: task is required for spawn_colony", None)
        # Build CasteSlot objects — accept both plain strings and dicts
        caste_slots = _parse_caste_slots(raw_castes)

        # Colony chaining (ADR-033): optional input_from parameter
        input_from = inputs.get("input_from", "")
        input_sources: list[InputSource] | None = None
        if input_from:
            input_sources = [InputSource(type="colony", colony_id=input_from)]

        # Spawn controls (Wave 22 Track A)
        max_rounds = max(1, min(int(inputs.get("max_rounds", 25)), 50))
        budget_limit = max(0.01, min(float(inputs.get("budget_limit", 5.0)), 50.0))
        template_id = str(inputs.get("template_id", ""))
        strategy = str(inputs.get("strategy", "stigmergic"))
        if strategy not in ("stigmergic", "sequential"):
            strategy = "stigmergic"

        # Wave 30 (Track B): optional step_index for workflow steps
        step_index = int(inputs.get("step_index", -1))

        # Wave 41: optional target_files for multi-file coordination
        raw_target_files = inputs.get("target_files", [])
        target_files: list[str] = (
            [str(f) for f in raw_target_files]  # type: ignore[reportUnknownArgumentType]
            if isinstance(raw_target_files, list) else []
        )

        # Wave 47: fast_path and preview flags
        fast_path = bool(inputs.get("fast_path", False))
        preview = bool(inputs.get("preview", False))

        # Preview mode: return plan summary without dispatching
        if preview:
            return self._preview_spawn_colony(
                task=task,
                caste_slots=caste_slots,
                strategy=strategy,
                max_rounds=max_rounds,
                budget_limit=budget_limit,
                fast_path=fast_path,
                target_files=target_files,
            )

        # Wave 43: workspace-level budget check before spawning
        from formicos.surface.runtime import BudgetEnforcer  # noqa: PLC0415

        enforcer = BudgetEnforcer(self._runtime.projections)
        allowed, reason = enforcer.check_spawn_allowed(workspace_id)
        if not allowed:
            return (f"Cannot spawn colony: {reason}", None)

        try:
            colony_id = await self._runtime.spawn_colony(
                workspace_id, thread_id, task, caste_slots,
                strategy=strategy,
                max_rounds=max_rounds,
                budget_limit=budget_limit,
                template_id=template_id,
                input_sources=input_sources,
                step_index=step_index,
                target_files=target_files if target_files else None,
                fast_path=fast_path,
                spawn_source="queen",
            )
        except ValueError as exc:
            return (str(exc), None)
        # Start the colony's round loop
        if self._runtime.colony_manager is not None:
            _start_task = asyncio.create_task(
                self._runtime.colony_manager.start_colony(colony_id),
            )
            _start_task.add_done_callback(_log_task_exception)
        # Decision trace (Wave 25 B3)
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        cat_name, cat = classify_task(task)

        # Expected output types: template > classifier > empty
        expected_outputs: list[str] = []
        template_match = ""
        if template_id:
            try:
                templates = await load_all_templates(
                    projection_templates=self._runtime.projections.templates,
                )
                for t in templates:
                    if t.template_id == template_id:
                        template_match = template_id
                        expected_outputs = getattr(
                            t, "expected_output_types", [],
                        )
                        break
            except Exception:  # noqa: BLE001
                pass
        if not expected_outputs:
            expected_outputs = cat.get("default_outputs", [])

        # Store expected_output_types on projection
        colony_proj = self._runtime.projections.get_colony(colony_id)
        if colony_proj is not None and expected_outputs:
            colony_proj.expected_output_types = expected_outputs

        team_desc = ", ".join(
            f"{s.caste}({s.tier.value})" + (f"x{s.count}" if s.count > 1 else "")
            for s in caste_slots
        )
        trace_lines = [
            f"Colony {colony_id} spawned.",
            f"Classification: {cat_name}",
        ]
        if template_match:
            trace_lines.append(f"Template: {template_match} (matched)")
        trace_lines.append(f"Team: {team_desc}")
        trace_lines.append(
            f"Rounds: {max_rounds}, Budget: ${budget_limit:.2f}, "
            f"Strategy: {strategy}",
        )
        if expected_outputs:
            trace_lines.append(
                f"Expected output: {', '.join(expected_outputs)}",
            )
        spawn_msg = "\n".join(trace_lines)

        # Post-spawn prior work surfacing (Wave 23 B1)
        # This is post-decision — it does not influence the team/round/budget
        # choice already made. It helps the operator see related prior work.
        vector_port = self._runtime.vector_store
        if vector_port is not None:
            try:
                from formicos.core.types import VectorSearchHit  # noqa: PLC0415

                hits: list[VectorSearchHit] = []
                for collection in (workspace_id, "skill_bank_v2"):
                    with contextlib.suppress(Exception):
                        hits.extend(await vector_port.search(
                            collection=collection,
                            query=task,
                            top_k=3,
                        ))
                # Deduplicate by id
                seen: set[str] = set()
                unique: list[VectorSearchHit] = []
                for hit in hits:
                    if hit.id not in seen:
                        seen.add(hit.id)
                        unique.append(hit)
                top = unique[:3]
                if top:
                    lines: list[str] = []
                    for hit in top:
                        source = (
                            hit.metadata.get("source_colony")
                            or hit.metadata.get("source_file")
                            or "unknown"
                        )
                        preview = hit.content[:160].replace("\n", " ")
                        lines.append(f"- {preview} (source: {source})")
                    spawn_msg += "\n\nRelated prior work:\n" + "\n".join(lines)
            except Exception:
                log.debug("queen.prior_work_surfacing_failed", colony_id=colony_id)

        return (spawn_msg, {"tool": "spawn_colony", "colony_id": colony_id})

    def _preview_spawn_colony(
        self,
        task: str,
        caste_slots: list[CasteSlot],
        strategy: str,
        max_rounds: int,
        budget_limit: float,
        fast_path: bool,
        target_files: list[str],
    ) -> tuple[str, dict[str, Any] | None]:
        """Return a preview summary without dispatching the colony."""
        # Wave 50: template-aware preview — check for matching learned template
        matched_tmpl = None
        from formicos.surface.task_classifier import classify_task  # noqa: PLC0415

        cat_name, _ = classify_task(task)
        for tmpl in self._runtime.projections.templates.values():
            if (
                tmpl.learned
                and tmpl.task_category == cat_name
                and tmpl.success_count > 0
            ):
                matched_tmpl = tmpl
                break

        meta = build_colony_preview(
            task=task,
            caste_slots=caste_slots,
            strategy=strategy,
            max_rounds=max_rounds,
            budget_limit=budget_limit,
            fast_path=fast_path,
            target_files=target_files,
        )
        meta["tool"] = "spawn_colony"
        # Wave 50: annotate preview with nested template object (matches fc-preview-card.ts)
        if matched_tmpl is not None:
            meta["template"] = {
                "templateId": matched_tmpl.id,
                "templateName": matched_tmpl.name,
                "learned": matched_tmpl.learned,
                "successCount": matched_tmpl.success_count,
                "failureCount": matched_tmpl.failure_count,
                "useCount": matched_tmpl.use_count,
                "taskCategory": matched_tmpl.task_category,
            }
        return (meta["summary"], meta)

    # ------------------------------------------------------------------ #
    # Parallel colony dispatch (Wave 35 A1)                                #
    # ------------------------------------------------------------------ #

    async def _spawn_parallel(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Validate a DelegationPlan and dispatch colony groups concurrently."""
        from formicos.core.events import ParallelPlanCreated  # noqa: PLC0415
        from formicos.core.types import ColonyTask, DelegationPlan  # noqa: PLC0415

        reasoning = inputs.get("reasoning", "")
        raw_tasks = inputs.get("tasks", [])
        parallel_groups = inputs.get("parallel_groups", [])
        estimated_cost = float(inputs.get("estimated_total_cost", 0.0))
        knowledge_gaps = inputs.get("knowledge_gaps", [])

        # ── Build and validate DelegationPlan ──
        try:
            tasks = [ColonyTask(**t) for t in raw_tasks]
        except Exception as exc:
            log.warning("queen.parallel_plan_invalid_tasks", error=str(exc))
            return (f"Invalid plan tasks: {exc}. Falling back to sequential.", None)

        try:
            plan = DelegationPlan(
                reasoning=reasoning,
                tasks=tasks,
                parallel_groups=parallel_groups,
                estimated_total_cost=estimated_cost,
                knowledge_gaps=knowledge_gaps,
            )
        except Exception as exc:
            log.warning("queen.parallel_plan_invalid", error=str(exc))
            return (f"Invalid plan: {exc}. Falling back to sequential.", None)

        # Validate: all task_ids unique
        task_ids = {t.task_id for t in plan.tasks}
        if len(task_ids) != len(plan.tasks):
            return ("Invalid plan: duplicate task_ids. Falling back to sequential.", None)

        # Validate: parallel_groups cover all task_ids exactly once
        group_ids: list[str] = []
        for group in plan.parallel_groups:
            group_ids.extend(group)
        if set(group_ids) != task_ids or len(group_ids) != len(task_ids):
            return (
                "Invalid plan: parallel_groups must cover all task_ids exactly once. "
                "Falling back to sequential.",
                None,
            )

        # Validate: depends_on references exist
        for t in plan.tasks:
            for dep in t.depends_on:
                if dep not in task_ids:
                    return (
                        f"Invalid plan: task {t.task_id} depends on unknown {dep}. "
                        "Falling back to sequential.",
                        None,
                    )

        # Validate: no circular dependencies (topological sort)
        if not self._validate_dag(plan.tasks):
            return (
                "Invalid plan: circular dependencies detected. "
                "Falling back to sequential.",
                None,
            )

        # Wave 47: preview mode — return validated plan summary without dispatch
        if bool(inputs.get("preview", False)):
            lines = [
                "[PREVIEW — no colonies dispatched]",
                f"Plan: {len(plan.tasks)} tasks in "
                f"{len(plan.parallel_groups)} groups.",
                f"Reasoning: {plan.reasoning[:200]}",
                f"Estimated cost: ${plan.estimated_total_cost:.2f}",
            ]
            for gi, group in enumerate(plan.parallel_groups):
                task_descs = []
                for tid in group:
                    ct = {t.task_id: t for t in plan.tasks}.get(tid)
                    if ct:
                        task_descs.append(f"{ct.task_id} ({ct.caste})")
                lines.append(f"  Group {gi + 1}: {', '.join(task_descs)}")
            if plan.knowledge_gaps:
                lines.append(f"Knowledge gaps: {', '.join(plan.knowledge_gaps)}")
            # Wave 48: structured preview metadata for frontend Review step
            preview_meta: dict[str, Any] = {
                "tool": "spawn_parallel",
                "preview": True,
                "estimated_cost": plan.estimated_total_cost,
                "task_count": len(plan.tasks),
                "group_count": len(plan.parallel_groups),
                "groups": [
                    [tid for tid in group]
                    for group in plan.parallel_groups
                ],
            }
            if plan.knowledge_gaps:
                preview_meta["knowledge_gaps"] = plan.knowledge_gaps
            return (
                "\n".join(lines),
                preview_meta,
            )

        # ── Emit ParallelPlanCreated event ──
        await self._runtime.emit_and_broadcast(ParallelPlanCreated(
            seq=0,
            timestamp=_now(),
            address=f"{workspace_id}/{thread_id}",
            thread_id=thread_id,
            workspace_id=workspace_id,
            plan=plan.model_dump(),
            parallel_groups=plan.parallel_groups,
            reasoning=plan.reasoning,
            knowledge_gaps=plan.knowledge_gaps,
            estimated_cost=plan.estimated_total_cost,
        ))

        # ── Dispatch groups sequentially, tasks within each group concurrently ──
        task_map = {t.task_id: t for t in plan.tasks}
        # Maps task_id -> colony_id (populated as colonies are spawned)
        colony_map: dict[str, str] = {}
        all_colony_ids: list[str] = []
        result_lines = [
            f"Parallel plan created: {len(plan.tasks)} tasks in "
            f"{len(plan.parallel_groups)} groups.",
            f"Reasoning: {plan.reasoning[:200]}",
        ]

        for group_idx, group in enumerate(plan.parallel_groups):
            group_tasks = [task_map[tid] for tid in group]

            async def _spawn_one(ct: ColonyTask) -> tuple[str, str]:
                """Spawn a single colony for a ColonyTask, return (task_id, colony_id)."""
                caste_slots = [CasteSlot(caste=ct.caste)]
                valid = ("sequential", "stigmergic")
                strategy = ct.strategy if ct.strategy in valid else "stigmergic"
                max_rounds = max(1, min(ct.max_rounds, 50))
                budget = max(0.01, min(ct.budget_limit, 50.0))

                # Chain input from completed tasks if specified
                input_sources: list[InputSource] | None = None
                if ct.input_from:
                    sources: list[InputSource] = []
                    for src_tid in ct.input_from:
                        src_cid = colony_map.get(src_tid, "")
                        if src_cid:
                            sources.append(InputSource(type="colony", colony_id=src_cid))
                    if sources:
                        input_sources = sources

                colony_id = await self._runtime.spawn_colony(
                    workspace_id, thread_id, ct.task, caste_slots,
                    strategy=strategy,
                    max_rounds=max_rounds,
                    budget_limit=budget,
                    input_sources=input_sources,
                    target_files=ct.target_files if ct.target_files else None,
                    spawn_source="queen",
                )
                # Start the colony
                if self._runtime.colony_manager is not None:
                    start_task = asyncio.create_task(
                        self._runtime.colony_manager.start_colony(colony_id),
                    )
                    start_task.add_done_callback(_log_task_exception)
                return (ct.task_id, colony_id)

            # Spawn all tasks in this group concurrently
            try:
                spawn_results = await asyncio.gather(
                    *[_spawn_one(ct) for ct in group_tasks],
                    return_exceptions=True,
                )
            except Exception as exc:
                log.exception("queen.parallel_group_spawn_failed", group_idx=group_idx)
                result_lines.append(f"Group {group_idx + 1}: spawn failed — {exc}")
                continue

            group_colonies: list[str] = []
            for res in spawn_results:
                if isinstance(res, BaseException):
                    log.error("queen.parallel_task_spawn_failed", error=str(res))
                    result_lines.append(f"  Task spawn failed: {res}")
                else:
                    pair: tuple[str, str] = res  # pyright: ignore[reportAssignmentType]
                    colony_map[pair[0]] = pair[1]
                    all_colony_ids.append(pair[1])
                    group_colonies.append(f"{pair[0]}={pair[1]}")

            result_lines.append(
                f"Group {group_idx + 1}/{len(plan.parallel_groups)}: "
                f"spawned {', '.join(group_colonies)}"
            )

        result_msg = "\n".join(result_lines)
        return (
            result_msg,
            {
                "tool": "spawn_parallel",
                "colony_ids": all_colony_ids,
                "parallel_groups": plan.parallel_groups,
            },
        )

    @staticmethod
    def _validate_dag(tasks: list[Any]) -> bool:
        """Return True if tasks form a valid DAG (no cycles)."""
        # Kahn's algorithm for topological sort
        task_ids = {t.task_id for t in tasks}
        adj: dict[str, list[str]] = {t.task_id: [] for t in tasks}
        in_degree: dict[str, int] = {t.task_id: 0 for t in tasks}
        for t in tasks:
            for dep in t.depends_on:
                if dep in task_ids:
                    adj[dep].append(t.task_id)
                    in_degree[t.task_id] += 1

        queue = [tid for tid, deg in in_degree.items() if deg == 0]
        visited = 0
        while queue:
            node = queue.pop(0)
            visited += 1
            for neighbor in adj[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return visited == len(task_ids)

    def _get_status(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        ws_id = inputs.get("workspace_id", workspace_id)
        ws = self._runtime.projections.workspaces.get(ws_id)
        if ws is None:
            return (f"Workspace '{ws_id}' not found.", None)
        threads_info: list[str] = []
        for t in ws.threads.values():
            colonies_info = ", ".join(
                f"{c.id}({c.status}, r{c.round_number})"
                for c in t.colonies.values()
            )
            threads_info.append(
                f"  Thread '{t.name}': {colonies_info or 'no colonies'}"
            )
        return (
            f"Workspace '{ws_id}':\n" + "\n".join(threads_info),
            None,
        )

    async def _list_templates(self) -> tuple[str, dict[str, Any] | None]:
        templates = await load_all_templates(
            projection_templates=self._runtime.projections.templates,
        )
        if not templates:
            return ("No templates available.", None)
        lines: list[str] = ["Available templates:"]
        for i, tmpl in enumerate(templates[:20], 1):
            team = ", ".join(
                f"{s.caste}({s.tier.value})" + (f"x{s.count}" if s.count > 1 else "")
                for s in tmpl.castes
            )
            source_tag = "[learned]" if tmpl.learned else "[operator]"
            lines.append(
                f"{i}. {tmpl.template_id} — {tmpl.name} {source_tag}: "
                f"{tmpl.description}"
                f" (tags: {', '.join(tmpl.tags) or 'none'})"
            )
            lines.append(f"   Team: {team or 'none'}")
            stats = f"   Used {tmpl.use_count} times"
            if tmpl.learned:
                stats += (
                    f" | success: {tmpl.success_count}"
                    f" | failure: {tmpl.failure_count}"
                )
            lines.append(stats)
        return ("\n".join(lines), None)

    async def _inspect_template(
        self, inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        template_id = inputs.get("template_id", "")
        if not template_id:
            return ("Error: template_id is required.", None)
        templates = await load_all_templates(
            projection_templates=self._runtime.projections.templates,
        )
        # Exact ID match first, then case-insensitive name substring
        match = None
        for tmpl in templates:
            if tmpl.template_id == template_id:
                match = tmpl
                break
        if match is None:
            lower = template_id.lower()
            for tmpl in templates:
                if lower in tmpl.name.lower():
                    match = tmpl
                    break
        if match is None:
            return ("Template not found. Use list_templates to see available options.", None)
        team = "\n".join(
            f"  - {s.caste} (tier: {s.tier.value}, count: {s.count})"
            for s in match.castes
        )
        parts = [
            f"Template: {match.name} ({match.template_id})",
            f"Description: {match.description}",
            f"Strategy: {match.strategy}",
            f"Budget: ${match.budget_limit:.2f}",
            f"Max rounds: {match.max_rounds}",
            f"Tags: {', '.join(match.tags) or 'none'}",
            f"Used {match.use_count} times",
        ]
        if match.source_colony_id:
            parts.append(f"Source colony: {match.source_colony_id}")
        parts.append(f"Team:\n{team or '  (empty)'}")
        return ("\n".join(parts), None)

    def _inspect_colony(
        self, inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        colony_id = inputs.get("colony_id", "")
        if not colony_id:
            return ("Error: colony_id is required.", None)
        colony = self._find_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)
        name = colony.display_name or colony.id
        models_used = sorted({a.model for a in colony.agents.values() if a.model})
        castes_summary = ", ".join(
            sorted({a.caste for a in colony.agents.values()})
        )
        parts = [
            f"Colony: {name}",
            f"Status: {colony.status} | Round {colony.round_number}/{colony.max_rounds}",
            f"Quality: {colony.quality_score:.2f} | "
            + (
                f"Cost: ${colony.cost:.4f} API / ${colony.budget_limit:.2f} budget"
                if colony.cost > 0
                else f"Cost: local only / ${colony.budget_limit:.2f} budget"
            ),
            f"Skills extracted: {colony.skills_extracted}",
            f"Strategy: {colony.strategy}",
            f"Team: {castes_summary or 'none'}",
            f"Models used: {', '.join(models_used) or 'none'}",
        ]
        # Last round outputs (truncated)
        if colony.round_records:
            last_round = colony.round_records[-1]
            if last_round.agent_outputs:
                parts.append("\nLast round summary:")
                for aid, output in last_round.agent_outputs.items():
                    agent = colony.agents.get(aid)
                    caste = agent.caste if agent else "unknown"
                    parts.append(f"  {aid} ({caste}): {output[:500]}")
        return ("\n".join(parts), None)

    def _read_workspace_files(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        ws_id = inputs.get("workspace_id", workspace_id)
        data_dir = self._runtime.settings.system.data_dir
        ws_path = os.path.join(data_dir, "workspaces", ws_id)
        if not os.path.isdir(ws_path):
            return (f"No files found for workspace '{ws_id}'.", None)
        entries: list[str] = []
        for f in sorted(os.listdir(ws_path))[:50]:
            full = os.path.join(ws_path, f)
            if os.path.isfile(full):
                size = os.path.getsize(full)
                entries.append(f"  {f} ({size:,} bytes)")
            elif os.path.isdir(full):
                entries.append(f"  {f}/ (directory)")
        if not entries:
            return (f"Workspace '{ws_id}' directory exists but contains no files.", None)
        return (
            f"Files in workspace '{ws_id}' ({len(entries)} entries):\n" + "\n".join(entries),
            None,
        )

    def _suggest_config_change(
        self, inputs: dict[str, Any], thread_id: str = "",
    ) -> tuple[str, dict[str, Any] | None]:
        param_path = inputs.get("param_path", "")
        proposed_value = inputs.get("proposed_value", "")
        reason = inputs.get("reason", "")
        if not param_path or not proposed_value:
            return ("Error: param_path and proposed_value are required.", None)

        # Gate 1: structural safety (config_validator.py)
        payload = {"param_path": param_path, "value": proposed_value}
        result = validate_config_update(payload)
        if not result.valid:
            return (
                f"Proposal rejected (safety): {result.error}",
                None,
            )

        # Gate 2: Queen scope (experimentable_params.yaml)
        if not _is_experimentable(param_path):
            return (
                f"Proposal rejected (scope): '{param_path}' is not in the "
                "experimentable parameters whitelist. The Queen cannot propose "
                "changes to this parameter.",
                None,
            )

        # Both gates pass — store pending proposal and format response
        current_value = self._resolve_current_value(param_path)
        proposal_id = hashlib.sha256(
            f"{param_path}:{result.value}".encode(),
        ).hexdigest()[:8]

        if thread_id:
            self._pending_proposals[thread_id] = PendingConfigProposal(
                proposal_id=proposal_id,
                thread_id=thread_id,
                param_path=param_path,
                proposed_value=str(result.value),
                current_value=current_value,
                reason=reason,
                proposed_at=_now(),
            )

        return (
            f"**Config change proposal** (#{proposal_id}):\n"
            f"  Parameter: `{param_path}`\n"
            f"  Current value: {current_value}\n"
            f"  Proposed value: {result.value}\n"
            f"  Reason: {reason}\n\n"
            f"Say 'approve' to apply this change.",
            {
                "tool": "suggest_config_change",
                "param_path": param_path,
                "proposed_value": str(result.value),
                "proposal_id": proposal_id,
                "status": "proposed",
            },
        )

    async def _approve_config_change(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Apply a pending config proposal after re-validation."""
        proposal = self._pending_proposals.get(thread_id)

        if proposal is None:
            return ("No pending config proposal in this thread.", None)

        if proposal.is_expired:
            del self._pending_proposals[thread_id]
            return (
                f"Proposal #{proposal.proposal_id} expired "
                f"({proposal.ttl_minutes} minute TTL). Please propose again.",
                None,
            )

        # Gate 1: re-validate structural safety
        payload = {"param_path": proposal.param_path, "value": proposal.proposed_value}
        result = validate_config_update(payload)
        if not result.valid:
            del self._pending_proposals[thread_id]
            return (
                f"Proposal #{proposal.proposal_id} failed re-validation: "
                f"{result.error}",
                None,
            )

        # Gate 2: re-validate Queen scope
        if not _is_experimentable(proposal.param_path):
            del self._pending_proposals[thread_id]
            return (
                f"Proposal #{proposal.proposal_id} is no longer in "
                "experimentable scope.",
                None,
            )

        # Apply via existing config mutation path
        try:
            await self._runtime.apply_config_change(
                proposal.param_path,
                proposal.proposed_value,
                workspace_id,
            )
        except Exception as exc:
            del self._pending_proposals[thread_id]
            return (f"Failed to apply: {exc}", None)

        pid = proposal.proposal_id
        old = proposal.current_value
        new = proposal.proposed_value
        path = proposal.param_path
        del self._pending_proposals[thread_id]

        return (
            f"Applied proposal #{pid}:\n"
            f"  `{path}`: {old} -> {new}",
            {
                "tool": "approve_config_change",
                "proposal_id": pid,
                "applied": True,
            },
        )

    async def _redirect_colony(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        colony_id = inputs.get("colony_id", "")
        new_goal = inputs.get("new_goal", "")
        reason = inputs.get("reason", "")
        if not colony_id or not new_goal or not reason:
            return (
                "Error: colony_id, new_goal, and reason are required.",
                None,
            )

        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)
        if colony.status != "running":
            return (
                f"Colony {colony_id} is {colony.status}, not running. "
                "Cannot redirect.",
                None,
            )

        max_redirects = (
            self._runtime.settings.governance.max_redirects_per_colony
        )
        history = getattr(colony, "redirect_history", [])
        if len(history) >= max_redirects:
            return (
                f"Colony {colony_id} has already been redirected "
                f"{len(history)} time(s). "
                f"Maximum redirects per colony: {max_redirects}.",
                None,
            )

        redirect_index = len(history)
        address = f"{workspace_id}/{thread_id}/{colony_id}"
        await self._runtime.emit_and_broadcast(ColonyRedirected(
            seq=0,
            timestamp=_now(),
            address=address,
            colony_id=colony_id,
            redirect_index=redirect_index,
            original_goal=colony.task,
            new_goal=new_goal,
            reason=reason,
            trigger=RedirectTrigger.queen_inspection,
            round_at_redirect=colony.round_number,
        ))

        log.info(
            "queen.redirect_colony",
            colony_id=colony_id,
            redirect_index=redirect_index,
            round=colony.round_number,
            new_goal=new_goal[:100],
        )

        # Metacognitive nudge: save_corrections (Wave 26 Track C)
        if should_nudge("save_corrections", self._nudge_cooldowns):
            nudge = format_nudge("save_corrections")
            if nudge:
                log.debug("queen.nudge_save_corrections", colony_id=colony_id)

        return (
            f"Colony {colony_id} redirected at round "
            f"{colony.round_number}.\n"
            f"New goal: {new_goal}\n"
            f"Reason: {reason}",
            {
                "tool": "redirect_colony",
                "colony_id": colony_id,
                "redirect_index": redirect_index,
            },
        )

    async def _escalate_colony(
        self,
        inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        colony_id = inputs.get("colony_id", "")
        tier = inputs.get("tier", "")
        reason = inputs.get("reason", "")
        if not colony_id or not tier or not reason:
            return (
                "Error: colony_id, tier, and reason are required.",
                None,
            )

        valid_tiers = {"standard", "heavy", "max"}
        if tier not in valid_tiers:
            return (
                f"Error: tier must be one of {sorted(valid_tiers)}, "
                f"got '{tier}'.",
                None,
            )

        colony = self._runtime.projections.get_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)
        if colony.status != "running":
            return (
                f"Colony {colony_id} is {colony.status}, not running. "
                "Cannot escalate.",
                None,
            )

        # Wave 51: emit replay-safe event instead of direct projection mutation
        from formicos.core.events import ColonyEscalated  # noqa: PLC0415

        await self._runtime.emit_and_broadcast(ColonyEscalated(
            seq=0,
            timestamp=_now(),
            address=colony.address,
            colony_id=colony_id,
            tier=tier,
            reason=reason,
            set_at_round=colony.round_number,
        ))

        log.info(
            "queen.escalate_colony",
            colony_id=colony_id,
            tier=tier,
            reason=reason[:100],
            round=colony.round_number,
        )

        return (
            f"Colony {colony_id} escalated to tier '{tier}' "
            f"at round {colony.round_number}.\n"
            f"Reason: {reason}\n"
            f"Subsequent rounds will route to the upgraded model.",
            {
                "tool": "escalate_colony",
                "colony_id": colony_id,
                "tier": tier,
                "set_at_round": colony.round_number,
            },
        )

    def _read_colony_output(
        self, inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        colony_id = inputs.get("colony_id", "")
        if not colony_id:
            return ("Error: colony_id is required.", None)

        colony = self._find_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)

        round_number = inputs.get("round_number")
        agent_id = inputs.get("agent_id")

        # Find the target round
        if round_number is not None:
            target_round = None
            for rp in colony.round_records:
                if rp.round_number == int(round_number):
                    target_round = rp
                    break
            if target_round is None:
                available = [r.round_number for r in colony.round_records]
                return (
                    f"Round {round_number} not found. "
                    f"Available rounds: {available}",
                    None,
                )
        else:
            # Default: latest round with outputs
            target_round = None
            for rp in reversed(colony.round_records):
                if rp.agent_outputs:
                    target_round = rp
                    break
            if target_round is None:
                return (
                    f"Colony '{colony.id}' has no round output yet.",
                    None,
                )

        parts = [
            f"Colony: {colony.display_name or colony.id}",
            f"Round: {target_round.round_number}",
            "",
        ]

        outputs = target_round.agent_outputs
        if agent_id:
            if agent_id not in outputs:
                available = list(outputs.keys())
                return (
                    f"Agent '{agent_id}' not found in round "
                    f"{target_round.round_number}. "
                    f"Available agents: {available}",
                    None,
                )
            outputs = {agent_id: outputs[agent_id]}

        for aid, output in outputs.items():
            agent = colony.agents.get(aid)
            caste = agent.caste if agent else "unknown"
            model = agent.model if agent else "unknown"
            tools = target_round.tool_calls.get(aid, [])
            parts.append(f"--- {aid} ({caste}) ---")
            parts.append(f"Model: {model}")
            if tools:
                parts.append(f"Tools: {', '.join(tools)}")
            truncated = output[:self._OUTPUT_TRUNCATE]
            if len(output) > self._OUTPUT_TRUNCATE:
                truncated += (
                    f"\n[...truncated at {self._OUTPUT_TRUNCATE}"
                    f" chars, total {len(output)}]"
                )
            parts.append("")
            parts.append(truncated)
            parts.append("")

        return ("\n".join(parts), None)

    async def _memory_search(
        self, inputs: dict[str, Any], workspace_id: str,
        thread_id: str = "",
    ) -> tuple[str, dict[str, Any] | None]:
        """Handle the memory_search Queen tool -- unified knowledge catalog."""
        catalog = getattr(self._runtime, "knowledge_catalog", None)
        if catalog is None:
            return ("Knowledge catalog is not available.", None)

        query = inputs.get("query", "")
        if not query:
            return ("Error: query is required.", None)

        entry_type = inputs.get("entry_type", "")
        limit = min(int(inputs.get("limit", 5)), 10)

        results: list[dict[str, Any]] = await catalog.search(
            query=query,
            canonical_type=entry_type,
            workspace_id=workspace_id,
            thread_id=thread_id,
            top_k=limit,
        )

        if not results:
            return (f"No knowledge entries found for: {query}", None)

        lines = [f"Found {len(results)} entries:"]
        for r in results:
            polarity = str(r.get("polarity", "positive"))
            polarity_tag = f" ({polarity})" if polarity != "positive" else ""
            ctype = str(r.get("canonical_type", "skill")).upper()
            source = str(r.get("source_system", ""))
            status = str(r.get("status", "candidate"))
            title = r.get("title", "")
            content = str(r.get("content_preview", ""))[:200]
            lines.append(
                f"- [{ctype}, {status}, {source}]{polarity_tag} "
                f'"{title}": {content}',
            )
            domains = r.get("domains", [])
            if domains:
                lines.append(f"  domains: {', '.join(domains)}")
            colony = r.get("source_colony_id", "")
            conf = r.get("confidence", 0.5)
            lines.append(f"  source: colony {colony}, confidence: {conf:.1f}")

        return ("\n".join(lines), None)

    def _write_workspace_file(
        self, inputs: dict[str, Any], workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        filename = inputs.get("filename", "")
        content = inputs.get("content", "")
        if not filename or not content:
            return ("Error: filename and content are required.", None)

        # Sanitize: strip path traversal, use only the basename
        safe_name = Path(filename).name
        if not safe_name:
            return ("Error: invalid filename.", None)

        suffix = Path(safe_name).suffix.lower()
        if suffix not in self._WS_FILE_ALLOWED_EXT:
            return (
                f"Error: extension '{suffix}' not allowed. "
                f"Allowed: {sorted(self._WS_FILE_ALLOWED_EXT)}",
                None,
            )

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > self._WS_FILE_MAX_BYTES:
            return (
                f"Error: content too large ({len(content_bytes):,} bytes). "
                f"Max: {self._WS_FILE_MAX_BYTES:,} bytes.",
                None,
            )

        data_dir = self._runtime.settings.system.data_dir
        ws_dir = Path(data_dir) / "workspaces" / workspace_id / "files"
        ws_dir.mkdir(parents=True, exist_ok=True)

        path = ws_dir / safe_name
        path.write_bytes(content_bytes)

        log.info(
            "queen.write_workspace_file",
            workspace_id=workspace_id,
            filename=safe_name,
            bytes=len(content_bytes),
        )

        return (
            f"File '{safe_name}' written to workspace ({len(content_bytes):,} bytes).",
            {"tool": "write_workspace_file", "filename": safe_name},
        )

    # -- queen_note helpers (shared with QueenAgent) --

    def _queen_notes_path(self, workspace_id: str, thread_id: str) -> Path:
        data_dir = self._runtime.settings.system.data_dir
        return (
            Path(data_dir) / "workspaces" / workspace_id
            / "threads" / thread_id / "queen_notes.yaml"
        )

    def _load_queen_notes(self, workspace_id: str, thread_id: str) -> list[dict[str, str]]:
        path = self._queen_notes_path(workspace_id, thread_id)
        if not path.exists():
            return []
        try:
            with path.open(encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                notes = data.get("notes", [])  # pyright: ignore[reportUnknownMemberType]
                return [n for n in notes if isinstance(n, dict)]  # pyright: ignore[reportUnknownVariableType]
        except Exception:  # noqa: BLE001
            log.debug("queen.notes_load_error", path=str(path))
        return []

    def _save_queen_notes(
        self, workspace_id: str, thread_id: str, notes: list[dict[str, str]],
    ) -> None:
        path = self._queen_notes_path(workspace_id, thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump({"notes": notes}, f, default_flow_style=False)

    async def save_thread_note(
        self, workspace_id: str, thread_id: str, content: str,
    ) -> int:
        """Save a single note to thread-scoped Queen notes. Returns note count.

        Wave 51: emits QueenNoteSaved event for replay safety.
        YAML file kept as backup but projection is source of truth.
        """
        content = content[:self._MAX_NOTE_CHARS]

        # Emit replay-safe event — projection handler stores it
        from formicos.core.events import QueenNoteSaved  # noqa: PLC0415

        await self._runtime.emit_and_broadcast(QueenNoteSaved(
            seq=0,
            timestamp=_now(),
            address=f"{workspace_id}/{thread_id}",
            workspace_id=workspace_id,
            thread_id=thread_id,
            content=content,
        ))

        # Read back from projection for count
        key = f"{workspace_id}/{thread_id}"
        notes = self._runtime.projections.queen_notes.get(key, [])

        # Keep YAML as backup
        self._save_queen_notes(workspace_id, thread_id, list(notes))

        log.info(
            "queen.note_saved",
            workspace_id=workspace_id,
            thread_id=thread_id,
            note_count=len(notes),
        )
        return len(notes)

    async def _queen_note(
        self, inputs: dict[str, Any], workspace_id: str, thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        action = inputs.get("action", "")

        if action == "list":
            # Wave 51: read from projection (replay-safe) with YAML fallback
            key = f"{workspace_id}/{thread_id}"
            notes = self._runtime.projections.queen_notes.get(key, [])
            if not notes:
                # Fallback to YAML for pre-Wave-51 notes
                notes = self._load_queen_notes(workspace_id, thread_id)
            if not notes:
                return ("No Queen notes saved yet.", None)
            lines = [f"Queen notes ({len(notes)} total):"]
            for i, note in enumerate(notes, 1):
                ts = note.get("timestamp", "")
                content = note.get("content", "")
                lines.append(f"{i}. [{ts}] {content}")
            return ("\n".join(lines), None)

        if action == "save":
            content = inputs.get("content", "")
            if not content:
                return ("Error: content is required for save.", None)
            count = await self.save_thread_note(workspace_id, thread_id, content)
            return (
                f"Note saved ({count}/{self._MAX_NOTES} notes).",
                {"tool": "queen_note", "action": "save"},
            )

        return (f"Error: unknown action '{action}'. Use 'save' or 'list'.", None)

    def _resolve_current_value(self, param_path: str) -> str:
        """Traverse live config to find the current value for a dot-path."""
        parts = param_path.split(".")
        # castes.{caste}.{field} — read from caste recipes
        if len(parts) == 3 and parts[0] == "castes" and self._runtime.castes:
            recipe = self._runtime.castes.castes.get(parts[1])
            if recipe:
                val = getattr(recipe, parts[2], None)
                if val is not None:
                    return str(val)
        # governance.{field}
        if len(parts) == 2 and parts[0] == "governance":
            val = getattr(self._runtime.settings.governance, parts[1], None)
            if val is not None:
                return str(val)
        # routing.{field}
        if len(parts) == 2 and parts[0] == "routing":
            val = getattr(self._runtime.settings.routing, parts[1], None)
            if val is not None:
                return str(val)
        return "(unknown)"


__all__ = ["DELEGATE_THREAD", "QueenToolDispatcher"]
