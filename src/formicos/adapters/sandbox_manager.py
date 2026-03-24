"""Sandboxed code execution via Docker containers (Wave 14, Wave 20, Wave 43).

Provides isolated Python execution with resource limits.
Falls back to subprocess with restricted environment when Docker is unavailable.

Set ``SANDBOX_ENABLED=false`` to skip Docker entirely and always use the
subprocess fallback — useful for development without Docker socket access.

Wave 41 B1: Adds workspace command execution — repo-backed commands
(test runners, linters, build tools) in a working directory with structured
failure parsing. Separate from sandbox execution (different concern).

Wave 43: Container hardening and workspace executor isolation.
- Sandbox containers: --cap-drop=ALL, --security-opt=no-new-privileges,
  --pids-limit=256, custom seccomp profile.
- Workspace executor: runs commands inside disposable containers instead of
  unsandboxed host-shell subprocess. Network-aware phase execution.
- Git clone: hooks disabled, submodules off, symlinks off, shallow by default.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Any

import structlog

from formicos.core.types import (
    SandboxExecutionResult,
    TestFailure,
    WorkspaceExecutionResult,
)

log = structlog.get_logger()

# Container image for sandboxed execution
SANDBOX_IMAGE = "formicos-sandbox:latest"

# Container image for workspace execution (repo-backed commands)
WORKSPACE_IMAGE = os.environ.get(
    "WORKSPACE_IMAGE", "python:3.12-slim",
)

# Resource limits
DEFAULT_TIMEOUT_S = 10
MAX_TIMEOUT_S = 30
MEMORY_LIMIT_MB = 256
MAX_OUTPUT_BYTES = 50_000  # 50KB raw before sanitization

# Workspace executor resource limits (more generous for real builds/tests)
WORKSPACE_MEMORY_LIMIT_MB = int(os.environ.get("WORKSPACE_MEMORY_MB", "512"))
WORKSPACE_PIDS_LIMIT = 512

# Feature flag: set SANDBOX_ENABLED=false to skip Docker and use subprocess only.
SANDBOX_ENABLED = os.environ.get("SANDBOX_ENABLED", "true").lower() in ("true", "1", "yes")

# Feature flag: set WORKSPACE_ISOLATION=false to use legacy host-shell execution.
WORKSPACE_ISOLATION = os.environ.get(
    "WORKSPACE_ISOLATION", "true",
).lower() in ("true", "1", "yes")

# Seccomp profile path (shipped alongside the source tree)
_SECCOMP_PROFILE = Path(__file__).parent.parent.parent.parent / "config" / "seccomp-sandbox.json"


async def execute_sandboxed(
    code: str,
    timeout_s: int = DEFAULT_TIMEOUT_S,
) -> SandboxExecutionResult:
    """Execute Python code in a sandboxed environment.

    When ``SANDBOX_ENABLED`` is true (default), tries Docker first then falls
    back to subprocess. When false, skips Docker entirely.
    """
    timeout_s = min(timeout_s, MAX_TIMEOUT_S)

    if SANDBOX_ENABLED:
        try:
            return await _execute_docker(code, timeout_s)
        except Exception:
            log.debug("sandbox.docker_unavailable", fallback="subprocess")

    # Fallback: restricted subprocess
    return await _execute_subprocess(code, timeout_s)


async def _execute_docker(
    code: str,
    timeout_s: int,
) -> SandboxExecutionResult:
    """Execute code inside a Docker container with resource limits.

    Code is piped via stdin rather than bind-mounted as a temp file.
    Bind-mount fails in Docker-in-Docker (e.g. formicos running inside a
    container with the host Docker socket): the daemon resolves mount paths
    against the *host* filesystem, not the inner container, so the temp file
    is invisible and Docker auto-creates it as an empty directory.

    Wave 43: Hardened container profile — capabilities dropped, no privilege
    escalation, PID limit, custom seccomp profile when available.
    """
    cmd: list[str] = [
        "docker", "run",
        "--rm",
        "-i",
        "--network=none",
        f"--memory={MEMORY_LIMIT_MB}m",
        "--cpus=0.5",
        "--read-only",
        "--tmpfs", "/tmp:size=50m",
        # Wave 43 hardening
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
    ]
    if _SECCOMP_PROFILE.is_file():
        cmd.extend(["--security-opt", f"seccomp={_SECCOMP_PROFILE}"])
    cmd.extend([SANDBOX_IMAGE, "-"])  # python reads script from stdin

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=code.encode()),
            timeout=timeout_s,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return SandboxExecutionResult(
            stdout="",
            stderr=f"Execution timed out after {timeout_s}s",
            exit_code=124,
        )

    return SandboxExecutionResult(
        stdout=stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        stderr=stderr_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        exit_code=proc.returncode or 0,
    )


async def _execute_subprocess(
    code: str,
    timeout_s: int,
) -> SandboxExecutionResult:
    """Fallback: execute in a restricted subprocess (no Docker)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False,
    ) as f:
        f.write(code)
        script_path = f.name

    try:
        temp_home = tempfile.gettempdir()
        restricted_env = os.environ.copy()
        restricted_env.update({
            "PATH": "",
            "HOME": temp_home,
            "TMPDIR": temp_home,
            "TEMP": temp_home,
            "TMP": temp_home,
            "PYTHONDONTWRITEBYTECODE": "1",
        })
        proc = await asyncio.create_subprocess_exec(
            sys.executable, script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=restricted_env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_s,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return SandboxExecutionResult(
                stdout="",
                stderr=f"Execution timed out after {timeout_s}s",
                exit_code=124,
            )

        return SandboxExecutionResult(
            stdout=stdout_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            stderr=stderr_bytes[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
        )
    finally:
        Path(script_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Wave 41 B1 / Wave 43: Workspace command execution
# ---------------------------------------------------------------------------

WORKSPACE_MAX_TIMEOUT_S = 120
WORKSPACE_MAX_OUTPUT_BYTES = 100_000  # 100KB

# Commands that are considered dependency/setup phase (may need network)
_SETUP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(pip|uv|npm|yarn|pnpm|cargo|go)\s+(install|add|sync|get|mod)\b"),
    re.compile(r"\bapt(-get)?\s+install\b"),
]


def _is_setup_command(command: str) -> bool:
    """Return True if *command* looks like a dependency-install phase."""
    return any(p.search(command) for p in _SETUP_PATTERNS)


def _snapshot_workspace(
    work_path: Path,
) -> tuple[set[str], dict[str, tuple[int, int]]]:
    """Return a lightweight snapshot of workspace directories and files."""
    dirs: set[str] = set()
    files: dict[str, tuple[int, int]] = {}

    for path in work_path.rglob("*"):
        rel = path.relative_to(work_path).as_posix()
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        if path.is_dir():
            dirs.add(f"{rel}/")
        elif path.is_file():
            files[rel] = (stat.st_size, stat.st_mtime_ns)

    return dirs, files


def _diff_workspace(
    before: tuple[set[str], dict[str, tuple[int, int]]],
    after: tuple[set[str], dict[str, tuple[int, int]]],
) -> tuple[list[str], list[str], list[str]]:
    """Return created, modified, and deleted workspace paths."""
    before_dirs, before_files = before
    after_dirs, after_files = after

    created = sorted((after_dirs - before_dirs) | (after_files.keys() - before_files.keys()))
    deleted = sorted((before_dirs - after_dirs) | (before_files.keys() - after_files.keys()))
    modified = sorted(
        path
        for path in (after_files.keys() & before_files.keys())
        if after_files[path] != before_files[path]
    )
    return created, modified, deleted


def _looks_like_workspace_mutation(command: str) -> bool:
    """Heuristic: return True when a shell command is expected to touch files."""
    lowered = command.lower()
    mutation_markers = (
        ">",
        ">>",
        "mkdir",
        "touch",
        "tee ",
        " cp ",
        " mv ",
        " rm ",
        " install ",
        "patch",
        "sed -i",
        "printf ",
        "echo ",
    )
    return any(marker in lowered for marker in mutation_markers)


def _build_workspace_result(
    *,
    command: str,
    work_path: Path,
    stdout: str,
    stderr: str,
    exit_code: int,
    timed_out: bool = False,
    before_snapshot: tuple[set[str], dict[str, tuple[int, int]]] | None = None,
) -> WorkspaceExecutionResult:
    """Build a structured workspace execution result with filesystem diff."""
    after_snapshot = _snapshot_workspace(work_path)
    created: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []
    warning = ""
    if before_snapshot is not None:
        created, modified, deleted = _diff_workspace(before_snapshot, after_snapshot)
        if (
            exit_code == 0
            and _looks_like_workspace_mutation(command)
            and not (created or modified or deleted)
        ):
            warning = (
                "Command exited successfully but no workspace changes were detected. "
                "This may indicate a sandbox copy or permission issue."
            )

    combined = stdout + "\n" + stderr
    parsed = parse_test_output(combined)

    return WorkspaceExecutionResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        command=command,
        working_dir=str(work_path),
        timed_out=timed_out,
        files_created=created,
        files_modified=modified,
        files_deleted=deleted,
        warning=warning,
        tests_passed=parsed["tests_passed"],
        tests_failed=parsed["tests_failed"],
        tests_errored=parsed["tests_errored"],
        test_failures=parsed["test_failures"],
        language=parsed["language"],
    )


async def _run_exec(
    *cmd: str,
    timeout_s: int | None = None,
    input_bytes: bytes | None = None,
) -> tuple[int, bytes, bytes, bool]:
    """Run a subprocess command and return exit/stdout/stderr/timed_out."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE if input_bytes is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(input=input_bytes),
            timeout=timeout_s,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, b"", f"Command timed out after {timeout_s}s".encode(), True
    return proc.returncode or 0, stdout_bytes, stderr_bytes, False


def _archive_workspace(work_path: Path) -> bytes:
    """Create a tar archive of workspace contents."""
    with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
        tar_path = Path(tmp.name)
    try:
        with tarfile.open(tar_path, "w") as tf:
            for child in work_path.iterdir():
                tf.add(child, arcname=child.name, recursive=True)
        return tar_path.read_bytes()
    finally:
        tar_path.unlink(missing_ok=True)


def _restore_workspace_from_archive(archive: bytes, work_path: Path) -> None:
    """Replace workspace contents with files extracted from *archive*."""
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        with tempfile.NamedTemporaryFile(suffix=".tar", delete=False) as tmp:
            tar_path = Path(tmp.name)
            tmp.write(archive)
        try:
            with tarfile.open(tar_path, "r:*") as tf:
                tf.extractall(temp_dir)
        finally:
            tar_path.unlink(missing_ok=True)

        for child in list(work_path.iterdir()):
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)

        for child in temp_dir.iterdir():
            target = work_path / child.name
            if child.is_dir():
                shutil.copytree(child, target, symlinks=True)
            else:
                shutil.copy2(child, target)


async def execute_workspace_command(
    command: str,
    working_dir: str,
    timeout_s: int = 60,
) -> WorkspaceExecutionResult:
    """Execute a shell command in a workspace directory.

    Wave 43: When WORKSPACE_ISOLATION is true and Docker is available, runs
    commands inside a disposable container with workspace contents copied in
    and copied back out so Docker-in-Docker deployments stay truthful.
    Network access is allowed only for dependency-install commands; test/build
    execution runs with --network=none.

    Falls back to host-shell execution when Docker is unavailable or
    WORKSPACE_ISOLATION is false.
    """
    timeout_s = min(timeout_s, WORKSPACE_MAX_TIMEOUT_S)

    work_path = Path(working_dir)
    if not work_path.is_dir():
        return WorkspaceExecutionResult(
            exit_code=1,
            stderr=f"Working directory does not exist: {working_dir}",
            command=command,
            working_dir=working_dir,
        )
    before_snapshot = _snapshot_workspace(work_path)

    log.info("workspace.execute", command=command, working_dir=working_dir,
             isolated=WORKSPACE_ISOLATION)

    if WORKSPACE_ISOLATION and SANDBOX_ENABLED:
        try:
            return await _execute_workspace_docker(
                command, work_path, timeout_s, before_snapshot,
            )
        except Exception:
            log.warning("workspace.docker_unavailable", fallback="subprocess")

    return await _execute_workspace_subprocess(
        command, work_path, timeout_s, before_snapshot,
    )


async def _execute_workspace_docker(
    command: str,
    work_path: Path,
    timeout_s: int,
) -> WorkspaceExecutionResult:
    """Run *command* inside a disposable container with *work_path* mounted.

    Phase-aware networking:
    - Setup commands (pip install, npm install, etc.) → network allowed
    - Test/build commands → --network=none
    """
    network = "bridge" if _is_setup_command(command) else "none"
    workspace_mount = str(work_path.resolve())

    cmd: list[str] = [
        "docker", "run",
        "--rm",
        f"--network={network}",
        f"--memory={WORKSPACE_MEMORY_LIMIT_MB}m",
        "--cpus=1.0",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--pids-limit={WORKSPACE_PIDS_LIMIT}",
        "--tmpfs", "/tmp:size=100m",
        "-v", f"{workspace_mount}:/workspace",
        "-w", "/workspace",
        WORKSPACE_IMAGE,
        "sh", "-c", command,
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout_s,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return WorkspaceExecutionResult(
            stdout="",
            stderr=f"Command timed out after {timeout_s}s",
            exit_code=124,
            command=command,
            working_dir=str(work_path),
            timed_out=True,
        )

    stdout = stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    stderr = stderr_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    exit_code = proc.returncode or 0

    combined = stdout + "\n" + stderr
    parsed = parse_test_output(combined)

    return WorkspaceExecutionResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        command=command,
        working_dir=str(work_path),
        tests_passed=parsed["tests_passed"],
        tests_failed=parsed["tests_failed"],
        tests_errored=parsed["tests_errored"],
        test_failures=parsed["test_failures"],
        language=parsed["language"],
    )


async def _execute_workspace_subprocess(
    command: str,
    work_path: Path,
    timeout_s: int,
) -> WorkspaceExecutionResult:
    """Legacy host-shell fallback for workspace execution."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_path),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_s,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return WorkspaceExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout_s}s",
                exit_code=124,
                command=command,
                working_dir=str(work_path),
                timed_out=True,
            )

        stdout = stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode(
            "utf-8", errors="replace",
        )
        stderr = stderr_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode(
            "utf-8", errors="replace",
        )
        exit_code = proc.returncode or 0

        combined = stdout + "\n" + stderr
        parsed = parse_test_output(combined)

        return WorkspaceExecutionResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            command=command,
            working_dir=str(work_path),
            tests_passed=parsed["tests_passed"],
            tests_failed=parsed["tests_failed"],
            tests_errored=parsed["tests_errored"],
            test_failures=parsed["test_failures"],
            language=parsed["language"],
        )

    except OSError as exc:
        return WorkspaceExecutionResult(
            exit_code=1,
            stderr=f"Failed to execute command: {exc}",
            command=command,
            working_dir=str(work_path),
        )


