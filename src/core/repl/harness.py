"""
FormicOS v0.8.0 -- REPL Execution Harness

Sandboxed ``exec()`` loop for Root_Architect agents.  Injects two colony
primitives into the execution globals:

  formic_read_bytes(start, length) -> str
      Read a byte-range from the SecuredTopologicalMemory.

  formic_subcall(task_description, data_slice, target_caste="Coder") -> str
      Farm a task to a fresh sub-agent.  Blocks the REPL thread until
      the sub-agent finishes and returns its output string.

The harness runs **synchronously** in a worker thread (called via
``asyncio.to_thread()`` from the agent's ``_tool_code_execute`` path).
``formic_subcall`` uses ``asyncio.run_coroutine_threadsafe()`` to schedule
the sub-agent coroutine on the main event loop, then ``.result()`` blocks
the REPL thread until it completes.

Thread safety:
  - ``formic_read_bytes`` is O(1) mmap access (read-only, process-global).
  - ``formic_subcall`` blocks only the REPL worker thread; the main event
    loop is free to run the sub-agent.
  - Sub-agents are fresh instances with no shared mutable state.
"""

from __future__ import annotations

import ast
import asyncio
import contextlib
import io
import logging
import traceback
from typing import TYPE_CHECKING, Any

from src.core.repl.secured_memory import FormicMemoryError, SecuredTopologicalMemory

if TYPE_CHECKING:
    from src.core.orchestrator.router import SubcallRouter

logger = logging.getLogger("formicos.repl.harness")

# Dedicated telemetry logger for REPL primitive invocations.
# Handlers on "formicos.repl" will receive events from both this
# logger and the harness debug logger above (child propagation).
repl_telemetry = logging.getLogger("formicos.repl")


class REPLHarnessError(Exception):
    """Raised when the REPL sandbox encounters a fatal error."""


# ── AST Pre-Parser Guardrail ─────────────────────────────────────────

# Modules that must never be imported inside the REPL sandbox.
_BANNED_MODULES = frozenset({"time", "os", "subprocess"})

# Fully-qualified function calls that are forbidden.
_BANNED_CALLS = frozenset({
    "time.sleep",
    "os.system",
    "os.popen",
    "os.exec",
    "os.execv",
    "os.execve",
    "os.execvp",
    "os.execvpe",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_call",
    "subprocess.check_output",
    "subprocess.Popen",
})


