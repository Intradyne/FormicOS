"""Tests for lightweight structural analysis (Wave 42 Pillar 1)."""

from __future__ import annotations

import os
import tempfile

import pytest

from formicos.adapters.code_analysis import (
    FileInfo,
    WorkspaceStructure,
    _classify_role,
    _detect_language,
    _find_test_companion,
    _parse_go,
    _parse_js_ts,
    _parse_python,
    _path_to_module,
    analyze_workspace,
)


# ---------------------------------------------------------------------------
# File classification
# ---------------------------------------------------------------------------


class TestClassifyRole:
    def test_python_source(self) -> None:
        assert _classify_role("src/foo.py", ".py") == "source"

    def test_python_test_prefix(self) -> None:
        assert _classify_role("tests/test_foo.py", ".py") == "test"

    def test_python_test_dir(self) -> None:
        assert _classify_role("tests/unit/helper.py", ".py") == "test"

    def test_go_test_suffix(self) -> None:
        assert _classify_role("pkg/auth_test.go", ".go") == "test"

    def test_js_spec(self) -> None:
        assert _classify_role("src/auth.spec.ts", ".ts") == "test"

    def test_config_yaml(self) -> None:
        assert _classify_role("config/settings.yaml", ".yaml") == "config"

    def test_docs_md(self) -> None:
        assert _classify_role("docs/README.md", ".md") == "docs"

    def test_unknown_ext(self) -> None:
        assert _classify_role("data/binary.bin", ".bin") == "unknown"


class TestDetectLanguage:
    def test_python(self) -> None:
        assert _detect_language(".py") == "python"

    def test_typescript(self) -> None:
        assert _detect_language(".ts") == "typescript"

    def test_go(self) -> None:
        assert _detect_language(".go") == "go"

    def test_unknown(self) -> None:
        assert _detect_language(".rs") == "unknown"


# ---------------------------------------------------------------------------
# Python parsing
# ---------------------------------------------------------------------------


class TestParsePython:
    def test_imports_and_defs(self) -> None:
        source = """\
import os
from pathlib import Path

class MyClass:
    pass

def my_function():
    pass

async def async_func():
    pass
"""
        imports, defs = _parse_python(source)
        assert "os" in imports
        assert "pathlib" in imports
        assert "class MyClass" in defs
        assert "def my_function" in defs
        assert "def async_func" in defs

    def test_syntax_error(self) -> None:
        imports, defs = _parse_python("def (broken")
        assert imports == []
        assert defs == []

    def test_nested_ignored(self) -> None:
        source = """\
class Outer:
    def inner_method(self):
        import inner_import
"""
        imports, defs = _parse_python(source)
        # Only top-level nodes
        assert "class Outer" in defs
        assert "def inner_method" not in defs
        assert "inner_import" not in imports


class TestPathToModule:
    def test_src_prefix(self) -> None:
        assert _path_to_module("src/formicos/core/types.py") == "formicos.core.types"

    def test_init(self) -> None:
        assert _path_to_module("src/formicos/core/__init__.py") == "formicos.core"

    def test_no_src(self) -> None:
        assert _path_to_module("formicos/core/types.py") == "formicos.core.types"


# ---------------------------------------------------------------------------
# JS/TS parsing
# ---------------------------------------------------------------------------


class TestParseJsTs:
    def test_imports(self) -> None:
        source = """\
import React from 'react';
import { useState } from 'react';
import './styles.css';
const fs = require('fs');
export { helper } from './utils';
"""
        imports, _ = _parse_js_ts(source)
        assert "react" in imports
        assert "./styles.css" in imports
        assert "fs" in imports
        assert "./utils" in imports

    def test_definitions(self) -> None:
        source = """\
export function fetchData() {}
class UserService {}
const handleClick = (e) => {}
export async function loadAsync() {}
"""
        _, defs = _parse_js_ts(source)
        assert "function fetchData" in defs
        assert "class UserService" in defs
        assert "const handleClick" in defs
        assert "function loadAsync" in defs


# ---------------------------------------------------------------------------
# Go parsing
# ---------------------------------------------------------------------------


class TestParseGo:
    def test_single_import(self) -> None:
        source = 'import "fmt"\n'
        imports, _ = _parse_go(source)
        assert "fmt" in imports

    def test_block_import(self) -> None:
        source = """\
import (
    "fmt"
    "net/http"
    "github.com/user/pkg"
)
"""
        imports, _ = _parse_go(source)
        assert "fmt" in imports
        assert "net/http" in imports
        assert "github.com/user/pkg" in imports

    def test_definitions(self) -> None:
        source = """\
func main() {}
func (s *Server) Start() {}
type Config struct {}
type Handler interface {}
"""
        _, defs = _parse_go(source)
        assert "func main" in defs
        assert "func Start" in defs
        assert "type Config" in defs
        assert "type Handler" in defs


