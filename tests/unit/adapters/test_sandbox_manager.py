"""Tests for sandbox_manager.py (Wave 20 Track A)."""

from __future__ import annotations

import os
import shutil
import sys
from unittest.mock import AsyncMock, patch

import pytest

from formicos.adapters.sandbox_manager import (
    MAX_TIMEOUT_S,
    SANDBOX_IMAGE,
    _execute_docker,
    _execute_subprocess,
    _execute_workspace_docker,
    execute_sandboxed,
)
from formicos.core.types import WorkspaceExecutionResult


class TestSandboxEnabled:
    """SANDBOX_ENABLED flag behaviour."""

    @pytest.mark.asyncio
    async def test_sandbox_disabled_skips_docker(self) -> None:
        """When SANDBOX_ENABLED=false, _execute_docker is never called."""
        with (
            patch("formicos.adapters.sandbox_manager.SANDBOX_ENABLED", False),
            patch("formicos.adapters.sandbox_manager._execute_subprocess", new_callable=AsyncMock) as mock_sub,
            patch("formicos.adapters.sandbox_manager._execute_docker", new_callable=AsyncMock) as mock_docker,
        ):
            from formicos.core.types import SandboxExecutionResult
            mock_sub.return_value = SandboxExecutionResult(stdout="ok", stderr="", exit_code=0)
            result = await execute_sandboxed("print('hi')")
            mock_docker.assert_not_called()
            mock_sub.assert_awaited_once()
            assert result.stdout == "ok"

    @pytest.mark.asyncio
    async def test_sandbox_enabled_tries_docker_first(self) -> None:
        """When SANDBOX_ENABLED=true, tries Docker before subprocess."""
        with (
            patch("formicos.adapters.sandbox_manager.SANDBOX_ENABLED", True),
            patch("formicos.adapters.sandbox_manager._execute_docker", new_callable=AsyncMock) as mock_docker,
        ):
            from formicos.core.types import SandboxExecutionResult
            mock_docker.return_value = SandboxExecutionResult(stdout="4", stderr="", exit_code=0)
            result = await execute_sandboxed("print(2+2)")
            mock_docker.assert_awaited_once()
            assert result.stdout == "4"

    @pytest.mark.asyncio
    async def test_docker_failure_falls_back_to_subprocess(self) -> None:
        """If Docker fails, falls back to subprocess."""
        with (
            patch("formicos.adapters.sandbox_manager.SANDBOX_ENABLED", True),
            patch("formicos.adapters.sandbox_manager._execute_docker", new_callable=AsyncMock) as mock_docker,
            patch("formicos.adapters.sandbox_manager._execute_subprocess", new_callable=AsyncMock) as mock_sub,
        ):
            from formicos.core.types import SandboxExecutionResult
            mock_docker.side_effect = FileNotFoundError("docker not found")
            mock_sub.return_value = SandboxExecutionResult(stdout="fallback", stderr="", exit_code=0)
            result = await execute_sandboxed("print('hi')")
            mock_docker.assert_awaited_once()
            mock_sub.assert_awaited_once()
            assert result.stdout == "fallback"


class TestTimeoutClamping:
    """Timeout is clamped to MAX_TIMEOUT_S."""

    @pytest.mark.asyncio
    async def test_timeout_clamped(self) -> None:
        with (
            patch("formicos.adapters.sandbox_manager.SANDBOX_ENABLED", False),
            patch("formicos.adapters.sandbox_manager._execute_subprocess", new_callable=AsyncMock) as mock_sub,
        ):
            from formicos.core.types import SandboxExecutionResult
            mock_sub.return_value = SandboxExecutionResult(stdout="", stderr="", exit_code=0)
            await execute_sandboxed("x=1", timeout_s=999)
            # The effective timeout passed to subprocess should be clamped
            call_args = mock_sub.call_args
            assert call_args[0][1] <= MAX_TIMEOUT_S


class TestConstants:
    """Verify sandbox constants are set correctly."""

    def test_sandbox_image(self) -> None:
        assert SANDBOX_IMAGE == "formicos-sandbox:latest"

    def test_max_timeout(self) -> None:
        assert MAX_TIMEOUT_S == 30


class _DummyProc:
    def __init__(self, stdout: bytes = b"ok", stderr: bytes = b"") -> None:
        self.returncode = 0
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return (self._stdout, self._stderr)


