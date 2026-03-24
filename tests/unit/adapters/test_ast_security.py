"""Tests for AST-based security screening (Wave 32 C1a).

Covers blocked modules, bypass vectors, allowed operations, and syntax errors.
"""

from __future__ import annotations

import pytest

from formicos.adapters.ast_security import BLOCKED_BUILTINS, BLOCKED_MODULES, check_ast_safety


class TestBlockedModules:
    """Dangerous modules must be rejected."""

    @pytest.mark.parametrize("module", [
        "os", "subprocess", "sys", "shutil", "socket", "ctypes",
        "multiprocessing", "threading", "signal", "http",
        "importlib", "code", "compileall", "runpy", "pathlib",
    ])
    def test_blocked_top_level_import(self, module: str) -> None:
        result = check_ast_safety(f"import {module}")
        assert not result.safe
        assert "Blocked import" in result.reason

    @pytest.mark.parametrize("module", [
        "os", "subprocess", "sys", "shutil", "socket", "ctypes",
    ])
    def test_blocked_from_import(self, module: str) -> None:
        result = check_ast_safety(f"from {module} import path")
        assert not result.safe
        assert "Blocked import" in result.reason

    def test_blocked_dotted_import(self) -> None:
        result = check_ast_safety("import os.path")
        assert not result.safe

    def test_blocked_nested_from_import_in_function(self) -> None:
        """from os import path inside a function body should be blocked."""
        code = "def f():\n    from os import path\n    return path"
        result = check_ast_safety(code)
        assert not result.safe


class TestBypassVectors:
    """Common sandbox escape attempts must be caught."""

    def test_importlib_import_module(self) -> None:
        result = check_ast_safety('import importlib\nimportlib.import_module("os")')
        assert not result.safe

    def test_eval_dunder_import(self) -> None:
        result = check_ast_safety("eval(\"__import__('os')\")")
        assert not result.safe
        assert "Blocked builtin" in result.reason
        assert "eval" in result.reason

    def test_exec_call(self) -> None:
        result = check_ast_safety("exec('import os')")
        assert not result.safe
        assert "exec" in result.reason

    def test_compile_call(self) -> None:
        result = check_ast_safety("compile('import os', '<string>', 'exec')")
        assert not result.safe

    def test_dunder_import_call(self) -> None:
        result = check_ast_safety("__import__('os')")
        assert not result.safe

    def test_open_call(self) -> None:
        result = check_ast_safety("open('/etc/passwd')")
        assert not result.safe
        assert "open" in result.reason

    def test_breakpoint_call(self) -> None:
        result = check_ast_safety("breakpoint()")
        assert not result.safe


class TestAllowedOperations:
    """Safe code should pass the check."""

    def test_import_math(self) -> None:
        result = check_ast_safety("import math\nresult = math.sqrt(4)")
        assert result.safe

    def test_import_json(self) -> None:
        result = check_ast_safety("import json\ndata = json.loads('{}')")
        assert result.safe

    def test_string_operations(self) -> None:
        result = check_ast_safety("x = 'hello'.upper()\ny = x + ' world'")
        assert result.safe

    def test_list_comprehension(self) -> None:
        result = check_ast_safety("[x**2 for x in range(10)]")
        assert result.safe

    def test_function_definition(self) -> None:
        code = "def add(a, b):\n    return a + b\nresult = add(1, 2)"
        result = check_ast_safety(code)
        assert result.safe

    def test_class_definition(self) -> None:
        code = "class Foo:\n    def bar(self): return 42"
        result = check_ast_safety(code)
        assert result.safe

    def test_empty_code(self) -> None:
        result = check_ast_safety("")
        assert result.safe


class TestSyntaxErrors:
    """Malformed code should not crash the checker."""

    def test_syntax_error_returns_unsafe(self) -> None:
        result = check_ast_safety("def f(\n  invalid syntax here")
        assert not result.safe
        assert "Syntax error" in result.reason

    def test_incomplete_expression(self) -> None:
        result = check_ast_safety("if True:\n")
        # May or may not parse depending on Python version; shouldn't crash
        assert isinstance(result.safe, bool)
