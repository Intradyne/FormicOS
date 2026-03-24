"""AST-based security screening for sandboxed code execution (Wave 14).

Scans Python source for dangerous imports, builtins, and patterns
BEFORE execution. Rejects code that tries to escape the sandbox.
"""

from __future__ import annotations

import ast

import structlog
from pydantic import BaseModel, ConfigDict

log = structlog.get_logger()


class ASTCheckResult(BaseModel):
    """Result of AST safety check."""

    model_config = ConfigDict(frozen=True)

    safe: bool
    reason: str = ""


# Modules that must never be imported in sandbox
BLOCKED_MODULES: frozenset[str] = frozenset({
    "subprocess", "os", "sys", "shutil", "signal", "ctypes",
    "multiprocessing", "threading", "socket", "http",
    "importlib", "code", "compileall", "runpy",
    "pathlib",  # prevent fs escape
})

# Builtins that must not be called directly
BLOCKED_BUILTINS: frozenset[str] = frozenset({
    "eval", "exec", "compile", "__import__", "breakpoint",
    "open",  # file I/O blocked in sandbox
})


def check_ast_safety(code: str) -> ASTCheckResult:
    """Parse and scan Python code for dangerous patterns.

    Returns ASTCheckResult with safe=False and a reason if blocked.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return ASTCheckResult(safe=False, reason=f"Syntax error: {exc}")

    for node in ast.walk(tree):
        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                module_root = alias.name.split(".")[0]
                if module_root in BLOCKED_MODULES:
                    return ASTCheckResult(
                        safe=False,
                        reason=f"Blocked import: '{alias.name}'",
                    )

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module_root = node.module.split(".")[0]
                if module_root in BLOCKED_MODULES:
                    return ASTCheckResult(
                        safe=False,
                        reason=f"Blocked import: 'from {node.module}'",
                    )

        # Check dangerous builtin calls
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_BUILTINS:
                return ASTCheckResult(
                    safe=False,
                    reason=f"Blocked builtin: '{func.id}'",
                )

    log.debug("ast_security.passed", code_len=len(code))
    return ASTCheckResult(safe=True)
