"""
FormicOS v0.6.0 -- Agents

LLM execution units that receive context, stream responses from an inference
backend, buffer and execute tool calls, and return structured output.

Two sources for tool calls (both supported):
  1. Structured: delta.tool_calls in streaming response (OpenAI standard)
  2. Content-based: <tool_call>{JSON}</tool_call> in text (llama.cpp / Qwen)

Both paths merge into the same execution pipeline.

This module is consumed by the orchestrator; it must NOT import from
orchestrator, server, or any other high-level module.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import json
import logging
import os
import posixpath
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable
from urllib.parse import quote_plus

import httpx
from json_repair import repair_json
from src.llm_client import LLMClient
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models import (
    AgentState,
    AgentStatus,
    BuiltinCaste,
    CasteConfig,
    FormicOSConfig,
    ModelRegistryEntry,
    SubcasteMapEntry,
    SubcasteTier,
)

logger = logging.getLogger("formicos.agents")

# ── Regex for extracting <tool_call>...</tool_call> XML wrappers ─────────
_TC_XML_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)

# ── Built-in tool schemas (proper parameters so the LLM knows required args) ──
_BUILTIN_TOOL_SCHEMAS: dict[str, dict] = {
    "file_read": {
        "description": "Read the contents of a file in the workspace. Returns the file text.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the workspace (e.g. 'snake_game.py', 'src/main.js')",
                },
            },
            "required": ["path"],
        },
    },
    "file_write": {
        "description": "Write content to a file in the workspace. Creates the file if it does not exist, overwrites if it does.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the workspace (e.g. 'snake_game.py')",
                },
                "content": {
                    "type": "string",
                    "description": "The full content to write to the file",
                },
            },
            "required": ["path", "content"],
        },
    },
    "file_delete": {
        "description": "Delete a file from the workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file to delete",
                },
            },
            "required": ["path"],
        },
    },
    "code_execute": {
        "description": (
            "Execute Python in the workspace. Accepts either raw Python code "
            "(executed with python -c) or a python command string such as "
            "'python snake_game.py' or 'python -m pytest -q'. Returns stdout/stderr."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code or python command string. "
                        "Do not pass non-python shell commands."
                    ),
                },
            },
            "required": ["code"],
        },
    },
    "qdrant_search": {
        "description": "Search the project knowledge base (RAG) for relevant documents. Returns matching text chunks.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                },
            },
            "required": ["query"],
        },
    },
    "fetch": {
        "description": "Fetch content from a URL. Returns the response body as text.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
            },
            "required": ["url"],
        },
    },
    "web_search": {
        "description": "Search the web and return top results with titles and links.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query text",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5)",
                },
            },
            "required": ["query"],
        },
    },
    # ── CFO / Expense Tools ──────────────────────────────────────────────
    "expense_request": {
        "description": (
            "Create an expense request for external API access. "
            "This request must be approved and signed by the CFO before "
            "the egress proxy will forward it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "amount": {
                    "type": "number",
                    "description": "Expense amount in USD",
                },
                "target_api": {
                    "type": "string",
                    "description": "Target API URL (must start with https://)",
                },
                "justification": {
                    "type": "string",
                    "description": "Business justification for the expense",
                },
            },
            "required": ["amount", "target_api", "justification"],
        },
    },
    "expense_review": {
        "description": (
            "Review a pending expense request. Returns approval recommendation "
            "with budget analysis. CFO-only tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "Expense request nonce/ID to review",
                },
            },
            "required": ["request_id"],
        },
    },
    "expense_approve": {
        "description": (
            "Approve and cryptographically sign an expense request with the "
            "colony's Ed25519 private key. CFO-only tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "Expense request nonce/ID to approve",
                },
            },
            "required": ["request_id"],
        },
    },
    "expense_reject": {
        "description": "Reject an expense request with a reason. CFO-only tool.",
        "parameters": {
            "type": "object",
            "properties": {
                "request_id": {
                    "type": "string",
                    "description": "Expense request nonce/ID to reject",
                },
                "reason": {
                    "type": "string",
                    "description": "Reason for rejection",
                },
            },
            "required": ["request_id", "reason"],
        },
    },
}

# ── Default approval-gated tools ─────────────────────────────────────────
DEFAULT_APPROVAL_REQUIRED: list[str] = ["file_write", "file_delete", "code_execute"]

# Safe MCP defaults for castes that do not explicitly set mcp_tools.
# Prevents "empty = all" from inheriting unrelated domain-specific MCP servers.
_SAFE_DEFAULT_MCP_PREFIXES = (
    "filesystem",
    "fetch",
    "memory",
    "sequentialthinking",
    "wikipedia",
    "tavily",
)


_DYNAMIC_MCP_MANAGEMENT_TOOL_NAMES = (
    "mcp-add", "mcp_add",
    "mcp-remove", "mcp_remove",
    "mcp-config-set", "mcp_config_set",
    "mcp-exec", "mcp_exec",
)


def _is_safe_default_mcp_tool_id(tool_id: str) -> bool:
    return str(tool_id or "").lower().startswith(_SAFE_DEFAULT_MCP_PREFIXES)


def _is_dynamic_mcp_management_tool(tool_name: str) -> bool:
    name = str(tool_name or "").lower()
    if not name:
        return False
    for base in _DYNAMIC_MCP_MANAGEMENT_TOOL_NAMES:
        if (
            name == base
            or name.endswith("__" + base)
            or name.endswith(":" + base)
            or name.endswith("/" + base)
            or name.endswith("." + base)
        ):
            return True
    return False

# ── Default system prompts (fallback when prompt files are absent) ───────
DEFAULT_PROMPTS: dict[str, str] = {
    "manager": (
        "You are the Manager of a colony of AI agents. "
        "Your role is to set round goals, evaluate progress, "
        "and decide when the task is complete.\n\n"
        "At each round, you receive summaries of all agent outputs "
        "and the current task state. You must respond with JSON:\n"
        '{"goal": "<round goal>", "terminate": false}\n'
        "or\n"
        '{"goal": "", "terminate": true, '
        '"final_answer": "<answer>"}\n'
    ),
    "architect": (
        "You are an Architect agent. You design solutions, "
        "plan implementations, and produce architectural documents.\n\n"
        "Respond with JSON:\n"
        '{"key": "<what you provide>", '
        '"query": "<what you need from others>", '
        '"work": "<your output>"}\n'
    ),
    "coder": (
        "You are a Coder agent. You write, modify, and debug code. "
        "You work in a shared workspace and must respect file locks.\n\n"
        "Respond with JSON:\n"
        '{"key": "<what you provide>", '
        '"query": "<what you need from others>", '
        '"work": "<your code output>", '
        '"files_modified": ["<path>", ...]}\n'
    ),
    "reviewer": (
        "You are a Reviewer agent. You review code, run tests, "
        "and identify bugs or improvements.\n\n"
        "Respond with JSON:\n"
        '{"key": "<what you provide>", '
        '"query": "<what you need from others>", '
        '"work": "<your review>", '
        '"test_results": {"passed": 0, "failed": 0}}\n'
    ),
    "researcher": (
        "You are a Researcher agent. You search documentation, "
        "find relevant information, and synthesize findings.\n\n"
        "Respond with JSON:\n"
        '{"key": "<what you provide>", '
        '"query": "<what you need from others>", '
        '"work": "<your findings>"}\n'
    ),
}


# ═════════════════════════════════════════════════════════════════════════════
# AgentOutput — structured result from a single agent execution
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation during agent execution."""

    tool_name: str
    arguments: dict[str, Any]
    result: str
    approved: bool = True


