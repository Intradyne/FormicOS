"""Tests for workspace root resolution (Wave 81 Track A)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

from formicos.surface.workspace_roots import (
    workspace_binding_status,
    workspace_library_root,
    workspace_project_root,
    workspace_runtime_root,
)

if TYPE_CHECKING:
    from pathlib import Path


class TestWorkspaceLibraryRoot:
    def test_returns_path_under_data_dir(self, tmp_path: Path) -> None:
        result = workspace_library_root(str(tmp_path), "ws1")
        assert str(result).endswith("workspaces/ws1/files") or "ws1" in str(result)

    def test_different_workspace_ids(self, tmp_path: Path) -> None:
        r1 = workspace_library_root(str(tmp_path), "a")
        r2 = workspace_library_root(str(tmp_path), "b")
        assert r1 != r2


class TestWorkspaceProjectRoot:
    def test_returns_none_when_no_project_dir(self) -> None:
        with patch.dict(os.environ, {"PROJECT_DIR": "/nonexistent/path"}, clear=False):
            result = workspace_project_root("ws1")
            assert result is None

    def test_returns_path_when_project_exists(self, tmp_path: Path) -> None:
        project = tmp_path / "myproject"
        project.mkdir()
        with patch.dict(os.environ, {"PROJECT_DIR": str(project)}, clear=False):
            result = workspace_project_root("ws1")
            assert result is not None
            assert result == project

    def test_default_project_dir(self) -> None:
        # Default /project doesn't exist on test machine
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("PROJECT_DIR", None)
            result = workspace_project_root("ws1")
            # /project likely doesn't exist on dev machines
            assert result is None or result.is_dir()


class TestWorkspaceRuntimeRoot:
    def test_falls_back_to_library_when_no_project(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"PROJECT_DIR": "/nonexistent"}, clear=False):
            result = workspace_runtime_root(str(tmp_path), "ws1")
            assert "workspaces" in str(result)

    def test_uses_project_when_bound(self, tmp_path: Path) -> None:
        project = tmp_path / "myproject"
        project.mkdir()
        with patch.dict(os.environ, {"PROJECT_DIR": str(project)}, clear=False):
            result = workspace_runtime_root(str(tmp_path), "ws1")
            assert result == project


class TestWorkspaceBindingStatus:
    def test_unbound_status(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"PROJECT_DIR": "/nonexistent"}, clear=False):
            status = workspace_binding_status(str(tmp_path), "ws1")
            assert status["project_bound"] is False
            assert status["project_root"] is None
            assert "library_root" in status
            assert "runtime_root" in status

    def test_bound_status(self, tmp_path: Path) -> None:
        project = tmp_path / "myproject"
        project.mkdir()
        with patch.dict(os.environ, {"PROJECT_DIR": str(project)}, clear=False):
            status = workspace_binding_status(str(tmp_path), "ws1")
            assert status["project_bound"] is True
            assert status["project_root"] == str(project)
            assert status["runtime_root"] == str(project)
