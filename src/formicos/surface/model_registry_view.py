"""Model registry display helpers (Wave 5).

Derives model status views from SystemSettings registry entries and
environment state. Mirrors types.ts CloudEndpoint and LocalModel shapes.
"""

from __future__ import annotations

import os
from typing import Any

from formicos.core.settings import SystemSettings


def model_registry_view(settings: SystemSettings) -> list[dict[str, Any]]:
    """Build the full model registry view for the operator UI."""
    return [
        {
            "address": m.address,
            "provider": m.provider,
            "contextWindow": m.context_window,
            "supportsTools": m.supports_tools,
            "supportsVision": m.supports_vision or False,
            "status": _derive_status(m.api_key_env, m.status),
            "costPerInputToken": m.cost_per_input_token,
            "costPerOutputToken": m.cost_per_output_token,
        }
        for m in settings.models.registry
    ]


def cloud_endpoints_view(settings: SystemSettings) -> list[dict[str, Any]]:
    """Build cloud endpoint summary grouped by provider."""
    providers_seen: set[str] = set()
    endpoints: list[dict[str, Any]] = []
    for model in settings.models.registry:
        provider = model.provider
        if provider in providers_seen:
            continue
        providers_seen.add(provider)
        api_key_set = bool(os.environ.get(model.api_key_env or ""))
        status = "connected" if api_key_set else "no_key"
        endpoints.append({
            "id": provider,
            "provider": provider,
            "models": [
                m.address for m in settings.models.registry if m.provider == provider
            ],
            "status": status,
        })
    return endpoints


def model_defaults_view(settings: SystemSettings) -> dict[str, str]:
    """Return the current default model assignments per caste."""
    return settings.models.defaults.model_dump()


def _derive_status(api_key_env: str | None, configured_status: str) -> str:
    """Derive effective model status from env and configured status."""
    if configured_status in ("error", "unavailable"):
        return configured_status
    if api_key_env and not os.environ.get(api_key_env):
        return "no_key"
    return configured_status


__all__ = ["cloud_endpoints_view", "model_defaults_view", "model_registry_view"]
