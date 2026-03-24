"""Route modules for the FormicOS surface layer.

Each module exports a ``routes(**deps) -> list[Route | Mount]`` factory
that receives dependencies explicitly — no global state.
"""

from __future__ import annotations

from formicos.surface.routes.a2a import routes as a2a_routes
from formicos.surface.routes.api import routes as api_routes
from formicos.surface.routes.colony_io import routes as colony_io_routes
from formicos.surface.routes.health import routes as health_routes
from formicos.surface.routes.knowledge_api import routes as knowledge_routes
from formicos.surface.routes.memory_api import routes as memory_routes
from formicos.surface.routes.protocols import routes as protocol_routes

__all__ = [
    "a2a_routes",
    "api_routes",
    "colony_io_routes",
    "health_routes",
    "knowledge_routes",
    "memory_routes",
    "protocol_routes",
]