@dataclass
class AgentOutput:
    """Structured output from Agent.execute()."""

    approach: str = ""
    alternatives_rejected: str = ""
    output: str = ""
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    tokens_used: int = 0
    tokens_prompt: int = 0
    tokens_completion: int = 0


class ContextExceededError(Exception):
    """Raised when the assembled messages exceed the hard context window limit.

    The Orchestrator catches this and converts it into a SYSTEM_HALT message
    returned to the agent, preventing the LLM request from ever being sent.
    """


# ═════════════════════════════════════════════════════════════════════════════
# Agent
# ═════════════════════════════════════════════════════════════════════════════


class Agent:
    """
    A single colony agent.  Lightweight — constructs prompts, streams LLM
    responses, buffers tool calls, executes them, and returns AgentOutput.
    Agents are stateless between rounds; all memory comes from the Context Tree.
    """

    def __init__(
        self,
        id: str,
        caste: str,
        system_prompt: str,
        model_client: LLMClient,
        model_name: str,
        tools: list[dict[str, Any]] | None = None,
        config: dict[str, Any] | None = None,
        rag_engine: Any | None = None,
    ) -> None:
        self.id = id
        self.caste = caste
        self.system_prompt = system_prompt
        self.model_client = model_client
        self.model_name = model_name
        self.tools = tools or []
        self.config = config or {}
        self.rag_engine = rag_engine

        # Configurable fields from config dict
        self.max_tokens: int = self.config.get("max_tokens", 5000)
        self.temperature: float = self.config.get("temperature", 0.0)
        self.seed: int | None = self.config.get("seed", None)
        self.context_length: int = self.config.get("context_length", 4096)
        self.workspace_root: str = self.config.get("workspace_root", "./workspace")
        cfg_approval = self.config.get("approval_required", list(DEFAULT_APPROVAL_REQUIRED))
        if not isinstance(cfg_approval, list):
            cfg_approval = list(DEFAULT_APPROVAL_REQUIRED)
        # Dynamic MCP session-management tools are always operator-gated.
        self.approval_required: list[str] = list(dict.fromkeys(
            list(cfg_approval) + list(_DYNAMIC_MCP_MANAGEMENT_TOOL_NAMES)
        ))

        # Draft-refine pipeline (optional)
        self.refine_client: LLMClient | None = self.config.get("refine_client")
        self.refine_model: str | None = self.config.get("refine_model")
        self.refine_prompt: str = self.config.get(
            "refine_prompt",
            "Review and correct this draft for accuracy and completeness.",
        )

        # MCP gateway callback for unknown tools
        self.mcp_gateway_callback: (
            Callable[[str, dict], Awaitable[str]] | None
        ) = self.config.get("mcp_gateway_callback")

        # Escalation fallback chain (from CasteRecipe, if any)
        self.escalation_fallback: list = self.config.get("escalation_fallback", [])

        # Cancellation flag
        self._cancelled = False

        # Runtime state (for status tracking)
        self.state = AgentState(agent_id=id, caste=caste)

    # ── Cancellation ─────────────────────────────────────────────────────

    def cancel(self) -> None:
        """Signal the agent to abort the current execution."""
        self._cancelled = True

    def _check_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError(f"Agent '{self.id}' was cancelled")

    # ── Raw Execution (Phase 1 Manager) ─────────────────────────────────

    async def execute_raw(
        self,
        system_override: str,
        user_prompt: str,
    ) -> str:
        """
        Direct LLM call without the agent execution wrapper.

        Used for Phase 1 manager goal-setting where a custom JSON schema
        is needed ({"goal", "terminate", "final_answer"}) that conflicts
        with the standard execute() wrapper ({"approach", "output", "status"}).
        """
        self._cancelled = False
        self.state.status = AgentStatus.THINKING

        try:
            response = await self.model_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_override},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1000,
            )
            return response.choices[0].message.content or "{}"
        except Exception as e:
            logger.error("Agent '%s' execute_raw failed: %s", self.id, e)
            return "{}"
        finally:
            self.state.status = AgentStatus.IDLE

    # ── Intent Generation (Phase 2) ─────────────────────────────────────

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def generate_intent(
        self,
        task: str,
        round_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, str]:
        """
        Generate routing descriptors (key + query) for DyTopo routing.

        Uses a strict prompt demanding specificity (per AnyLoom patterns)
        and low temperature (0.1) for focused descriptor generation.

        Args:
            task: The colony task description.
            round_history: List of previous round summaries.

        Returns:
            {"key": "<what this agent provides>", "query": "<what it needs>"}
            with role-enriched descriptors for better embedding separation.
        """
        self._cancelled = False
        self.state.status = AgentStatus.THINKING

        caste_name = self.caste.value if hasattr(self.caste, "value") else str(self.caste).lower()

        history_block = ""
        if round_history:
            summaries = []
            for rh in round_history[-3:]:
                goal = rh.get("goal", "N/A")
                agent_outs = rh.get("agent_outputs", {})
                out_summary = "; ".join(
                    f"{aid}: {info.get('output', '')[:100]}"
                    for aid, info in agent_outs.items()
                ) if agent_outs else rh.get("summary", "")
                summaries.append(
                    f"Round {rh.get('round', '?')} (goal: {goal}): {out_summary}"
                )
            history_block = "\n\nROUND HISTORY:\n" + "\n".join(summaries)

        prompt = (
            f"You are a {caste_name}. Given the task and round history, "
            f"generate routing descriptors.\n\n"
            f"TASK: {task}\n"
            f"{history_block}\n\n"
            "KEY: What SPECIFIC output will you produce this round?\n"
            "  Be concrete: mention file names, function signatures, "
            "design patterns, test cases.\n"
            '  BAD: "code output"  '
            'GOOD: "Python snake_game.py with Game class, move(), '
            'render(), collision detection"\n\n'
            "QUERY: What SPECIFIC information do you need from other agents?\n"
            '  BAD: "general input"  '
            'GOOD: "Architecture design with class diagram and module '
            'boundaries"\n'
            "  If you need nothing, write exactly: "
            '"I have sufficient information to proceed independently."\n\n'
            'Respond with ONLY a JSON object: {"key": "...", "query": "..."}'
        )

        try:
            response = await self.model_client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=512,
                temperature=0.1,  # Low temp for focused descriptors
            )

            raw = response.choices[0].message.content or "{}"
            try:
                parsed = json.loads(repair_json(raw))
            except (json.JSONDecodeError, Exception):
                parsed = {}

            raw_key = parsed.get("key", f"{caste_name} output")
            raw_query = parsed.get("query", "general input")

            # Role-enrich descriptors before embedding (per AnyLoom pattern)
            return {
                "key": f"As a {caste_name}: {raw_key}",
                "query": f"As a {caste_name}: {raw_query}",
            }
        finally:
            self.state.status = AgentStatus.IDLE

    # ── Main Execution (Phase 4) ─────────────────────────────────────────

    async def execute(
        self,
        context: str,
        round_goal: str,
        routed_messages: list[str] | None = None,
        skill_context: str | None = None,
        callbacks: dict[str, Any] | None = None,
    ) -> AgentOutput:
        """
        Execute the agent's task with full context and return AgentOutput.

        Args:
            context: Assembled context string from the Context Tree.
            round_goal: The goal for this round (set by manager).
            routed_messages: Outputs from upstream agents (via DyTopo routing).
            skill_context: Optional skill context from SkillBank.
            callbacks: Optional dict with keys:
                - stream_callback(agent_id, token) -> None
                - tool_call_callback(agent_id, tool_name, args, result="") -> None
                - approval_callback(agent_id, tool_name, args) -> bool

        Returns:
            AgentOutput with approach, alternatives_rejected, output, tool_calls, tokens_used.
        """
        self._cancelled = False
        self.state.status = AgentStatus.EXECUTING
        callbacks = callbacks or {}

        stream_callback = callbacks.get("stream_callback")
        tool_call_callback = callbacks.get("tool_call_callback")
        approval_callback = callbacks.get("approval_callback")

        try:
            return await self._execute_inner(
                context=context,
                round_goal=round_goal,
                routed_messages=routed_messages or [],
                skill_context=skill_context,
                stream_callback=stream_callback,
                tool_call_callback=tool_call_callback,
                approval_callback=approval_callback,
            )
        except asyncio.CancelledError:
            return AgentOutput(output=f"Agent '{self.id}' was cancelled.")
        except ContextExceededError:
            raise  # Propagate to Orchestrator for SYSTEM_HALT handling
        except Exception as e:
            logger.error("Agent '%s' execution failed: %s", self.id, e)
            return AgentOutput(output=f"ERROR: {type(e).__name__}: {str(e)[:500]}")
        finally:
            self.state.status = AgentStatus.IDLE

    async def _execute_inner(
        self,
        context: str,
        round_goal: str,
        routed_messages: list[str],
        skill_context: str | None,
        stream_callback: Any,
        tool_call_callback: Any,
        approval_callback: Any,
    ) -> AgentOutput:
        """Core execution logic, separated for clean error handling."""

        # ── Build prompt ─────────────────────────────────────────────────
        messages_block = ""
        if routed_messages:
            messages_block = (
                "\n\nMESSAGES FROM CONNECTED AGENTS:\n"
                + "\n---\n".join(routed_messages)
            )

        skill_block = ""
        if skill_context:
            skill_block = f"\n\nRELEVANT SKILLS:\n{skill_context}"

        tool_guidance = ""
        if self.tools:
            tool_names = [
                t.get("id", t.get("name", "?"))
                for t in self.tools
                if t.get("enabled", True)
            ]
            if tool_names:
                tool_guidance = (
                    "\n\nAVAILABLE TOOLS: " + ", ".join(tool_names) + "\n"
                    "Use tools to accomplish concrete work. "
                    "Call tools proactively -- do not just describe what you would do.\n"
                    "Do not loop on the same tool call with the same arguments.\n"
                    "If file_read returns NOT FOUND, do not retry the same missing path repeatedly -- "
                    "create the file with file_write or choose an existing file from the hint list.\n"
                    "For code_execute, pass Python code or a python command only (e.g. "
                    "'python snake_game.py' or 'python -m pytest -q').\n"
                    "Do not use MCP server-management tools (mcp-add/mcp-remove/mcp-config-set/mcp-exec) "
                    "unless the task explicitly requires changing the MCP server setup."
                )

        user_prompt = (
            f"ROUND GOAL: {round_goal}\n\n"
            f"CONTEXT:\n{context}"
            f"{messages_block}"
            f"{skill_block}"
            f"{tool_guidance}\n\n"
            "Produce your work for this round. Be concrete and specific.\n"
            "Write actual code, designs, reviews, or analysis as "
            "appropriate for your role.\n"
            "Do NOT wrap your output in JSON — just produce your deliverables directly.\n"
            "IMPORTANT: If you received your previous round output above, "
            "BUILD ON IT — advance the work, do not regenerate the same content.\n"
            "Use your tools (file_write, code_execute) to create actual files, not just descriptions."
        )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ── Hard context window circuit breaker ───────────────────────────
        # Must run BEFORE soft truncation: if the assembled messages
        # exceed the hard context window, halt immediately rather than
        # silently truncating and producing degraded output.
        self._check_context_limit(messages)

        # ── Soft token budget enforcement (legacy) ────────────────────────
        messages = self._enforce_token_budget(messages)

        # ── Build OpenAI tools array ─────────────────────────────────────
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if self.seed is not None:
            kwargs["seed"] = self.seed

        if self.tools:
            openai_tools = []
            for t in self.tools:
                openai_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": t.get("id", t.get("name", "unknown")),
                            "description": t.get("description", ""),
                            "parameters": t.get(
                                "parameters", {"type": "object", "properties": {}}
                            ),
                        },
                    }
                )
            if openai_tools:
                kwargs["tools"] = openai_tools

        # ── Streaming loop with tool call handling ───────────────────────
        all_tool_records: list[ToolCallRecord] = []
        total_tokens = 0
        prompt_tokens = 0
        completion_tokens = 0
        final_content = ""
        _MAX_TOOL_ROUNDS = 10
        _MAX_TOTAL_TOOL_CALLS = 32
        _MAX_IDENTICAL_TOOL_CALLS = 2
        _MAX_PER_TOOL_CALLS = 8
        _CACHEABLE_READ_TOOLS = {"file_read", "qdrant_search"}
        _MUTATING_TOOLS = {"file_write", "file_delete", "code_execute"}
        _tool_round = 0
        _tool_signature_counts: dict[str, int] = {}
        _tool_name_counts: dict[str, int] = {}
        _tool_signature_last_result: dict[str, str] = {}
        _tool_signature_last_epoch: dict[str, int] = {}
        _workspace_mutation_epoch = 0

        while True:
            self._check_cancelled()
            _tool_round += 1
            if _tool_round > _MAX_TOOL_ROUNDS:
                logger.warning(
                    "Agent '%s' hit max tool rounds (%d) — breaking loop",
                    self.id, _MAX_TOOL_ROUNDS,
                )
                break
            kwargs["messages"] = messages

            response = await self.model_client.chat.completions.create(
                **kwargs, stream=True
            )

            full_content = ""
            tool_calls_buffer: dict[int, dict[str, str]] = {}
            finish_reason: str | None = None

            async for chunk in response:
                self._check_cancelled()
                choice = chunk.choices[0]
                delta = choice.delta

                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason

                # Accumulate usage from chunks that provide it
                if hasattr(chunk, "usage") and chunk.usage:
                    if hasattr(chunk.usage, "total_tokens") and chunk.usage.total_tokens:
                        total_tokens = chunk.usage.total_tokens
                    if hasattr(chunk.usage, "prompt_tokens") and chunk.usage.prompt_tokens:
                        prompt_tokens = chunk.usage.prompt_tokens
                    if hasattr(chunk.usage, "completion_tokens") and chunk.usage.completion_tokens:
                        completion_tokens = chunk.usage.completion_tokens

                # Text stream
                if delta.content:
                    full_content += delta.content
                    if stream_callback:
                        await stream_callback(self.id, delta.content)

                # Source 1: Structured tool calls (delta.tool_calls)
                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id and not tool_calls_buffer[idx]["id"]:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function:
                            if (
                                tc.function.name
                                and not tool_calls_buffer[idx]["name"]
                            ):
                                tool_calls_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx][
                                    "arguments"
                                ] += tc.function.arguments

            # ── Merge tool calls from both sources ───────────────────────
            calls: list[dict[str, str]] = []
            openai_tool_calls: list[dict[str, Any]] = []

            # Source 1: Structured delta.tool_calls
            # llama.cpp returns finish_reason="tool", OpenAI returns "tool_calls"
            if finish_reason in ("tool_calls", "tool") and tool_calls_buffer:
                for idx in sorted(tool_calls_buffer.keys()):
                    buf = tool_calls_buffer[idx]
                    call_id = buf["id"] or f"tc_{idx}"
                    t_name = buf["name"]
                    t_args = buf["arguments"]
                    if not t_name:
                        continue
                    calls.append(
                        {"id": call_id, "name": t_name, "arguments": t_args}
                    )
                    openai_tool_calls.append(
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": t_name, "arguments": t_args},
                        }
                    )

            # Source 2: Content-based fallback (<tool_call> XML tags)
            # Use regex only to extract the XML wrapper; json_repair for the JSON body
            if not calls and full_content:
                for i, m in enumerate(_TC_XML_RE.finditer(full_content)):
                    try:
                        raw_json = m.group(1)
                        repaired = repair_json(raw_json)
                        tc = json.loads(repaired)
                        cid = f"content_tc_{i}"
                        name = tc.get("name") or tc.get("tool") or ""
                        if not isinstance(name, str):
                            continue
                        name = name.strip()
                        if not name:
                            continue
                        args_raw = json.dumps(tc.get("arguments", {}))
                        calls.append(
                            {"id": cid, "name": name, "arguments": args_raw}
                        )
                        openai_tool_calls.append(
                            {
                                "id": cid,
                                "type": "function",
                                "function": {"name": name, "arguments": args_raw},
                            }
                        )
                    except (json.JSONDecodeError, AttributeError, TypeError):
                        continue

                if calls:
                    logger.info(
                        "Agent '%s' -- parsed %d tool call(s) from content text",
                        self.id,
                        len(calls),
                    )

            # ── Execute tool calls ───────────────────────────────────────
            if calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": full_content or None,
                        "tool_calls": openai_tool_calls,
                    }
                )

                for call in calls:
                    call_id = call["id"]
                    t_name = call["name"]

                    try:
                        t_args = (
                            json.loads(call["arguments"]) if call["arguments"] else {}
                        )
                    except json.JSONDecodeError:
                        t_args = {}

                    # Normalize workspace paths so './x.py' and 'x.py' share
                    # the same cache signature (and the same execution path).
                    if t_name in self._PATH_TOOLS and "path" in t_args:
                        t_args["path"] = self._normalize_tool_path(
                            str(t_args["path"])
                        )

                    # Guardrail: suppress repeated identical calls and runaway tool loops.
                    try:
                        sig_args = json.dumps(t_args, sort_keys=True, default=str)
                    except Exception:
                        sig_args = str(t_args)
                    call_signature = t_name + "|" + sig_args

                    sig_count = _tool_signature_counts.get(call_signature, 0)
                    tool_count = _tool_name_counts.get(t_name, 0)
                    _tool_signature_counts[call_signature] = sig_count + 1
                    _tool_name_counts[t_name] = tool_count + 1

                    approved = True
                    result_str = ""
                    if len(all_tool_records) >= _MAX_TOTAL_TOOL_CALLS:
                        result_str = (
                            "GUARDRAIL: Tool call suppressed due to max tool-call budget "
                            f"({_MAX_TOTAL_TOOL_CALLS}) for this agent turn."
                        )
                        approved = False
                    elif (
                        t_name in _CACHEABLE_READ_TOOLS
                        and sig_count >= 1
                        and _tool_signature_last_epoch.get(call_signature, -1) == _workspace_mutation_epoch
                    ):
                        prior = _tool_signature_last_result.get(call_signature, "")
                        result_str = (
                            "GUARDRAIL: Duplicate read/search call suppressed in the same workspace state. "
                            "Reuse the previous result."
                        )
                        if prior:
                            result_str += "\nPREVIOUS RESULT (truncated):\n" + prior[:1200]
                        approved = False
                    elif sig_count >= _MAX_IDENTICAL_TOOL_CALLS:
                        result_str = (
                            "GUARDRAIL: Repeated identical tool call suppressed to prevent loop."
                        )
                        approved = False
                    elif tool_count >= _MAX_PER_TOOL_CALLS:
                        result_str = (
                            "GUARDRAIL: Tool call suppressed due to per-tool call limit "
                            f"({_MAX_PER_TOOL_CALLS}) in this agent turn."
                        )
                        approved = False
                    else:
                        # Approval gate
                        requires_approval = (
                            t_name in self.approval_required
                            or _is_dynamic_mcp_management_tool(t_name)
                        )
                        if requires_approval and approval_callback:
                            approved = await approval_callback(self.id, t_name, t_args)

                        # Execute tool
                        if not approved:
                            result_str = "ERROR: Execution denied by operator."
                        else:
                            result_str = await self._execute_tool(t_name, t_args)
                            if (
                                t_name in _MUTATING_TOOLS
                                and not str(result_str).startswith("ERROR:")
                            ):
                                _workspace_mutation_epoch += 1

                    _tool_signature_last_result[call_signature] = str(result_str)
                    _tool_signature_last_epoch[call_signature] = _workspace_mutation_epoch

                    # UI callback (post-execution so result is visible in stream)
                    if tool_call_callback:
                        try:
                            await tool_call_callback(self.id, t_name, t_args, result_str)
                        except TypeError:
                            await tool_call_callback(self.id, t_name, t_args)

                    all_tool_records.append(
                        ToolCallRecord(
                            tool_name=t_name,
                            arguments=t_args,
                            result=result_str,
                            approved=approved,
                        )
                    )

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": t_name,
                            "content": result_str,
                        }
                    )

                # Continue loop so the LLM can respond after seeing tool results
                continue

            # No tool calls -- done streaming
            final_content = full_content
            break

        # ── Extract output ────────────────────────────────────────────────
        # Workers produce natural text, not JSON. The agent's work IS
        # its output. Try JSON parse as fallback for backward compat,
        # but prefer treating the full text as the work product.
        raw_text = final_content or ""
        parsed: dict[str, Any] = {}

        # If the output looks like JSON, try to parse it for structured fields
        stripped = raw_text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                parsed = json.loads(repair_json(raw_text))
            except (json.JSONDecodeError, Exception):
                pass

        # ── Draft-refine pipeline ────────────────────────────────────────
        if self.refine_client and self.refine_model and final_content:
            parsed = await self._draft_refine(final_content, parsed)

        # Use parsed fields if available, otherwise use raw text as output
        output_text = (
            parsed.get("output")
            or parsed.get("work")
            or raw_text[:5000]
        )

        return AgentOutput(
            approach=parsed.get("approach", ""),
            alternatives_rejected=parsed.get("alternatives_rejected", ""),
            output=output_text,
            tool_calls=all_tool_records,
            tokens_used=total_tokens,
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
        )

    # ── Draft-Refine ─────────────────────────────────────────────────────

    async def _draft_refine(
        self, draft_content: str, draft_parsed: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Send draft to the refine model. Falls back to draft on failure.
        """
        try:
            refine_response = await self.refine_client.chat.completions.create(
                model=self.refine_model,
                messages=[
                    {"role": "system", "content": self.refine_prompt},
                    {"role": "user", "content": draft_content},
                ],
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
            refined_raw = refine_response.choices[0].message.content or ""
            if refined_raw.strip():
                try:
                    return json.loads(repair_json(refined_raw))
                except (json.JSONDecodeError, Exception):
                    pass  # Keep draft
        except Exception as e:
            logger.warning("Draft-refine failed for '%s': %s", self.id, e)

        return draft_parsed

    # ── Token Budget ─────────────────────────────────────────────────────

    def _enforce_token_budget(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Rough token budget enforcement.  Estimates ~4 chars per token.
        If the total exceeds context_length, truncates the user message
        (oldest context first).
        """
        chars_per_token = 4
        max_chars = self.context_length * chars_per_token

        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        if total_chars <= max_chars:
            return messages

        # Truncate user message content (the longest one, which contains context)
        _TRUNC_MARKER = "[...truncated...]\n"
        overshoot = total_chars - max_chars + len(_TRUNC_MARKER)
        logger.warning(
            "Agent '%s' context exceeds budget by ~%d tokens, truncating",
            self.id,
            overshoot // chars_per_token,
        )

        result = []
        for m in messages:
            if m["role"] == "user" and len(m.get("content", "")) > overshoot:
                content = m["content"]
                # Truncate from the beginning of the context (oldest first)
                truncated = content[overshoot:]
                result.append({**m, "content": _TRUNC_MARKER + truncated})
            else:
                result.append(m)
        return result

    # ── Hard Context Window Check ─────────────────────────────────────────

    def _check_context_limit(self, messages: list[dict[str, Any]]) -> None:
        """Raise ``ContextExceededError`` if messages exceed the hard context window.

        This is a **circuit breaker** that fires BEFORE the LLM request is sent.
        Unlike ``_enforce_token_budget()`` which soft-truncates, this is a hard
        halt — the Orchestrator converts it into a ``[SYSTEM_HALT]`` message.

        Uses ~4 chars/token as a conservative estimate (same heuristic as the
        soft truncation path).
        """
        chars_per_token = 4
        total_chars = sum(len(m.get("content", "") or "") for m in messages)
        estimated_tokens = total_chars // chars_per_token

        if estimated_tokens > self.context_length:
            raise ContextExceededError(
                f"Estimated {estimated_tokens:,} tokens exceeds hard context "
                f"window of {self.context_length:,} tokens "
                f"(~{total_chars:,} chars at ~4 chars/token). "
                f"Agent '{self.id}' cannot proceed — truncate your data."
            )

    # ── Tool Execution Dispatcher ────────────────────────────────────────

    async def _execute_tool(self, tool_name: str, args: dict[str, Any]) -> str:
        """
        Dispatch a tool call to its handler.

        Built-in tools: file_read, file_write, file_delete, code_execute, fetch,
        web_search, qdrant_search. Anything else forwards to MCP gateway callback.
        """
        workspace = Path(self.workspace_root).resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        try:
            if tool_name == "file_read":
                return await self._tool_file_read(workspace, args)
            elif tool_name == "file_write":
                return await self._tool_file_write(workspace, args)
            elif tool_name == "file_delete":
                return await self._tool_file_delete(workspace, args)
            elif tool_name == "code_execute":
                return await self._tool_code_execute(workspace, args)
            elif tool_name == "fetch":
                return await self._tool_fetch(args)
            elif tool_name == "web_search":
                return await self._tool_web_search(args)
            elif tool_name == "qdrant_search":
                return await self._tool_qdrant_search(args)
            elif tool_name == "expense_request":
                return await self._tool_expense_request(workspace, args)
            elif tool_name in ("expense_review", "expense_approve", "expense_reject"):
                return await self._tool_cfo_action(tool_name, workspace, args)
            else:
                # Validate tool is in agent's assigned tool list before forwarding
                known_ids = {t.get("id", t.get("name", "")) for t in (self.tools or [])}
                if tool_name not in known_ids:
                    return (
                        f"ERROR: '{tool_name}' is not an available tool. "
                        f"Available tools: {sorted(known_ids)}"
                    )
                # Forward to MCP gateway
                if self.mcp_gateway_callback:
                    return await self.mcp_gateway_callback(tool_name, args)
                return f"Unknown tool: {tool_name}"
        except Exception as e:
            return f"ERROR: {type(e).__name__}: {str(e)[:500]}"

    # ── Path Normalization ─────────────────────────────────────────────────

    _PATH_TOOLS = frozenset({"file_read", "file_write", "file_delete"})

    @staticmethod
    def _normalize_tool_path(raw: str) -> str:
        """Canonicalize a workspace-relative path for cache-hit consistency.

        Strips whitespace, converts backslashes to forward slashes, collapses
        redundant separators and ``.`` components via ``posixpath.normpath``,
        and strips any leading ``./`` prefix so that ``'./snake_game.py'`` and
        ``'snake_game.py'`` produce the exact same string.

        The result is purely lexical — no filesystem access — so it is safe to
        call before the workspace even exists (e.g. during signature hashing).
        """
        p = raw.strip().replace("\\", "/")
        p = posixpath.normpath(p)
        # normpath turns '' into '.'; restore empty to empty
        if p == ".":
            return ""
        return p

    # ── Built-in Tool Implementations ────────────────────────────────────

    def _validate_workspace_path(
        self, workspace: Path, relative_path: str
    ) -> tuple[Path, str | None]:
        """
        Resolve a relative path within the workspace, following symlinks.
        Returns (resolved_path, error_string_or_None).
        """
        target = (workspace / relative_path).resolve()
        if not str(target).startswith(str(workspace)):
            return target, "ERROR: Path escapes workspace sandbox."
        return target, None

    async def _tool_file_read(self, workspace: Path, args: dict) -> str:
        rel_path = str(args.get("path", "")).strip()
        if not rel_path:
            return "ERROR: Missing 'path' argument for file_read."
        target, err = self._validate_workspace_path(workspace, rel_path)
        if err:
            return err
        if not target.exists():
            try:
                all_files = [
                    str(p.relative_to(workspace)).replace("\\", "/")
                    for p in workspace.rglob("*")
                    if p.is_file()
                ]
            except Exception:
                all_files = []

            if not all_files:
                return (
                    f"ERROR: File not found: {rel_path}\n"
                    "Workspace is currently empty. Create the file with file_write first."
                )

            basename = Path(rel_path).name.lower()
            ranked = [
                p for p in all_files
                if Path(p).name.lower() == basename or basename in p.lower()
            ]
            if not ranked:
                ranked = all_files
            hints = ", ".join(ranked[:8])
            return (
                f"ERROR: File not found: {rel_path}\n"
                f"Available files: {hints}"
            )
        if target.is_dir():
            try:
                entries = sorted(
                    str(p.relative_to(workspace)).replace("\\", "/")
                    for p in target.rglob("*")
                    if p.is_file()
                )
            except Exception:
                entries = []
            if entries:
                return (
                    f"ERROR: '{rel_path}' is a directory, not a file.\n"
                    f"Files under it: {', '.join(entries[:8])}"
                )
            return f"ERROR: '{rel_path}' is an empty directory."
        content = await asyncio.to_thread(
            target.read_text, encoding="utf-8", errors="replace"
        )
        return content[:50000]

    async def _tool_file_write(self, workspace: Path, args: dict) -> str:
        rel_path = str(args.get("path", "")).strip()
        if not rel_path:
            return "ERROR: Missing 'path' argument for file_write."
        target, err = self._validate_workspace_path(workspace, rel_path)
        if err:
            return err
        suffix = target.suffix.lower()
        binary_exts = {
            ".wav", ".mp3", ".ogg", ".flac",
            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico",
            ".zip", ".pdf", ".woff", ".woff2",
        }
        if suffix in binary_exts:
            return (
                f"ERROR: file_write is text-only and cannot safely create binary '{suffix}' assets. "
                "Use code_execute to generate binary files, or remove this asset write."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        content = args.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        return f"Written {len(content)} chars to {rel_path}"

    async def _tool_file_delete(self, workspace: Path, args: dict) -> str:
        rel_path = args.get("path", "")
        target, err = self._validate_workspace_path(workspace, rel_path)
        if err:
            return err
        if not target.exists():
            return f"ERROR: File not found: {rel_path}"
        await asyncio.to_thread(target.unlink)
        return f"Deleted {rel_path}"

    async def _tool_code_execute(self, workspace: Path, args: dict) -> str:
        code = str(args.get("code", "")).strip()
        if not code:
            return "ERROR: Missing 'code' argument for code_execute."

        # v0.8.0: Route through REPL harness for root_architect agents.
        # The harness injects formic_subcall() and formic_read_bytes() into
        # exec() globals and bridges to the async sub-agent pipeline.
        repl_harness = self.config.get("repl_harness")
        if repl_harness is not None:
            try:
                return await asyncio.to_thread(repl_harness.execute, code)
            except Exception as exc:
                return f"ERROR: REPL harness failed: {exc}"

        timeout = min(int(args.get("timeout", 10)), 30)
        run_args: list[str] = []

        # Support command-style usage such as:
        #   "python snake_game.py"
        #   "python -m pytest -q"
        #   "python -c \"print('ok')\""
        if "\n" not in code and code.lower().startswith(("python ", "python3 ", "py ")):
            try:
                parts = shlex.split(code, posix=(os.name != "nt"))
            except ValueError as exc:
                return f"ERROR: Invalid python command syntax: {exc}"
            if len(parts) < 2:
                return "ERROR: Invalid python command. Provide script/module/code after python."
            run_args = [sys.executable] + parts[1:]

            # If invoking a script path, validate it's inside workspace.
            first_arg = parts[1]
            if not first_arg.startswith("-"):
                script_path, err = self._validate_workspace_path(workspace, first_arg)
                if err:
                    return err
                if not script_path.exists():
                    return (
                        f"ERROR: Script not found: {first_arg}\n"
                        "Use file_write to create it first or verify the path from file_read hints."
                    )
        else:
            # Raw Python snippet path.
            run_args = [sys.executable, "-c", code]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                run_args,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(workspace),
                env=os.environ.copy(),  # Full env for Windows compatibility
            )
        except subprocess.TimeoutExpired:
            return f"ERROR: code_execute timed out after {timeout}s"

        output = result.stdout[:10000]
        if result.returncode != 0:
            output += f"\nSTDERR:\n{result.stderr[:5000]}"
        return output or "(no output)"

    async def _tool_fetch(self, args: dict) -> str:
        url = args.get("url", "")
        if not url.startswith(("http://", "https://")):
            return "ERROR: Invalid URL scheme."
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.text[:50000]

    async def _tool_web_search(self, args: dict) -> str:
        query = str(args.get("query", "")).strip()
        if not query:
            return "ERROR: Missing 'query' argument."
        max_results = int(args.get("max_results", 5) or 5)
        max_results = max(1, min(max_results, 10))

        # DuckDuckGo HTML endpoint keeps this dependency-light and works with plain HTTP.
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "FormicOS/0.7.1"})
            resp.raise_for_status()
            html_text = resp.text

        results: list[str] = []
        for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html_text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            href = html_lib.unescape(m.group(1))
            title = re.sub(r"<[^>]+>", "", m.group(2))
            title = html_lib.unescape(title).strip()
            if not title:
                continue
            results.append(f"- {title}\n  {href}")
            if len(results) >= max_results:
                break

        if results:
            return f"Web search results for '{query}':\n" + "\n".join(results)

        # Fallback if no structured matches are found in returned markup.
        compact = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text)).strip()
        return f"Web search returned no parsed results for '{query}'. Raw snippet:\n{compact[:3000]}"

    async def _tool_qdrant_search(self, args: dict) -> str:
        query = args.get("query", "")
        top_k = int(args.get("top_k", 5))

        if not self.rag_engine:
            return (
                "QDRANT_UNAVAILABLE: RAG engine not configured for this colony.\n"
                f"Query: {query}\n"
                "Use file_read for workspace files and web_search/fetch for external sources."
            )

        # Derive collection name from colony_id in config
        colony_id = self.config.get("colony_id", "")
        if not colony_id:
            return "QDRANT_UNAVAILABLE: No colony_id configured for RAG search."

        collection = f"colony_{colony_id}_docs"
        try:
            results = await self.rag_engine.search(
                query=query, collection=collection, top_k=top_k,
            )
        except Exception as exc:
            logger.warning("qdrant_search failed for colony '%s': %s", colony_id, exc)
            return f"QDRANT_ERROR: Search failed — {exc}"

        if not results:
            return f"No results found for query: {query}"

        parts = [f"Found {len(results)} result(s) for: {query}\n"]
        for i, r in enumerate(results, 1):
            source = r.metadata.get("source", "unknown")
            score = f"{r.score:.3f}" if r.score else "?"
            parts.append(f"--- Result {i} (score: {score}, source: {source}) ---")
            parts.append(r.content[:2000])
            parts.append("")
        return "\n".join(parts)

    # ── CFO / Expense Tool Implementations ─────────────────────────────

    async def _tool_expense_request(self, workspace: Path, args: dict) -> str:
        """Create an unsigned expense request (Coder-facing tool)."""
        from src.core.network.egress_proxy import ExpenseRequest

        amount = args.get("amount")
        target_api = str(args.get("target_api", "")).strip()
        justification = str(args.get("justification", "")).strip()

        if not amount or not target_api or not justification:
            return "ERROR: Missing required fields: amount, target_api, justification."

        try:
            req = ExpenseRequest(
                amount=float(amount),
                target_api=target_api,
                justification=justification,
            )
        except Exception as exc:
            return f"ERROR: Invalid expense request: {exc}"

        pending_dir = workspace / "expenses" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        path = pending_dir / f"{req.nonce}.json"
        await asyncio.to_thread(
            path.write_text,
            req.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return (
            f"Expense request created: {req.nonce} "
            f"(${req.amount:.2f} → {req.target_api}). "
            "Awaiting CFO approval."
        )

    async def _tool_cfo_action(
        self, action: str, workspace: Path, args: dict,
    ) -> str:
        """Dispatch CFO expense tools (review/approve/reject)."""
        toolkit = self.config.get("cfo_toolkit")
        if toolkit is None:
            return (
                "ERROR: CFO toolkit not available. "
                "Only CFO agents can execute expense approval tools."
            )

        request_id = str(args.get("request_id", "")).strip()
        if not request_id:
            return "ERROR: Missing 'request_id' argument."

        pending_path = workspace / "expenses" / "pending" / f"{request_id}.json"
        if not pending_path.exists():
            return f"ERROR: No pending expense request with ID '{request_id}'."

        raw = json.loads(
            await asyncio.to_thread(pending_path.read_text, encoding="utf-8")
        )

        if action == "expense_review":
            colony_objective = self.config.get("colony_objective", "")
            result = toolkit.review_expense(raw, colony_objective)
            return json.dumps(result, indent=2)

        elif action == "expense_approve":
            result = toolkit.approve_and_sign(raw)
            approved_dir = workspace / "expenses" / "approved"
            approved_dir.mkdir(parents=True, exist_ok=True)
            dest = approved_dir / f"{request_id}.json"
            await asyncio.to_thread(
                dest.write_text, json.dumps(result, indent=2), encoding="utf-8",
            )
            await asyncio.to_thread(pending_path.unlink)
            return (
                f"APPROVED: Expense {request_id} signed. "
                f"Signature: {result['signature'][:32]}..."
            )

        elif action == "expense_reject":
            reason = str(args.get("reason", "No reason provided"))
            result = toolkit.reject_expense(raw, reason)
            rejected_dir = workspace / "expenses" / "rejected"
            rejected_dir.mkdir(parents=True, exist_ok=True)
            dest = rejected_dir / f"{request_id}.json"
            await asyncio.to_thread(
                dest.write_text, json.dumps(result, indent=2), encoding="utf-8",
            )
            await asyncio.to_thread(pending_path.unlink)
            return f"REJECTED: Expense {request_id} denied. Reason: {reason}"

        return f"ERROR: Unknown CFO action: {action}"


# ═════════════════════════════════════════════════════════════════════════════
# AgentFactory
# ═════════════════════════════════════════════════════════════════════════════


class AgentFactory:
    """
    Creates Agent instances from caste configurations.

    Resolves model assignment via: explicit override -> subcaste tier -> caste
    config model_override -> default model.  Optionally loads system prompts
    from files and appends the descriptor suffix for non-manager castes.
    """

    def __init__(
        self,
        model_registry: dict[str, ModelRegistryEntry],
        config: FormicOSConfig,
        model_clients: dict[str, LLMClient] | None = None,
        prompt_dir: str | Path | None = None,
        mcp_client: Any | None = None,
        caste_recipes: dict | None = None,
        rag_engine: Any | None = None,
    ) -> None:
        """
        Args:
            model_registry: Mapping of model_id -> ModelRegistryEntry.
            config: The top-level FormicOSConfig.
            model_clients: Pre-built LLM clients keyed by model_id.
                           If None, clients are constructed from registry entries.
            prompt_dir: Directory to search for caste prompt files.
            mcp_client: Optional MCPGatewayClient for tool injection.
            caste_recipes: Optional CasteRecipe overrides keyed by caste name.
            rag_engine: Optional RAGEngine for qdrant_search tool.
        """
        self.model_registry = model_registry
        self.config = config
        self.model_clients = model_clients or {}
        self.prompt_dir = Path(prompt_dir) if prompt_dir else None
        self.mcp_client = mcp_client
        self.castes = config.castes
        self.subcaste_map = config.subcaste_map
        self.caste_recipes: dict = caste_recipes or {}
        self.rag_engine = rag_engine

    def _get_client(self, model_id: str) -> tuple[LLMClient, str]:
        """
        Resolve a model_id to (LLMClient, model_string).

        Looks up the model_id in model_clients first, then constructs a client
        from the registry entry's endpoint.
        """
        entry = self.model_registry.get(model_id)
        if entry is None:
            raise KeyError(f"Model '{model_id}' not found in registry")

        model_string = entry.model_string or model_id

        if model_id in self.model_clients:
            return self.model_clients[model_id], model_string

        # Construct from endpoint — fallback to AsyncOpenAI when no
        # aio_session is available (e.g. in tests).
        if entry.endpoint:
            from openai import AsyncOpenAI
            client: LLMClient = AsyncOpenAI(
                base_url=entry.endpoint, api_key="not-needed"
            )
            self.model_clients[model_id] = client
            return client, model_string

        raise ValueError(f"No client or endpoint for model '{model_id}'")

    def _load_prompt(self, caste: str) -> str:
        """Load system prompt from file or use default."""
        prompt: str | None = None
        caste_name = caste.lower() if isinstance(caste, str) else caste.value

        caste_config = self.castes.get(caste_name)

        if self.prompt_dir and caste_config and caste_config.system_prompt_file:
            prompt_path = Path(caste_config.system_prompt_file)
            if not prompt_path.is_absolute():
                # Try relative to prompt_dir's parent (handles "prompts/x.md")
                from_config_root = self.prompt_dir.parent / caste_config.system_prompt_file
                from_prompt_dir = self.prompt_dir / prompt_path.name
                if from_config_root.exists():
                    prompt = from_config_root.read_text(encoding="utf-8")
                elif from_prompt_dir.exists():
                    prompt = from_prompt_dir.read_text(encoding="utf-8")

        if prompt is None and self.prompt_dir:
            caste_file = self.prompt_dir / f"{caste_name}.md"
            if caste_file.exists():
                prompt = caste_file.read_text(encoding="utf-8")

        if prompt is None:
            prompt = DEFAULT_PROMPTS.get(caste_name, "You are an AI agent.")

        # Append descriptor suffix for non-manager castes
        if caste_name != "manager" and self.prompt_dir:
            suffix_path = self.prompt_dir / "_descriptor_suffix.md"
            if suffix_path.exists():
                suffix = suffix_path.read_text(encoding="utf-8")
                prompt = prompt.rstrip() + "\n\n" + suffix

        return prompt

    def create(
        self,
        agent_id: str,
        caste: str | BuiltinCaste,
        model_override: str | None = None,
        subcaste_tier: SubcasteTier | None = None,
        workspace_root: str | None = None,
        colony_id: str | None = None,
    ) -> Agent:
        """
        Create a new Agent instance.

        Resolution order for model:
          1. Explicit model_override
          2. Per-caste subcaste_overrides -> SubcasteTier
          3. Global subcaste_map -> SubcasteTier
          4. CasteConfig.model_override
          5. config.inference defaults

        Args:
            agent_id: Unique agent identifier.
            caste: The agent's caste name (string).
            model_override: Explicit model_id from the registry.
            subcaste_tier: Optional subcaste tier for model resolution.

        Returns:
            Configured Agent instance.
        """
        # Normalise caste to lowercase string
        caste_name = caste.value if hasattr(caste, "value") else str(caste).lower()

        # Resolve model client and name
        client: LLMClient | None = None
        model_name: str = self.config.inference.model
        refine_client: LLMClient | None = None
        refine_model: str | None = None
        refine_prompt: str = "Review and correct this draft for accuracy and completeness."

        # Look up caste config early (needed for subcaste overrides + tools)
        caste_config = self.castes.get(caste_name)

        # Apply CasteRecipe overlay (if present)
        recipe = self.caste_recipes.get(caste_name)
        if recipe and caste_config:
            from src.models import merge_recipe_into_caste_config
            caste_config = merge_recipe_into_caste_config(caste_config, recipe)
        elif recipe and not caste_config:
            caste_config = CasteConfig(
                system_prompt_file=recipe.system_prompt_file or f"{caste_name}.md",
                tools=recipe.tools or [],
                mcp_tools=recipe.mcp_tools or [],
                model_override=recipe.model_override,
                subcaste_overrides=recipe.subcaste_overrides or {},
                description=recipe.description or "",
            )

        # 1. Explicit override
        if model_override:
            try:
                client, model_name = self._get_client(model_override)
            except (KeyError, ValueError):
                pass  # Fall through

        # 2. Subcaste resolution — per-caste overrides first, then global map
        if client is None and subcaste_tier:
            tier_key = (
                subcaste_tier.value
                if isinstance(subcaste_tier, SubcasteTier)
                else str(subcaste_tier)
            )

            # 2a. Per-caste subcaste overrides (e.g. architect heavy → cloud/opus)
            caste_subcaste_entry = None
            if caste_config and caste_config.subcaste_overrides:
                caste_subcaste_entry = caste_config.subcaste_overrides.get(tier_key)

            if caste_subcaste_entry:
                try:
                    primary_id = (
                        caste_subcaste_entry.primary
                        if isinstance(caste_subcaste_entry, SubcasteMapEntry)
                        else caste_subcaste_entry
                    )
                    client, model_name = self._get_client(primary_id)
                    if isinstance(caste_subcaste_entry, SubcasteMapEntry) and caste_subcaste_entry.refine_with:
                        refine_client, refine_model = self._get_client(
                            caste_subcaste_entry.refine_with
                        )
                        if caste_subcaste_entry.refine_prompt:
                            refine_prompt = caste_subcaste_entry.refine_prompt
                except (KeyError, ValueError) as e:
                    logger.warning(
                        "Per-caste subcaste override failed for '%s' caste '%s' tier '%s': %s",
                        agent_id, caste_name, tier_key, e,
                    )

            # 2b. Global subcaste_map
            if client is None and self.subcaste_map:
                entry = self.subcaste_map.get(tier_key)
                if entry:
                    try:
                        primary_id = (
                            entry.primary if isinstance(entry, SubcasteMapEntry) else entry
                        )
                        client, model_name = self._get_client(primary_id)

                        # Draft-refine from subcaste map
                        if isinstance(entry, SubcasteMapEntry) and entry.refine_with:
                            refine_client, refine_model = self._get_client(
                                entry.refine_with
                            )
                            if entry.refine_prompt:
                                refine_prompt = entry.refine_prompt
                    except (KeyError, ValueError) as e:
                        logger.warning(
                            "Subcaste resolution failed for '%s' tier '%s': %s",
                            agent_id, tier_key, e,
                        )

        # 3. CasteConfig model_override
        if client is None and caste_config and caste_config.model_override:
            try:
                client, model_name = self._get_client(caste_config.model_override)
            except (KeyError, ValueError):
                pass

        # 4. Default -- build from inference config
        if client is None:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                base_url=self.config.inference.endpoint, api_key="not-needed"
            )

        # Resolve builtin tools from caste config
        tools_list: list[dict[str, Any]] = []
        if caste_config and caste_config.tools:
            for tool_name in caste_config.tools:
                schema = _BUILTIN_TOOL_SCHEMAS.get(tool_name, {
                    "description": f"Built-in tool: {tool_name}",
                    "parameters": {"type": "object", "properties": {}},
                })
                tools_list.append(
                    {
                        "id": tool_name,
                        "name": tool_name,
                        "description": schema["description"],
                        "parameters": schema["parameters"],
                        "enabled": True,
                    }
                )

        # Inject MCP tools filtered by caste config
        caste_mcp_ids: list[str] = []
        allowed_mcp_ids: list[str] = []
        if caste_config:
            caste_mcp_ids = caste_config.mcp_tools
        if self.mcp_client and getattr(self.mcp_client, "connected", False):
            all_mcp = self.mcp_client.get_tools()
            if caste_mcp_ids:
                # Only include the caste's assigned MCP tools
                for mcp_tool in all_mcp:
                    if mcp_tool["id"] in caste_mcp_ids:
                        tools_list.append(mcp_tool)
                        allowed_mcp_ids.append(mcp_tool["id"])
            else:
                # Empty mcp_tools list now uses a safe default subset.
                for mcp_tool in all_mcp:
                    tool_id = mcp_tool.get("id", "")
                    if _is_safe_default_mcp_tool_id(tool_id):
                        tools_list.append(mcp_tool)
                        allowed_mcp_ids.append(tool_id)

        # Load system prompt
        system_prompt = self._load_prompt(caste_name)

        # Resolve context_length from the model registry entry
        context_length = self.config.inference.context_size
        if model_override and model_override in self.model_registry:
            context_length = self.model_registry[model_override].context_length

        agent_config: dict[str, Any] = {
            "max_tokens": self.config.inference.max_tokens_per_agent,
            "temperature": self.config.inference.temperature,
            "context_length": context_length,
            "workspace_root": workspace_root or "./workspace",
            "approval_required": list(self.config.approval_required)
            or list(DEFAULT_APPROVAL_REQUIRED),
            "refine_client": refine_client,
            "refine_model": refine_model,
            "refine_prompt": refine_prompt,
            "colony_id": colony_id or "",
        }

        # Apply CasteRecipe inference overrides
        if recipe:
            if recipe.temperature is not None:
                agent_config["temperature"] = recipe.temperature
            if recipe.context_window is not None:
                agent_config["context_length"] = min(
                    recipe.context_window, agent_config["context_length"],
                )
            if recipe.max_tokens is not None:
                agent_config["max_tokens"] = recipe.max_tokens
            if recipe.escalation_fallback:
                agent_config["escalation_fallback"] = recipe.escalation_fallback

        # Set MCP gateway callback scoped to this agent's allowed tools
        if self.mcp_client:
            allowed_mcp = set(allowed_mcp_ids)

            async def _mcp_callback(
                tool_name: str, args: dict,
                _client: Any = self.mcp_client, _allowed: set[str] = allowed_mcp,
            ) -> str:
                if tool_name not in _allowed:
                    return f"ERROR: Tool '{tool_name}' not assigned to this agent's caste."
                return await _client.call_tool(tool_name, args)

            agent_config["mcp_gateway_callback"] = _mcp_callback

        return Agent(
            id=agent_id,
            caste=caste_name,
            system_prompt=system_prompt,
            model_client=client,
            model_name=model_name,
            tools=tools_list,
            config=agent_config,
            rag_engine=self.rag_engine,
        )
