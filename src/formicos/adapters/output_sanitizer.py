"""Output sanitization for sandboxed code execution (Wave 14).

Strips ANSI escapes and truncates output to safe limits.
"""

from __future__ import annotations

import re

# Max output size in characters (10KB — spec says 50KB raw truncated to 10KB)
MAX_OUTPUT_CHARS = 10_000

# ANSI escape sequence pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def sanitize_output(text: str) -> str:
    """Strip ANSI escapes and truncate to safe limit."""
    # Strip ANSI escape sequences
    clean = _ANSI_RE.sub("", text)

    # Truncate to limit
    if len(clean) > MAX_OUTPUT_CHARS:
        clean = clean[:MAX_OUTPUT_CHARS] + "\n[... output truncated]"

    return clean
