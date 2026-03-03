"""
Tests for FormicOS REPL AST Pre-Parser Guardrail.

Covers:
1. Valid code passes validation (for loops, comprehensions, formic_* calls)
2. `while` loops are blocked instantly without execution
3. `import time` / `from time import sleep` blocked
4. `import os` / `import subprocess` blocked
5. `time.sleep()`, `os.system()`, `subprocess.run()` calls blocked
6. Syntax errors produce REPLHarnessError (not SyntaxError)
7. Integration: REPLHarness.execute() returns error string for blocked code
8. Nested/indirect patterns (while inside function, chained imports)
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.core.repl.harness import ASTValidator, REPLHarness, REPLHarnessError


# ── 1. Valid Code Passes ─────────────────────────────────────────────


class TestValidCode:
    """Code that should pass validation cleanly."""

    def test_for_loop_range(self):
        ASTValidator.validate("for i in range(100):\n    print(i)")

    def test_for_loop_enumerate(self):
        ASTValidator.validate(
            "data = [1, 2, 3]\nfor i, v in enumerate(data):\n    print(i, v)"
        )

    def test_list_comprehension(self):
        ASTValidator.validate("result = [x**2 for x in range(50)]")

    def test_dict_comprehension(self):
        ASTValidator.validate("d = {k: v for k, v in enumerate('abc')}")

    def test_generator_expression(self):
        ASTValidator.validate("total = sum(x for x in range(10))")

    def test_function_definition(self):
        ASTValidator.validate(
            "def greet(name):\n    return f'Hello {name}'\nprint(greet('world'))"
        )

    def test_formic_read_bytes_call(self):
        ASTValidator.validate("data = formic_read_bytes(0, 4096)\nprint(data)")

    def test_formic_subcall(self):
        ASTValidator.validate(
            'result = formic_subcall("Fix the bug", "def foo(): pass")\n'
            "print(result)"
        )

    def test_nested_for_loops(self):
        ASTValidator.validate(
            "for i in range(10):\n"
            "    for j in range(10):\n"
            "        print(i * j)"
        )

    def test_try_except(self):
        ASTValidator.validate(
            "try:\n    x = 1 / 0\nexcept ZeroDivisionError:\n    print('caught')"
        )

    def test_class_definition(self):
        ASTValidator.validate(
            "class Foo:\n    def bar(self):\n        return 42"
        )

    def test_safe_imports(self):
        """json, re, math, etc. should be allowed."""
        ASTValidator.validate("import json\nimport re\nimport math")

    def test_empty_code(self):
        ASTValidator.validate("")

    def test_assignment_only(self):
        ASTValidator.validate("x = 42\ny = x + 1")


# ── 2. While Loops Blocked ──────────────────────────────────────────


class TestWhileBlocked:
    """All while loops must be rejected."""

    def test_while_true(self):
        with pytest.raises(REPLHarnessError, match="while.*forbidden"):
            ASTValidator.validate("while True:\n    pass")

    def test_while_condition(self):
        with pytest.raises(REPLHarnessError, match="while.*forbidden"):
            ASTValidator.validate("x = 10\nwhile x > 0:\n    x -= 1")

    def test_while_inside_function(self):
        with pytest.raises(REPLHarnessError, match="while.*forbidden"):
            ASTValidator.validate(
                "def spin():\n    while True:\n        pass\nspin()"
            )

    def test_while_with_break(self):
        """Even while-with-break is banned (can't trust the LLM's break)."""
        with pytest.raises(REPLHarnessError, match="while.*forbidden"):
            ASTValidator.validate(
                "while True:\n    break"
            )

    def test_while_in_class_method(self):
        with pytest.raises(REPLHarnessError, match="while.*forbidden"):
            ASTValidator.validate(
                "class Spinner:\n"
                "    def run(self):\n"
                "        while True:\n"
                "            pass"
            )

    def test_while_reports_line_number(self):
        with pytest.raises(REPLHarnessError, match="line 3"):
            ASTValidator.validate("x = 1\ny = 2\nwhile True:\n    pass")


# ── 3. Banned Module Imports ────────────────────────────────────────


class TestBannedImports:
    """import time, os, subprocess must be blocked."""

    def test_import_time(self):
        with pytest.raises(REPLHarnessError, match="import time.*forbidden"):
            ASTValidator.validate("import time")

    def test_import_os(self):
        with pytest.raises(REPLHarnessError, match="import os.*forbidden"):
            ASTValidator.validate("import os")

    def test_import_subprocess(self):
        with pytest.raises(REPLHarnessError, match="import subprocess.*forbidden"):
            ASTValidator.validate("import subprocess")

    def test_from_time_import_sleep(self):
        with pytest.raises(REPLHarnessError, match="from time.*forbidden"):
            ASTValidator.validate("from time import sleep")

    def test_from_os_import_system(self):
        with pytest.raises(REPLHarnessError, match="from os.*forbidden"):
            ASTValidator.validate("from os import system")

    def test_from_os_path_import(self):
        """os.path is still under the `os` top-level module."""
        with pytest.raises(REPLHarnessError, match="from os.*forbidden"):
            ASTValidator.validate("from os.path import join")

    def test_from_subprocess_import_popen(self):
        with pytest.raises(REPLHarnessError, match="from subprocess.*forbidden"):
            ASTValidator.validate("from subprocess import Popen")

    def test_import_time_as_alias(self):
        """import time as t should still be caught."""
        with pytest.raises(REPLHarnessError, match="import time.*forbidden"):
            ASTValidator.validate("import time as t")


# ── 4. Banned Function Calls ────────────────────────────────────────


class TestBannedCalls:
    """Direct function calls to dangerous APIs must be blocked."""

    def test_time_sleep(self):
        with pytest.raises(REPLHarnessError, match="time.sleep.*forbidden"):
            ASTValidator.validate("time.sleep(10)")

    def test_os_system(self):
        with pytest.raises(REPLHarnessError, match="os.system.*forbidden"):
            ASTValidator.validate("os.system('rm -rf /')")

    def test_os_popen(self):
        with pytest.raises(REPLHarnessError, match="os.popen.*forbidden"):
            ASTValidator.validate("os.popen('ls')")

    def test_subprocess_run(self):
        with pytest.raises(REPLHarnessError, match="subprocess.run.*forbidden"):
            ASTValidator.validate("subprocess.run(['ls'])")

    def test_subprocess_popen(self):
        with pytest.raises(REPLHarnessError, match="subprocess.Popen.*forbidden"):
            ASTValidator.validate("subprocess.Popen(['ls'])")

    def test_subprocess_check_output(self):
        with pytest.raises(REPLHarnessError, match="subprocess.check_output.*forbidden"):
            ASTValidator.validate("subprocess.check_output(['ls'])")

    def test_call_reports_line_number(self):
        with pytest.raises(REPLHarnessError, match="line 2"):
            ASTValidator.validate("x = 1\ntime.sleep(5)")


# ── 5. Syntax Errors ────────────────────────────────────────────────


class TestSyntaxErrors:
    """Syntax errors should raise REPLHarnessError, not raw SyntaxError."""

    def test_syntax_error_raises_harness_error(self):
        with pytest.raises(REPLHarnessError, match="Syntax error"):
            ASTValidator.validate("def foo(:\n    pass")

    def test_incomplete_code(self):
        with pytest.raises(REPLHarnessError, match="Syntax error"):
            ASTValidator.validate("if True")


# ── 6. Integration with REPLHarness.execute() ───────────────────────


class TestHarnessIntegration:
    """ASTValidator is called from execute() and returns error strings."""

    @pytest.fixture
    def harness(self):
        """Minimal harness with mocked dependencies."""
        memory = MagicMock()
        memory.read_slice.return_value = b"test data"
        router = MagicMock()
        loop = MagicMock()
        return REPLHarness(
            memory=memory, router=router, loop=loop,
        )

    def test_valid_code_executes(self, harness):
        result = harness.execute("print('hello')")
        assert result == "hello\n"

    def test_for_loop_executes(self, harness):
        result = harness.execute(
            "total = 0\nfor i in range(100):\n    total += i\nprint(total)"
        )
        assert result.strip() == "4950"

    def test_while_blocked_returns_error_string(self, harness):
        """while loop is blocked BEFORE exec(), returns error to LLM."""
        start = time.monotonic()
        result = harness.execute("while True:\n    pass")
        elapsed = time.monotonic() - start

        assert "BLOCKED" in result
        assert "while" in result
        assert "forbidden" in result
        # Must return instantly (< 1s), NOT hang
        assert elapsed < 1.0

    def test_import_time_blocked_returns_error(self, harness):
        result = harness.execute("import time\ntime.sleep(100)")
        assert "BLOCKED" in result
        assert "time" in result

    def test_import_os_blocked_returns_error(self, harness):
        result = harness.execute("import os\nos.system('echo pwned')")
        assert "BLOCKED" in result
        assert "os" in result

    def test_import_subprocess_blocked_returns_error(self, harness):
        result = harness.execute("import subprocess\nsubprocess.run(['ls'])")
        assert "BLOCKED" in result
        assert "subprocess" in result

    def test_time_sleep_call_blocked(self, harness):
        result = harness.execute("time.sleep(60)")
        assert "BLOCKED" in result

    def test_blocked_code_never_executes(self, harness):
        """Verify the dangerous code path is never reached."""
        # If exec() ran, it would set a global flag — but AST blocks first
        result = harness.execute(
            "import os\n"
            "# This line must never execute\n"
            "print('ESCAPED')"
        )
        assert "BLOCKED" in result
        assert "ESCAPED" not in result

    def test_formic_read_bytes_still_works(self, harness):
        """Injected primitives remain accessible after AST gate."""
        result = harness.execute("data = formic_read_bytes(0, 100)\nprint(len(data))")
        assert "9" in result  # len(b"test data") = 9
