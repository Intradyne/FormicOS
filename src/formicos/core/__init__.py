"""Core layer — types, events, ports, state. Imports NOTHING outside this package."""

from formicos.core.events import (
    CoordinationStrategyName,
    FormicOSEvent,
    PhaseName,
    deserialize,
    serialize,
)
from formicos.core.types import (
    AgentConfig,
    CasteRecipe,
    ColonyConfig,
    ColonyContext,
    ModelRecord,
    NodeAddress,
    NodeType,
)

__all__ = [
    "AgentConfig",
    "CasteRecipe",
    "ColonyConfig",
    "ColonyContext",
    "CoordinationStrategyName",
    "deserialize",
    "FormicOSEvent",
    "ModelRecord",
    "NodeAddress",
    "NodeType",
    "PhaseName",
    "serialize",
]
