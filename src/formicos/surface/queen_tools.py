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
import re as _re
import shlex
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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
        # Wave 64 Track 6a: addon-registered tool specs (appended to Queen tool list)
        self._addon_tool_specs: list[dict[str, Any]] = []
        # Wave 62 Track 6: dict-based dispatch registry
        # Each handler is wrapped to accept (inputs, workspace_id, thread_id).
        self._handlers: dict[str, Callable[..., Any]] = {
            "spawn_colony": self._spawn_colony,
            "spawn_parallel": self._spawn_parallel,
            "kill_colony": self._handle_kill_colony,
            "get_status": lambda i, w, t: self._get_status(i, w),
            "list_templates": lambda i, w, t: self._list_templates(),
            "inspect_template": lambda i, w, t: self._inspect_template(i),
            "inspect_colony": lambda i, w, t: self._inspect_colony(i),
            "read_workspace_files": lambda i, w, t: self._read_workspace_files(i, w),
            "suggest_config_change": lambda i, w, t: self._suggest_config_change(i, t),
            "approve_config_change": self._approve_config_change,
            "redirect_colony": self._redirect_colony,
            "escalate_colony": lambda i, w, t: self._escalate_colony(i),
            "read_colony_output": lambda i, w, t: self._read_colony_output(i),
            "memory_search": self._memory_search,
            "write_workspace_file": lambda i, w, t: self._write_workspace_file(i, w),
            "queen_note": self._queen_note,
            "set_thread_goal": self._handle_set_thread_goal,
            "complete_thread": self._handle_complete_thread,
            "query_service": self._handle_query_service,
            "propose_plan": lambda i, w, t: self._propose_plan(i, w, t),
            "query_outcomes": lambda i, w, t: self._query_outcomes(i, w),
            "analyze_colony": lambda i, w, t: self._analyze_colony(i),
            "query_briefing": lambda i, w, t: self._query_briefing(i, w),
            "search_codebase": lambda i, w, t: self._search_codebase(i, w),
            "run_command": lambda i, w, t: self._run_command(i, w),
            # Wave 63 Track 3: write tools
            "edit_file": lambda i, w, t: self._edit_file(i, w),
            "run_tests": lambda i, w, t: self._run_tests(i, w),
            "delete_file": lambda i, w, t: self._delete_file(i, w),
            # Wave 68: plan step tracking
            "mark_plan_step": self._mark_plan_step,
            # Wave 64 Track 3: retry failed colony
            "retry_colony": self._retry_colony,
            # Wave 65 Track 5: autonomous agency tools
            "batch_command": lambda i, w, t: self._batch_command(i, w),
            "summarize_thread": lambda i, w, t: self._summarize_thread(i, w, t),
            "draft_document": lambda i, w, t: self._draft_document(i, w),
            "list_addons": lambda i, w, t: self._list_addons(),
            # Wave 65 Track 4: manual addon trigger
            "trigger_addon": lambda i, w, t: self._trigger_addon(i),
            # Wave 68 Track 6: workspace taxonomy
            "set_workspace_tags": self._set_workspace_tags,
            # Wave 70.0 Track 5: project-level milestone tools
            "propose_project_milestone": self._propose_project_milestone,
            "complete_project_milestone": self._complete_project_milestone,
            # Wave 70.0 Track 7: autonomy budget visibility
            "check_autonomy_budget": self._check_autonomy_budget,
            # Wave 74 Track 3: display board posting
            "post_observation": self._post_observation,
        }

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
            {
                "name": "propose_plan",
                "description": (
                    "Present a proposed plan to the operator before executing. "
                    "Use this as your DEFAULT first response for any non-trivial task. "
                    "The operator reviews and confirms before resources are committed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "One-line summary of the proposed approach.",
                        },
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                    "colonies": {
                                        "type": "integer",
                                        "description": "Number of colonies needed.",
                                    },
                                },
                                "required": ["label", "description"],
                            },
                            "description": "1-4 options the operator can choose from.",
                        },
                        "questions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Clarifying questions for the operator.",
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "Which option you recommend and why.",
                        },
                    },
                    "required": ["summary"],
                },
            },
            # Wave 68: plan step tracking
            {
                "name": "mark_plan_step",
                "description": (
                    "Update a plan step's status. Call after spawning "
                    "a colony for a plan step or when a step "
                    "completes/blocks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "step_index": {
                            "type": "integer",
                            "description": (
                                "Zero-based step index in the plan"
                            ),
                        },
                        "status": {
                            "type": "string",
                            "enum": [
                                "pending", "started",
                                "completed", "blocked",
                            ],
                            "description": "New status for this step",
                        },
                        "description": {
                            "type": "string",
                            "description": (
                                "Step description (required when "
                                "adding a new step)"
                            ),
                        },
                        "colony_id": {
                            "type": "string",
                            "description": (
                                "Colony executing this step (optional)"
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": (
                                "Brief status note (optional)"
                            ),
                        },
                    },
                    "required": ["step_index", "status"],
                },
            },
            # Wave 61 Track 3: analytical tools
            {
                "name": "query_outcomes",
                "description": (
                    "Query colony outcomes to analyze performance patterns. "
                    "Use to compare strategies, identify failure patterns, "
                    "or assess model effectiveness."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "period": {
                            "type": "string",
                            "description": (
                                "Time window: 1d, 7d, 30d. Default: 7d"
                            ),
                            "default": "7d",
                        },
                        "strategy": {
                            "type": "string",
                            "description": (
                                "Filter by strategy (stigmergic, sequential)"
                            ),
                        },
                        "succeeded": {
                            "type": "boolean",
                            "description": "Filter by success/failure",
                        },
                        "sort_by": {
                            "type": "string",
                            "description": (
                                "Sort field: cost, quality, rounds, duration. "
                                "Default: quality"
                            ),
                            "default": "quality",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results. Default: 10",
                            "default": 10,
                        },
                    },
                },
            },
            {
                "name": "analyze_colony",
                "description": (
                    "Deep analysis of a colony's execution: quality trends, "
                    "tool usage, cost breakdown, knowledge impact. Use after "
                    "completion to understand what happened."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "Colony ID to analyze",
                        },
                        "include_rounds": {
                            "type": "boolean",
                            "description": "Show per-round progression",
                            "default": True,
                        },
                        "include_tools": {
                            "type": "boolean",
                            "description": "Show tool call summary",
                            "default": True,
                        },
                        "include_knowledge": {
                            "type": "boolean",
                            "description": "Show knowledge impact",
                            "default": True,
                        },
                    },
                    "required": ["colony_id"],
                },
            },
            {
                "name": "query_briefing",
                "description": (
                    "Query proactive intelligence insights with filters. "
                    "Goes deeper than the automatic briefing summary."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": (
                                "Filter: knowledge_health, performance, "
                                "learning, evaporation, all. Default: all"
                            ),
                            "default": "all",
                        },
                        "rule": {
                            "type": "string",
                            "description": (
                                "Specific rule name "
                                "(e.g., contradiction, cost_outlier)"
                            ),
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max insights to return. Default: 10",
                            "default": 10,
                        },
                        "include_suggested_colonies": {
                            "type": "boolean",
                            "description": (
                                "Include auto-dispatch colony configs"
                            ),
                            "default": False,
                        },
                    },
                },
            },
            # Wave 62 Track 2: Queen direct work tools
            {
                "name": "search_codebase",
                "description": (
                    "Search the workspace codebase for text patterns. "
                    "Returns matching lines with file paths and line numbers. "
                    "Use this to find definitions, usages, or patterns "
                    "without spawning a colony."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search text or regex pattern",
                        },
                        "path": {
                            "type": "string",
                            "description": (
                                "Subdirectory to search within (relative to "
                                "workspace). Default: entire workspace"
                            ),
                        },
                        "regex": {
                            "type": "boolean",
                            "description": "Treat query as regex. Default: false",
                            "default": False,
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Max matching lines. Default: 20, max: 50",
                            "default": 20,
                        },
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "run_command",
                "description": (
                    "Run an allowlisted shell command in the workspace. "
                    "Use for git status, test results, linting, and other "
                    "read-only operations. Allowed: git (status/diff/log/"
                    "blame/show/branch), pytest, ruff check, ls, cat, "
                    "head, tail, wc, find."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "Command to run. Must start with an "
                                "allowlisted program."
                            ),
                        },
                        "timeout": {
                            "type": "integer",
                            "description": (
                                "Timeout in seconds. Default: 30, max: 60"
                            ),
                            "default": 30,
                        },
                    },
                    "required": ["command"],
                },
            },
            # Wave 63 Track 3: Queen write tools
            {
                "name": "edit_file",
                "description": (
                    "Propose a file edit. Shows a diff to the operator for "
                    "approval before applying. Use for small fixes, typos, "
                    "or config changes that don't need a full colony."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Workspace-relative file path to edit"
                            ),
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Exact text to find and replace",
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this change is needed",
                        },
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
            {
                "name": "run_tests",
                "description": (
                    "Run pytest and return structured results (pass/fail "
                    "counts, error summary). Use to verify changes or "
                    "check project health."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pattern": {
                            "type": "string",
                            "description": (
                                "Test file or pattern. Default: run all tests"
                            ),
                        },
                        "timeout": {
                            "type": "integer",
                            "description": (
                                "Max seconds. Default: 120, max: 300"
                            ),
                            "default": 120,
                        },
                    },
                },
            },
            {
                "name": "delete_file",
                "description": (
                    "Propose deleting a workspace file. Requires operator "
                    "approval. The file is backed up before deletion."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Workspace-relative file path to delete"
                            ),
                        },
                        "reason": {
                            "type": "string",
                            "description": (
                                "Why this file should be deleted"
                            ),
                        },
                    },
                    "required": ["path"],
                },
            },
            # Wave 64 Track 3: retry failed colony with different settings
            {
                "name": "retry_colony",
                "description": (
                    "Retry a failed colony with different settings. "
                    "Copies the original task, adds failure context, "
                    "and optionally switches model or strategy."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "colony_id": {
                            "type": "string",
                            "description": "The failed colony to retry",
                        },
                        "model_override": {
                            "type": "string",
                            "description": (
                                "Model address for the retry "
                                "(e.g., openai/gpt-4o)"
                            ),
                        },
                        "strategy_override": {
                            "type": "string",
                            "description": (
                                "Strategy: sequential or stigmergic"
                            ),
                            "enum": ["sequential", "stigmergic"],
                        },
                        "additional_context": {
                            "type": "string",
                            "description": (
                                "Extra guidance based on failure analysis"
                            ),
                        },
                    },
                    "required": ["colony_id"],
                },
            },
            # Wave 65 Track 5: autonomous agency tools
            {
                "name": "batch_command",
                "description": (
                    "Run multiple allowlisted commands in sequence and "
                    "return aggregated results. Use for multi-step checks "
                    "like 'test + lint + git status' in one call."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "commands": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Commands to run. Each must pass the "
                                "same allowlist as run_command."
                            ),
                        },
                        "stop_on_error": {
                            "type": "boolean",
                            "description": (
                                "Stop on first non-zero exit. "
                                "Default: true"
                            ),
                            "default": True,
                        },
                    },
                    "required": ["commands"],
                },
            },
            {
                "name": "summarize_thread",
                "description": (
                    "Produce a structured summary of a thread's history: "
                    "goal, colony outcomes, knowledge extracted, total "
                    "cost, timeline. Useful for changelogs, PR "
                    "descriptions, and progress reports."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread to summarize.",
                        },
                        "detail_level": {
                            "type": "string",
                            "description": (
                                "'brief' or 'full'. Default: brief"
                            ),
                            "enum": ["brief", "full"],
                            "default": "brief",
                        },
                    },
                    "required": ["thread_id"],
                },
            },
            {
                "name": "draft_document",
                "description": (
                    "Write a structured document to the workspace. "
                    "Supports overwrite, prepend (e.g. changelog), and "
                    "append modes."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": (
                                "Workspace-relative file path."
                            ),
                        },
                        "content": {
                            "type": "string",
                            "description": "Document content to write.",
                        },
                        "mode": {
                            "type": "string",
                            "description": (
                                "'overwrite', 'prepend', or 'append'. "
                                "Default: overwrite"
                            ),
                            "enum": ["overwrite", "prepend", "append"],
                            "default": "overwrite",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_addons",
                "description": (
                    "List installed addons with their tools, handlers, "
                    "and version. Shows the full addon capability "
                    "surface."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
            # Wave 65 Track 4: manually fire addon triggers
            {
                "name": "trigger_addon",
                "description": (
                    "Manually fire an addon's trigger (e.g., reindex "
                    "codebase, refresh briefing cache). Use list_addons "
                    "to discover available triggers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "addon_name": {
                            "type": "string",
                            "description": "Addon to trigger.",
                        },
                        "handler": {
                            "type": "string",
                            "description": (
                                "Handler reference from the addon manifest "
                                "(e.g., 'indexer.py::full_reindex')."
                            ),
                        },
                    },
                    "required": ["addon_name", "handler"],
                },
            },
            # Wave 68 Track 6: workspace taxonomy
            {
                "name": "set_workspace_tags",
                "description": (
                    "Set soft taxonomy tags on the current workspace. "
                    "Tags are free-form hints (e.g., 'python', 'auth', "
                    "'web-api') that help route queries to the right "
                    "sources."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "List of tags (max 20, each max 50 chars)."
                            ),
                        },
                    },
                    "required": ["tags"],
                },
            },
            # Wave 70.0 Track 5: project-level milestone tools
            {
                "name": "propose_project_milestone",
                "description": (
                    "Add a milestone to the project-wide plan. Creates the "
                    "plan file if it doesn't exist. Milestones span threads "
                    "and give the Queen cross-thread planning context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "description": {
                            "type": "string",
                            "description": (
                                "What this milestone achieves."
                            ),
                        },
                        "goal": {
                            "type": "string",
                            "description": (
                                "Overall project goal (used only when "
                                "creating a new plan)."
                            ),
                        },
                    },
                    "required": ["description"],
                },
            },
            {
                "name": "complete_project_milestone",
                "description": (
                    "Mark a project milestone as completed. "
                    "Use the milestone index from the project plan."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "milestone_index": {
                            "type": "integer",
                            "description": "Index of the milestone to complete.",
                        },
                        "note": {
                            "type": "string",
                            "description": "Optional completion note.",
                        },
                    },
                    "required": ["milestone_index"],
                },
            },
            # Wave 70.0 Track 7: autonomy budget visibility
            {
                "name": "check_autonomy_budget",
                "description": (
                    "Check daily autonomy budget status: remaining budget, "
                    "active maintenance colonies, autonomy level, and trust "
                    "score. Optionally estimate blast radius for a proposed task."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": (
                                "Optional task description to estimate blast radius."
                            ),
                        },
                    },
                },
            },
            # Wave 74 Track 3: display board posting
            {
                "name": "post_observation",
                "description": (
                    "Post a structured observation to the display board. Use for "
                    "status updates, flagged concerns, notable findings. The operator "
                    "sees these when they open the Queen tab."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["observation", "status", "concern", "metric"],
                            "description": "Kind of observation.",
                        },
                        "priority": {
                            "type": "string",
                            "enum": ["normal", "attention", "urgent"],
                            "description": (
                                "Display priority. Use 'urgent' sparingly — only "
                                "for items requiring immediate operator action."
                            ),
                        },
                        "title": {
                            "type": "string",
                            "description": "Short heading (under 80 chars).",
                        },
                        "content": {
                            "type": "string",
                            "description": "Body text with details. Keep under 200 chars.",
                        },
                    },
                    "required": ["type", "title", "content"],
                },
            },
            # Wave 64 Track 6a: addon-registered tools appended dynamically
            *self._addon_tool_specs,
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

            # Wave 62 Track 6: dict-based dispatch registry
            handler = self._handlers.get(name)
            if handler is None:
                return (f"Unknown tool: {name}", None)
            result = handler(inputs, workspace_id, thread_id)
            if hasattr(result, "__await__"):
                return await result
            return result
        except Exception as exc:
            log.exception("queen.tool_error", tool=name)
            return (f"Tool {name} failed: {exc}", None)

    # ------------------------------------------------------------------ #
    # Tool handlers                                                       #
    # ------------------------------------------------------------------ #

    # Wave 62: extracted inline handlers for registry dispatch

    async def _handle_kill_colony(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        colony_id = inputs.get("colony_id", "")
        if not colony_id:
            return ("Error: colony_id is required", None)
        await self._runtime.kill_colony(colony_id)
        return (
            f"Colony {colony_id} killed.",
            {"tool": "kill_colony", "colony_id": colony_id},
        )

    async def _handle_set_thread_goal(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
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

    async def _handle_complete_thread(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
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

    async def _handle_query_service(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
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

        # Wave 63 Track 2: register colonies for parallel aggregation
        if all_colony_ids:
            queen = getattr(self._runtime, "queen", None)
            if queen is not None:
                import uuid  # noqa: PLC0415

                plan_id = f"plan-{workspace_id[:8]}-{thread_id[:8]}-{uuid.uuid4().hex[:8]}"
                queen.register_parallel_plan(plan_id, all_colony_ids)

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

    async def _retry_colony(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Wave 64 Track 3: retry a failed colony with different settings.

        Spawns a standalone colony — does NOT re-register into the
        original parallel plan's DAG.
        """
        colony_id = inputs.get("colony_id", "")
        if not colony_id:
            return ("Error: colony_id is required.", None)

        colony = self._find_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)
        if colony.status not in ("completed", "failed", "stalled"):
            return (
                f"Colony {colony_id} is {colony.status}. "
                "retry_colony is for completed/failed/stalled colonies.",
                None,
            )

        model_override = inputs.get("model_override", "")
        strategy_override = inputs.get("strategy_override", "")
        additional_context = inputs.get("additional_context", "")

        # Build retry task from original colony data
        original_task = getattr(colony, "task", "") or ""
        original_castes = (
            list(colony.castes) if hasattr(colony, "castes") else []
        )
        original_strategy = (
            colony.strategy if hasattr(colony, "strategy") else "sequential"
        )
        failure_reason = (
            getattr(colony, "failure_reason", "")
            or f"status={colony.status}"
        )

        # Compose retry context
        context_parts = [
            f"Previous attempt failed: {failure_reason}.",
        ]
        if additional_context:
            context_parts.append(additional_context)
        context_parts.append(f"\nOriginal task:\n{original_task}")
        retry_task = "\n".join(context_parts)

        strategy = strategy_override or original_strategy

        # Build spawn inputs for single colony
        spawn_inputs: dict[str, Any] = {
            "task": retry_task,
            "workspace_id": workspace_id,
            "strategy": strategy,
        }
        if original_castes:
            spawn_inputs["castes"] = original_castes
        if model_override:
            spawn_inputs["routing_override"] = model_override

        result, action = await self._spawn_colony(
            spawn_inputs, workspace_id, thread_id,
        )

        retry_action: dict[str, Any] = {
            "tool": "retry_colony",
            "original_colony_id": colony_id,
            "model_override": model_override or None,
            "strategy_override": strategy_override or None,
        }
        if action:
            retry_action.update(action)

        return (
            f"Retrying colony {colony_id} with "
            f"{'model ' + model_override if model_override else 'same model'}"
            f"{', strategy ' + strategy if strategy_override else ''}.\n"
            f"{result}",
            retry_action,
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

    # ------------------------------------------------------------------ #
    # Wave 61 Track 3: analytical tool handlers                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_period(period_str: str) -> timedelta:
        """Parse a period string like '7d' into a timedelta."""
        period_str = period_str.strip().lower()
        if period_str.endswith("d"):
            with contextlib.suppress(ValueError):
                return timedelta(days=int(period_str[:-1]))
        return timedelta(days=7)

    def _query_outcomes(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Query colony outcomes with filters and sorting."""
        period = self._parse_period(str(inputs.get("period", "7d")))
        strategy_filter = inputs.get("strategy")
        succeeded_filter = inputs.get("succeeded")
        sort_by = str(inputs.get("sort_by", "quality"))
        limit = max(1, min(int(inputs.get("limit", 10)), 50))

        cutoff = datetime.now(tz=UTC) - period
        all_outcomes = self._runtime.projections.colony_outcomes

        # Filter outcomes by workspace and period
        filtered: list[Any] = []
        for outcome in all_outcomes.values():
            if outcome.workspace_id != workspace_id:
                continue
            # Use colony's completed_at for time filtering
            colony = self._runtime.projections.get_colony(outcome.colony_id)
            if colony and colony.completed_at:
                try:
                    completed = datetime.fromisoformat(colony.completed_at)
                    if completed < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            # Apply filters
            if strategy_filter and outcome.strategy != strategy_filter:
                continue
            if succeeded_filter is not None and outcome.succeeded != succeeded_filter:
                continue
            filtered.append(outcome)

        if not filtered:
            return ("No outcomes found matching filters.", None)

        # Sort
        sort_keys = {
            "cost": lambda o: o.total_cost,
            "quality": lambda o: o.quality_score,
            "rounds": lambda o: o.total_rounds,
            "duration": lambda o: o.duration_ms,
        }
        key_fn = sort_keys.get(sort_by, sort_keys["quality"])
        filtered.sort(key=key_fn, reverse=(sort_by == "quality"))
        filtered = filtered[:limit]

        # Format table
        lines = [
            f"Colony Outcomes ({len(filtered)} results, period={inputs.get('period', '7d')}):",
            "",
            (
                f"{'Colony':<20} {'Task':<60} {'OK':>3} "
                f"{'Rnd':>4} {'Qual':>5} {'Cost':>8} "
                f"{'Strategy':<11} {'Entries':>7}"
            ),
            "-" * 130,
        ]
        total_cost = 0.0
        total_quality = 0.0
        success_count = 0
        for o in filtered:
            colony = self._runtime.projections.get_colony(o.colony_id)
            name = (colony.display_name if colony and colony.display_name else o.colony_id)[:20]
            task = (colony.task if colony else "")[:60]
            ok = "Y" if o.succeeded else "N"
            lines.append(
                f"{name:<20} {task:<60} {ok:>3} {o.total_rounds:>4} "
                f"{o.quality_score:>5.2f} ${o.total_cost:>7.4f} "
                f"{o.strategy:<11} {o.entries_extracted:>7}",
            )
            total_cost += o.total_cost
            total_quality += o.quality_score
            if o.succeeded:
                success_count += 1

        n = len(filtered)
        lines.append("")
        lines.append(
            f"Aggregates: avg_quality={total_quality / n:.2f}, "
            f"success_rate={success_count}/{n} ({100 * success_count / n:.0f}%), "
            f"total_cost=${total_cost:.4f}",
        )
        return ("\n".join(lines), None)

    def _analyze_colony(
        self,
        inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """Deep analysis of a single colony's execution."""
        colony_id = inputs.get("colony_id", "")
        if not colony_id:
            return ("Error: colony_id is required.", None)

        colony = self._find_colony(colony_id)
        if colony is None:
            return (f"Colony '{colony_id}' not found.", None)

        include_rounds = bool(inputs.get("include_rounds", True))
        include_tools = bool(inputs.get("include_tools", True))
        include_knowledge = bool(inputs.get("include_knowledge", True))

        outcome = self._runtime.projections.colony_outcomes.get(colony.id)

        # Header
        name = colony.display_name or colony.id
        castes_str = ", ".join(
            sorted({a.caste for a in colony.agents.values()}),
        )
        parts = [
            f"=== Colony Analysis: {name} ===",
            f"Status: {colony.status}",
            f"Task: {colony.task[:300]}",
            f"Strategy: {colony.strategy}",
            f"Team: {castes_str or 'none'}",
        ]
        if outcome:
            parts.append(
                f"Result: {'succeeded' if outcome.succeeded else 'failed'} "
                f"| {outcome.total_rounds} rounds "
                f"| quality {outcome.quality_score:.2f} "
                f"| duration {outcome.duration_ms}ms",
            )

        # Per-round progression
        if include_rounds and colony.round_records:
            parts.append("")
            parts.append("--- Round Progression ---")
            for rnd in colony.round_records:
                parts.append(
                    f"  Round {rnd.round_number}: "
                    f"cost=${rnd.cost:.4f}, "
                    f"convergence={rnd.convergence:.2f}",
                )
                for aid, output in rnd.agent_outputs.items():
                    agent = colony.agents.get(aid)
                    caste = agent.caste if agent else "unknown"
                    parts.append(f"    {caste}: {output[:200]}")

        # Tool call summary
        if include_tools and colony.round_records:
            tool_counts: dict[str, int] = {}
            for rnd in colony.round_records:
                for _aid, calls in rnd.tool_calls.items():
                    for call in calls:
                        tool_name = call if isinstance(call, str) else str(call)
                        tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
            if tool_counts:
                parts.append("")
                parts.append("--- Tool Usage ---")
                for tname, count in sorted(
                    tool_counts.items(), key=lambda x: x[1], reverse=True,
                ):
                    parts.append(f"  {tname}: {count}")

        # Knowledge impact
        if include_knowledge:
            parts.append("")
            parts.append("--- Knowledge Impact ---")
            if colony.knowledge_accesses:
                parts.append(f"  Entries accessed: {len(colony.knowledge_accesses)}")
                for acc in colony.knowledge_accesses[:10]:
                    title = acc.get("title", acc.get("entry_id", "unknown"))
                    parts.append(f"    - {title}")
            else:
                parts.append("  No knowledge accessed.")
            parts.append(f"  Entries extracted: {colony.entries_extracted_count}")

        # Cost breakdown
        parts.append("")
        parts.append("--- Cost Breakdown ---")
        budget = colony.budget_truth
        if budget.model_usage:
            parts.append(f"  Total: ${budget.total_cost:.4f}")
            for model, usage in sorted(budget.model_usage.items()):
                model_cost = usage.get("cost", 0.0)
                in_tok = int(usage.get("input_tokens", 0))
                out_tok = int(usage.get("output_tokens", 0))
                parts.append(
                    f"  {model}: ${model_cost:.4f} "
                    f"({in_tok} in / {out_tok} out)",
                )
        else:
            parts.append(f"  Total: ${colony.cost:.4f} (no per-model breakdown)")

        # Error info
        if colony.failure_reason:
            parts.append("")
            parts.append("--- Failure Info ---")
            parts.append(f"  Reason: {colony.failure_reason}")
            if colony.failed_at_round is not None:
                parts.append(f"  Failed at round: {colony.failed_at_round}")
        if colony.killed_by:
            parts.append("")
            parts.append("--- Kill Info ---")
            parts.append(f"  Killed by: {colony.killed_by}")
            if colony.killed_at_round is not None:
                parts.append(f"  Killed at round: {colony.killed_at_round}")

        return ("\n".join(parts), None)

    def _query_briefing(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Query proactive intelligence insights with filters."""
        from formicos.surface.proactive_intelligence import generate_briefing

        category_filter = str(inputs.get("category", "all"))
        rule_filter = inputs.get("rule")
        limit = max(1, min(int(inputs.get("limit", 10)), 50))
        include_suggested = bool(inputs.get("include_suggested_colonies", False))

        briefing = generate_briefing(
            workspace_id=workspace_id,
            projections=self._runtime.projections,
        )

        insights = briefing.insights

        # Category mapping for grouping
        knowledge_health_categories = {
            "confidence", "contradiction", "federation",
            "coverage", "staleness", "merge", "inbound",
        }
        performance_categories = {
            "strategy_efficiency", "diminishing_rounds",
            "cost_outlier", "knowledge_roi",
        }

        if category_filter != "all":
            if category_filter == "knowledge_health":
                insights = [
                    i for i in insights
                    if i.category in knowledge_health_categories
                ]
            elif category_filter == "performance":
                insights = [
                    i for i in insights
                    if i.category in performance_categories
                ]
            elif category_filter == "evaporation":
                insights = [
                    i for i in insights if i.category == "evaporation"
                ]
            elif category_filter == "learning":
                insights = [
                    i for i in insights
                    if i.category in (
                        "earned_autonomy", "template_health",
                        "outcome_digest", "popular_unexamined",
                    )
                ]
            else:
                insights = [
                    i for i in insights if i.category == category_filter
                ]

        if rule_filter:
            insights = [
                i for i in insights if rule_filter in i.category
            ]

        insights = insights[:limit]

        if not insights:
            return (
                f"No insights found (category={category_filter}"
                + (f", rule={rule_filter}" if rule_filter else "")
                + f"). Total entries: {briefing.total_entries}.",
                None,
            )

        parts = [
            f"Proactive Intelligence ({len(insights)} insights, "
            f"{briefing.total_entries} entries):",
            "",
        ]
        for idx, insight in enumerate(insights, 1):
            parts.append(
                f"{idx}. [{insight.severity.upper()}] {insight.category}: "
                f"{insight.title}",
            )
            parts.append(f"   {insight.detail}")
            if insight.suggested_action:
                parts.append(f"   Action: {insight.suggested_action}")
            if insight.affected_entries:
                parts.append(
                    f"   Affected: {', '.join(insight.affected_entries[:5])}",
                )
            if include_suggested and insight.suggested_colony:
                sc = insight.suggested_colony
                parts.append(
                    f"   Suggested colony: {sc.caste} / {sc.strategy} "
                    f"/ {sc.max_rounds} rounds — {sc.task[:100]}",
                )
            parts.append("")

        return ("\n".join(parts), None)

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


    def _propose_plan(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str = "",
    ) -> tuple[str, dict[str, Any] | None]:
        """Handle propose_plan tool — present a plan for operator review."""
        summary = inputs.get("summary", "")
        if not summary:
            return ("Error: summary is required for propose_plan", None)

        options: list[dict[str, Any]] = inputs.get("options", [])
        questions: list[str] = inputs.get("questions", [])
        recommendation: str = inputs.get("recommendation", "")

        # Estimate cost for options that specify colony counts
        max_rounds = self._runtime.settings.governance.max_rounds_per_colony
        est_rounds = max(1, max_rounds // 2)
        est_tokens_per_round = 4000

        # Look up default coder model cost rates
        coder_model_name = self._runtime.settings.models.defaults.coder
        cost_per_output = 0.0
        for rec in self._runtime.settings.models.registry:
            if rec.address == coder_model_name:
                cost_per_output = rec.cost_per_output_token or 0.0
                break

        enriched_options: list[dict[str, Any]] = []
        for opt in options:
            enriched = dict(opt)
            colonies = opt.get("colonies")
            if colonies is not None and isinstance(colonies, int):
                if cost_per_output > 0.0:
                    est = colonies * est_rounds * est_tokens_per_round * cost_per_output
                    enriched["estimated_cost"] = f"${est:.2f}"
                else:
                    enriched["estimated_cost"] = "local (free)"
            enriched_options.append(enriched)

        # Build formatted response text
        lines = [f"## Proposed Plan\n\n{summary}"]

        if enriched_options:
            lines.append("\n### Options")
            for i, opt in enumerate(enriched_options, 1):
                label = opt.get("label", f"Option {i}")
                desc = opt.get("description", "")
                line = f"\n**{label}:** {desc}"
                if opt.get("colonies") is not None:
                    line += f" ({opt['colonies']} colonies)"
                if opt.get("estimated_cost"):
                    line += f" — est. {opt['estimated_cost']}"
                lines.append(line)

        if recommendation:
            lines.append(f"\n### Recommendation\n{recommendation}")

        if questions:
            lines.append("\n### Questions")
            for q in questions:
                lines.append(f"- {q}")

        # Wave 64 Track 3: provider-aware planning — show available
        # providers per caste with cost estimates
        provider_lines: list[str] = []
        by_caste: dict[str, list[str]] = {}
        for rec in self._runtime.settings.models.registry:
            if rec.status in ("unavailable", "error"):
                continue
            # Derive caste affinity from defaults
            for caste_name in ("coder", "reviewer", "researcher"):
                default_addr = getattr(
                    self._runtime.settings.models.defaults,
                    caste_name, "",
                )
                if rec.address == default_addr:
                    cost_label = (
                        f"${rec.cost_per_output_token:.6f}/tok"
                        if rec.cost_per_output_token
                        else "local"
                    )
                    by_caste.setdefault(caste_name, []).append(
                        f"{rec.address} ({cost_label})"
                    )
        if by_caste:
            provider_lines.append("\n### Available Providers")
            for caste_name, models in sorted(by_caste.items()):
                provider_lines.append(
                    f"- **{caste_name}**: {', '.join(models)}"
                )
            lines.extend(provider_lines)

        # Wave 62 Track 1.5: enrich proposal with empirical outcome data
        stats = self._runtime.projections.outcome_stats(workspace_id)
        if stats:
            lines.append("\n### Empirical Basis (from prior colonies)")
            for s in sorted(stats, key=lambda x: -x["success_rate"])[:5]:
                lines.append(
                    f"- {s['strategy']} / {s['caste_mix']}: "
                    f"{s['success_rate']:.0%} success rate, "
                    f"{s['avg_rounds']:.1f} avg rounds, "
                    f"${s['avg_cost']:.2f} avg cost "
                    f"({s['total']} colonies)"
                )

        lines.append("\n*Awaiting your confirmation before proceeding.*")
        result_text = "\n".join(lines)

        # Build proposal metadata for the action dict
        proposal: dict[str, Any] = {
            "summary": summary,
            "options": enriched_options,
            "questions": questions,
            "recommendation": recommendation,
        }
        action: dict[str, Any] = {
            "tool": "propose_plan",
            "render": "proposal_card",
            "proposal": proposal,
        }

        # Wave 70.0 Track 8: attach blast-radius and autonomy truth
        try:
            from formicos.surface.self_maintenance import (  # noqa: PLC0415
                compute_autonomy_score,
                estimate_blast_radius,
            )

            _br = estimate_blast_radius(
                task=summary,
                workspace_id=workspace_id,
                projections=self._runtime.projections,
            )
            action["blast_radius"] = {
                "score": _br.score,
                "level": _br.level,
                "factors": _br.factors,
                "recommendation": _br.recommendation,
            }
            _as = compute_autonomy_score(workspace_id, self._runtime.projections)
            action["autonomy_score"] = {
                "score": _as.score,
                "grade": _as.grade,
                "components": _as.components,
                "recommendation": _as.recommendation,
            }
        except Exception:  # noqa: BLE001
            pass  # best-effort metadata, not critical

        # Wave 68: persist plan to file for attention injection
        try:
            _data_dir = self._runtime.settings.system.data_dir
            if isinstance(_data_dir, str) and _data_dir and thread_id:
                _plan_dir = Path(_data_dir) / ".formicos" / "plans"
                _plan_dir.mkdir(parents=True, exist_ok=True)
                _plan_path = _plan_dir / f"{thread_id}.md"
                _plan_lines = [f"# Plan: {summary[:200]}", ""]
                if recommendation:
                    _plan_lines.append(f"**Approach:** {recommendation}")
                    _plan_lines.append("")
                if enriched_options:
                    _plan_lines.append("## Options")
                    for _i, _opt in enumerate(enriched_options, 1):
                        _label = _opt.get("label", f"Option {_i}")
                        _desc = _opt.get("description", "")
                        _plan_lines.append(f"{_i}. **{_label}:** {_desc}")
                    _plan_lines.append("")
                _plan_lines.append("## Steps")
                _plan_lines.append(
                    "*(No steps defined yet."
                    " Use mark_plan_step to add.)*"
                )
                _plan_path.write_text(
                    "\n".join(_plan_lines), encoding="utf-8",
                )
        except (OSError, TypeError):
            pass  # plan file is best-effort, not critical path

        return (result_text, action)

    # ------------------------------------------------------------------ #
    # Wave 68: plan step tracking                                          #
    # ------------------------------------------------------------------ #

    _STEP_RE = _re.compile(
        r"^- \[(\d+)\] \[(\w+)\] (.*)$",
    )

    def _mark_plan_step(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, None]:
        """Update or append a step in the thread's plan file."""
        step_index: int = inputs.get("step_index", 0)
        status: str = inputs.get("status", "pending")
        description: str = inputs.get("description", "")
        colony_id: str = inputs.get("colony_id", "")
        note: str = inputs.get("note", "")

        try:
            _data_dir = self._runtime.settings.system.data_dir
            if not isinstance(_data_dir, str) or not _data_dir:
                return ("No data directory configured.", None)
            _plan_path = (
                Path(_data_dir)
                / ".formicos"
                / "plans"
                / f"{thread_id}.md"
            )
            if not _plan_path.is_file():
                return (
                    f"No plan file for thread {thread_id}. "
                    "Use propose_plan first.",
                    None,
                )

            text = _plan_path.read_text(encoding="utf-8")
            lines = text.split("\n")

            # Find the ## Steps section
            steps_idx = -1
            for li, line in enumerate(lines):
                if line.strip() == "## Steps":
                    steps_idx = li
                    break
            if steps_idx == -1:
                lines.append("## Steps")
                steps_idx = len(lines) - 1

            # Parse existing steps
            steps: list[dict[str, Any]] = []
            step_line_indices: list[int] = []
            for li in range(steps_idx + 1, len(lines)):
                m = self._STEP_RE.match(lines[li])
                if m:
                    steps.append({
                        "index": int(m.group(1)),
                        "status": m.group(2),
                        "text": m.group(3),
                    })
                    step_line_indices.append(li)

            # Build step line
            col_suffix = (
                f" (colony {colony_id[:8]})" if colony_id else ""
            )
            note_suffix = f" — {note}" if note else ""
            desc_text = description or (
                steps[step_index]["text"].split(" — ")[0].split(
                    " (colony",
                )[0]
                if step_index < len(steps)
                else f"Step {step_index}"
            )
            new_line = (
                f"- [{step_index}] [{status}]"
                f" {desc_text}{col_suffix}{note_suffix}"
            )

            if step_index < len(steps):
                # Update existing step
                lines[step_line_indices[step_index]] = new_line
            else:
                # Append new step — remove placeholder if present
                insert_at = (
                    step_line_indices[-1] + 1
                    if step_line_indices
                    else steps_idx + 1
                )
                # Remove the "no steps" placeholder
                for li in range(steps_idx + 1, len(lines)):
                    if "No steps defined yet" in lines[li]:
                        lines.pop(li)
                        insert_at = (
                            min(insert_at, li)
                            if step_line_indices
                            else li
                        )
                        break
                lines.insert(insert_at, new_line)

            _plan_path.write_text(
                "\n".join(lines), encoding="utf-8",
            )
            return (
                f"Step [{step_index}] marked as [{status}].",
                None,
            )
        except (OSError, TypeError) as exc:
            return (f"Failed to update plan: {exc}", None)

    # ------------------------------------------------------------------ #
    # Wave 70.0 Track 5: project-level milestone tools                     #
    # ------------------------------------------------------------------ #

    def _propose_project_milestone(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, None]:
        """Add a milestone to the project-wide plan."""
        description = inputs.get("description", "").strip()
        if not description:
            return ("Error: description is required.", None)

        goal = inputs.get("goal", "").strip()

        _data_dir = self._runtime.settings.system.data_dir
        if not isinstance(_data_dir, str) or not _data_dir:
            return ("No data directory configured.", None)

        try:
            from formicos.surface.project_plan import add_milestone  # noqa: PLC0415

            plan = add_milestone(
                _data_dir,
                description,
                thread_id=thread_id,
                goal=goal,
            )
            count = len(plan.get("milestones", []))
            return (
                f"Milestone added to project plan ({count} total). "
                f"Goal: {plan.get('goal', 'N/A')}",
                None,
            )
        except (OSError, TypeError) as exc:
            return (f"Failed to add milestone: {exc}", None)

    def _complete_project_milestone(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, None]:
        """Mark a project milestone as completed."""
        milestone_index = inputs.get("milestone_index")
        if milestone_index is None:
            return ("Error: milestone_index is required.", None)
        note = inputs.get("note", "").strip()

        _data_dir = self._runtime.settings.system.data_dir
        if not isinstance(_data_dir, str) or not _data_dir:
            return ("No data directory configured.", None)

        try:
            from formicos.surface.project_plan import complete_milestone  # noqa: PLC0415

            plan = complete_milestone(
                _data_dir,
                int(milestone_index),
                note=note,
            )
            if plan.get("error"):
                return (f"Error: {plan['error']}", None)
            return (
                f"Milestone [{milestone_index}] marked as completed.",
                None,
            )
        except (OSError, TypeError, ValueError) as exc:
            return (f"Failed to complete milestone: {exc}", None)

    # ------------------------------------------------------------------ #
    # Wave 70.0 Track 7: autonomy budget visibility                       #
    # ------------------------------------------------------------------ #

    def _check_autonomy_budget(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Show the Queen her remaining daily budget and autonomy status."""
        import json as _json  # noqa: PLC0415

        from formicos.core.types import MaintenancePolicy  # noqa: PLC0415
        from formicos.surface.self_maintenance import (  # noqa: PLC0415
            compute_autonomy_score,
            estimate_blast_radius,
        )

        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return ("Workspace not found.", None)

        raw_policy = ws.config.get("maintenance_policy")
        policy = MaintenancePolicy()
        if raw_policy is not None:
            try:
                data = _json.loads(raw_policy) if isinstance(raw_policy, str) else raw_policy
                policy = MaintenancePolicy(**data)
            except Exception:  # noqa: BLE001
                pass

        dispatcher = getattr(self._runtime, "maintenance_dispatcher", None)
        daily_spend = 0.0
        active_maintenance = 0
        if dispatcher is not None:
            dispatcher._reset_daily_budget_if_needed()  # pyright: ignore[reportPrivateUsage]
            daily_spend = dispatcher._daily_spend.get(workspace_id, 0.0)  # pyright: ignore[reportPrivateUsage]
            active_maintenance = dispatcher._count_active_maintenance_colonies(  # pyright: ignore[reportPrivateUsage]
                workspace_id,
            )

        budget_limit = policy.daily_maintenance_budget
        remaining = max(0.0, budget_limit - daily_spend)

        budget = getattr(ws, "budget", None)
        total_cost = budget.total_cost if budget else 0.0

        lines = [
            "## Autonomy Budget Status",
            "",
            f"**Autonomy level:** {policy.autonomy_level}",
            f"**Daily budget:** ${budget_limit:.2f}",
            f"**Spent today:** ${daily_spend:.2f}",
            f"**Remaining:** ${remaining:.2f}",
            f"**Active maintenance colonies:** {active_maintenance}"
            f" / {policy.max_maintenance_colonies} max",
            "",
            f"**Workspace total cost:** ${total_cost:.2f}",
        ]

        if policy.auto_actions:
            lines.append(
                f"**Auto-dispatch categories:** {', '.join(policy.auto_actions)}"
            )
        else:
            lines.append("**Auto-dispatch categories:** none")

        if remaining <= 0:
            lines.extend([
                "",
                "Warning: Daily budget exhausted. No autonomous dispatch until "
                "midnight UTC reset.",
            ])
        elif remaining < budget_limit * 0.2:
            lines.extend([
                "",
                f"Warning: Budget running low ({remaining / budget_limit:.0%} remaining).",
            ])

        # Optional blast radius estimate
        task_text = inputs.get("task", "")
        if task_text:
            estimate = estimate_blast_radius(
                task=task_text,
                workspace_id=workspace_id,
                projections=self._runtime.projections,
            )
            lines.extend([
                "",
                "## Blast Radius Estimate",
                f"**Score:** {estimate.score} ({estimate.level})",
                f"**Recommendation:** {estimate.recommendation}",
            ])
            for factor in estimate.factors:
                lines.append(f"  - {factor}")

        # Autonomy score
        auto_score = compute_autonomy_score(
            workspace_id, self._runtime.projections,
        )
        lines.extend([
            "",
            "## Autonomy Score",
            f"**Score:** {auto_score.score}/100 (Grade: {auto_score.grade})",
            f"**Recommendation:** {auto_score.recommendation}",
        ])
        for component, value in auto_score.components.items():
            lines.append(f"  - {component}: {value}")

        return ("\n".join(lines), None)

    # ------------------------------------------------------------------ #
    # Wave 74 Track 3: display board posting                               #
    # ------------------------------------------------------------------ #

    async def _post_observation(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Post a structured observation to the display board."""
        from formicos.surface.operational_state import append_journal_entry  # noqa: PLC0415

        obs_type = inputs.get("type", "observation")
        priority = inputs.get("priority", "normal")
        title = inputs.get("title", "")
        content = inputs.get("content", "")

        data_dir = self._runtime.settings.system.data_dir
        append_journal_entry(
            data_dir, workspace_id,
            source="queen",
            message=content,
            heading=f"{obs_type}:{priority} — {title}",
            metadata={"display_board": True, "type": obs_type, "priority": priority},
        )
        return (f"Posted {obs_type}: {title}", None)

    # ------------------------------------------------------------------ #
    # Wave 62 Track 2: Queen direct work tools                            #
    # ------------------------------------------------------------------ #

    # Shell metacharacters that are never allowed in run_command
    _SHELL_METACHAR_RE = _re.compile(r"[|><;&`$(){}]")

    # Command allowlist for run_command
    _CMD_ALLOWLIST: dict[str, set[str] | bool] = {
        "git": {"status", "diff", "log", "blame", "show", "branch"},
        "pytest": True,
        "ruff": {"check"},
        "python": {"-m"},
        "ls": True,
        "cat": True,
        "head": True,
        "tail": True,
        "wc": True,
        "find": True,
    }

    async def _search_codebase(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Search the workspace codebase with grep."""
        query = inputs.get("query", "").strip()
        if not query:
            return ("Error: query is required.", None)
        sub_path = inputs.get("path", "")
        use_regex = inputs.get("regex", False)
        max_results = min(int(inputs.get("max_results", 20)), 50)

        # Determine search root
        ws = self._runtime.projections.workspaces.get(workspace_id)
        search_root: Path | None = None
        if ws is not None:
            ws_dir = getattr(ws, "directory", None) or getattr(ws, "repo_path", None)
            if ws_dir:
                search_root = Path(str(ws_dir))
        # Fallback: workspace files directory
        if search_root is None or not search_root.exists():
            data_dir = getattr(self._runtime, "data_dir", None)
            if data_dir:
                search_root = Path(str(data_dir)) / "workspaces" / workspace_id / "files"
        if search_root is None or not search_root.exists():
            return ("Error: workspace directory not found.", None)

        if sub_path:
            search_root = search_root / sub_path
            if not search_root.exists():
                return (f"Error: path '{sub_path}' not found.", None)

        # Try grep (available in python:3.12-slim Docker image)
        grep_args = ["grep", "-rn", "--color=never", "--max-count=5"]
        if not use_regex:
            grep_args.append("-F")  # fixed-string mode
        grep_args.extend(["--include=*.py", "--include=*.ts", "--include=*.yaml",
                          "--include=*.yml", "--include=*.json", "--include=*.md",
                          "--include=*.toml", "--include=*.txt", "--include=*.cfg"])
        grep_args.extend([query, str(search_root)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *grep_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")
        except FileNotFoundError:
            # grep not available — Python fallback
            output = self._search_codebase_fallback(
                query, search_root, use_regex, max_results,
            )
        except TimeoutError:
            return ("Error: search timed out after 10 seconds.", None)

        if not output.strip():
            return (f"No matches found for '{query}'.", None)

        # Truncate to max_results lines and output limit
        lines = output.strip().split("\n")
        if len(lines) > max_results:
            lines = lines[:max_results]
            lines.append(f"... (truncated, showing {max_results} of many matches)")
        result = "\n".join(lines)
        if len(result) > self._OUTPUT_TRUNCATE:
            result = result[:self._OUTPUT_TRUNCATE] + "\n... (truncated)"

        # Make paths relative to search root for readability
        root_str = str(search_root)
        result = result.replace(root_str + os.sep, "")
        result = result.replace(root_str + "/", "")

        return (result, None)

    @staticmethod
    def _search_codebase_fallback(
        query: str,
        root: Path,
        use_regex: bool,
        max_results: int,
    ) -> str:
        """Pure-Python fallback when grep is not available."""
        pattern = _re.compile(query if use_regex else _re.escape(query))
        matches: list[str] = []
        exts = {".py", ".ts", ".yaml", ".yml", ".json", ".md", ".toml", ".txt"}
        for p in root.rglob("*"):
            if p.suffix not in exts or not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.split("\n"), 1):
                if pattern.search(line):
                    rel = p.relative_to(root)
                    matches.append(f"{rel}:{i}:{line.rstrip()}")
                    if len(matches) >= max_results:
                        return "\n".join(matches)
        return "\n".join(matches)

    async def _run_command(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Run an allowlisted shell command."""
        command_str = inputs.get("command", "").strip()
        if not command_str:
            return ("Error: command is required.", None)
        timeout = min(int(inputs.get("timeout", 30)), 60)

        # Block shell metacharacters
        if self._SHELL_METACHAR_RE.search(command_str):
            return (
                "Error: shell metacharacters (|, >, <, ;, &, `, $) "
                "are not allowed.",
                None,
            )

        # Parse into tokens
        try:
            tokens = shlex.split(command_str)
        except ValueError as exc:
            return (f"Error: invalid command syntax: {exc}", None)
        if not tokens:
            return ("Error: empty command.", None)

        program = tokens[0]
        allowed = self._CMD_ALLOWLIST.get(program)
        if allowed is None:
            return (
                f"Error: '{program}' is not in the allowlist. "
                f"Allowed: {', '.join(sorted(self._CMD_ALLOWLIST))}",
                None,
            )

        # For commands with sub-command restrictions, check the sub-command
        if isinstance(allowed, set) and len(tokens) > 1:
            subcmd = tokens[1]
            if subcmd not in allowed:
                return (
                    f"Error: '{program} {subcmd}' is not allowed. "
                    f"Allowed sub-commands: {', '.join(sorted(allowed))}",
                    None,
                )

        # Determine working directory
        cwd: str | None = None
        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is not None:
            ws_dir = getattr(ws, "directory", None) or getattr(ws, "repo_path", None)
            if ws_dir and Path(str(ws_dir)).exists():
                cwd = str(ws_dir)

        try:
            proc = await asyncio.create_subprocess_exec(
                *tokens,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except FileNotFoundError:
            return (f"Error: '{program}' not found on PATH.", None)
        except TimeoutError:
            return (
                f"Error: command timed out after {timeout} seconds.",
                None,
            )

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        parts: list[str] = [f"Exit code: {proc.returncode}"]
        if out.strip():
            if len(out) > self._OUTPUT_TRUNCATE:
                out = out[:self._OUTPUT_TRUNCATE] + "\n... (truncated)"
            parts.append(f"stdout:\n{out}")
        if err.strip():
            if len(err) > 1000:
                err = err[:1000] + "\n... (truncated)"
            parts.append(f"stderr:\n{err}")
        if not out.strip() and not err.strip():
            parts.append("(no output)")

        return ("\n".join(parts), None)


    # ------------------------------------------------------------------ #
    # Wave 63 Track 3: Queen write tools                                   #
    # ------------------------------------------------------------------ #

    _EDIT_MAX_FILE_BYTES = 100 * 1024  # 100 KB

    def _resolve_workspace_path(
        self, workspace_id: str, rel_path: str,
    ) -> tuple[Path | None, str]:
        """Resolve workspace-relative path. Returns (abs_path, error) or (path, "")."""
        if not rel_path:
            return (None, "Error: path is required.")
        ws = self._runtime.projections.workspaces.get(workspace_id)
        ws_dir = None
        if ws is not None:
            ws_dir = getattr(ws, "directory", None) or getattr(ws, "repo_path", None)
        if not ws_dir:
            data_dir = self._runtime.settings.system.data_dir
            ws_dir = str(Path(data_dir) / "workspaces" / workspace_id / "files")

        root = Path(str(ws_dir)).resolve()
        target = (root / rel_path).resolve()
        # Path traversal check
        try:
            target.relative_to(root)
        except ValueError:
            return (None, "Error: path is outside the workspace root.")
        return (target, "")

    def _edit_file(
        self, inputs: dict[str, Any], workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Propose a file edit — returns diff preview for operator approval."""
        path_str = inputs.get("path", "")
        old_text = inputs.get("old_text", "")
        new_text = inputs.get("new_text", "")
        reason = inputs.get("reason", "")

        if not old_text or not new_text:
            return ("Error: old_text and new_text are required.", None)
        if old_text == new_text:
            return ("Error: old_text and new_text are identical.", None)

        target, err = self._resolve_workspace_path(workspace_id, path_str)
        if target is None:
            return (err, None)
        if not target.exists():
            return (f"Error: file not found: {path_str}", None)
        if not target.is_file():
            return (f"Error: not a file: {path_str}", None)

        # Reject binary/large files
        try:
            content_bytes = target.read_bytes()
        except OSError as exc:
            return (f"Error reading file: {exc}", None)
        if len(content_bytes) > self._EDIT_MAX_FILE_BYTES:
            return (
                f"Error: file too large ({len(content_bytes):,} bytes). "
                f"Max: {self._EDIT_MAX_FILE_BYTES:,} bytes.",
                None,
            )
        if b"\x00" in content_bytes[:4096]:
            return ("Error: binary files cannot be edited.", None)

        content = content_bytes.decode("utf-8", errors="replace")
        if old_text not in content:
            return ("Error: old_text not found in file.", None)

        # Build diff preview
        new_content = content.replace(old_text, new_text, 1)
        import difflib  # noqa: PLC0415
        diff_lines = list(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{path_str}",
            tofile=f"b/{path_str}",
            lineterm="",
        ))
        diff_text = "\n".join(diff_lines[:100])  # cap diff display

        meta: dict[str, Any] = {
            "tool": "edit_file",
            "preview": True,
            "path": path_str,
            "diff": diff_text,
            "old_text": old_text,
            "new_text": new_text,
            "reason": reason,
        }
        summary = (
            f"Proposed edit to `{path_str}`:\n```diff\n{diff_text}\n```"
        )
        if reason:
            summary += f"\nReason: {reason}"
        summary += "\nReply 'apply' to confirm or 'reject' to cancel."

        return (summary, meta)

    async def _run_tests(
        self, inputs: dict[str, Any], workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Run pytest and return structured results."""
        pattern = inputs.get("pattern", "")
        timeout = min(int(inputs.get("timeout", 120)), 300)

        # Determine working directory
        cwd: str | None = None
        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is not None:
            ws_dir = getattr(ws, "directory", None) or getattr(ws, "repo_path", None)
            if ws_dir and Path(str(ws_dir)).exists():
                cwd = str(ws_dir)

        import sys  # noqa: PLC0415
        cmd = [sys.executable, "-m", "pytest", "-q", "--tb=short"]
        if pattern:
            cmd.append(pattern)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout,
            )
        except FileNotFoundError:
            return ("Error: python/pytest not found on PATH.", None)
        except TimeoutError:
            return (f"Error: tests timed out after {timeout} seconds.", None)

        out = stdout.decode("utf-8", errors="replace")
        err = stderr.decode("utf-8", errors="replace")

        # Truncate output
        if len(out) > 2000:
            out = out[:2000] + "\n...(truncated)"

        # Parse summary line (e.g., "3 passed, 1 failed in 2.5s")
        parts: list[str] = [f"Exit code: {proc.returncode}"]
        parts.append(out)
        if err.strip():
            if len(err) > 500:
                err = err[:500] + "\n...(truncated)"
            parts.append(f"stderr:\n{err}")

        return ("\n".join(parts), {"tool": "run_tests", "exit_code": proc.returncode})

    def _delete_file(
        self, inputs: dict[str, Any], workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Propose deleting a file — returns confirmation request."""
        path_str = inputs.get("path", "")
        reason = inputs.get("reason", "")

        target, err = self._resolve_workspace_path(workspace_id, path_str)
        if target is None:
            return (err, None)
        if not target.exists():
            return (f"Error: file not found: {path_str}", None)

        # Get file size for context
        try:
            size = target.stat().st_size
        except OSError:
            size = 0

        meta: dict[str, Any] = {
            "tool": "delete_file",
            "preview": True,
            "path": path_str,
            "size": size,
            "reason": reason,
        }
        summary = f"Proposed deletion of `{path_str}` ({size:,} bytes)."
        if reason:
            summary += f"\nReason: {reason}"
        summary += "\nReply 'apply' or 'confirm' to proceed, or 'reject' to cancel."

        return (summary, meta)


    # ------------------------------------------------------------------ #
    # Wave 65 Track 5: Autonomous agency tools                             #
    # ------------------------------------------------------------------ #

    async def _batch_command(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Run multiple allowlisted commands in sequence."""
        commands = inputs.get("commands", [])
        if not commands or not isinstance(commands, list):
            return ("Error: commands must be a non-empty list.", None)
        if len(commands) > 10:
            return ("Error: max 10 commands per batch.", None)
        stop_on_error = inputs.get("stop_on_error", True)

        results: list[str] = []
        for i, cmd in enumerate(commands, 1):
            result_text, _ = await self._run_command(
                {"command": cmd, "timeout": 30}, workspace_id,
            )
            results.append(f"[{i}/{len(commands)}] {cmd}\n{result_text}")
            # Check for error exit code in the result
            if stop_on_error and "Exit code:" in result_text:
                code_line = [
                    ln for ln in result_text.splitlines()
                    if ln.startswith("Exit code:")
                ]
                if code_line:
                    try:
                        code = int(code_line[0].split(":")[1].strip())
                        if code != 0:
                            results.append(
                                f"(stopped: command {i} exited with {code})"
                            )
                            break
                    except (ValueError, IndexError):
                        pass
            # Also stop on validation errors from run_command
            if stop_on_error and result_text.startswith("Error:"):
                results.append(f"(stopped: command {i} failed validation)")
                break

        return ("\n\n".join(results), {"tool": "batch_command"})

    def _summarize_thread(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Produce a structured summary of a thread's history."""
        target_thread_id = inputs.get("thread_id", thread_id)
        detail = inputs.get("detail_level", "brief")

        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return ("Error: workspace not found.", None)

        thread = ws.threads.get(target_thread_id)
        if thread is None:
            return (f"Thread '{target_thread_id}' not found.", None)

        parts: list[str] = [
            f"# Thread: {thread.name or thread.id}",
            f"Status: {thread.status}",
        ]
        if thread.goal:
            parts.append(f"Goal: {thread.goal}")

        # Colony summary
        total_cost = 0.0
        total_rounds = 0
        colony_lines: list[str] = []
        for cid, colony in thread.colonies.items():
            total_cost += colony.cost
            total_rounds += colony.round_number
            status_icon = (
                "ok" if colony.status == "completed" else colony.status
            )
            line = (
                f"- {colony.display_name or cid}: "
                f"{status_icon}, {colony.round_number} rounds, "
                f"${colony.cost:.3f}"
            )
            if detail == "full":
                line += f", quality={colony.quality_score:.2f}"
                if colony.castes:
                    line += f", team={colony.castes}"
            colony_lines.append(line)

        parts.append(f"\n## Colonies ({len(thread.colonies)})")
        parts.append(
            f"Completed: {thread.completed_colony_count}, "
            f"Failed: {thread.failed_colony_count}"
        )
        if colony_lines:
            parts.extend(colony_lines)

        parts.append("\n## Totals")
        parts.append(f"Cost: ${total_cost:.3f}")
        parts.append(f"Rounds: {total_rounds}")

        # Knowledge extracted
        total_skills = sum(
            c.skills_extracted for c in thread.colonies.values()
        )
        if total_skills:
            parts.append(f"Knowledge entries extracted: {total_skills}")

        # Workflow steps
        if thread.workflow_steps:
            parts.append(f"\n## Workflow Steps ({len(thread.workflow_steps)})")
            for step in thread.workflow_steps:
                s_status = step.get("status", "pending")
                s_desc = step.get("description", "")[:80]
                parts.append(f"- [{s_status}] {s_desc}")

        # Active plan
        if thread.active_plan and detail == "full":
            plan = thread.active_plan
            parts.append("\n## Active Plan")
            parts.append(
                f"Tasks: {len(plan.get('tasks', []))}, "
                f"Groups: {len(plan.get('parallel_groups', []))}"
            )

        return ("\n".join(parts), None)

    def _draft_document(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Write a structured document to the workspace."""
        rel_path = inputs.get("path", "")
        content = inputs.get("content", "")
        mode = inputs.get("mode", "overwrite")

        if not rel_path or not content:
            return ("Error: path and content are required.", None)
        if mode not in ("overwrite", "prepend", "append"):
            return ("Error: mode must be overwrite, prepend, or append.", None)

        # Resolve workspace directory
        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return ("Error: workspace not found.", None)
        ws_dir = getattr(ws, "directory", None) or getattr(ws, "repo_path", None)
        if not ws_dir:
            return ("Error: workspace has no directory.", None)

        target = Path(str(ws_dir)) / rel_path
        # Security: prevent path traversal
        try:
            target.resolve().relative_to(Path(str(ws_dir)).resolve())
        except ValueError:
            return ("Error: path traversal not allowed.", None)

        target.parent.mkdir(parents=True, exist_ok=True)

        if mode == "overwrite":
            target.write_text(content, encoding="utf-8")
        elif mode == "prepend":
            existing = ""
            if target.exists():
                existing = target.read_text(encoding="utf-8")
            target.write_text(content + "\n" + existing, encoding="utf-8")
        elif mode == "append":
            existing = ""
            if target.exists():
                existing = target.read_text(encoding="utf-8")
            target.write_text(existing + "\n" + content, encoding="utf-8")

        size = target.stat().st_size
        return (
            f"Written {size:,} bytes to {rel_path} (mode={mode}).",
            {"tool": "draft_document", "path": rel_path, "mode": mode},
        )

    async def _set_workspace_tags(
        self,
        inputs: dict[str, Any],
        workspace_id: str,
        thread_id: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Set soft taxonomy tags on a workspace."""
        import json as _json  # noqa: PLC0415

        from formicos.core.events import WorkspaceConfigChanged  # noqa: PLC0415

        raw_tags = inputs.get("tags", [])
        if not isinstance(raw_tags, list):
            return ("Error: tags must be a list of strings.", None)

        # Normalize: lowercase, strip, dedup, cap
        tags: list[str] = []
        seen: set[str] = set()
        for t in raw_tags:
            if not isinstance(t, str):
                continue
            normalized = t.strip().lower()[:50]
            if normalized and normalized not in seen:
                tags.append(normalized)
                seen.add(normalized)
            if len(tags) >= 20:
                break

        ws = self._runtime.projections.workspaces.get(workspace_id)
        if ws is None:
            return ("Error: workspace not found.", None)

        old_raw = ws.config.get("taxonomy_tags")
        old_str = str(old_raw) if old_raw is not None else None

        await self._runtime.emit_and_broadcast(WorkspaceConfigChanged(
            seq=0,
            timestamp=_now(),
            address=workspace_id,
            workspace_id=workspace_id,
            field="taxonomy_tags",
            old_value=old_str,
            new_value=_json.dumps(tags),
        ))

        return (
            f"Workspace tags set: {', '.join(tags)}",
            {"tool": "set_workspace_tags", "tags": tags},
        )

    def _list_addons(self) -> tuple[str, dict[str, Any] | None]:
        """List installed addons with capability metadata for Queen routing."""
        manifests: list[Any] = getattr(self, "_addon_manifests", []) or []

        parts: list[str] = ["# Installed Addons"]
        if not manifests:
            parts.append("\nNo addons installed.")
            return ("\n".join(parts), None)

        # Wave 70.0: capability-based bridge health (no addon-name branching)
        _addon_ctx: dict[str, Any] = getattr(
            self, "_addon_runtime_context", {},
        ) or {}
        _bridge_health_fn = _addon_ctx.get("get_bridge_health")

        for m in manifests:
            parts.append(f"\n**{m.name}**: {m.description}")
            if m.content_kinds:
                parts.append(f"  Content: {', '.join(m.content_kinds)}")
            if m.path_globs:
                parts.append(f"  Files: {', '.join(m.path_globs)}")
            if m.search_tool:
                parts.append(f"  Search via: {m.search_tool}")
            # Surface refresh/index path from manual triggers
            for trigger in m.triggers:
                if trigger.type == "manual":
                    parts.append(f"  Index via: {trigger.handler}")
            tool_names = [t.name for t in m.tools]
            if tool_names:
                parts.append(f"  Tools: {', '.join(tool_names)}")

        # Capability-based: surface bridge health if available
        if callable(_bridge_health_fn):
            try:
                bh = _bridge_health_fn()
                parts.append(
                    f"\n## Bridge Status: "
                    f"{bh.get('connectedServers', 0)} connected, "
                    f"{bh.get('unhealthyServers', 0)} unhealthy, "
                    f"{bh.get('totalRemoteTools', 0)} remote tools"
                )
            except Exception:  # noqa: BLE001
                pass

        parts.append(f"\nTotal: {len(manifests)} addons")
        return ("\n".join(parts), None)

    async def _trigger_addon(
        self, inputs: dict[str, Any],
    ) -> tuple[str, dict[str, Any] | None]:
        """Manually fire an addon trigger via the TriggerDispatcher."""
        import inspect as _insp  # noqa: PLC0415

        addon_name = inputs.get("addon_name", "")
        handler_ref = inputs.get("handler", "")

        if not addon_name or not handler_ref:
            return ("Error: addon_name and handler are required.", None)

        # Access the trigger dispatcher from the app state
        app = getattr(self._runtime, "_app", None)
        trigger_dispatcher = (
            getattr(app.state, "trigger_dispatcher", None)
            if app else None
        )

        # Validate the trigger exists via fire_manual
        if trigger_dispatcher is not None:
            result = trigger_dispatcher.fire_manual(addon_name, handler_ref)
            if result is None:
                return (f"No manual trigger found: {addon_name}::{handler_ref}", None)

        # Resolve and execute the handler
        try:
            from formicos.surface.addon_loader import _resolve_handler  # noqa: PLC0415

            handler_fn = _resolve_handler(addon_name, handler_ref)
            ctx = getattr(self, "_addon_runtime_context", None)
            sig = _insp.signature(handler_fn)
            if "runtime_context" in sig.parameters:
                await handler_fn(runtime_context=ctx)
            else:
                await handler_fn()
            return (
                f"Manual trigger fired: {addon_name}::{handler_ref}",
                {"action": "trigger_addon", "addon": addon_name, "handler": handler_ref},
            )
        except Exception as exc:  # noqa: BLE001
            return (f"Failed to trigger {addon_name}::{handler_ref}: {exc}", None)


__all__ = ["DELEGATE_THREAD", "QueenToolDispatcher"]
