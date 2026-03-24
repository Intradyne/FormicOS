"""Capability registry — single source of system truth (ADR-036).

Built once during app assembly from explicit manifests. Frozen after
construction. All consumer surfaces read from this registry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolEntry:
    name: str
    description: str


@dataclass(frozen=True)
class ProtocolEntry:
    name: str
    status: str
    endpoint: str | None = None
    transport: str | None = None
    semantics: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class CapabilityRegistry:
    event_names: tuple[str, ...]
    mcp_tools: tuple[ToolEntry, ...]
    queen_tools: tuple[ToolEntry, ...]
    agui_events: tuple[str, ...]
    protocols: tuple[ProtocolEntry, ...]
    castes: tuple[str, ...]
    version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "events": {
                "count": len(self.event_names),
                "names": list(self.event_names),
            },
            "mcp": {
                "tools": len(self.mcp_tools),
                "entries": [
                    {"name": t.name, "description": t.description}
                    for t in self.mcp_tools
                ],
            },
            "queen": {
                "tools": len(self.queen_tools),
                "entries": [
                    {"name": t.name, "description": t.description}
                    for t in self.queen_tools
                ],
            },
            "agui": {
                "events": len(self.agui_events),
                "names": list(self.agui_events),
            },
            "protocols": [
                {
                    key: value
                    for key, value in {
                        "name": p.name,
                        "status": p.status,
                        "endpoint": p.endpoint,
                        "transport": p.transport,
                        "semantics": p.semantics,
                        "note": p.note,
                    }.items()
                    if value is not None
                }
                for p in self.protocols
            ],
            "castes": list(self.castes),
        }


__all__ = ["CapabilityRegistry", "ProtocolEntry", "ToolEntry"]