# ---------------------------------------------------------------------------
# Test output parsers — detect common test runner formats
# ---------------------------------------------------------------------------

# pytest: "5 passed, 2 failed, 1 error in 3.45s"
_PYTEST_SUMMARY = re.compile(
    r"(?:=+\s*)?"
    r"(?:(?P<failed>\d+)\s+failed)?"
    r"[,\s]*"
    r"(?:(?P<passed>\d+)\s+passed)?"
    r"[,\s]*"
    r"(?:(?P<error>\d+)\s+error)?"
    r"[,\s]*in\s+[\d.]+s",
)

# pytest FAILED line: "FAILED tests/test_foo.py::TestBar::test_baz - AssertionError: ..."
_PYTEST_FAILURE = re.compile(
    r"FAILED\s+(?P<path>[^\s:]+)::(?P<name>[^\s]+)"
    r"(?:\s*-\s*(?P<error_type>\w+):\s*(?P<message>.+))?",
)

# Generic xunit: "Tests run: 10, Failures: 2, Errors: 1"
_XUNIT_SUMMARY = re.compile(
    r"Tests?\s+run:\s*(?P<total>\d+)"
    r"[,\s]+Failures?:\s*(?P<failed>\d+)"
    r"[,\s]+Errors?:\s*(?P<error>\d+)",
)

