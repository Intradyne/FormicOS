"""JSONL debug sink for the telemetry bus (Wave 17, Track A).

Appends each telemetry event as a single JSON line to a file.
Best-effort: write failures are logged and swallowed.

Note: This adapter uses duck-typing for the event (``model_dump_json()``)
to avoid importing from ``engine/`` (layer boundary: adapters → core only).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


class JSONLSink:
    """Append-only JSONL file sink for telemetry events."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    async def __call__(self, event: Any) -> None:  # noqa: ANN401
        """Write a single event as a JSON line."""
        try:
            line: str = event.model_dump_json() + "\n"
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line)
        except Exception:  # noqa: BLE001
            log.debug("jsonl_sink.write_error", path=str(self._path))


__all__ = ["JSONLSink"]
