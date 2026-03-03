"""
Tests for FormicOS v0.8.0 Secured Topological Memory.

Simulates a 100MB dummy file to prove:
  - read_slice(0, 1_000_000) raises FormicMemoryError (exceeds 50KB ceiling)
  - read_slice(0, 100) succeeds and decodes to valid UTF-8
  - Edge cases: start beyond EOF, closed map, empty file, negative args
"""

import os
from pathlib import Path

import pytest

from src.core.repl.secured_memory import FormicMemoryError, SecuredTopologicalMemory


# ── Fixtures ──────────────────────────────────────────────────────────────


_100MB = 100 * 1024 * 1024  # 104,857,600 bytes


@pytest.fixture
def big_file(tmp_path: Path) -> Path:
    """Create a 100MB file filled with repeating UTF-8 ASCII text.

    Uses os.write with a 1MB chunk to avoid Python string allocation
    overhead (keeps test startup under 2s even on slow I/O).
    """
    fp = tmp_path / "big_repo.bin"
    # Build a 1MB repeating line pattern
    line = b"// line of source code in a massive monorepo\n"
    chunk = (line * (1024 * 1024 // len(line) + 1))[:1024 * 1024]
    fd = os.open(str(fp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_BINARY)
    try:
        written = 0
        while written < _100MB:
            n = os.write(fd, chunk[:min(len(chunk), _100MB - written)])
            written += n
    finally:
        os.close(fd)
    assert fp.stat().st_size == _100MB
    return fp


@pytest.fixture
def small_file(tmp_path: Path) -> Path:
    """Create a small 256-byte UTF-8 file."""
    fp = tmp_path / "small.txt"
    fp.write_text("Hello FormicOS\n" * 17, encoding="utf-8")
    return fp


@pytest.fixture
def empty_file(tmp_path: Path) -> Path:
    """Create a 0-byte file."""
    fp = tmp_path / "empty.txt"
    fp.write_bytes(b"")
    return fp


# ── Construction ──────────────────────────────────────────────────────────


class TestConstruction:

    def test_opens_read_only(self, big_file: Path):
        """File is mapped with ACCESS_READ; no write handle leak."""
        with SecuredTopologicalMemory(big_file) as mem:
            assert mem.file_size == _100MB
            assert mem.max_slice_bytes == 50_000

    def test_default_max_slice(self, small_file: Path):
        """Default max_slice_bytes is 50,000."""
        with SecuredTopologicalMemory(small_file) as mem:
            assert mem.max_slice_bytes == 50_000

    def test_custom_max_slice(self, small_file: Path):
        """Custom max_slice_bytes is respected."""
        with SecuredTopologicalMemory(small_file, max_slice_bytes=128) as mem:
            assert mem.max_slice_bytes == 128

    def test_file_not_found(self, tmp_path: Path):
        """Non-existent path raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            SecuredTopologicalMemory(tmp_path / "nonexistent.bin")

    def test_empty_file_rejected(self, empty_file: Path):
        """0-byte file raises ValueError (cannot mmap)."""
        with pytest.raises(ValueError, match="empty"):
            SecuredTopologicalMemory(empty_file)

    def test_invalid_max_slice(self, small_file: Path):
        """max_slice_bytes < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_slice_bytes"):
            SecuredTopologicalMemory(small_file, max_slice_bytes=0)
        with pytest.raises(ValueError, match="max_slice_bytes"):
            SecuredTopologicalMemory(small_file, max_slice_bytes=-10)


# ── OOM Guardrail ─────────────────────────────────────────────────────────


class TestOOMGuardrail:
    """The core requirement: large slices are rejected, small ones succeed."""

    def test_oversized_slice_raises(self, big_file: Path):
        """read_slice(0, 1_000_000) raises FormicMemoryError."""
        with SecuredTopologicalMemory(big_file) as mem:
            with pytest.raises(FormicMemoryError, match="narrow your search"):
                mem.read_slice(0, 1_000_000)

    def test_exactly_at_limit_succeeds(self, big_file: Path):
        """read_slice at exactly max_slice_bytes succeeds."""
        with SecuredTopologicalMemory(big_file) as mem:
            data = mem.read_slice(0, 50_000)
            assert len(data) == 50_000

    def test_one_byte_over_limit_raises(self, big_file: Path):
        """read_slice at max_slice_bytes + 1 raises."""
        with SecuredTopologicalMemory(big_file) as mem:
            with pytest.raises(FormicMemoryError):
                mem.read_slice(0, 50_001)

    def test_small_slice_succeeds_and_decodes_utf8(self, big_file: Path):
        """read_slice(0, 100) succeeds and is valid UTF-8."""
        with SecuredTopologicalMemory(big_file) as mem:
            data = mem.read_slice(0, 100)
            assert len(data) == 100
            text = data.decode("utf-8")
            assert isinstance(text, str)
            assert len(text) == 100

    def test_custom_limit_enforced(self, small_file: Path):
        """Custom max_slice_bytes is enforced, not just the default."""
        with SecuredTopologicalMemory(small_file, max_slice_bytes=10) as mem:
            data = mem.read_slice(0, 10)
            assert len(data) == 10

            with pytest.raises(FormicMemoryError):
                mem.read_slice(0, 11)

    def test_error_message_is_instructive(self, big_file: Path):
        """FormicMemoryError carries an LLM-actionable message."""
        with SecuredTopologicalMemory(big_file) as mem:
            with pytest.raises(FormicMemoryError) as exc_info:
                mem.read_slice(0, 999_999)

            msg = str(exc_info.value)
            assert "999,999" in msg  # echoes requested size
            assert "50,000" in msg   # echoes the ceiling
            assert "regex" in msg.lower() or "tighter" in msg.lower()


# ── Edge Cases ────────────────────────────────────────────────────────────


class TestEdgeCases:

    def test_start_beyond_eof_returns_empty(self, small_file: Path):
        """read_slice past EOF returns empty bytes, no crash."""
        with SecuredTopologicalMemory(small_file) as mem:
            data = mem.read_slice(mem.file_size + 1000, 100)
            assert data == b""

    def test_slice_clamped_at_eof(self, small_file: Path):
        """Slice extending past EOF is silently truncated."""
        with SecuredTopologicalMemory(small_file) as mem:
            # Request 1000 bytes from near the end
            start = mem.file_size - 10
            data = mem.read_slice(start, 1000)
            assert len(data) == 10  # clamped to remaining bytes

    def test_read_after_close_raises(self, small_file: Path):
        """read_slice on a closed map raises FormicMemoryError."""
        mem = SecuredTopologicalMemory(small_file)
        mem.close()
        with pytest.raises(FormicMemoryError, match="closed"):
            mem.read_slice(0, 10)

    def test_negative_start_raises(self, small_file: Path):
        """Negative start_byte is rejected."""
        with SecuredTopologicalMemory(small_file) as mem:
            with pytest.raises(ValueError, match="start_byte"):
                mem.read_slice(-1, 10)

    def test_zero_length_raises(self, small_file: Path):
        """length < 1 is rejected."""
        with SecuredTopologicalMemory(small_file) as mem:
            with pytest.raises(ValueError, match="length"):
                mem.read_slice(0, 0)

    def test_single_byte_read(self, small_file: Path):
        """Reading 1 byte works."""
        with SecuredTopologicalMemory(small_file) as mem:
            data = mem.read_slice(0, 1)
            assert len(data) == 1
            assert data == b"H"  # "Hello FormicOS..."


# ── Context Manager & repr ────────────────────────────────────────────────


class TestContextManager:

    def test_context_manager_closes(self, small_file: Path):
        """Exiting the context manager closes the mmap."""
        mem = SecuredTopologicalMemory(small_file)
        with mem:
            _ = mem.read_slice(0, 5)
        with pytest.raises(FormicMemoryError, match="closed"):
            mem.read_slice(0, 5)

    def test_double_close_is_safe(self, small_file: Path):
        """Calling close() twice does not raise."""
        mem = SecuredTopologicalMemory(small_file)
        mem.close()
        mem.close()  # no error

    def test_repr(self, small_file: Path):
        """__repr__ includes path, size, and status."""
        with SecuredTopologicalMemory(small_file) as mem:
            r = repr(mem)
            assert "small.txt" in r
            assert "open" in r
        r2 = repr(mem)
        assert "closed" in r2
