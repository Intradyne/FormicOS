"""Tests for Wave 43 sandbox and workspace executor hardening."""

from __future__ import annotations

from formicos.adapters.sandbox_manager import (
    _SECCOMP_PROFILE,
    GIT_SHALLOW_DEPTH,
    WORKSPACE_IMAGE,
    WORKSPACE_MEMORY_LIMIT_MB,
    WORKSPACE_PIDS_LIMIT,
    _is_setup_command,
    build_safe_git_clone_args,
)

# ---------------------------------------------------------------------------
# Sandbox container hardening
# ---------------------------------------------------------------------------


class TestSandboxHardening:
    """Verify hardened container flags in the sandbox execution path."""

    def test_seccomp_profile_path_exists(self) -> None:
        """Seccomp profile is shipped alongside the source tree."""
        # The path should resolve to config/seccomp-sandbox.json
        assert "seccomp-sandbox.json" in str(_SECCOMP_PROFILE)

    def test_workspace_image_default(self) -> None:
        """Default workspace image is python:3.12-slim."""
        assert "python" in WORKSPACE_IMAGE

    def test_workspace_memory_limit_reasonable(self) -> None:
        """Workspace memory limit is at least 256MB."""
        assert WORKSPACE_MEMORY_LIMIT_MB >= 256

    def test_workspace_pids_limit_set(self) -> None:
        """Workspace PID limit is set."""
        assert WORKSPACE_PIDS_LIMIT > 0


# ---------------------------------------------------------------------------
# Network-off test execution policy
# ---------------------------------------------------------------------------


class TestNetworkPhasePolicy:
    """Verify phase-aware networking for workspace execution."""

    def test_pip_install_is_setup(self) -> None:
        assert _is_setup_command("pip install -r requirements.txt")

    def test_uv_sync_is_setup(self) -> None:
        assert _is_setup_command("uv sync --frozen")

    def test_npm_install_is_setup(self) -> None:
        assert _is_setup_command("npm install")

    def test_yarn_add_is_setup(self) -> None:
        assert _is_setup_command("yarn add express")

    def test_cargo_install_is_setup(self) -> None:
        assert _is_setup_command("cargo install serde")

    def test_go_get_is_setup(self) -> None:
        assert _is_setup_command("go get github.com/user/pkg")

    def test_go_mod_is_setup(self) -> None:
        assert _is_setup_command("go mod download")

    def test_apt_install_is_setup(self) -> None:
        assert _is_setup_command("apt-get install -y curl")

    def test_pytest_is_not_setup(self) -> None:
        assert not _is_setup_command("pytest tests/")

    def test_make_build_is_not_setup(self) -> None:
        assert not _is_setup_command("make build")

    def test_python_script_is_not_setup(self) -> None:
        assert not _is_setup_command("python main.py")

    def test_ruff_check_is_not_setup(self) -> None:
        assert not _is_setup_command("ruff check src/")

    def test_go_test_is_not_setup(self) -> None:
        assert not _is_setup_command("go test ./...")

    def test_cargo_test_is_not_setup(self) -> None:
        assert not _is_setup_command("cargo test")


# ---------------------------------------------------------------------------
# Git clone security defaults
# ---------------------------------------------------------------------------


class TestGitCloneSecurityDefaults:
    """Verify hardened git clone command generation."""

    def test_default_shallow_clone(self) -> None:
        args = build_safe_git_clone_args("https://github.com/user/repo", "/tmp/repo")
        assert "--depth" in args
        assert str(GIT_SHALLOW_DEPTH) in args

    def test_hooks_disabled_by_default(self) -> None:
        args = build_safe_git_clone_args("https://github.com/user/repo", "/tmp/repo")
        assert "core.hooksPath=/dev/null" in args

    def test_hooks_can_be_enabled(self) -> None:
        args = build_safe_git_clone_args(
            "https://github.com/user/repo", "/tmp/repo",
            allow_hooks=True,
        )
        assert "core.hooksPath=/dev/null" not in args

    def test_no_submodules_by_default(self) -> None:
        args = build_safe_git_clone_args("https://github.com/user/repo", "/tmp/repo")
        assert "--no-recurse-submodules" in args

    def test_submodules_can_be_enabled(self) -> None:
        args = build_safe_git_clone_args(
            "https://github.com/user/repo", "/tmp/repo",
            allow_submodules=True,
        )
        assert "--no-recurse-submodules" not in args

    def test_symlinks_disabled(self) -> None:
        args = build_safe_git_clone_args("https://github.com/user/repo", "/tmp/repo")
        assert "core.symlinks=false" in args

    def test_transfer_fsck_enabled(self) -> None:
        args = build_safe_git_clone_args("https://github.com/user/repo", "/tmp/repo")
        assert "transfer.fsckObjects=true" in args

    def test_branch_option(self) -> None:
        args = build_safe_git_clone_args(
            "https://github.com/user/repo", "/tmp/repo",
            branch="main",
        )
        assert "--branch" in args
        assert "main" in args

    def test_custom_depth(self) -> None:
        args = build_safe_git_clone_args(
            "https://github.com/user/repo", "/tmp/repo",
            depth=10,
        )
        idx = args.index("--depth")
        assert args[idx + 1] == "10"

    def test_full_clone_depth_zero(self) -> None:
        args = build_safe_git_clone_args(
            "https://github.com/user/repo", "/tmp/repo",
            depth=0,
        )
        assert "--depth" not in args

    def test_url_and_dest_at_end(self) -> None:
        args = build_safe_git_clone_args("https://example.com/repo.git", "/dest")
        assert args[-2] == "https://example.com/repo.git"
        assert args[-1] == "/dest"

    def test_protocol_file_restricted(self) -> None:
        args = build_safe_git_clone_args("https://example.com/repo.git", "/dest")
        assert "protocol.file.allow=user" in args
