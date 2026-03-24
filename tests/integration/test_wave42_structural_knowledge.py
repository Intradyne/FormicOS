"""Integration tests for Wave 42 structural analysis + topology prior."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from formicos.adapters.code_analysis import analyze_workspace
from formicos.engine.runner import _compute_knowledge_prior, _PRIOR_MIN


def _make_agent(agent_id: str, caste: str = "coder") -> MagicMock:
    agent = MagicMock()
    agent.id = agent_id
    agent.caste = caste
    recipe = MagicMock()
    recipe.name = caste
    agent.recipe = recipe
    return agent


class TestStructuralAnalysisToPrior:
    """End-to-end: workspace → structural analysis → topology prior."""

    def test_python_project_produces_structural_prior(self) -> None:
        """A real Python project produces dependency-based topology prior."""
        root = tempfile.mkdtemp()
        src = os.path.join(root, "src", "myapp")
        os.makedirs(src)

        with open(os.path.join(src, "__init__.py"), "w") as f:
            f.write("")
        with open(os.path.join(src, "api.py"), "w") as f:
            f.write("from myapp.models import User\nfrom myapp.db import connect\n\ndef handle_request(): pass\n")
        with open(os.path.join(src, "models.py"), "w") as f:
            f.write("from myapp.db import connect\n\nclass User: pass\n")
        with open(os.path.join(src, "db.py"), "w") as f:
            f.write("import sqlite3\n\ndef connect(): pass\n")

        tests_dir = os.path.join(root, "tests")
        os.makedirs(tests_dir)
        with open(os.path.join(tests_dir, "test_api.py"), "w") as f:
            f.write("from myapp.api import handle_request\n\ndef test_api(): pass\n")

        # Analyze workspace
        structure = analyze_workspace(root)
        assert len(structure.files) >= 4
        assert len(structure.dependency_graph) > 0

        # Extract deps subset for target files
        target_files = ["src/myapp/api.py"]
        deps: dict[str, list[str]] = {}
        relevant = set(target_files)
        for tf in target_files:
            relevant.update(structure.neighbors(tf, max_hops=1))
        for f in relevant:
            if f in structure.dependency_graph:
                deps[f] = sorted(structure.dependency_graph[f])

        # Compute prior with structural deps
        agents = [_make_agent("a1", "coder"), _make_agent("a2", "reviewer")]
        prior = _compute_knowledge_prior(
            agents, None,
            structural_deps=deps,
            target_files=target_files,
        )

        assert prior is not None
        for val in prior.values():
            assert val >= _PRIOR_MIN

    def test_no_workspace_falls_back_gracefully(self) -> None:
        """Non-existent workspace dir produces neutral prior."""
        agents = [_make_agent("a1"), _make_agent("a2")]
        structure = analyze_workspace("/nonexistent")
        deps = {}
        prior = _compute_knowledge_prior(
            agents, None,
            structural_deps=deps,
            target_files=["src/a.py"],
        )
        assert prior is None

    def test_structural_context_string_bounded(self) -> None:
        """Structural context stays within token budget."""
        root = tempfile.mkdtemp()
        src = os.path.join(root, "src")
        os.makedirs(src)

        # Create many files
        for i in range(20):
            with open(os.path.join(src, f"mod_{i}.py"), "w") as f:
                imports = [f"from mod_{j} import something" for j in range(max(0, i - 2), i)]
                f.write("\n".join(imports) + f"\n\ndef func_{i}(): pass\n")

        structure = analyze_workspace(root)
        ctx = structure.relevant_context(["src/mod_10.py"], max_tokens=500)

        # ~500 tokens * 4 chars = 2000 chars max
        assert len(ctx) <= 2500
        assert "mod_10" in ctx

    def test_test_companion_detection(self) -> None:
        """Test companion mapping works for naming-heuristic matches."""
        root = tempfile.mkdtemp()
        src = os.path.join(root, "src")
        tests_dir = os.path.join(root, "tests")
        os.makedirs(src)
        os.makedirs(tests_dir)

        with open(os.path.join(src, "auth.py"), "w") as f:
            f.write("def authenticate(): pass\n")
        with open(os.path.join(tests_dir, "test_auth.py"), "w") as f:
            f.write("from auth import authenticate\n\ndef test_auth(): pass\n")

        structure = analyze_workspace(root)
        # Should detect test_auth.py → auth.py companion
        assert len(structure.test_companions) >= 1
        for test_path, source_path in structure.test_companions.items():
            assert "test_auth" in test_path
            assert "auth.py" in source_path

    def test_js_workspace(self) -> None:
        """JS/TS regex parsing produces structural facts."""
        root = tempfile.mkdtemp()
        src = os.path.join(root, "src")
        os.makedirs(src)

        with open(os.path.join(src, "app.ts"), "w") as f:
            f.write("import { Router } from './router';\nimport React from 'react';\n\nexport class App {}\n")
        with open(os.path.join(src, "router.ts"), "w") as f:
            f.write("export function createRouter() {}\nexport class Router {}\n")

        structure = analyze_workspace(root)
        app_info = structure.files.get("src/app.ts")
        assert app_info is not None
        assert app_info.language == "typescript"
        assert "./router" in app_info.imports or "react" in app_info.imports
        assert "class App" in app_info.definitions

    def test_go_workspace(self) -> None:
        """Go regex parsing produces structural facts."""
        root = tempfile.mkdtemp()
        pkg = os.path.join(root, "pkg", "auth")
        os.makedirs(pkg)

        with open(os.path.join(pkg, "handler.go"), "w") as f:
            f.write("""package auth

import (
    "fmt"
    "net/http"
)

func HandleLogin() {}
type AuthService struct {}
""")

        structure = analyze_workspace(root)
        handler_info = None
        for path, info in structure.files.items():
            if "handler.go" in path:
                handler_info = info
                break

        assert handler_info is not None
        assert handler_info.language == "go"
        assert "fmt" in handler_info.imports
        assert "net/http" in handler_info.imports
        assert "func HandleLogin" in handler_info.definitions
        assert "type AuthService" in handler_info.definitions