# ---------------------------------------------------------------------------
# Full workspace analysis
# ---------------------------------------------------------------------------


class TestAnalyzeWorkspace:
    def test_python_workspace(self, tmp_path: str) -> None:
        """Analyze a small Python project structure."""
        root = tempfile.mkdtemp()

        # Create source files
        src = os.path.join(root, "src", "myapp")
        os.makedirs(src)
        with open(os.path.join(src, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(src, "models.py"), "w") as f:
            f.write("from myapp.db import connect\n\nclass User:\n    pass\n")
        with open(os.path.join(src, "db.py"), "w") as f:
            f.write("import sqlite3\n\ndef connect():\n    pass\n")

        # Create test file
        tests = os.path.join(root, "tests")
        os.makedirs(tests)
        with open(os.path.join(tests, "test_models.py"), "w") as f:
            f.write("from myapp.models import User\n\ndef test_user():\n    pass\n")

        structure = analyze_workspace(root)

        assert len(structure.files) >= 3
        # Check role classification
        for path, info in structure.files.items():
            if "test_models" in path:
                assert info.role == "test"
            elif "models.py" in path:
                assert info.role == "source"

    def test_empty_workspace(self) -> None:
        """Empty dir produces empty structure."""
        root = tempfile.mkdtemp()
        structure = analyze_workspace(root)
        assert len(structure.files) == 0

    def test_nonexistent_dir(self) -> None:
        """Nonexistent dir returns empty structure."""
        structure = analyze_workspace("/nonexistent/path/xyz")
        assert len(structure.files) == 0


# ---------------------------------------------------------------------------
# WorkspaceStructure helpers
# ---------------------------------------------------------------------------


class TestWorkspaceStructure:
    def _sample_structure(self) -> WorkspaceStructure:
        ws = WorkspaceStructure()
        ws.files = {
            "src/a.py": FileInfo("src/a.py", "source", ("b",), ("class A",), "python"),
            "src/b.py": FileInfo("src/b.py", "source", ("c",), ("def b_func",), "python"),
            "src/c.py": FileInfo("src/c.py", "source", (), ("def c_func",), "python"),
            "tests/test_a.py": FileInfo("tests/test_a.py", "test", ("a",), ("def test_a",), "python"),
        }
        ws.dependency_graph = {
            "src/a.py": {"src/b.py"},
            "src/b.py": {"src/c.py"},
            "src/c.py": set(),
            "tests/test_a.py": {"src/a.py"},
        }
        ws.reverse_deps = {
            "src/b.py": {"src/a.py"},
            "src/c.py": {"src/b.py"},
            "src/a.py": {"tests/test_a.py"},
        }
        ws.test_companions = {"tests/test_a.py": "src/a.py"}
        return ws

    def test_neighbors_1hop(self) -> None:
        ws = self._sample_structure()
        n = ws.neighbors("src/a.py", max_hops=1)
        assert "src/b.py" in n
        assert "tests/test_a.py" in n
        assert "src/c.py" not in n

    def test_neighbors_2hop(self) -> None:
        ws = self._sample_structure()
        n = ws.neighbors("src/a.py", max_hops=2)
        assert "src/c.py" in n

    def test_relevant_context_nonempty(self) -> None:
        ws = self._sample_structure()
        ctx = ws.relevant_context(["src/a.py"])
        assert "src/a.py" in ctx
        assert "source" in ctx

    def test_relevant_context_empty_targets(self) -> None:
        ws = self._sample_structure()
        assert ws.relevant_context([]) == ""

    def test_relevant_context_budget(self) -> None:
        ws = self._sample_structure()
        ctx = ws.relevant_context(["src/a.py"], max_tokens=10)
        # Very tight budget — should still return something but be truncated
        assert len(ctx) <= 60  # 10 tokens * 4 chars + some margin


# ---------------------------------------------------------------------------
# Test companion detection
# ---------------------------------------------------------------------------


class TestTestCompanion:
    def test_naming_heuristic(self) -> None:
        all_files = {
            "src/auth.py": FileInfo("src/auth.py", "source", (), (), "python"),
            "tests/test_auth.py": FileInfo("tests/test_auth.py", "test", ("auth",), (), "python"),
        }
        test_info = all_files["tests/test_auth.py"]
        companion = _find_test_companion("tests/test_auth.py", test_info, all_files)
        assert companion == "src/auth.py"

    def test_no_match(self) -> None:
        all_files = {
            "src/models.py": FileInfo("src/models.py", "source", (), (), "python"),
        }
        test_info = FileInfo("tests/test_auth.py", "test", (), (), "python")
        companion = _find_test_companion("tests/test_auth.py", test_info, all_files)
        assert companion is None