class TestSubprocessFallback:
    @pytest.mark.asyncio
    async def test_subprocess_uses_current_python_and_restricted_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FORMICOS_TEST_SENTINEL", "1")

        with patch("formicos.adapters.sandbox_manager.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _DummyProc()

            result = await _execute_subprocess("print('hi')", 5)

            assert result.stdout == "ok"
            call_args = mock_exec.call_args
            assert call_args.args[0] == sys.executable
            env = call_args.kwargs["env"]
            assert env["PATH"] == ""
            assert env["PYTHONDONTWRITEBYTECODE"] == "1"
            assert env["FORMICOS_TEST_SENTINEL"] == "1"
            assert env["HOME"]
            system_root = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
            if system_root is not None:
                assert env.get("SystemRoot") == system_root or env.get("SYSTEMROOT") == system_root


class TestDockerExecution:
    @pytest.mark.asyncio
    async def test_docker_pipes_code_via_stdin(self) -> None:
        with patch("formicos.adapters.sandbox_manager.asyncio.create_subprocess_exec", new_callable=AsyncMock) as mock_exec:
            mock_proc = _DummyProc(stdout=b"4\n")
            mock_proc.communicate = AsyncMock(return_value=(b"4\n", b""))  # type: ignore[assignment]
            mock_exec.return_value = mock_proc

            result = await _execute_docker("print(2+2)", 5)

            assert result.stdout == "4\n"
            call_args = mock_exec.call_args
            assert SANDBOX_IMAGE in call_args.args
            # Code is passed via stdin, not bind-mounted
            image_index = call_args.args.index(SANDBOX_IMAGE)
            assert call_args.args[image_index + 1] == "-"
            assert "-i" in call_args.args
            # stdin pipe must be set
            assert call_args.kwargs.get("stdin") is not None
            # Code is sent via communicate(input=...)
            mock_proc.communicate.assert_awaited_once()
            sent_input = mock_proc.communicate.call_args.kwargs.get("input")
            assert sent_input == b"print(2+2)"


class TestWorkspaceDockerExecution:
    @pytest.mark.asyncio
    async def test_workspace_archive_and_restore_use_to_thread(self) -> None:
        from pathlib import Path

        work_path = Path(".sandbox-manager-test-workspace")
        if work_path.exists():
            shutil.rmtree(work_path)
        work_path.mkdir()
        try:
            (work_path / "example.txt").write_text("hello", encoding="utf-8")
            before_snapshot = (set(), {})

            async def fake_run_exec(*cmd: str, **kwargs: object) -> tuple[int, bytes, bytes, bool]:
                if cmd[:2] == ("docker", "create"):
                    return 0, b"container-123\n", b"", False
                if cmd[:2] == ("docker", "start"):
                    return 0, b"", b"", False
                if cmd[:3] == ("docker", "exec", "-i"):
                    assert kwargs["input_bytes"] == b"workspace-archive"
                    return 0, b"", b"", False
                if cmd[:3] == ("docker", "exec", "container-123") and "cd /workspace && tar -cf - ." in cmd:
                    return 0, b"restored-archive", b"", False
                if cmd[:3] == ("docker", "exec", "container-123"):
                    return 0, b"stdout", b"stderr", False
                if cmd[:3] == ("docker", "rm", "-f"):
                    return 0, b"", b"", False
                msg = f"unexpected command: {cmd}"
                raise AssertionError(msg)

            async def fake_to_thread(func: object, *args: object) -> object:
                if getattr(func, "__name__", "") == "_archive_workspace":
                    assert args == (work_path,)
                    return b"workspace-archive"
                if getattr(func, "__name__", "") == "_restore_workspace_from_archive":
                    assert args == (b"restored-archive", work_path)
                    return None
                msg = f"unexpected to_thread target: {func!r}"
                raise AssertionError(msg)

            with (
                patch("formicos.adapters.sandbox_manager._run_exec", side_effect=fake_run_exec),
                patch("formicos.adapters.sandbox_manager.asyncio.to_thread", side_effect=fake_to_thread) as mock_to_thread,
                patch(
                    "formicos.adapters.sandbox_manager._build_workspace_result",
                    return_value=WorkspaceExecutionResult(
                        stdout="stdout",
                        stderr="stderr",
                        exit_code=0,
                        command="pytest -q",
                        working_dir=str(work_path),
                    ),
                ) as mock_result,
            ):
                result = await _execute_workspace_docker(
                    "pytest -q",
                    work_path,
                    30,
                    before_snapshot,
                )
        finally:
            shutil.rmtree(work_path, ignore_errors=True)

        assert result.exit_code == 0
        assert mock_to_thread.await_count == 2
        assert mock_result.called