# Node/jest: "Tests: 2 failed, 5 passed, 7 total"
_JEST_SUMMARY = re.compile(
    r"Tests?:\s+"
    r"(?:(?P<failed>\d+)\s+failed,?\s*)?"
    r"(?:(?P<passed>\d+)\s+passed,?\s*)?"
    r"(?P<total>\d+)\s+total",
)

# Go test: "ok" / "FAIL" lines + "--- FAIL: TestName"
_GO_FAIL = re.compile(r"---\s+FAIL:\s+(?P<name>\S+)")

# Cargo test: "test result: FAILED. 3 passed; 1 failed;"
_CARGO_SUMMARY = re.compile(
    r"test result:.*?"
    r"(?P<passed>\d+)\s+passed"
    r"[;\s]+"
    r"(?P<failed>\d+)\s+failed",
)


def parse_test_output(output: str) -> dict[str, Any]:
    """Parse test runner output into structured results.

    Detects pytest, jest/node, xunit (Java/C#), Go test, and Cargo test
    output formats. Returns a dict with test counts, failures, and language.
    """
    result: dict[str, Any] = {
        "tests_passed": 0,
        "tests_failed": 0,
        "tests_errored": 0,
        "test_failures": list[TestFailure](),
        "language": "",
    }

    # Try pytest first (most common for FormicOS work)
    m = _PYTEST_SUMMARY.search(output)
    if m:
        result["language"] = "python/pytest"
        result["tests_passed"] = int(m.group("passed") or 0)
        result["tests_failed"] = int(m.group("failed") or 0)
        result["tests_errored"] = int(m.group("error") or 0)
        # Extract individual failure details
        for fm in _PYTEST_FAILURE.finditer(output):
            path = fm.group("path") or ""
            result["test_failures"].append(TestFailure(
                test_name=fm.group("name") or "",
                error_type=fm.group("error_type") or "",
                message=fm.group("message") or "",
                file_path=path,
            ))
        return result

    # Jest / node
    m = _JEST_SUMMARY.search(output)
    if m:
        result["language"] = "javascript/jest"
        result["tests_passed"] = int(m.group("passed") or 0)
        result["tests_failed"] = int(m.group("failed") or 0)
        total = int(m.group("total") or 0)
        result["tests_errored"] = max(
            0, total - result["tests_passed"] - result["tests_failed"],
        )
        return result

    # Cargo (Rust)
    m = _CARGO_SUMMARY.search(output)
    if m:
        result["language"] = "rust/cargo"
        result["tests_passed"] = int(m.group("passed") or 0)
        result["tests_failed"] = int(m.group("failed") or 0)
        return result

    # Go test
    go_failures = _GO_FAIL.findall(output)
    if go_failures or "--- PASS:" in output:
        result["language"] = "go/test"
        result["tests_failed"] = len(go_failures)
        # Count PASS lines
        result["tests_passed"] = output.count("--- PASS:")
        for name in go_failures:
            result["test_failures"].append(TestFailure(test_name=name))
        return result

    # xunit (Java, C#, etc.)
    m = _XUNIT_SUMMARY.search(output)
    if m:
        result["language"] = "xunit"
        total = int(m.group("total") or 0)
        result["tests_failed"] = int(m.group("failed") or 0)
        result["tests_errored"] = int(m.group("error") or 0)
        result["tests_passed"] = max(
            0, total - result["tests_failed"] - result["tests_errored"],
        )
        return result

    return result


