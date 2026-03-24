"""Heuristic artifact extraction from agent output text.

Deterministic, not LLM-based. Called after each round on full agent outputs.
Extracted artifacts accumulate on the colony projection during live execution
and are persisted on ColonyCompleted for replay safety.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from formicos.core.types import Artifact, ArtifactType

# Regex for fenced code blocks: ```lang\n...\n```
_FENCED_RE = re.compile(
    r"```(\w*)\s*\n(.*?)```",
    re.DOTALL,
)

# Language hint -> artifact type
_LANG_TYPE: dict[str, ArtifactType] = {
    "python": ArtifactType.code,
    "py": ArtifactType.code,
    "javascript": ArtifactType.code,
    "js": ArtifactType.code,
    "typescript": ArtifactType.code,
    "ts": ArtifactType.code,
    "rust": ArtifactType.code,
    "go": ArtifactType.code,
    "java": ArtifactType.code,
    "json": ArtifactType.data,
    "yaml": ArtifactType.config,
    "yml": ArtifactType.config,
    "sql": ArtifactType.code,
    "html": ArtifactType.code,
    "css": ArtifactType.code,
    "sh": ArtifactType.code,
    "bash": ArtifactType.code,
}

_LANG_MIME: dict[str, str] = {
    "python": "text/x-python",
    "py": "text/x-python",
    "javascript": "text/javascript",
    "js": "text/javascript",
    "typescript": "text/typescript",
    "ts": "text/typescript",
    "json": "application/json",
    "yaml": "text/yaml",
    "yml": "text/yaml",
    "html": "text/html",
    "css": "text/css",
    "sql": "text/x-sql",
}

_SCHEMA_HINTS = {"$schema", '"type"', '"properties"', "'type'", "'properties'"}


def extract_artifacts(
    output: str,
    colony_id: str,
    agent_id: str,
    round_number: int,
) -> list[dict[str, Any]]:
    """Extract typed artifacts from agent output text.

    Returns a list of artifact dicts (serialized Artifact shape).
    Deterministic: fenced blocks become typed artifacts, remaining prose
    becomes a document artifact if substantial.
    """
    artifacts: list[dict[str, Any]] = []
    now = datetime.now(UTC).isoformat()

    # Extract fenced code blocks
    for match in _FENCED_RE.finditer(output):
        lang = match.group(1).lower().strip()
        content = match.group(2).strip()

        if not content:
            continue

        # Determine type
        art_type = _LANG_TYPE.get(lang, ArtifactType.code if lang else ArtifactType.generic)

        # Check if JSON content looks like a schema
        if art_type == ArtifactType.data and any(hint in content[:500] for hint in _SCHEMA_HINTS):
            art_type = ArtifactType.schema

        mime = _LANG_MIME.get(lang, "text/plain")
        art_id = f"art-{colony_id}-{agent_id}-r{round_number}-{len(artifacts)}"

        artifacts.append(Artifact(
            id=art_id,
            name=f"output-{len(artifacts)}",
            artifact_type=art_type,
            mime_type=mime,
            content=content,
            source_colony_id=colony_id,
            source_agent_id=agent_id,
            source_round=round_number,
            created_at=now,
            metadata={"language": lang} if lang else {},
        ).model_dump())

    # If no fenced blocks, check if output is a substantial document
    if not artifacts:
        header_count = len(re.findall(r"^#{1,3}\s+", output, re.MULTILINE))
        if len(output) > 500 and header_count >= 2:
            art_type = ArtifactType.document
        else:
            art_type = ArtifactType.generic

        art_id = f"art-{colony_id}-{agent_id}-r{round_number}-0"
        artifacts.append(Artifact(
            id=art_id,
            name="output-0",
            artifact_type=art_type,
            mime_type="text/plain",
            content=output,
            source_colony_id=colony_id,
            source_agent_id=agent_id,
            source_round=round_number,
            created_at=now,
        ).model_dump())

    return artifacts


__all__ = ["extract_artifacts"]
