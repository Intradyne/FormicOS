"""
FormicOS v0.8.0 -- Secured Topological Memory

Read-only ``mmap`` wrapper that prevents LLM-driven REPL sessions from
pulling an entire mapped file into active RAM.  Designed for Root_Architect
agents that need to analyze 10M+ token repositories by reading precise
byte-ranges rather than loading whole files into the context window.

OOM Guard
---------
Every ``read_slice()`` call is capped by ``max_slice_bytes``.  If the LLM
requests a larger window the call raises ``FormicMemoryError`` with an
instructive message telling it to narrow its search with tighter regex or
AST traversal loops.  This prevents a single careless slice from crashing
the Docker container.

Usage
-----
>>> mem = SecuredTopologicalMemory("big_repo.bin", max_slice_bytes=50_000)
>>> chunk = mem.read_slice(0, 4096)
>>> mem.close()
"""

from __future__ import annotations

import mmap
import os
from pathlib import Path


class FormicMemoryError(Exception):
    """Raised when an LLM-driven memory access violates the slice budget.

    The error message is written in second-person so the LLM receives
    actionable feedback it can use to self-correct its next tool call.
    """


_DEFAULT_MAX_SLICE = 50_000  # bytes


class SecuredTopologicalMemory:
    """Read-only mmap wrapper with a hard per-read byte ceiling.

    Parameters
    ----------
    filepath : str | Path
        File to memory-map.  Must exist and be non-empty.
    max_slice_bytes : int
        Upper bound on any single ``read_slice()`` call.  Defaults to 50 000.

    Raises
    ------
    FileNotFoundError
        If *filepath* does not exist.
    ValueError
        If *filepath* is empty (0 bytes) or *max_slice_bytes* < 1.
    """

    def __init__(
        self,
        filepath: str | Path,
        max_slice_bytes: int = _DEFAULT_MAX_SLICE,
    ) -> None:
        filepath = Path(filepath)

        if not filepath.exists():
            raise FileNotFoundError(f"Cannot map file: {filepath}")

        file_size = filepath.stat().st_size
        if file_size == 0:
            raise ValueError(f"Cannot mmap an empty file: {filepath}")

        if max_slice_bytes < 1:
            raise ValueError(
                f"max_slice_bytes must be >= 1, got {max_slice_bytes}"
            )

        self._max_slice: int = max_slice_bytes
        self._file_size: int = file_size
        self._path: Path = filepath

        # Open in read-only mode; fd is kept alive for the mmap lifetime.
        self._fd: int = os.open(str(filepath), os.O_RDONLY)
        try:
            self._mm: mmap.mmap = mmap.mmap(
                self._fd, 0, access=mmap.ACCESS_READ,
            )
        except Exception:
            os.close(self._fd)
            raise

    # -- public API --------------------------------------------------------

    @property
    def file_size(self) -> int:
        """Total size of the mapped file in bytes."""
        return self._file_size

    @property
    def max_slice_bytes(self) -> int:
        """Maximum bytes allowed per ``read_slice()`` call."""
        return self._max_slice

    def read_slice(self, start_byte: int, length: int) -> bytes:
        """Return up to *length* bytes starting at *start_byte*.

        Parameters
        ----------
        start_byte : int
            Offset from the beginning of the file.  Clamped to [0, file_size).
        length : int
            Number of bytes to read.  Must be >= 1.

        Returns
        -------
        bytes
            The raw slice.  Decode with ``.decode("utf-8", errors="replace")``
            when feeding into the LLM context.

        Raises
        ------
        FormicMemoryError
            If *length* exceeds ``max_slice_bytes``.
        ValueError
            If *length* < 1 or *start_byte* < 0.
        """
        if self._mm.closed:
            raise FormicMemoryError("Memory map is closed.")

        if length < 1:
            raise ValueError(f"length must be >= 1, got {length}")
        if start_byte < 0:
            raise ValueError(f"start_byte must be >= 0, got {start_byte}")

        if length > self._max_slice:
            raise FormicMemoryError(
                f"Requested {length:,} bytes but the per-read ceiling is "
                f"{self._max_slice:,} bytes.  You MUST narrow your search: "
                f"use tighter regex patterns, AST node visitors, or binary "
                f"search on byte offsets to locate the exact region you need, "
                f"then request a slice of <= {self._max_slice:,} bytes."
            )

        # Clamp start to file bounds
        if start_byte >= self._file_size:
            return b""

        # Clamp end to file bounds (never read past EOF)
        end = min(start_byte + length, self._file_size)
        return self._mm[start_byte:end]

    def close(self) -> None:
        """Release the mmap and the underlying file descriptor."""
        if not self._mm.closed:
            self._mm.close()
        try:
            os.close(self._fd)
        except OSError:
            pass  # already closed

    # -- context manager ---------------------------------------------------

    def __enter__(self) -> SecuredTopologicalMemory:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- repr --------------------------------------------------------------

    def __repr__(self) -> str:
        status = "closed" if self._mm.closed else "open"
        return (
            f"<SecuredTopologicalMemory path={self._path.name!r} "
            f"size={self._file_size:,} max_slice={self._max_slice:,} "
            f"status={status}>"
        )
