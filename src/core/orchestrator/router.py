"""
FormicOS v0.8.0 -- Subcall Router

Bridges the synchronous REPL thread to the async agent execution pipeline.
When ``formic_subcall()`` is invoked from inside ``exec()``, the REPL thread
calls ``asyncio.run_coroutine_threadsafe()`` which schedules
``route_subcall()`` on the main event loop.

The router:
  1. Creates a NEW Agent via AgentFactory (full model resolution, tool injection)
  2. Executes the agent with BLANK context (only system prompt + task + data)
  3. Returns the agent's output string

Sub-agents do NOT inherit the Root_Architect's context tree, history, or
any parent state.  They start clean.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.agents import AgentFactory

logger = logging.getLogger("formicos.orchestrator.router")

# Cap data_slice to prevent context overflow in sub-agent prompt
_MAX_DATA_SLICE_CHARS = 20_000


class SubcallRouter:
    """Routes ``formic_subcall()`` requests to ephemeral sub-agents.

    Parameters
    ----------
    factory : AgentFactory
        Pre-configured factory with model registry, recipes, and MCP client.
    workspace_root : str
        Workspace path passed to created agents.
    colony_id : str
        Colony identifier for agent scoping.
    agent_timeout : float
        Maximum seconds for sub-agent execution.
    """

    def __init__(
        self,
        factory: AgentFactory,
        workspace_root: str,
        colony_id: str = "",
        agent_timeout: float = 240.0,
    ) -> None:
        self._factory = factory
        self._workspace_root = workspace_root
        self._colony_id = colony_id
        self._agent_timeout = agent_timeout
        self._subcall_log: list[dict[str, Any]] = []

    async def route_subcall(
        self,
        task_description: str,
        data_slice: str,
        target_caste: str = "Coder",
    ) -> str:
        """Create and execute a sub-agent for a REPL subcall.

        This coroutine runs on the main event loop (scheduled by
        ``asyncio.run_coroutine_threadsafe`` from the REPL thread).

        Parameters
        ----------
        task_description : str
            The task the sub-agent should accomplish.
        data_slice : str
            Data context provided to the sub-agent (may be empty).
        target_caste : str
            Caste for the sub-agent (looked up via AgentFactory).

        Returns
        -------
        str
            The sub-agent's final output text.
        """
        subcall_id = f"subcall-{uuid.uuid4().hex[:8]}"
        caste_lower = target_caste.lower()

        logger.info(
            "SubcallRouter: creating %s agent '%s' for task: %.100s",
            caste_lower, subcall_id, task_description,
        )

        # 1. Create the sub-agent via the full AgentFactory pipeline
        try:
            agent = self._factory.create(
                agent_id=subcall_id,
                caste=caste_lower,
                workspace_root=self._workspace_root,
                colony_id=self._colony_id,
            )
        except Exception as exc:
            msg = f"Failed to create {caste_lower} sub-agent: {exc}"
            logger.error(msg)
            return f"ERROR: {msg}"

        # 2. Build BLANK context — no parent history, no context tree assembly
        context = f"SUBCALL TASK: {task_description}"
        if data_slice:
            capped = data_slice[:_MAX_DATA_SLICE_CHARS]
            if len(data_slice) > _MAX_DATA_SLICE_CHARS:
                capped += (
                    f"\n... (data truncated to {_MAX_DATA_SLICE_CHARS:,} chars)"
                )
            context += f"\n\nDATA:\n{capped}"

        round_goal = task_description

        # 3. Execute the sub-agent's inference loop
        try:
            output = await asyncio.wait_for(
                agent.execute(
                    context=context,
                    round_goal=round_goal,
                    routed_messages=None,
                    skill_context=None,
                    callbacks=None,
                ),
                timeout=self._agent_timeout,
            )
        except asyncio.TimeoutError:
            msg = (
                f"Sub-agent '{subcall_id}' timed out "
                f"after {self._agent_timeout}s"
            )
            logger.warning(msg)
            return f"ERROR: {msg}"
        except Exception as exc:
            msg = (
                f"Sub-agent '{subcall_id}' failed: "
                f"{type(exc).__name__}: {str(exc)[:500]}"
            )
            logger.error(msg)
            return f"ERROR: {msg}"

        result = output.output or "(no output from sub-agent)"

        # 4. Log for diagnostics
        self._subcall_log.append({
            "subcall_id": subcall_id,
            "caste": caste_lower,
            "task": task_description[:200],
            "output_length": len(result),
            "tokens_used": output.tokens_used,
            "tool_calls": len(output.tool_calls),
        })

        logger.info(
            "SubcallRouter: '%s' completed — %d chars, %d tokens, %d tool calls",
            subcall_id, len(result), output.tokens_used, len(output.tool_calls),
        )

        return result

    @property
    def subcall_log(self) -> list[dict[str, Any]]:
        """Return the diagnostic log of all subcalls made."""
        return list(self._subcall_log)