# ---------------------------------------------------------------------------
# Wave 43: Git clone security defaults
# ---------------------------------------------------------------------------

# Default shallow depth for git clones
GIT_SHALLOW_DEPTH = int(os.environ.get("GIT_CLONE_DEPTH", "1"))


def build_safe_git_clone_args(
    url: str,
    dest: str,
    *,
    branch: str | None = None,
    depth: int | None = None,
    allow_hooks: bool = False,
    allow_submodules: bool = False,
) -> list[str]:
    """Build a git clone command with hardened defaults.

    Wave 43 security defaults:
    - Shallow clone (depth=1) unless explicitly expanded
    - Hooks disabled via core.hooksPath=/dev/null
    - No recursive submodules
    - Symlinks disabled (core.symlinks=false)
    - Transfer fsck enabled for object verification
    """
    effective_depth = depth if depth is not None else GIT_SHALLOW_DEPTH
    cmd = [
        "git",
        "-c", "protocol.file.allow=user",
        "-c", "transfer.fsckObjects=true",
    ]
    if not allow_hooks:
        cmd.extend(["-c", "core.hooksPath=/dev/null"])
    cmd.extend(["-c", "core.symlinks=false"])
    cmd.append("clone")
    if effective_depth > 0:
        cmd.extend(["--depth", str(effective_depth)])
    if not allow_submodules:
        cmd.append("--no-recurse-submodules")
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([url, dest])
    return cmd