class ASTValidator(ast.NodeVisitor):
    """Walks a Python AST and rejects dangerous constructs before exec().

    Raises ``REPLHarnessError`` on the first violation found.

    Forbidden constructs
    --------------------
    - ``while`` loops (unbounded iteration hangs the executor thread)
    - ``import time`` / ``from time import ...`` (``time.sleep`` blocks)
    - ``import os`` / ``import subprocess`` (shell escape)
    - Calls to ``time.sleep``, ``os.system``, ``subprocess.*``
    """

    def visit_While(self, node: ast.While) -> None:  # noqa: N802
        raise REPLHarnessError(
            f"BLOCKED: `while` loops are forbidden in the REPL sandbox "
            f"(line {node.lineno}). Use bounded `for` loops instead "
            f"(e.g., `for i in range(n):`)."
        )

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in _BANNED_MODULES:
                raise REPLHarnessError(
                    f"BLOCKED: `import {alias.name}` is forbidden in the "
                    f"REPL sandbox (line {node.lineno}). "
                    f"The module `{top}` is banned for safety."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            top = node.module.split(".")[0]
            if top in _BANNED_MODULES:
                raise REPLHarnessError(
                    f"BLOCKED: `from {node.module} import ...` is forbidden "
                    f"in the REPL sandbox (line {node.lineno}). "
                    f"The module `{top}` is banned for safety."
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = self._resolve_call_name(node.func)
        if name in _BANNED_CALLS:
            raise REPLHarnessError(
                f"BLOCKED: `{name}()` is forbidden in the REPL sandbox "
                f"(line {node.lineno})."
            )
        self.generic_visit(node)

    @staticmethod
    def _resolve_call_name(node: ast.expr) -> str:
        """Best-effort resolution of a call target to a dotted name."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = ASTValidator._resolve_call_name(node.value)
            if prefix:
                return f"{prefix}.{node.attr}"
            return node.attr
        return ""

    @classmethod
    def validate(cls, code: str) -> None:
        """Parse and validate ``code``.

        Raises ``REPLHarnessError`` on the first forbidden construct,
        or if the code contains a syntax error.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            raise REPLHarnessError(
                f"BLOCKED: Syntax error in submitted code — {exc}"
            ) from exc
        cls().visit(tree)


class REPLHarness:
    """Sandboxed ``exec()`` environment with colony primitive injection.

    Parameters
    ----------
    memory : SecuredTopologicalMemory
        The read-only mmap wrapper for dense data access.
    router : SubcallRouter
        The synchronous sub-agent router for ``formic_subcall()``.
    loop : asyncio.AbstractEventLoop
        The main event loop (needed for ``run_coroutine_threadsafe``).
    workspace_root : str
        Colony workspace path (informational).
    max_output_chars : int
        Maximum captured stdout characters returned to the LLM.
    max_subcalls : int
        Circuit breaker: maximum ``formic_subcall()`` invocations per
        ``execute()`` call.
    """

    def __init__(
        self,
        memory: SecuredTopologicalMemory,
        router: SubcallRouter,
        loop: asyncio.AbstractEventLoop,
        workspace_root: str = "./workspace",
        max_output_chars: int = 50_000,
        max_subcalls: int = 10,
    ) -> None:
        self._memory = memory
        self._router = router
        self._loop = loop
        self._workspace_root = workspace_root
        self._max_output_chars = max_output_chars
        self._max_subcalls = max_subcalls
        self._subcall_count = 0

    # ── Closure Builders ──────────────────────────────────────────

    def _make_formic_read_bytes(self):
        """Build the ``formic_read_bytes`` closure for injection."""
        mem = self._memory

        def formic_read_bytes(start: int, length: int) -> str:
            """Read a byte-range from the memory-mapped file.

            Returns decoded UTF-8 text.  Maximum 50,000 bytes per call.
            """
            raw = mem.read_slice(start, length)
            actual = len(raw)
            repl_telemetry.info(
                "formic_read_bytes  offset=%d  length=%d  actual=%d",
                start, length, actual,
                extra={
                    "repl_event": "formic_read_bytes",
                    "offset": start,
                    "length": length,
                    "actual_bytes": actual,
                },
            )
            return raw.decode("utf-8", errors="replace")

        return formic_read_bytes

    def _make_formic_subcall(self):
        """Build the ``formic_subcall`` closure for injection."""
        router = self._router
        loop = self._loop
        harness = self

        def formic_subcall(
            task_description: str,
            data_slice: str,
            target_caste: str = "Coder",
        ) -> str:
            """Farm a task to a sub-agent. Blocks until complete.

            Parameters
            ----------
            task_description : str
                What the sub-agent should do.
            data_slice : str
                Data context provided to the sub-agent.
            target_caste : str
                Caste of the sub-agent (default: "Coder").

            Returns
            -------
            str
                The sub-agent's final output.
            """
            if harness._subcall_count >= harness._max_subcalls:
                return (
                    f"ERROR: Subcall limit reached ({harness._max_subcalls}). "
                    "Consolidate your work or break the task differently."
                )
            harness._subcall_count += 1

            repl_telemetry.info(
                "formic_subcall  target_caste=%s  task=%.100s",
                target_caste, task_description,
                extra={
                    "repl_event": "formic_subcall",
                    "target_caste": target_caste,
                    "task_preview": task_description[:200],
                    "data_slice_len": len(data_slice),
                    "subcall_num": harness._subcall_count,
                },
            )

            # Schedule the async coroutine on the main event loop
            future = asyncio.run_coroutine_threadsafe(
                router.route_subcall(
                    task_description=task_description,
                    data_slice=data_slice,
                    target_caste=target_caste,
                ),
                loop,
            )

            # Block the REPL thread until the sub-agent completes
            try:
                result = future.result(timeout=300.0)
                repl_telemetry.info(
                    "formic_subcall  complete  target_caste=%s  result_len=%d",
                    target_caste, len(result),
                    extra={
                        "repl_event": "formic_subcall_complete",
                        "target_caste": target_caste,
                        "result_len": len(result),
                        "subcall_num": harness._subcall_count,
                    },
                )
                return result
            except TimeoutError:
                return "ERROR: Sub-agent timed out after 300 seconds."
            except Exception as exc:
                return (
                    f"ERROR: Sub-agent failed: "
                    f"{type(exc).__name__}: {str(exc)[:500]}"
                )

        return formic_subcall

    # ── Execution ─────────────────────────────────────────────────

    def execute(self, code: str) -> str:
        """Execute Python code in the sandboxed REPL.

        This method runs **synchronously** in a worker thread.  It is
        called via ``asyncio.to_thread()`` from the agent's
        ``_tool_code_execute`` path.

        Parameters
        ----------
        code : str
            Raw Python code to execute.

        Returns
        -------
        str
            Captured stdout (truncated to ``max_output_chars``), or
            error message.
        """
        self._subcall_count = 0  # fresh budget per exec block

        # v0.8.0: AST pre-parse guardrail — reject dangerous constructs
        # before exec() to prevent thread hangs and shell escapes.
        try:
            ASTValidator.validate(code)
        except REPLHarnessError as ve:
            logger.warning("AST validation blocked code: %s", ve)
            return str(ve)

        # Build isolated globals with injected primitives
        exec_globals: dict[str, Any] = {
            "__builtins__": __builtins__,
            "formic_read_bytes": self._make_formic_read_bytes(),
            "formic_subcall": self._make_formic_subcall(),
        }

        stdout_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_capture):
                exec(code, exec_globals)  # noqa: S102
        except FormicMemoryError as fme:
            return f"FormicMemoryError: {fme}"
        except Exception:
            tb = traceback.format_exc()
            return f"REPL execution error:\n{tb[-2000:]}"

        output = stdout_capture.getvalue()
        if len(output) > self._max_output_chars:
            output = (
                output[: self._max_output_chars]
                + "\n... (output truncated)"
            )
        return output or "(no output)"
