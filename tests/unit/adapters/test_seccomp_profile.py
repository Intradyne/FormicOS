"""Tests for Wave 43 seccomp profile validity."""

from __future__ import annotations

import json
from pathlib import Path

SECCOMP_PATH = Path(__file__).parent.parent.parent.parent / "config" / "seccomp-sandbox.json"


class TestSeccompProfile:
    """Validate the seccomp profile structure and content."""

    def test_profile_exists(self) -> None:
        assert SECCOMP_PATH.is_file(), f"Seccomp profile not found at {SECCOMP_PATH}"

    def test_valid_json(self) -> None:
        profile = json.loads(SECCOMP_PATH.read_text())
        assert isinstance(profile, dict)

    def test_default_action_deny(self) -> None:
        profile = json.loads(SECCOMP_PATH.read_text())
        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"

    def test_has_architectures(self) -> None:
        profile = json.loads(SECCOMP_PATH.read_text())
        archs = profile["architectures"]
        assert "SCMP_ARCH_X86_64" in archs
        assert "SCMP_ARCH_AARCH64" in archs

    def test_has_allowed_syscalls(self) -> None:
        profile = json.loads(SECCOMP_PATH.read_text())
        syscalls = profile["syscalls"]
        assert len(syscalls) >= 1
        allowed = syscalls[0]
        assert allowed["action"] == "SCMP_ACT_ALLOW"
        names = allowed["names"]
        assert len(names) > 50  # Should have many allowed syscalls

    def test_essential_syscalls_allowed(self) -> None:
        """Verify essential syscalls for Python/Node/Go runtimes are allowed."""
        profile = json.loads(SECCOMP_PATH.read_text())
        names = profile["syscalls"][0]["names"]
        essentials = [
            "read", "write", "open", "openat", "close",
            "mmap", "mprotect", "munmap",
            "execve", "clone", "fork",
            "socket", "connect", "bind",
            "futex", "brk",
        ]
        for syscall in essentials:
            assert syscall in names, f"Essential syscall '{syscall}' not in allowed list"

    def test_dangerous_syscalls_blocked(self) -> None:
        """Verify dangerous syscalls are NOT in the allow list."""
        profile = json.loads(SECCOMP_PATH.read_text())
        names = set(profile["syscalls"][0]["names"])
        dangerous = [
            "mount", "umount2",
            "pivot_root", "chroot",
            "reboot",
            "kexec_load",
            "init_module", "finit_module", "delete_module",
            "ptrace",
            "keyctl",
            "bpf",
        ]
        for syscall in dangerous:
            assert syscall not in names, f"Dangerous syscall '{syscall}' should be blocked"