async def safe_git_clone(
    url: str,
    dest: str,
    *,
    branch: str | None = None,
    depth: int | None = None,
    timeout_s: int = 120,
    allow_hooks: bool = False,
    allow_submodules: bool = False,
) -> WorkspaceExecutionResult:
    """Clone a git repository with hardened defaults.

    Runs the clone command inside a container when workspace isolation is
    enabled, otherwise falls back to host execution.
    """
    cmd = build_safe_git_clone_args(
        url, dest if not WORKSPACE_ISOLATION else "/workspace/repo",
        branch=branch, depth=depth,
        allow_hooks=allow_hooks, allow_submodules=allow_submodules,
    )
    command_str = " ".join(cmd)

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    if WORKSPACE_ISOLATION and SANDBOX_ENABLED:
        try:
            return await _execute_workspace_docker(
                command_str,
                dest_path.parent,
                timeout_s,
                _snapshot_workspace(dest_path.parent),
            )
        except Exception:
            log.warning("git_clone.docker_unavailable", fallback="subprocess")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s,
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return WorkspaceExecutionResult(
            stdout="", stderr=f"git clone timed out after {timeout_s}s",
            exit_code=124, command=command_str, working_dir=str(dest_path.parent),
            timed_out=True,
        )

    return WorkspaceExecutionResult(
        stdout=stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        stderr=stderr_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
        exit_code=proc.returncode or 0,
        command=command_str, working_dir=str(dest_path.parent),
    )


async def _execute_workspace_docker(
    command: str,
    work_path: Path,
    timeout_s: int,
    before_snapshot: tuple[set[str], dict[str, tuple[int, int]]],
) -> WorkspaceExecutionResult:
    """Run *command* inside a disposable container with tar copy-in/copy-out."""
    network = "bridge" if _is_setup_command(command) else "none"
    create_cmd: list[str] = [
        "docker", "create",
        f"--network={network}",
        f"--memory={WORKSPACE_MEMORY_LIMIT_MB}m",
        "--cpus=1.0",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        f"--pids-limit={WORKSPACE_PIDS_LIMIT}",
        "--tmpfs", "/tmp:size=100m",
        WORKSPACE_IMAGE,
        "sh", "-lc", "while true; do sleep 3600; done",
    ]
    create_code, create_stdout, create_stderr, create_timed_out = await _run_exec(
        *create_cmd, timeout_s=min(timeout_s, 30),
    )
    if create_timed_out or create_code != 0:
        stderr = create_stderr[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        return WorkspaceExecutionResult(
            stdout="",
            stderr=stderr or f"Failed to create workspace sandbox (exit {create_code})",
            exit_code=124 if create_timed_out else create_code,
            command=command,
            working_dir=str(work_path),
            timed_out=create_timed_out,
        )

    container_id = create_stdout.decode("utf-8", errors="replace").strip()
    if not container_id:
        return WorkspaceExecutionResult(
            stdout="",
            stderr="Failed to create workspace sandbox container",
            exit_code=1,
            command=command,
            working_dir=str(work_path),
        )

    try:
        start_code, _, start_stderr, start_timed_out = await _run_exec(
            "docker", "start", container_id, timeout_s=min(timeout_s, 30),
        )
        if start_timed_out or start_code != 0:
            stderr = start_stderr[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            return WorkspaceExecutionResult(
                stdout="",
                stderr=stderr or f"Failed to start workspace sandbox (exit {start_code})",
                exit_code=124 if start_timed_out else start_code,
                command=command,
                working_dir=str(work_path),
                timed_out=start_timed_out,
            )

        workspace_archive = _archive_workspace(work_path)
        copy_in_code, _, copy_in_stderr, copy_in_timed_out = await _run_exec(
            "docker", "exec", "-i", container_id,
            "sh", "-lc", "mkdir -p /workspace && tar -xf - -C /workspace",
            timeout_s=min(timeout_s, 30),
            input_bytes=workspace_archive,
        )
        if copy_in_timed_out or copy_in_code != 0:
            stderr = copy_in_stderr[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            return WorkspaceExecutionResult(
                stdout="",
                stderr=stderr or f"Failed to copy workspace into sandbox (exit {copy_in_code})",
                exit_code=124 if copy_in_timed_out else copy_in_code,
                command=command,
                working_dir=str(work_path),
                timed_out=copy_in_timed_out,
            )

        exit_code, stdout_bytes, stderr_bytes, timed_out = await _run_exec(
            "docker", "exec", container_id,
            "sh", "-lc", f"cd /workspace && {command}",
            timeout_s=timeout_s,
        )
        if timed_out:
            return WorkspaceExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout_s}s",
                exit_code=124,
                command=command,
                working_dir=str(work_path),
                timed_out=True,
            )

        copy_out_code, archive_bytes, copy_out_stderr, copy_out_timed_out = await _run_exec(
            "docker", "exec", container_id,
            "sh", "-lc", "cd /workspace && tar -cf - .",
            timeout_s=min(timeout_s, 30),
        )
        if copy_out_timed_out or copy_out_code != 0:
            stderr = copy_out_stderr[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
            return WorkspaceExecutionResult(
                stdout=stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
                stderr=stderr or f"Failed to copy workspace out of sandbox (exit {copy_out_code})",
                exit_code=124 if copy_out_timed_out else copy_out_code,
                command=command,
                working_dir=str(work_path),
                timed_out=copy_out_timed_out,
            )

        _restore_workspace_from_archive(archive_bytes, work_path)
        return _build_workspace_result(
            command=command,
            work_path=work_path,
            stdout=stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            stderr=stderr_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            exit_code=exit_code,
            before_snapshot=before_snapshot,
        )
    finally:
        await _run_exec("docker", "rm", "-f", container_id, timeout_s=15)


async def _execute_workspace_subprocess(
    command: str,
    work_path: Path,
    timeout_s: int,
    before_snapshot: tuple[set[str], dict[str, tuple[int, int]]],
) -> WorkspaceExecutionResult:
    """Legacy host-shell fallback with truthful workspace diff reporting."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(work_path),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_s,
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            return WorkspaceExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout_s}s",
                exit_code=124,
                command=command,
                working_dir=str(work_path),
                timed_out=True,
            )

        return _build_workspace_result(
            command=command,
            work_path=work_path,
            stdout=stdout_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            stderr=stderr_bytes[:WORKSPACE_MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
            before_snapshot=before_snapshot,
        )
    except OSError as exc:
        return WorkspaceExecutionResult(
            exit_code=1,
            stderr=f"Failed to execute command: {exc}",
            command=command,
            working_dir=str(work_path),
        )
